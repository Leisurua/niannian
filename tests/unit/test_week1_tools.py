import importlib.util
import json
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


baseline = load_script("collect_device_baseline")
verify = load_script("verify_week1")


def fake_adb(devices="private-serial device", properties=None):
    observed = []
    values = properties or dict(zip(baseline.PROPERTIES.values(),
                                   ["Fictional", "Test Tablet", "SKU-A", "15", "35", "2026-09-01"]))

    def run(adb, arguments):
        observed.append(arguments)
        if arguments == ["devices"]:
            return "List of devices attached\n" + devices
        assert arguments[2:4] == ["shell", "getprop"]
        return values[arguments[-1]]
    return run, observed


def test_missing_adb_and_unauthorized_device_remain_unverified():
    assert baseline.collect(None)["status"] == "NOT_RUN"
    runner, commands = fake_adb("private-serial unauthorized")
    result = baseline.collect("adb", runner=runner)
    assert result["reason"] == "NO_AUTHORIZED_DEVICE"
    assert commands == [["devices"]]


def test_device_inventory_never_claims_capability_and_discards_serial():
    runner, commands = fake_adb()
    result = baseline.collect("adb", runner=runner)
    assert result["status"] == "PASS"
    assert result["device"]["model"] == "Test Tablet"
    assert result["hardware_gate"] == "NOT VERIFIED"
    assert set(result["capabilities"].values()) == {"UNKNOWN"}
    assert "private-serial" not in json.dumps(result)
    assert len(commands) == 1 + len(baseline.PROPERTIES)


def test_multiple_devices_require_explicit_selection():
    runner, commands = fake_adb("first device\nsecond device")
    assert baseline.collect("adb", runner=runner)["status"] == "NOT_RUN"
    assert commands == [["devices"]]
    assert baseline.collect("adb", serial="second", runner=runner)["status"] == "PASS"
    assert commands[-1][:2] == ["-s", "second"]


def test_failed_adb_does_not_save_diagnostics_or_claim_pass():
    def fail(*args):
        raise subprocess.CalledProcessError(1, "adb", stderr="private-serial")
    result = baseline.collect("adb", runner=fail)
    assert result["status"] == "BLOCKED"
    assert "private-serial" not in json.dumps(result)


@pytest.mark.parametrize("value", ["", "x" * 101, "line\nbreak", "sk-" + "x" * 24, "138" + "12345678"],
                         ids=["empty", "oversized", "multiline", "credential-shaped", "phone-shaped"])
def test_device_properties_reject_unknown_and_sensitive_values(value):
    assert baseline.safe_value(value) == "UNKNOWN"


def test_missing_infrastructure_is_not_success(monkeypatch, tmp_path):
    monkeypatch.setattr(verify.shutil, "which", lambda _: None)
    result = verify.run_checks(["infra"], tmp_path)
    assert result["status"] == "NOT VERIFIED"
    assert json.loads((tmp_path / "summary.json").read_text())["status"] == "NOT VERIFIED"


def test_failed_check_is_recorded_and_returns_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(verify.shutil, "which", lambda name: name)
    monkeypatch.setattr(verify.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1))
    result = verify.run_checks(["infra"], tmp_path)
    assert result["status"] == "FAIL"
    assert result["checks"][0]["exit_code"] == 1


def test_missing_device_exit_is_not_verification_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(verify.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 2))
    assert verify.run_checks(["device"], tmp_path)["status"] == "NOT VERIFIED"


def test_apk_gate_fails_instead_of_skipping_when_build_is_missing(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("apk_scan", ROOT / "tests/security/test_artifact_scan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setenv("NIANNIAN_REQUIRE_APKS", "1")
    with pytest.raises(AssertionError, match="requires rebuilt APKs"):
        module.ArtifactScanTest().test_built_apks_contain_no_secret_patterns()


def test_ci_pins_actions_and_keeps_all_foundation_gates():
    workflow = yaml.safe_load((ROOT / ".github/workflows/week1.yml").read_text())
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"backend", "android", "infrastructure"}
    for job in workflow["jobs"].values():
        assert job["timeout-minutes"] > 0
        assert any("verify_week1.py" in step.get("run", "") for step in job["steps"])
        for step in job["steps"]:
            if "uses" in step:
                revision = step["uses"].split("@")[1]
                assert len(revision) == 40 and all(c in "0123456789abcdef" for c in revision)
