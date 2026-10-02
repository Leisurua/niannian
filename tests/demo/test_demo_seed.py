"""E0-T08 fictional seed smoke and namespace safety checks."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import demo_seed  # noqa: E402
import pytest  # noqa: E402


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
            assert not any(("phone" in key and key != "phone_permission") or "audio" in key or "photo" in key
                           for key in row)
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


def test_rows_match_frozen_dictionary_columns_required_fields_and_enums() -> None:
    dictionary = (ROOT / "docs/data-dictionary.md").read_text(encoding="utf-8")
    for table, rows in demo_seed.ROWS.items():
        section = re.search(rf"^## \d+\. {table}\n(.*?)(?=^## |\Z)", dictionary, re.M | re.S)
        assert section, table
        columns = {}
        for line in section[1].splitlines():
            if not line.startswith("| "):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == 7 and cells[0] not in ("Column", "---"):
                columns[cells[0]] = cells[1:]
        required = {key for key, (_type, nullable, default, *_rest) in columns.items()
                    if nullable == "no" and default == "-"}
        for row in rows:
            assert row.keys() <= columns.keys(), table
            assert required <= row.keys(), (table, required - row.keys())
            for key, value in row.items():
                column_type, _nullable, _default, constraint, *_rest = columns[key]
                enums = re.search(r"CHECK ([A-Z][A-Z0-9_]+(?:/[A-Z0-9_]+)+)", constraint)
                if enums:
                    assert value in enums[1].split("/"), (table, key)
                if column_type == "jsonb":
                    assert key in demo_seed.JSON_COLUMNS
                    assert isinstance(value, (dict, list))


def test_deletion_degradation_and_failure_are_explicitly_simulated() -> None:
    deleted = next(row for row in demo_seed.ROWS["memory"] if row["id"] == demo_seed.MEMORY_DELETED)
    asset = demo_seed.ROWS["file_asset"][0]
    device = demo_seed.ROWS["device_binding"][0]
    assert deleted["verification_status"] == "DELETED" and deleted["deleted_at"]
    assert asset["memory_id"] == deleted["id"]
    assert asset["status"] == "DELETE_REQUESTED" and asset["deleted_at"]
    assert asset["size_bytes"] == 0 and asset["media_type"] == "OTHER"
    assert device["ble_status"] == "DISCONNECTED"
    assert device["kiosk_status"] == "DISABLED" and device["wakeword_status"] == "ERROR"
    assert device["camera_permission"] == device["phone_permission"] == "DENIED"
    assert device["capabilities"] == {"provider": "mock", "demo": True}
    assert all(scenario["provider"] == "mock" and scenario["demo"] for scenario in demo_seed.SCENARIOS.values())
    assert demo_seed.SCENARIOS["deletion_partial_failure"]["error_code"] == "MOCK_FAILURE"
    assert demo_seed.SCENARIOS["deletion_partial_failure"]["file_asset_id"] == asset["id"]


def test_health_revocation_withholds_protected_notification() -> None:
    assert not any(row["scope"] == "HEALTH_MEDICATION" and row["status"] == "GRANTED"
                   for row in demo_seed.ROWS["consent"])
    protected = {row["id"] for row in demo_seed.ROWS["signal_event"]
                 if row["type"] in ("PHYSICAL_DISCOMFORT", "SCAM_RISK")}
    assert all(row["consent_check_result"] == row["status"] == "WITHHELD"
               for row in demo_seed.ROWS["signal_event"] if row["id"] in protected)
    assert not any(row["signal_event_id"] in protected for row in demo_seed.ROWS["notification"])


def test_check_still_validates_in_optimized_python() -> None:
    code = "import demo_seed; demo_seed.ROWS['memory'][0]['family_id'] = demo_seed.uid(999); demo_seed.validate_fixture()"
    result = subprocess.run([sys.executable, "-O", "-c", code], cwd=ROOT / "scripts",
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "cross-family fixture reference" in result.stderr


@pytest.mark.parametrize("key,value", [("APP_ENV", "production"), ("DEMO_DATA", "false"),
                                       ("PROVIDER_MODE", "real"), ("DATABASE_URL", "")])
def test_apply_guard_rejects_each_unsafe_setting(monkeypatch, key, value) -> None:
    import seed_demo_data

    for field, setting in {"APP_ENV": "demo", "DEMO_DATA": "true", "PROVIDER_MODE": "mock",
                           "DATABASE_URL": "postgresql://unused"}.items():
        monkeypatch.setenv(field, setting)
    monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError):
        seed_demo_data._assert_demo_environment()
