"""Approved E0-T03 option A: actual main/worker execution and fatal process checks.

Separate from check_device_logging.py's unmanaged-thread reproduction. Synthetic
work is executed through the production boundary, never a direct sanitizer call.
"""

import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from check_device_logging import ANDROID, ROOT, CANARIES, checked, java_literal, mask, scan


HARNESS = ANDROID / "build" / "e0-t03-boundary-harness"
OUTPUT = ROOT / "docs" / "evidence" / "E0-T03" / "app-boundary"
RUNNER = "org.example.niannian.acceptance.BoundaryProbe"
MODES = ("main", "worker", "sink_failure", "hostile")


def probe_apk(role: str) -> Path:
    return ANDROID / f"app-{role}/build/outputs/apk/androidTest/demo/debug/app-{role}-demo-debug-androidTest.apk"


def prepare() -> tuple[Path, list[Path]]:
    source = HARNESS / "java/org/example/niannian/acceptance/BoundaryProbe.java"
    init = HARNESS / "acceptance.init.gradle"
    owned = [source, init, *(probe_apk(role) for role in ("elder", "family"))]
    if any(path.exists() for path in owned):
        raise RuntimeError("Probe files already exist; refusing to overwrite")
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("""package org.example.niannian.acceptance;
import android.app.Instrumentation;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import kotlin.Unit;
import org.example.niannian.core.telemetry.AppExecutionBoundary;
import org.example.niannian.core.telemetry.TelemetryLogger;

public final class BoundaryProbe extends Instrumentation {
    private String mode;
    private static final String CONTENT = """ + java_literal(" | ".join(CANARIES.values())) + """;
    @Override public void onCreate(Bundle args) {
        super.onCreate(args);
        mode = args.getString("mode");
        start();
    }
    @Override public void onStart() {
        try { Thread.sleep(3000); }
        catch (InterruptedException ignored) { finish(1, new Bundle()); return; }
        Runnable execution = () -> {
            Thread.currentThread().setName(CONTENT);
            AppExecutionBoundary boundary = "sink_failure".equals(mode)
                ? new AppExecutionBoundary(new TelemetryLogger(line -> { throw new Error(CONTENT); }))
                : new AppExecutionBoundary();
            boundary.run(() -> {
                RuntimeException failure = "hostile".equals(mode)
                    ? new RuntimeException() {
                        @Override public String getMessage() { return CONTENT; }
                        @Override public String toString() { return CONTENT; }
                    }
                    : new RuntimeException(CONTENT, new IllegalStateException(CONTENT));
                failure.addSuppressed(new IllegalArgumentException(CONTENT));
                throw failure;
            });
            Bundle survived = new Bundle();
            survived.putString("error", "PROCESS_SURVIVED_UNEXPECTEDLY");
            finish(1, survived);
        };
        if ("main".equals(mode)) new Handler(Looper.getMainLooper()).post(execution);
        else new Thread(execution, "E0T03-boundary-probe").start();
    }
}
""", encoding="utf-8")
    init.write_text("""allprojects { project ->
    project.plugins.withId('com.android.application') {
        project.android.defaultConfig.testInstrumentationRunner = 'org.example.niannian.acceptance.BoundaryProbe'
        project.android.sourceSets.androidTest.java.srcDirs = [new File(rootDir, 'build/e0-t03-boundary-harness/java')]
    }
}
""", encoding="utf-8")
    return init, owned


def cleanup(owned: list[Path]) -> None:
    for path in owned:
        resolved = path.resolve()
        if not resolved.is_relative_to(ANDROID.resolve()) or "build" not in resolved.parts:
            raise RuntimeError("Cleanup path outside Android build directory")
        path.unlink(missing_ok=True)


