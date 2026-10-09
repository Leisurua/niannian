# Device acceptance checks

`check_device_logging.py` runs the E0-T03 / PRIV-002 logging check against the
already-installed Elder and Family `demoDebug` apps on one explicitly selected
device. It does not add a production crash endpoint or change application code.

The script builds a temporary Android framework Instrumentation APK with an
offline Gradle init script. It calls the installed application's real
`TelemetryLogger`, injects synthetic canaries, and triggers an uncaught worker
exception with a nested cause. Only PID-scoped Logcat is read. Raw output stays
in memory; canary values are replaced before any evidence is written. No device
serial, credentials, real records, audio, or camera data is saved.

Run from the repository root with the project's Python 3.12 environment:

```powershell
backend/.venv/Scripts/python.exe tests/device/check_device_logging.py --serial <device>
```

ADB defaults to the SDK in `android/local.properties`; `--adb` can override it.
The script launches and force-stops only the two Demo apps, installs/removes
their dedicated test APKs, and relaunches both apps after the controlled crash.
Existing device logs are not cleared. Local test APKs and generated harness
source are removed after execution, preserving production APKs; safe report and
masked log excerpts are written to `docs/evidence/E0-T03/`. Intermediate build
outputs remain under ignored Android `build/` and must not be committed.

Exit 0 means the tested skeleton logging paths passed; exit 1 means a redaction
failure; an unavailable prerequisite raises an error. None of these outcomes
proves PRIV-002's future full business flow or OEM crash-upload privacy.

## Approved app execution boundary (separate probe)

`check_app_boundary_logging.py --install` updates only the two Demo APKs with
`adb install -r` (preserving app data), verifies installed hashes, and exercises
the production `AppExecutionBoundary` with actual throwing work on main and
worker threads. Separate cases cover nested/suppressed exceptions, a hostile
formatter and a failed telemetry sink. Each case requires a content-free
AndroidRuntime fatal record, no synthetic canary in any readable PID-scoped
buffer or instrumentation output, and observed process termination. Normal
startup/resume, probe removal and app recovery must also succeed.

Run with the same Python environment; omit `--install` to require already
installed matching APKs. It uses the sole connected device or `--serial`.
Results are saved separately under `docs/evidence/E0-T03/app-boundary/`.
The original unmanaged-thread probe and its failure evidence are unchanged.
This does not inject a failure into MainActivity itself, exercise future
business flows, or prove global framework/native/OEM crash privacy.
