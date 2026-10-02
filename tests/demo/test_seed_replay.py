"""Replay safety with an in-memory cursor double; not PostgreSQL acceptance."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import re
import subprocess
import sys

import pytest
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import demo_seed  # noqa: E402
import seed_demo_data  # noqa: E402


class MemoryConnection:
    """Models transactional data changes only, without emulating DB constraints."""

    def __init__(self):
        self.rows = {table: {} for table in demo_seed.ROWS}
        self.statements = []
        self.result = []
        self.missing_column = None
        self.fail_insert_table = None

    @contextmanager
    def transaction(self):
        original = deepcopy(self.rows)
        try:
            yield
        except Exception:
            self.rows = original
            raise

    @contextmanager
    def cursor(self):
        yield self

    def execute(self, statement, parameters=()):
        query = statement if isinstance(statement, str) else statement.as_string()
        self.statements.append(query)
        if "information_schema.columns" in query:
            self.result = [(table, column) for table, rows in demo_seed.ROWS.items()
                           for column in set().union(*(row.keys() for row in rows))
                           if (table, column) != self.missing_column]
            return
        table = re.search(r'(?:FROM|INTO) "([a-z_]+)"', query)[1]
        if query.startswith("SELECT"):
            identifiers = parameters[0] if "ANY(" in query else [parameters[0]]
            selection = query.split(" FROM ")[0].removeprefix("SELECT ")
            columns = [column.strip().strip('"') for column in selection.split(",")]
            self.result = [tuple(self.rows[table][identifier].get(column) for column in columns)
                           for identifier in identifiers if identifier in self.rows[table]]
        elif query.startswith("DELETE"):
            assert "WHERE id = ANY(%s::uuid[])" in query
            for identifier in parameters[0]:
                self.rows[table].pop(identifier, None)
        elif query.startswith("INSERT"):
            if table == self.fail_insert_table:
                raise RuntimeError("injected write failure")
            columns = re.search(r'\((.*?)\) VALUES', query)[1]
            values = [value.obj if isinstance(value, Jsonb) else value for value in parameters]
            row = dict(zip((column.strip().strip('"') for column in columns.split(",")), values))
            self.rows[table][row["id"]] = row
        else:
            raise AssertionError("unexpected SQL operation")

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result


def test_repeated_replay_preserves_outside_rows_and_stable_fixture_content() -> None:
    connection = MemoryConnection()
    sentinel = demo_seed.uid(999)
    for table in connection.rows:
        connection.rows[table][sentinel] = {"id": sentinel, "label": "unrelated fictional row"}
    seed_demo_data.replay(connection)
    first = deepcopy(connection.rows)
    seed_demo_data.replay(connection)
    assert connection.rows == first
    for table, rows in demo_seed.ROWS.items():
        assert len(connection.rows[table]) == len(rows) + 1
        assert connection.rows[table][sentinel]["label"] == "unrelated fictional row"
        assert all(connection.rows[table][row["id"]] == row for row in rows)
    deletes = [query for query in connection.statements if query.startswith("DELETE")]
    assert all("WHERE id = ANY(%s::uuid[])" in query for query in deletes)


@pytest.mark.parametrize("table,key", [
    ("family", "name"), ("user", "display_name"), ("family_member", "user_id"),
    ("consent", "grantee_user_id"), ("memory", "family_id"), ("memory", "subject_user_id"),
    ("device_binding", "owner_user_id"), ("file_asset", "memory_id"),
    ("reminder_execution", "reminder_id"), ("signal_event", "family_id"),
    ("notification", "recipient_user_id"), ("notification_attempt", "notification_id"),
    ("weekly_report", "family_id"),
])
def test_namespace_collision_is_rejected_before_delete(table, key) -> None:
    connection = MemoryConnection()
    seed_demo_data.replay(connection)
    row = next(iter(connection.rows[table].values()))
    row[key] = "another fictional namespace" if key in ("name", "display_name") else demo_seed.uid(999)
    before = deepcopy(connection.rows)
    connection.statements.clear()
    with pytest.raises(RuntimeError, match="belongs to another namespace"):
        seed_demo_data.replay(connection)
    assert connection.rows == before
    assert not any(query.startswith(("DELETE", "INSERT")) for query in connection.statements)


def test_missing_schema_is_rejected_before_namespace_or_writes() -> None:
    connection = MemoryConnection()
    connection.missing_column = ("memory", "deleted_at")
    with pytest.raises(RuntimeError, match="business schema unavailable or incomplete"):
        seed_demo_data.replay(connection)
    assert len(connection.statements) == 1
    assert not any(connection.rows.values())


def test_mid_replay_failure_rolls_back_existing_fixture() -> None:
    connection = MemoryConnection()
    seed_demo_data.replay(connection)
    connection.rows["memory"][demo_seed.MEMORY_OK]["title"] = "previous fictional fixture"
    before = deepcopy(connection.rows)
    connection.fail_insert_table = "notification"
    with pytest.raises(RuntimeError, match="injected write failure"):
        seed_demo_data.replay(connection)
    assert connection.rows == before


def test_driver_error_cli_exits_without_sensitive_exception_details() -> None:
    code = """
import os, runpy, sys, psycopg
sys.path.insert(0, 'scripts')
os.environ.update(APP_ENV='demo', DEMO_DATA='true', PROVIDER_MODE='mock', DATABASE_URL='postgresql://unused')
def fail(*args, **kwargs):
    raise psycopg.OperationalError('fictional-private-marker: synthetic connection and failed row details')
psycopg.connect = fail
sys.argv = ['scripts/seed_demo_data.py', '--apply']
runpy.run_path(sys.argv[0], run_name='__main__')
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "Seed failed: OperationalError; details redacted"
    assert "fictional-private-marker" not in result.stderr
    assert "Traceback" not in result.stderr