def install(adb: list[str], apk: Path, *, test: bool = False) -> None:
    result = subprocess.run([*adb, "install", "-r", *(["-t"] if test else []), str(apk)],
                            capture_output=True, timeout=60)
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if result.returncode or "Success" not in output:
        code = re.search(r"INSTALL_FAILED_[A-Z_]+", output)
        raise RuntimeError("APK installation failed: " + (code.group() if code else "UNKNOWN; raw output withheld"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial")
    parser.add_argument("--install", action="store_true", help="Update only both Demo apps, preserving app data")
    args = parser.parse_args()
    sdk = re.search(r"^sdk.dir=(.+)$", (ANDROID / "local.properties").read_text(), re.M)
    if not sdk:
        raise RuntimeError("Android SDK unavailable")
    adb_exe = str(Path(sdk.group(1).strip()) / "platform-tools/adb.exe")
    connected = [line.split()[0] for line in checked([adb_exe, "devices"]).splitlines()
                 if len(line.split()) == 2 and line.split()[1] == "device"]
    serial = args.serial or (connected[0] if len(connected) == 1 else None)
    if serial not in connected:
        raise RuntimeError("Require exactly one connected device or explicit selection")
    adb = [adb_exe, "-s", serial]
    for role in ("elder", "family"):
        test_package = f"org.example.niannian.{role}.demo.test"
        if f"package:{test_package}" in checked([*adb, "shell", "pm", "list", "packages", test_package]).splitlines():
            raise RuntimeError("An existing test package must not be overwritten")
    report = {
        "task": "E0-T03 approved option A app execution boundary",
        "time": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "source_commit": checked(["git", "-c", "safe.directory=D:/class_project", "rev-parse", "HEAD"]).strip(),
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(ANDROID.rglob("*.kt")) if "build" not in path.parts
        },
        "device": {key: checked([*adb, "shell", "getprop", prop]).strip() for key, prop in {
            "model": "ro.product.model", "android": "ro.build.version.release", "api": "ro.build.version.sdk",
            "os_build": "ro.build.display.id", "security_patch": "ro.build.version.security_patch",
        }.items()},
        "scope": "Installed production boundary executes throwing Runnable on main/worker; synthetic inputs only",
        "capture": "All readable buffers, observed PID only; original captures scanned in memory before masking",
        "limits": "Not full business flow, unmanaged/framework/native/ANR or private OEM reports; no global crash guarantee",
        "apps": [],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    init, owned = prepare()
    try:
        checked([str(ANDROID / "gradlew.bat"), "--offline", "--no-daemon", "--init-script", str(init),
                 ":app-elder:assembleDemoDebugAndroidTest", ":app-family:assembleDemoDebugAndroidTest", "-q"],
                cwd=ANDROID, timeout=240)
        for role in ("elder", "family"):
            package = f"org.example.niannian.{role}.demo"
            activity = f"{package}/org.example.niannian.{role}.MainActivity"
            local_apk = ANDROID / f"app-{role}/build/outputs/apk/demo/debug/app-{role}-demo-debug.apk"
            if args.install:
                install(adb, local_apk)
            base = checked([*adb, "shell", "pm", "path", package]).strip().removeprefix("package:")
            installed = subprocess.run([*adb, "exec-out", "cat", base], capture_output=True, timeout=30)
            local_hash = hashlib.sha256(local_apk.read_bytes()).hexdigest()
            installed_hash = hashlib.sha256(installed.stdout).hexdigest()
            if installed.returncode or installed_hash != local_hash:
                raise RuntimeError("Installed APK does not match local APK")
            app = {"role": role, "variant": "demoDebug", "provider": "mock", "local_apk_sha256": local_hash,
                   "installed_apk_sha256": installed_hash, "checks": []}
            checked([*adb, "shell", "am", "force-stop", package])
            launch = checked([*adb, "shell", "am", "start", "-W", "-n", activity])
            pid = checked([*adb, "shell", "pidof", package]).strip()
            checked([*adb, "shell", "input", "keyevent", "KEYCODE_HOME"])
            resume = checked([*adb, "shell", "am", "start", "-W", "-n", activity])
            normal = checked([*adb, "logcat", "-b", "all", "-d", "--pid=" + pid, "-v", "threadtime"])
            events = [json.loads(line[line.index("{"):]) for line in normal.splitlines()
                      if "NianNian" in line and "{" in line]
            app["normal_result"] = "PASS" if ("Status: ok" in launch and "Status: ok" in resume
                and events and all(event == {"event": "APP_STARTED", "provider": "mock"} for event in events)
                and not any(scan(normal).values()) and "FATAL EXCEPTION" not in normal) else "FAIL"
            app["normal_canary_hits"] = scan(normal)
            OUTPUT.joinpath(f"{role}-normal-redacted.txt").write_text(mask("\n".join(
                line for line in normal.splitlines() if "NianNian" in line or "AndroidRuntime" in line)) + "\n", encoding="utf-8")
            test_package = package + ".test"
            install(adb, probe_apk(role), test=True)
            app["probe_apk_sha256"] = hashlib.sha256(probe_apk(role).read_bytes()).hexdigest()
            try:
                for mode in MODES:
                    checked([*adb, "shell", "am", "force-stop", package])
                    proc = subprocess.Popen([*adb, "shell", "am", "instrument", "-w", "-e", "mode", mode,
                                             test_package + "/" + RUNNER], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    try:
                        probe_pid = ""
                        for _ in range(40):
                            found = subprocess.run([*adb, "shell", "pidof", package], capture_output=True, timeout=5)
                            probe_pid = found.stdout.decode().strip()
                            if probe_pid:
                                break
                            time.sleep(0.1)
                        if not probe_pid:
                            raise RuntimeError("Probe PID not observed")
                        stdout, stderr = proc.communicate(timeout=30)
                        crash = checked([*adb, "logcat", "-b", "all", "-d", "--pid=" + probe_pid, "-v", "threadtime"])
                        output = stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace")
                        hits = scan(crash + output)
                        still_running = subprocess.run([*adb, "shell", "pidof", package], capture_output=True, timeout=5)
                        telemetry = [json.loads(line[line.index("{"):]) for line in crash.splitlines()
                                     if "NianNian:" in line and "{" in line]
                        expected = [] if mode == "sink_failure" else [{"event": "APP_EXECUTION_FAILED",
                            "result": "FAILED", "error_code": "UNEXPECTED_FAILURE"}]
                        terminated = "Process crashed" in output and not still_running.stdout.strip()
                        safe_fatal = ("FATAL EXCEPTION: NianNian-fatal" in crash
                                      and "AppExecutionBoundary$ContentFreeFailure: APP_EXECUTION_FAILED" in crash)
                        result = "PASS" if (terminated and safe_fatal and telemetry == expected
                                             and not any(hits.values()) and "PROCESS_SURVIVED_UNEXPECTEDLY" not in output) else "FAIL"
                        app["checks"].append({"mode": mode, "result": result, "canary_hits": hits,
                            "process_terminated": terminated, "safe_fatal_observed": safe_fatal,
                            "telemetry_matches": telemetry == expected})
                        relevant = "\n".join(line for line in crash.splitlines() if "NianNian" in line or "AndroidRuntime" in line)
                        OUTPUT.joinpath(f"{role}-{mode}-redacted.txt").write_text(mask(relevant) + "\n", encoding="utf-8")
                        print(f"{role}/{mode}: {result}; terminated={terminated}; synthetic_hits={sum(hits.values())}")
                    finally:
                        if proc.poll() is None:
                            proc.kill()
                            proc.communicate()
            finally:
                app["test_apk_removed"] = "Success" in checked([*adb, "uninstall", test_package])
                checked([*adb, "shell", "am", "force-stop", package])
                app["recovered"] = "Status: ok" in checked([*adb, "shell", "am", "start", "-W", "-n", activity])
            report["apps"].append(app)
        report["result"] = "PASS" if all(app["normal_result"] == "PASS" and app["test_apk_removed"] and app["recovered"]
            and all(item["result"] == "PASS" for item in app["checks"]) for app in report["apps"]) else "FAIL"
    finally:
        cleanup(owned)
    report["local_probe_files_removed"] = all(not path.exists() for path in owned)
    OUTPUT.joinpath("device-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
