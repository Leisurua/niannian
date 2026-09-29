"""Validate or replay the fictional demo namespace into an existing schema.

Usage: python scripts/seed_demo_data.py --check
       APP_ENV=demo DEMO_DATA=true PROVIDER_MODE=mock DATABASE_URL=... \
         python scripts/seed_demo_data.py --apply

This script never creates tables or changes the frozen schema.
"""

from __future__ import annotations

import argparse
import os
import sys

from demo_seed import CHILD, ELDER, FAMILY, FAMILY_NAME, JSON_COLUMNS, NAMESPACE, ROWS, validate_fixture


def _assert_demo_environment() -> str:
    if (os.environ.get("APP_ENV"), os.environ.get("DEMO_DATA", "").lower(),
            os.environ.get("PROVIDER_MODE")) != ("demo", "true", "mock"):
        raise RuntimeError("--apply requires APP_ENV=demo, DEMO_DATA=true, PROVIDER_MODE=mock")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("--apply requires DATABASE_URL; credentials are never printed")
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def _check_schema(cursor) -> None:
    required = {table: set().union(*(row.keys() for row in rows)) for table, rows in ROWS.items()}
    cursor.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema()"
    )
    actual: dict[str, set[str]] = {}
    for table, column in cursor.fetchall():
        actual.setdefault(table, set()).add(column)
    missing = {table: sorted(columns - actual.get(table, set())) for table, columns in required.items()
               if not columns <= actual.get(table, set())}
    if missing:
        # Report names only; never emit connection strings or fixture values.
        raise RuntimeError(f"business schema unavailable or incomplete: {missing}")


def _check_namespace(cursor) -> None:
    from psycopg import sql

    cursor.execute(sql.SQL("SELECT name FROM {} WHERE id = %s").format(sql.Identifier("family")), (FAMILY,))
    existing_family = cursor.fetchone()
    if existing_family is not None and existing_family[0] != FAMILY_NAME:
        raise RuntimeError("demo family ID belongs to another namespace")
    for user_id, expected_name in ((ELDER, "演示老人"), (CHILD, "演示子女")):
        cursor.execute(sql.SQL("SELECT display_name FROM {} WHERE id = %s").format(sql.Identifier("user")), (user_id,))
        existing_user = cursor.fetchone()
        if existing_user is not None and existing_user[0] != expected_name:
            raise RuntimeError("demo user ID belongs to another namespace")
    for table, rows in ROWS.items():
        if table in ("user", "family"):
            continue
        marker = next((key for key in ("family_id", "owner_user_id", "user_id", "reminder_id",
                                       "signal_event_id", "notification_id") if key in rows[0]), None)
        if marker is None:
            raise RuntimeError(f"no namespace marker for {table}")
        expected = {row["id"]: row[marker] for row in rows}
        cursor.execute(
            sql.SQL("SELECT id, {} FROM {} WHERE id = ANY(%s::uuid[])").format(
                sql.Identifier(marker), sql.Identifier(table)
            ),
            (list(expected),),
        )
        for identifier, value in cursor.fetchall():
            if str(value) != str(expected[str(identifier)]):
                raise RuntimeError(f"demo row ID in {table} belongs to another namespace")


def replay(connection) -> None:
    """Delete only fixed demo IDs and rebuild them in one transaction."""
    from psycopg import sql
    from psycopg.types.json import Jsonb

    with connection.transaction():
        with connection.cursor() as cursor:
            _check_schema(cursor)
            _check_namespace(cursor)
            for table, rows in reversed(list(ROWS.items())):
                cursor.execute(
                    sql.SQL("DELETE FROM {} WHERE id = ANY(%s::uuid[])").format(sql.Identifier(table)),
                    ([row["id"] for row in rows],),
                )
            for table, rows in ROWS.items():
                for row in rows:
                    columns = list(row)
                    values = [Jsonb(row[column]) if column in JSON_COLUMNS else row[column] for column in columns]
                    cursor.execute(
                        sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                            sql.Identifier(table),
                            sql.SQL(", ").join(map(sql.Identifier, columns)),
                            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                        ),
                        values,
                    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fictional E0-T08 demo seed")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="validate fixture without database writes")
    mode.add_argument("--apply", action="store_true", help="replay into existing demo schema")
    args = parser.parse_args()
    validate_fixture()
    if args.check:
        print(f"PASS: {NAMESPACE} fixture, {sum(map(len, ROWS.values()))} deterministic rows")
        return 0
    dsn = _assert_demo_environment()
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as connection:
        replay(connection)
    print(f"PASS: replayed {NAMESPACE} fixture")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, RuntimeError) as exc:
        print(f"Seed validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
