"""Week 2 backend gates against an explicitly disposable PostgreSQL database."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[1]


def disposable_database(url: str) -> bool:
    try:
        parsed = make_url(url)
        return (parsed.drivername == "postgresql+psycopg" and not parsed.query
                and re.fullmatch(r"[A-Za-z0-9_]+_week2_test", parsed.database or "") is not None)
    except (ValueError, ArgumentError):
        return False


def run_checks(output: Path, *, device: bool = False) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    results = []
    database = os.environ.get("WEEK2_TEST_DATABASE_URL", "")
    environment = {**os.environ, "APP_ENV": "test", "PROVIDER_MODE": "mock", "PYTHONUTF8": "1",
                   "PYTHONPATH": str(ROOT / "backend")}
    python = sys.executable

    def record(name, status, **details):
        results.append({"check": name, "status": status, **details})
        print(f"{status}: {name}", flush=True)

    def execute(name, command, cwd=ROOT, unavailable_code=None):
        log = output / f"{name}.txt"
        try:
            with log.open("w", encoding="utf-8") as stream:
                completed = subprocess.run(command, cwd=cwd, env=environment, stdout=stream,
                    stderr=subprocess.STDOUT, timeout=300, check=False)
            status = "PASS" if completed.returncode == 0 else (
                "NOT VERIFIED" if completed.returncode == unavailable_code else "FAIL")
            record(name, status,
                   exit_code=completed.returncode, evidence=log.name)
            return completed.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as error:
            record(name, "NOT VERIFIED" if isinstance(error, OSError) else "FAIL",
                   reason=type(error).__name__, evidence=log.name)
            return False

    if sys.version_info[:2] != (3, 12):
        record("python", "NOT VERIFIED", reason="CPython 3.12 required")
    else:
        execute("lint", [python, "-m", "ruff", "check", "backend", "scripts", "tests"])
        ready = False
        if database and not disposable_database(database):
            record("postgres", "FAIL", reason="Require PostgreSQL driver, an ASCII _week2_test database name, and no query overrides")
        elif not database:
            record("postgres", "NOT VERIFIED", reason="Set WEEK2_TEST_DATABASE_URL to an explicitly disposable PostgreSQL database")
        else:
            environment["DATABASE_URL"] = database
            ready = execute("migration-upgrade", [python, "-m", "alembic", "upgrade", "head"], ROOT / "backend")
            if ready:
                execute("migration-parity", [python, "-m", "alembic", "check"], ROOT / "backend")
        report = output / "backend-tests.xml"
        # Do not reuse evidence left by an earlier invocation.
        report.unlink(missing_ok=True)
        command = [python, "-m", "pytest", "backend/tests", "tests", "-q", "--junitxml", str(report),
            "-k", "not test_built_apks_contain_no_secret_patterns"]
        if not ready:
            command += ["--ignore=backend/tests/integration"]
        # Never let an invalid DB URL reach fixtures that truncate business tables.
        if not ready:
            environment.pop("WEEK2_TEST_DATABASE_URL", None)
        if execute("backend-tests", command):
            try:
                suites = list(ET.parse(report).getroot().iter("testsuite"))
                counts = {key: sum(int(s.attrib.get(key, 0)) for s in suites)
                          for key in ("tests", "failures", "errors", "skipped")}
                status = "FAIL" if counts["failures"] or counts["errors"] else (
                    "NOT VERIFIED" if counts["skipped"] or not counts["tests"] else "PASS")
                record("test-inventory", status, **counts)
            except (OSError, ET.ParseError, ValueError):
                record("test-inventory", "NOT VERIFIED", reason="Missing or invalid test report")
        if device:
            execute("device-baseline", [python, "scripts/collect_device_baseline.py", "--output",
                str(output / "device-baseline.json")], unavailable_code=2)
            record("hardware-spikes", "NOT VERIFIED", reason="Inventory cannot verify kiosk/BLE/camera/wake/telephony gates")
    status = "FAIL" if any(r["status"] == "FAIL" for r in results) else (
        "NOT VERIFIED" if any(r["status"] == "NOT VERIFIED" for r in results) else "PASS")
    result = {"scope": "Week 2 backend" + (" and device inventory" if device else ""), "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status, "checks": results,
        "limits": ["Android build, UI/Keystore device smoke and APK scan are separate gates.",
                   "No real credential/provider, delivery or hardware acceptance."]}
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/week2/verification")
    parser.add_argument("--device", action="store_true", help="Also collect device inventory; hardware gates remain separate")
    args = parser.parse_args()
    return {"PASS": 0, "FAIL": 1, "NOT VERIFIED": 2}[run_checks(args.output.resolve(), device=args.device)["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
