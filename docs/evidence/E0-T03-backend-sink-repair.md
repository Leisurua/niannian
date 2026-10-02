# E0-T03 backend logging failure repair

Date: 2026-09-30, Asia/Shanghai. Scope: the configured backend logging handler and process/thread exception hooks. Existing Android option A changes and device evidence are preserved.

**Result: PASS for the repaired backend logging failure paths. Full PRIV-002 and the combined gate remain IN_PROGRESS.** This is an implementation fix under the existing prohibition on sensitive logs, not a contract change.

## Reproduced failure

When the configured output stream raised an exception, Python's default `StreamHandler.handleError` wrote the sink traceback and sometimes the original log message to stderr. A single synthetic original-content marker and a separate synthetic sink marker produced these counts before the repair; raw captures were kept only in memory:

| Context | Original marker hits | Sink marker hits | Raw traceback |
| --- | --- | --- | --- |
| Ordinary log | 1 | 1 | Yes |
| Uncaught process exception | 0 | 1 | Yes |
| Uncaught thread exception | 1 | 1 | Yes |

The first regression run also exposed an exit path: `logging.shutdown` called the broken stream's flush outside the handler's emit path, and Python's atexit diagnostics printed its exception. This was fixed before final verification.

## Change

- The configured `RedactedStreamHandler` never calls the default error reporter. Failed formatting, writes, and flushes produce only fixed JSON: event `LOGGING_FAILED`, error code `LOG_SINK_FAILED`, level `ERROR`, logger `nianian.runtime`.
- Flush is guarded independently so explicit/shutdown flush failures cannot escape into atexit diagnostics. Crash hooks also guard logger/filter failures before the handler is reached.
- The fallback never examines the original record or exception. If stderr also fails, the diagnostic is dropped without forwarding either exception. It does not recurse through logging.
- Process crashes still exit unsuccessfully; thread failures still end that thread. No retry, business recovery, API field, permission, retention, or Android boundary changed.

## Actual verification

| Check | Result |
| --- | --- |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests tests -q -o addopts='' -p no:cacheprovider --basetemp=.task-temp/e0-t03-sink-repair/pytest` after creating its parent directory | PASS, 57 tests; one existing Starlette/AnyIO deprecation warning |
| Existing Gradle 8.11.1 distribution, from `android/`: `--offline --no-daemon :core-telemetry:testDebugUnitTest :core-telemetry:testReleaseUnitTest --rerun-tasks -q`, JDK 17 | PASS, exit 0; 4 JUnit XML reports, 24 executions, 0 failures/errors/skips |
| Source/fixture, reachable Git blob, and existing production APK scans within the pytest run | PASS; 12 existing production APKs scanned, no APK rebuild needed for this backend-only change |
| `git -c safe.directory=D:/class_project diff --check` | PASS |

Four new security tests execute 24 isolated fault cases: write/flush/formatter failures with both `Exception` and `BaseException` across normal/process/thread contexts (18), failed crash-hook filters (2), failed primary plus fallback streams (3), and hostile message/argument formatting (1). Each checks all eight synthetic sensitive categories and absence of raw diagnostics. Healthy fallback output must match the exact fixed JSON; a failed fallback must emit nothing. Exit codes are checked, and hostile formatting methods must never be invoked. Only test source and this count-based report are retained, not raw captures.

Initial full-suite execution had five setup errors because the new basetemp parent did not exist; creating that directory allowed the complete 57-test rerun to pass. An initial Gradle wrapper attempt selected an empty cache and timed out; verification then used the already installed distribution offline, with actual tests forced to rerun. Neither failed attempt is counted as PASS.

## Limits

NOT VERIFIED in this repair: new on-device runs, future full business flows, arbitrary unmanaged Android/framework/native/OEM crash privacy, actual resource exhaustion, and third-party handlers or direct stdout/stderr writes outside the configured handler. Existing Android device results remain historical evidence from the [approved option A repair](E0-T03-repair.md), not a new device acceptance claim. A failure of both output streams necessarily loses the fixed diagnostic; no persisted fallback or new storage was introduced.

The original [unmanaged-thread FAIL](E0-T03.md) remains visible. No further development task was started.
