"""Read-only ENV-001 inventory. No serials, accounts, dumpsys, media or logcat saved."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess

PROPERTIES = {
    "manufacturer": "ro.product.manufacturer", "model": "ro.product.model",
    "sku": "ro.boot.hardware.sku", "android_version": "ro.build.version.release",
    "api_level": "ro.build.version.sdk", "security_patch": "ro.build.version.security_patch",
}


def run_adb(adb: str, arguments: list[str]) -> str:
    return subprocess.run([adb, *arguments], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=15, check=True).stdout.strip()


def safe_value(value: str) -> str:
    if not value or len(value) > 100 or not re.fullmatch(r"[\w .()+/-]+", value):
        return "UNKNOWN"
    if re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)|(?i:bearer|token|secret|sk-)", value):
        return "UNKNOWN"
    return value


def collect(adb: str | None, *, serial: str | None = None, runner=run_adb) -> dict:
    report = {"test_id": "ENV-001", "status": "NOT_RUN", "provider": "observed-adb",
              "recorded_at": datetime.now(timezone.utc).isoformat(),
              "reason": "ADB_UNAVAILABLE", "device": {key: "UNKNOWN" for key in PROPERTIES},
              "capabilities": {key: "UNKNOWN" for key in ["gms", "kiosk", "ble", "camera", "audio", "telephony"]},
              "app_build": "NOT VERIFIED", "hardware_gate": "NOT VERIFIED"}
    if not adb:
        return report
    try:
        devices = []
        for line in runner(adb, ["devices"]).splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[1] == "device":
                devices.append(fields[0])
        if serial:
            devices = [value for value in devices if value == serial]
        if len(devices) != 1:
            report["reason"] = "NO_AUTHORIZED_DEVICE" if not devices else "MULTIPLE_DEVICES_SELECT_SERIAL"
            return report
        prefix = ["-s", devices[0], "shell"]
        for key, prop in PROPERTIES.items():
            report["device"][key] = safe_value(runner(adb, [*prefix, "getprop", prop]))
        report["status"] = "PASS" if all(report["device"][key] != "UNKNOWN" for key in
                                             ["manufacturer", "model", "api_level", "security_patch"]) else "BLOCKED"
        report["reason"] = "INVENTORY_ONLY_MANUAL_CHECKS_REQUIRED"
    except (OSError, subprocess.SubprocessError):
        report["status"] = "BLOCKED"
        report["reason"] = "ADB_READ_FAILED"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default=shutil.which("adb"))
    parser.add_argument("--serial", help="Select locally; never written to the evidence")
    parser.add_argument("--output", type=Path, default=Path("artifacts/week1/device-baseline.json"))
    args = parser.parse_args()
    report = collect(args.adb, serial=args.serial)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: ENV-001 ({report['reason']}); hardware gate NOT VERIFIED")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
