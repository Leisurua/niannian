"""E0-T03 acceptance probe; synthetic inputs, masked evidence, no app changes."""

import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android"
OUTPUT = ROOT / "docs" / "evidence" / "E0-T03"
HARNESS = ANDROID / "build" / "e0-t03-harness"
RUNNER = "org.example.niannian.acceptance.LogProbe"
_probe_generated = False
CANARIES = {
    "token": "Bearer " + "e0t03synthetic" * 3,
    "key": "sk-" + "S" * 24,
    "audio": "E0T03_SYNTHETIC_AUDIO_PAYLOAD",
    "transcript": "E0T03 synthetic transcript content",
    "phone": "1" + "3" * 10,
    "health": "E0T03 synthetic health content",
    "memory": "E0T03 synthetic memory content",
    "url": "https://example.invalid/e0t03?signature=synthetic-only",
}


def checked(command: list[str], *, cwd: Path = ROOT, timeout: int = 30) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, timeout=timeout)
    if result.returncode:
        # Commands can contain the device serial; never include them in errors.
        raise RuntimeError(f"Command failed (exit {result.returncode}); raw output withheld")
    return result.stdout.decode("utf-8", errors="replace")


def mask(text: str) -> str:
    for category, value in CANARIES.items():
        text = text.replace(value, f"[REDACTED_SYNTHETIC_{category.upper()}]")
    text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[REDACTED_PHONE_PATTERN]", text)
    text = re.sub(r"sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}", "[REDACTED_KEY_PATTERN]", text)
    text = re.sub(r"Bearer [A-Za-z0-9._-]{20,}", "[REDACTED_TOKEN_PATTERN]", text)
    return text


def scan(text: str) -> dict[str, int]:
    return {category: text.count(value) for category, value in CANARIES.items()}


def java_literal(text: str) -> str:
    return json.dumps(text)


def prepare_harness() -> Path:
    global _probe_generated
    source = HARNESS / "java" / "org" / "example" / "niannian" / "acceptance"
    preexisting = [source / "LogProbe.java", HARNESS / "acceptance.init.gradle"]
    preexisting.extend(
        ANDROID / f"app-{role}" / "build" / "outputs" / "apk" / "androidTest" / "demo" / "debug"
        / f"app-{role}-demo-debug-androidTest.apk"
        for role in ("elder", "family")
    )
    if any(path.exists() for path in preexisting):
        raise RuntimeError("Probe source or test APK already exists; refusing to overwrite it")
    source.mkdir(parents=True, exist_ok=True)
    _probe_generated = True
    field_code = "\n".join(
        f"fields.put({java_literal(key)}, {java_literal(value)});"
        for key, value in CANARIES.items()
    )
    # Canaries are constructed at runtime in this Python source. Generated Java
    # and APK files stay in the ignored build directory and are never evidence.
    source.joinpath("LogProbe.java").write_text(
        """package org.example.niannian.acceptance;
import android.app.Instrumentation;
import android.os.Bundle;
import java.util.LinkedHashMap;
import java.util.Map;

public final class LogProbe extends Instrumentation {
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        try {
            Class<?> type = getTargetContext().getClassLoader().loadClass(
                "org.example.niannian.core.telemetry.TelemetryLogger");
            Object logger = type.getConstructor().newInstance();
            java.lang.reflect.Method info = type.getMethod("info", String.class, Map.class);
            Map<String, String> fields = new LinkedHashMap<>();
            fields.put("request_id", "req-e0t03");
            fields.put("correlation_id", "corr-e0t03");
            fields.put("provider", "mock");
            fields.put("result", "FAILED");
            fields.put("error_code", "CONTROLLED_EXCEPTION");
            fields.put("latency_ms", "12");
        """
        + field_code
        + "\nfields.put(\"user_id\", " + java_literal(CANARIES["phone"]) + ");\n"
        + """info.invoke(logger, "PRIVACY_PROBE", fields);
            fields.clear();
        """
        + "fields.put(\"request_id\", " + java_literal(CANARIES["key"]) + ");\n"
        + "fields.put(\"family_id\", " + java_literal(CANARIES["token"]) + ");\n"
        + "fields.put(\"device_id\", " + java_literal(CANARIES["transcript"]) + ");\n"
        + """info.invoke(logger, "PRIVACY_PROBE", fields);
            info.invoke(logger, "synthetic exception text with spaces", new LinkedHashMap<String, String>());
            Thread.sleep(3000);
            Thread crash = new Thread(new Runnable() {
                @Override public void run() {
                    throw new RuntimeException(
        """
        + java_literal(" | ".join(list(CANARIES.values())[:4]))
        + ", new IllegalStateException("
        + java_literal(" | ".join(list(CANARIES.values())[4:]))
        + """));
                }
            }, "E0T03-controlled-crash");
            crash.start();
            crash.join();
            Bundle result = new Bundle();
            result.putString("error", "PROCESS_SURVIVED_UNEXPECTEDLY");
            finish(1, result);
        } catch (Exception failure) {
            Bundle result = new Bundle();
            result.putString("error", "HARNESS_SETUP_FAILED");
            finish(1, result);
        }
    }
}
""",
        encoding="utf-8",
    )
    init = HARNESS / "acceptance.init.gradle"
    init.write_text(
        """allprojects { project ->
    project.plugins.withId('com.android.application') {
        project.android.defaultConfig.testInstrumentationRunner = 'org.example.niannian.acceptance.LogProbe'
        project.android.sourceSets.androidTest.java.srcDirs = [new File(rootDir, 'build/e0-t03-harness/java')]
    }
}
""",
        encoding="utf-8",
    )
    return init


