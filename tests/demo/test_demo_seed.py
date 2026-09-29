"""E0-T08 fictional seed smoke and namespace safety checks."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import demo_seed  # noqa: E402


def test_fixture_is_deterministic_and_covers_demo_states() -> None:
    demo_seed.validate_fixture()
    assert all(UUID(row["id"]).version == 7 for rows in demo_seed.ROWS.values() for row in rows)
    assert {row["status"] for row in demo_seed.ROWS["signal_event"]} == {
        "NOTIFIED", "WITHHELD", "NOTIFICATION_FAILED"
    }
    assert {row["status"] for row in demo_seed.ROWS["consent"]} == {"GRANTED", "REVOKED"}
    assert sum(row.get("reminder_done_count", 0) for row in demo_seed.ROWS["interaction_metric"]) == 1
    assert sum(row.get("reminder_no_response_count", 0) for row in demo_seed.ROWS["interaction_metric"]) == 1
    ready = next(row for row in demo_seed.ROWS["weekly_report"] if row["status"] == "READY")
    assert ready["metrics_snapshot"]["reminder_done_count"] == 1
    assert ready["metrics_snapshot"]["reminder_no_response_count"] == 1
    assert ready["missing_data"]


def test_all_entity_references_stay_in_demo_namespace() -> None:
    users = {row["id"] for row in demo_seed.ROWS["user"]}
    families = {row["id"] for row in demo_seed.ROWS["family"]}
    signals = {row["id"] for row in demo_seed.ROWS["signal_event"]}
    reminders = {row["id"] for row in demo_seed.ROWS["reminder"]}
    for table, rows in demo_seed.ROWS.items():
        for row in rows:
            if "family_id" in row:
                assert row["family_id"] in families, table
            for key in ("owner_user_id", "subject_user_id", "source_user_id", "created_by_user_id",
                        "grantor_user_id", "grantee_user_id", "recipient_user_id", "verified_by", "user_id"):
                if key in row:
                    assert row[key] in users, (table, key)
            if "signal_event_id" in row:
                assert row["signal_event_id"] in signals
            if "reminder_id" in row:
                assert row["reminder_id"] in reminders


def test_fixture_contains_no_contact_or_media_data() -> None:
    for rows in demo_seed.ROWS.values():
        for row in rows:
            assert not any("phone" in key or "audio" in key or "photo" in key for key in row)
    assert all(row["provider"] == "mock" for row in demo_seed.ROWS["notification"])


def test_cli_check_replays_stably_without_database() -> None:
    command = [sys.executable, str(ROOT / "scripts" / "seed_demo_data.py"), "--check"]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    assert first.stdout == second.stdout
    assert demo_seed.NAMESPACE in first.stdout


def test_apply_refuses_non_demo_environment(monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location("seed_demo_data", ROOT / "scripts" / "seed_demo_data.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("DEMO_DATA", "false")
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    try:
        module._assert_demo_environment()
    except RuntimeError as error:
        assert "APP_ENV=demo" in str(error)
    else:
        raise AssertionError("non-demo environment accepted")
