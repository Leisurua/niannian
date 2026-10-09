# E0-T03 redacted logging completion — 2026-10-02

## Task

Complete E0-T03's implemented foundation: structured redacted backend and Android logging, request/correlation identifiers, stable error codes, and source/fixture/Git/APK checks. Implementation, local verification and the approved application-owned device boundary: PASS. Full PRIV-002 and the combined privacy/release gate remain IN_PROGRESS.

## Changed

- Preserved the existing allowlisted logging, backend sink/shutdown protection and owner-approved Android option A execution boundary. Existing unrelated E0-T02/E0-T08 working-tree changes were left intact.
- Fixed backend unexpected-error logs losing request/correlation identifiers. Starlette invokes the outer error handler after request middleware resets its ContextVars; the handler now takes the already-validated identifier from request state. Response fields and HTTP behavior are unchanged.
- Applied the existing credential-pattern rejection to event names in both backend and Android telemetry. An uppercase credential-shaped string that otherwise satisfies the event syntax now emits `UNSTRUCTURED_LOG`.
- Added two backend regressions and one Android regression. The backend regressions failed before the fix: unexpected-error metadata lacked `request_id`, and a credential-shaped event was serialized unchanged. Two consecutive actual HTTP failures now retain their own identifiers and a fixed error code without exception content.

## Tests

| Executed check | Result |
| --- | --- |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests tests -q -o addopts='' -p no:cacheprovider --basetemp=.task-temp/e0-t03-20261002/pytest-final` | PASS: 59 tests; one existing Starlette/AnyIO deprecation warning |
| Installed Gradle 8.11.1, JDK 17, from `android/`: `--offline --no-daemon :core-telemetry:testDebugUnitTest :core-telemetry:testReleaseUnitTest :app-elder:assemble :app-family:assemble --rerun-tasks -q` | PASS: exit 0; 26 JUnit executions, zero failures/errors/skips; all 12 production APKs rebuilt |
| Final run after successful device probe cleanup: `backend/.venv/Scripts/python.exe -m pytest tests/security -q -o addopts='' -p no:cacheprovider --basetemp=.task-temp/e0-t03-20261002/security-after-device` | PASS: 15 tests, including final evidence/source/fixture/reachable Git blob and all 12 rebuilt production APK scans |
| Existing approved `check_app_boundary_logging` probe, `--install`, output overridden to the new date directory | PASS: exit 0; both normal startup/resume checks, eight fatal cases, installed APK hash matching, recovery and cleanup |
| `git -c safe.directory=D:/class_project diff --check` | PASS |

Android counts come from four newly generated JUnit XML reports: eight boundary cases plus five telemetry cases, each executed in debug and release. The fixed `LOGGING_FAILED` diagnostic printed when pytest's captured stream closed contains no original record or exception text; this is the existing safe sink-failure path.

The default Windows sandbox could not start (`helper_unknown_error: setup refresh had errors`). The commands above actually ran through reviewed escalated execution; this environment failure is not counted as a test result.

Device: Xiaomi model `2201123C`, Android 12/API 31, observed patch `2022-09-01`. Both installed `demoDebug` APKs match the rebuilt production APK hashes and use `provider=mock`. Each app passed main/worker, failed-sink and hostile-formatting crashes. Original PID-scoped Logcat buffers and instrumentation output were scanned in memory: all eight canary categories had zero hits; expected content-free fatal diagnostics and process termination were observed. Both apps recovered, test packages were uninstalled, and generated probe source/init/APKs were removed. Raw captures were not persisted; the [new device report](E0-T03/2026-10-02/app-boundary/device-check.json) contains counts, source fingerprints and APK hashes, with masked relevant excerpts alongside it. September evidence is unchanged.

To reproduce the device command, set JDK 17 and the existing Gradle cache as described above, then run the following code with `backend/.venv/Scripts/python.exe -u -c` from the repository root:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/device').resolve()))
import check_app_boundary_logging as probe
probe.OUTPUT = Path('docs/evidence/E0-T03/2026-10-02/app-boundary').resolve()
sys.argv = ['check_app_boundary_logging.py', '--install']
raise SystemExit(probe.main())
```

Initial device installation returned `INSTALL_FAILED_USER_RESTRICTED` before crash checks. That failed attempt was cleaned up and is not counted as PASS. The owner requested resending the prompt; the complete subsequent run produced the passing report above without changing ADB security settings or clearing app data/device logs.

## Decisions

Continue the [owner-approved option A](E0-T03-repair-proposal.md). Foundation task acceptance and the future full-business-flow gate are tracked separately. No analytics dashboard, business flow, platform-wide crash hook or subsequent development task was added. Pattern scans cover the tested formats; they do not prove absence of every possible secret or semantic private content.

## Contract Changes

None. No requirement, API/WSS, DB, public state, Consent/family boundary, permission, retention rule or security contract changed in this run.

## Not Verified

- The new credential-shaped event rejection is verified by Android unit tests; this device probe exercises the existing fatal boundary and Demo startup, not that exact malformed event input.
- The probe does not inject faults into MainActivity itself or prove a platform-wide crash privacy guarantee. Prior [2026-09-30 device results](E0-T03-repair.md) remain historical evidence.
- Full business flows are not implemented. Later Compose callbacks/recomposition, coroutine/executor roots, unmanaged/framework/native/ANR/OEM reports, actual resource exhaustion and untested device variants remain outside this run's proof.

## Issues

The original unmanaged-thread leak, E0-T03-LOG-001, remains a visible owner-approved residual risk. Its historical FAIL artifacts are retained. Do not close PRIV-002 or the combined privacy/release gate based on foundation task completion.

## Next

Future tasks must integrate and verify each actual application callback/worker when those flows exist. No subsequent development task was executed.
