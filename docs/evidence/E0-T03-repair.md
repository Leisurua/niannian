# E0-T03 approved application execution boundary repair

Date: 2026-09-30, Asia/Shanghai. Decision: repository owner approved [option A](E0-T03-repair-proposal.md) in this chat.

**Result: PASS for the implemented application execution boundary and current Demo startup flows. Full PRIV-002 and the combined checklist gate remain IN_PROGRESS, not PASS.** The historical unmanaged-thread leak remains a visible, approved residual risk; it was not fixed globally or relabelled as a passing test.

## Implementation

- `core-telemetry/AppExecutionBoundary` executes a synchronous root callback or worker body and replaces an escaping Throwable with a preallocated content-free Error. The original message, cause, suppressed exceptions, stack, and formatting methods are never inspected or retained in the replacement.
- Fatal thread names become `NianNian-fatal` before Android's early crash logger runs. The only app event is `APP_EXECUTION_FAILED` with fixed result/error-code fields. A failed telemetry sink cannot leak its exception or resume the failed work.
- If safe thread naming itself fails, the boundary terminates the process directly without forwarding the sensitive name to AndroidRuntime. The decision to invoke termination is unit-tested using a test terminator; this rare platform-failure path was not forced on-device.
- Both apps execute their existing synchronous `MainActivity.onCreate` body inside this boundary. Code inventory contains only these startup entry points, static Compose UI, core configuration helpers and telemetry. There are no implemented business/provider/device/worker callbacks to claim as covered.
- This wrapper protects work when it runs. Registering a future callback/Compose recomposition/coroutine inside it does not protect later execution. A caller must not catch the fatal Error and resume; executor/coroutine roots need their own reviewed integration when implemented.
- No Application default uncaught handler, hidden API hook, SDK downgrade, device policy change, crash endpoint, new business feature, raw audio retention, or provider change was introduced.

## Actual verification

| Check | Result |
| --- | --- |
| Offline Gradle `:core-telemetry:testDebugUnitTest :core-telemetry:testReleaseUnitTest :app-elder:assemble :app-family:assemble -q` | PASS; 8 boundary + 4 telemetry cases in each variant = 24 executions, 0 failure/error/skip; all 12 production APKs built |
| `backend/.venv/Scripts/python.exe -u tests/device/check_app_boundary_logging.py --install` | PASS, exit 0; both installed Demo APK hashes match local builds; normal cold-start/Home/resume and four fatal cases per app passed |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_logging.py tests/security -q -p no:cacheprovider --basetemp=.task-temp/e0-t03-approved/pytest-final` | PASS, 16 tests; after probe cleanup, backend logging/crash, source/fixture/reachable Git blob and final 12 production APK scans passed |
| `git -c safe.directory=D:/class_project diff --check` | PASS |

Boundary unit coverage: successful work, all eight sensitive categories, nested and suppressed errors, hostile Throwable accessors/formatting, failed sink, synthetic VM Error, failed thread preparation, immutable repeated failure diagnostics, and an actual worker's escaped fatal error. Synthetic VM errors do not simulate actual memory exhaustion.

The independent device probe executes throwing work through the **installed production boundary** on the Android main thread and a real worker thread; it does not call a sanitizer directly. Its four modes are main, worker, sink failure and hostile formatting. Inputs include nested/suppressed exceptions and a deliberately sensitive thread name. Each mode requires all of:

- Zero canary hits in original in-memory captures from every readable PID-scoped Logcat buffer and instrumentation output (eight categories: token/key/audio placeholder/transcript/phone/health/memory/URL).
- A fixed-name AndroidRuntime fatal record with the content-free Error, and exact expected structured telemetry (none for the deliberately failed sink).
- Instrumentation reporting process crash and no surviving app PID; unexpected callback return is a failure.

All eight cases met those checks. Normal startup/resume also passed on both apps. Probe APKs were removed, generated probe sources/APKs were removed, and both Demo apps were relaunched. Only masked relevant excerpts and non-sensitive counts/hashes are retained; raw captures stayed in memory. Device logs were not cleared. The initial install attempts were blocked with `INSTALL_FAILED_USER_RESTRICTED`; the owner requested a resend and subsequently allowed the successful installs. No ADB security setting was changed.

Device: Xiaomi model `2201123C`, Android 12/API 31, observed patch `2022-09-01`; this is a specific device observation, not a claim about all Android/OEM builds.

## Evidence

- [Machine-readable report, source fingerprints, APK hashes and cleanup](E0-T03/app-boundary/device-check.json).
- [Elder main-thread crash](E0-T03/app-boundary/elder-main-redacted.txt), [worker](E0-T03/app-boundary/elder-worker-redacted.txt), [sink failure](E0-T03/app-boundary/elder-sink_failure-redacted.txt), [hostile formatting](E0-T03/app-boundary/elder-hostile-redacted.txt).
- [Family main-thread crash](E0-T03/app-boundary/family-main-redacted.txt), [worker](E0-T03/app-boundary/family-worker-redacted.txt), [sink failure](E0-T03/app-boundary/family-sink_failure-redacted.txt), [hostile formatting](E0-T03/app-boundary/family-hostile-redacted.txt).
- [Elder normal startup](E0-T03/app-boundary/elder-normal-redacted.txt), [Family normal startup](E0-T03/app-boundary/family-normal-redacted.txt).
- Historical [unmanaged-thread failure evidence](E0-T03.md) and `check_device_logging.py` are retained unchanged apart from explanatory notes in the evidence document. That probe was not rerun in this repair.

## Contracts and remaining limits

The approved option A boundary is recorded in privacy-security §11, PRIV-002, and threat T-017. No API/WSS, database, permission, Consent/family, retention or public business state changed.

NOT VERIFIED: future full business flow (not implemented), fault injection into MainActivity itself (normal startup was exercised; fatal workload uses the shared boundary), later Compose callbacks/recomposition, coroutine/executor integration, actual resource exhaustion, forced failure of the OS thread-naming/termination calls, dev/qa/release variants on-device, framework/native/ANR/private OEM crash reports, real providers, delivery or other hardware gates. The current on-device proof applies to the reported Demo builds and exact probe cases only.

E0-T03-LOG-001 is mitigated for the implemented, tested application-owned boundaries. Arbitrary unmanaged exceptions still bypass them, as documented and approved. Full privacy/release acceptance must not be inferred from this scoped repair.
