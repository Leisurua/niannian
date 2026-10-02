"""Repeatable Week 1 gates. Missing prerequisites never count as a pass."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def run_checks(checks: list[str], output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    environment = {**os.environ, "APP_ENV": "test", "PROVIDER_MODE": "mock",
                   "PYTHONPATH": str(ROOT / "backend"), "PYTHONUTF8": "1"}

    def record(name: str, status: str, reason: str = "", **extra) -> None:
        results.append({"check": name, "status": status, "reason": reason, **extra})
        print(f"{status}: {name}" + (f" ({reason})" if reason else ""), flush=True)

    def execute(name: str, command: list[str], *, cwd: Path = ROOT,
                timeout: int = 300, env: dict | None = None, unavailable_code: int | None = None) -> bool:
        log = output / f"{name}.txt"
        try:
            with log.open("w", encoding="utf-8") as stream:
                result = subprocess.run(command, cwd=cwd, env=env or environment,
                                        stdout=stream, stderr=subprocess.STDOUT,
                                        timeout=timeout, check=False)
            status = "PASS" if result.returncode == 0 else (
                "NOT VERIFIED" if result.returncode == unavailable_code else "FAIL")
            record(name, status, exit_code=result.returncode, evidence=log.name)
            if status == "FAIL":
                print(log.read_text(encoding="utf-8", errors="replace")[-8000:], flush=True)
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as error:
            record(name, "NOT VERIFIED" if isinstance(error, OSError) else "FAIL",
                   type(error).__name__, evidence=log.name)
            return False

    python = sys.executable
    if "backend" in checks:
        if sys.version_info[:2] != (3, 12):
            record("python", "NOT VERIFIED", "CPython 3.12 required")
        else:
            execute("lint", [python, "-m", "ruff", "check", "backend", "scripts", "tests"])
            execute("python-compile", [python, "-m", "compileall", "-q", "backend/app", "scripts", "tests"])
            execute("backend-tests", [python, "-m", "pytest", "backend/tests", "tests", "-q",
                                      "--junitxml", str(output / "backend-tests.xml")])
            execute("demo-seed", [python, "scripts/seed_demo_data.py", "--check"])
            if execute("backend-wheel", [python, "-m", "pip", "wheel", "./backend", "--no-deps",
                                         "--no-build-isolation", "--disable-pip-version-check",
                                         "--wheel-dir", str(output / "wheels")]):
                execute("installed-wheel", [python, "scripts/check_backend_wheel.py", str(output / "wheels")])
    if "android" in checks:
        java = Path(os.environ.get("JAVA_HOME", "")) / "bin" / ("java.exe" if os.name == "nt" else "java")
        sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if os.environ.get("NIANNIAN_BUILD_ROOT"):
            record("android-build", "NOT VERIFIED", "Unset NIANNIAN_BUILD_ROOT so APK evidence matches this build")
        elif not (java.is_file() or shutil.which("java")) or not sdk or not Path(sdk).is_dir():
            record("android-build", "NOT VERIFIED", "JDK 17 and Android SDK 35 required; set JAVA_HOME and ANDROID_HOME")
        else:
            command = [str(ROOT / "android/gradlew.bat")] if os.name == "nt" else ["bash", "./gradlew"]
            if execute("android-build", [*command, "--no-daemon", "clean", "build"], cwd=ROOT / "android", timeout=1200):
                execute("apk-privacy", [python, "tests/security/test_artifact_scan.py"],
                        env={**environment, "NIANNIAN_REQUIRE_APKS": "1"})
    if "infra" in checks:
        if not shutil.which("docker") or not shutil.which("pwsh"):
            record("infra-smoke", "NOT VERIFIED", "Docker Compose and PowerShell 7 required")
        else:
            execute("infra-smoke", ["pwsh", "-NoProfile", "-File", "infra/smoke.ps1"], timeout=1200)
    if "device" in checks:
        execute("device-baseline", [python, "scripts/collect_device_baseline.py", "--output",
                                    str(output / "device-baseline.json")], unavailable_code=2)

    status = "FAIL" if any(r["status"] == "FAIL" for r in results) else (
        "NOT VERIFIED" if any(r["status"] == "NOT VERIFIED" for r in results) else "PASS")
    report = {"scope": "Week 1 engineering gates only", "checked_at": datetime.now(timezone.utc).isoformat(),
              "status": status, "checks": results,
              "limits": ["No real provider, physical device, delivery or business-flow acceptance.",
                         "Backend-only checks may skip APK scanning; the android gate requires all 12 APKs."]}
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checks", nargs="+", choices=["backend", "android", "infra", "device"],
                        default=["backend", "android", "infra"])
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/week1")
    args = parser.parse_args()
    result = run_checks(list(dict.fromkeys(args.checks)), args.output.resolve())
    return {"PASS": 0, "FAIL": 1, "NOT VERIFIED": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