def clean_local_probe() -> bool:
    global _probe_generated
    if not _probe_generated:
        return True
    # Delete only the exact files created for this probe. Keep production APKs,
    # all other build outputs, and pre-existing worktree files untouched.
    files = [HARNESS / "java" / "org" / "example" / "niannian" / "acceptance" / "LogProbe.java",
             HARNESS / "acceptance.init.gradle"]
    files.extend(
        ANDROID / f"app-{role}" / "build" / "outputs" / "apk" / "androidTest" / "demo" / "debug"
        / f"app-{role}-demo-debug-androidTest.apk"
        for role in ("elder", "family")
    )
    for path in files:
        resolved = path.resolve()
        if not resolved.is_relative_to(ANDROID.resolve()) or "build" not in resolved.parts:
            raise RuntimeError("Probe cleanup path outside Android build directory")
        path.unlink(missing_ok=True)
    _probe_generated = False
    return all(not path.exists() for path in files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="Explicit device; otherwise require exactly one connected device")
    parser.add_argument("--adb")
    args = parser.parse_args()
    sdk = re.search(r"^sdk.dir=(.+)$", (ANDROID / "local.properties").read_text(), re.M)
    if not args.adb and sdk is None:
        raise RuntimeError("Android SDK path unavailable")
    adb_exe = args.adb or str(Path(sdk.group(1).strip()) / "platform-tools" / "adb.exe")
    devices = checked([adb_exe, "devices"]).splitlines()
    connected = [line.split()[0] for line in devices if len(line.split()) == 2 and line.split()[1] == "device"]
    if args.serial:
        if args.serial not in connected:
            raise RuntimeError("Selected device unavailable")
        serial = args.serial
    elif len(connected) == 1:
        serial = connected[0]
    else:
        raise RuntimeError("Exactly one connected device or explicit --serial required")
    adb = [adb_exe, "-s", serial]
    report = {
        "task": "E0-T03 device log acceptance / PRIV-002",
        "time": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "source_commit": checked(["git", "-c", "safe.directory=D:/class_project", "rev-parse", "HEAD"]).strip(),
        "device": {
            key: checked([*adb, "shell", "getprop", prop]).strip()
            for key, prop in {
                "manufacturer": "ro.product.manufacturer", "model": "ro.product.model",
                "codename": "ro.product.device", "android": "ro.build.version.release",
                "api": "ro.build.version.sdk", "security_patch": "ro.build.version.security_patch",
                "os_build": "ro.build.display.id",
            }.items()
        },
        "canaries": "Eight synthetic categories; no real data; raw captures held only in memory",
        "capture_scope": "Each observed app PID only; all readable Logcat buffers; no device log clearing",
        "apps": [],
        "full_business_flow": "NOT VERIFIED: current apps have only Demo/Mock entry screens",
        "oem_crash_reports": "NOT VERIFIED: private DropBox/tombstone/upload pipeline not inspected",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    init = prepare_harness()
    build = subprocess.run(
        [str(ANDROID / "gradlew.bat"), "--offline", "--no-daemon", "--init-script", str(init),
         ":core-telemetry:testDebugUnitTest", ":core-telemetry:testReleaseUnitTest", "--rerun-tasks",
         ":app-elder:assembleDemoDebugAndroidTest", ":app-family:assembleDemoDebugAndroidTest", "-q"],
        cwd=ANDROID, capture_output=True, timeout=240,
    )
    if build.returncode:
        raise RuntimeError("Offline probe build failed: " + mask(build.stderr.decode("utf-8", errors="replace"))[-1500:])
    for role in ("elder", "family"):
        package = f"org.example.niannian.{role}.demo"
        activity = f"org.example.niannian.{role}.MainActivity"
        test_package = package + ".test"
        local_apk = ANDROID / f"app-{role}" / "build" / "outputs" / "apk" / "demo" / "debug" / f"app-{role}-demo-debug.apk"
        base = checked([*adb, "shell", "pm", "path", package]).strip().removeprefix("package:")
        installed = subprocess.run([*adb, "exec-out", "cat", base], capture_output=True, timeout=30)
        if installed.returncode:
            raise RuntimeError("Installed APK could not be read")
        installed_hash = hashlib.sha256(installed.stdout).hexdigest()
        local_hash = hashlib.sha256(local_apk.read_bytes()).hexdigest()
        if installed_hash != local_hash:
            raise RuntimeError("Installed APK does not match local build; acceptance stopped")
        version = checked([*adb, "shell", "dumpsys", "package", package])
        app = {
            "role": role, "package": package, "variant": "demoDebug", "provider": "mock",
            "version": re.findall(r"version(?:Code|Name)=[^\r\n]+", version),
            "installed_apk_sha256": installed_hash, "local_apk_sha256": local_hash,
            "normal_flow": [],
        }
        checked([*adb, "shell", "am", "force-stop", package])
        launch = checked([*adb, "shell", "am", "start", "-W", "-n", package + "/" + activity])
        pid = checked([*adb, "shell", "pidof", package]).strip()
        app["normal_flow"].append("Cold launch: " + ("ok" if "Status: ok" in launch else "FAILED"))
        checked([*adb, "shell", "input", "keyevent", "KEYCODE_HOME"])
        launch2 = checked([*adb, "shell", "am", "start", "-W", "-n", package + "/" + activity])
        app["normal_flow"].append("Home then resume: " + ("ok" if "Status: ok" in launch2 else "FAILED"))
        normal = checked([*adb, "logcat", "-b", "all", "-d", "--pid=" + pid, "-v", "threadtime"])
        normal_lines = [line for line in normal.splitlines() if "NianNian" in line or "AndroidRuntime" in line]
        normal_json = [json.loads(line[line.index("{"):]) for line in normal_lines if "NianNian" in line and "{" in line]
        app["normal_event_count"] = len(normal_json)
        app["normal_canary_hits"] = scan(normal)
        app["normal_result"] = "PASS" if (
            normal_json and all(item == {"event": "APP_STARTED", "provider": "mock"} for item in normal_json)
            and all(item.endswith("ok") for item in app["normal_flow"])
            and not any(app["normal_canary_hits"].values()) and "FATAL EXCEPTION" not in normal
        ) else "FAIL"
        OUTPUT.joinpath(f"xiaomi12-{role}-normal-redacted.txt").write_text(mask("\n".join(normal_lines)) + "\n", encoding="utf-8")
        test_apk = ANDROID / f"app-{role}" / "build" / "outputs" / "apk" / "androidTest" / "demo" / "debug" / f"app-{role}-demo-debug-androidTest.apk"
        if "Success" not in checked([*adb, "install", "-r", str(test_apk)]):
            raise RuntimeError("Probe APK install did not succeed")
        app["probe_apk_sha256"] = hashlib.sha256(test_apk.read_bytes()).hexdigest()
        proc = None
        try:
            checked([*adb, "shell", "am", "force-stop", package])
            proc = subprocess.Popen([*adb, "shell", "am", "instrument", "-w", test_package + "/" + RUNNER], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            probe_pid = ""
            for _ in range(40):
                found = subprocess.run([*adb, "shell", "pidof", package], capture_output=True, timeout=5)
                probe_pid = found.stdout.decode().strip()
                if probe_pid:
                    break
                time.sleep(0.1)
            if not probe_pid:
                raise RuntimeError("Probe process not observed")
            stdout, stderr = proc.communicate(timeout=30)
            crash = checked([*adb, "logcat", "-b", "all", "-d", "--pid=" + probe_pid, "-v", "threadtime"])
            telemetry = "\n".join(line for line in crash.splitlines() if "NianNian" in line)
            events = [json.loads(line[line.index("{"):]) for line in telemetry.splitlines() if "{" in line]
            expected = [
                {"event": "PRIVACY_PROBE", "request_id": "req-e0t03", "correlation_id": "corr-e0t03",
                 "provider": "mock", "result": "FAILED", "error_code": "CONTROLLED_EXCEPTION", "latency_ms": 12},
                {"event": "PRIVACY_PROBE"}, {"event": "UNSTRUCTURED_LOG"},
            ]
            app["telemetry_canary_hits"] = scan(telemetry)
            app["telemetry_result"] = "PASS" if events == expected and not any(scan(telemetry).values()) else "FAIL"
            runtime = "\n".join(line for line in crash.splitlines() if "AndroidRuntime" in line)
            app["uncaught_exception_observed"] = "FATAL EXCEPTION: E0T03-controlled-crash" in runtime
            app["nested_cause_observed"] = "Caused by: java.lang.IllegalStateException:" in runtime
            app["crash_canary_hits"] = scan(runtime)
            app["instrumentation_process_crashed"] = "Process crashed" in stdout.decode("utf-8", errors="replace")
            if not app["uncaught_exception_observed"] or not app["instrumentation_process_crashed"]:
                raise RuntimeError("Controlled crash not confirmed; cannot claim crash acceptance")
            app["crash_result"] = "FAIL" if any(app["crash_canary_hits"].values()) else "PASS"
            app["result"] = "PASS" if all(app[key] == "PASS" for key in ("normal_result", "telemetry_result", "crash_result")) else "FAIL"
            # Keep only relevant masked lines, never unrelated device output.
            OUTPUT.joinpath(f"xiaomi12-{role}-crash-redacted.txt").write_text(mask(telemetry + "\n" + runtime) + "\n", encoding="utf-8")
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.communicate()
            removed = "Success" in checked([*adb, "uninstall", test_package])
            checked([*adb, "shell", "am", "force-stop", package])
            recovered = checked([*adb, "shell", "am", "start", "-W", "-n", package + "/" + activity])
            app["test_apk_removed"] = removed
            app["relaunch_after_crash"] = "ok" if "Status: ok" in recovered else "FAIL"
        report["apps"].append(app)
        print(f"{role}: normal={app['normal_result']}, telemetry={app['telemetry_result']}, crash={app['crash_result']}; synthetic hits={app['crash_canary_hits']}")
    report["device_log_result"] = "PASS" if all(app["result"] == "PASS" for app in report["apps"]) else "FAIL"
    report["priv_002_result"] = report["device_log_result"] if report["device_log_result"] == "FAIL" else "NOT_RUN"
    report["local_probe_source_and_apks_removed"] = clean_local_probe()
    OUTPUT.joinpath("xiaomi12-log-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["device_log_result"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        clean_local_probe()
