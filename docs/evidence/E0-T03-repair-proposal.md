# E0-T03 Android crash privacy repair proposal

- Status: Option A approved by the repository owner in this chat ("批准"), 2026-09-30; option B not approved.
- Date: 2026-09-30 (Asia/Shanghai).
- Issue: E0-T03-LOG-001 / P0.
- Repair status: Option A implemented; [scoped verification PASS](E0-T03-repair.md). Historical unmanaged-thread FAIL evidence remains valid; full PRIV-002 remains IN_PROGRESS.

## Approved scope and review record

The owner approved the preceding request to implement option A and explicitly recognize system-crash residual risk. This authorizes application-owned synchronous execution boundaries and their tests, with these exact interpretations recorded in privacy-security, security-test-matrix and threat-model:

- App-owned root callback/worker bodies must prevent sensitive Throwables from escaping: no original message, cause, suppressed exceptions or sensitive thread name may reach runtime crash logging through those bodies.
- The boundary must fail fatally with a content-free error, not resume after an unexpected failure. It must not inspect or format the original Throwable, and a telemetry-sink failure must not expose a second Throwable.
- Registering asynchronous work inside a boundary does not protect its later execution. Each later app-owned callback/worker must execute inside its own boundary. Current apps contain only synchronous onCreate startup code and static Compose content; there are no implemented business/provider/device/worker callbacks to claim as covered.
- Unmanaged threads and framework/native/ANR/OEM crash paths remain outside this application-level guarantee. Existing raw-exception evidence remains FAIL and is retained as a visible, owner-approved residual risk, not rewritten as PASS.
- PRIV-002's full-business-flow acceptance remains NOT VERIFIED until those flows exist and are exercised. Approval is not a claim of platform-wide crash privacy, a production release approval, or permission to modify hidden-API policy/SDK targets.

No API, DB, permission, Consent/family, data-retention, provider, or user-visible state change is authorized by this decision.

## Verified cause

The existing [device evidence](E0-T03.md) reports eight synthetic sensitive categories in both Demo apps' AndroidRuntime output. This repair investigation did not rerun that device experiment or replace its artifacts.

Both app build files target SDK 35. Android 12 AOSP dispatches an uncaught exception to the runtime pre-handler **before** the thread/default exception handler. The runtime LoggingHandler passes the original Throwable to the crash log, including its message and nested causes. An Application-installed default UncaughtExceptionHandler can sanitize later reporting, but cannot remove the earlier disclosure. Killing the process in that handler is also too late.

The Android 12 hidden-API flags classify Thread.setUncaughtExceptionPreHandler as max-target-o (API 26); RuntimeHooks.setUncaughtExceptionPreHandler is blocked. Neither is an available supported replacement hook for these target-SDK-35 apps. No hidden-API exemption, target-SDK downgrade, device-policy modification, log clearing, or masking of the original scan results was performed.

Official sources inspected on 2026-09-30:

- [Android 12 Thread.java](https://android.googlesource.com/platform/libcore/+/android-12.0.0_r1/ojluni/src/main/java/java/lang/Thread.java): dispatchUncaughtException and setUncaughtExceptionPreHandler.
- [Android 12 RuntimeInit.java](https://android.googlesource.com/platform/frameworks/base/+/android-12.0.0_r1/core/java/com/android/internal/os/RuntimeInit.java): LoggingHandler, logUncaught, KillApplicationHandler and ensureLogging.
- [Android 12 hiddenapi-flags.csv](https://android.googlesource.com/platform/prebuilts/runtime/+/android-12.0.0_r1/appcompat/hiddenapi-flags.csv): the two setter restrictions above.

These sources explain why the conventional default-handler patch cannot fix the recorded failure. They are not a new execution result on the Xiaomi OEM build, nor proof that every possible platform-specific mitigation is unavailable.

## Decision requested

The frozen privacy requirements cover crash logs; the current probe injects arbitrary sensitive Throwables directly into an unmanaged thread. A supported application-level logger cannot intercept that runtime pre-handler. Select and review an explicit boundary before implementation:

| Option | Implementation and acceptance impact |
| --- | --- |
| A: Prevent sensitive exceptions at app-owned execution boundaries (recommended for the course project) | Audit input/provider/device/worker boundaries; catch failures before they escape and translate them to content-free errors without retaining the original cause, suppressed exceptions or sensitive thread names. Exercise real execution paths, nested/suppressed causes and fatal termination behavior on both apps. An optional default handler is defense in depth only. Arbitrary unmanaged framework/native/OEM crashes remain an explicit residual risk requiring security review; this is not equivalent to passing the existing arbitrary-Throwable probe. |
| B: Retain an unconditional guarantee for arbitrary process/OS crash output | First validate an OS/OEM-supported mechanism and deployment model that protects both early logging and later crash reports on the named device. This would require an architecture/device/security proposal and supporting evidence; no such mechanism is established here. |

Option A must not be used to silently narrow PRIV-002 or to mark the current failing probe PASS. Reviewers must decide whether its residual risk is acceptable and approve exact requirement/test wording before any change to those contracts. If neither option is approved and demonstrated, retain FAIL and the release blocker.

## Implementation plan after review

1. Record the accepted boundary, responsible reviewer, and exact affected contract/test changes. This document alone grants no implementation approval.
2. Implement only the reviewed E0-T03 boundary; do not add business flows or advance to another development task.
3. Add regression coverage for all eight synthetic categories, nested/suppressed failures, hostile exception formatting, main/worker execution, and logging failures. Confirm that a fatal path terminates rather than silently resuming inconsistent application state.
4. Keep the original unmanaged-thread reproduction and its historical FAIL evidence. Any additional app-boundary probe must be separately labelled and must not replace the old probe with a call directly to a sanitizer.
5. Rebuild both apps, verify installed APK hashes, rerun applicable unit/security/device checks, and retain only masked evidence. Full business flows, OEM reports and untested variants remain NOT VERIFIED until actually exercised.

## Initial investigation work and limits (before approval)

Only this proposal and a linked investigation note were added. No production code, manifest, SDK target, probe acceptance logic, frozen requirement, API, database or security contract was changed. Existing E0-T02 work and E0-T03 failure artifacts were preserved.

Production tests and the device probe were NOT RUN in this investigation because no executable code was changed. Source inspection is not a test PASS and does not close E0-T03-LOG-001.

After owner approval, the boundary, app integration, independent device probe and approved contract clarifications were implemented. Current results and limits are recorded in [E0-T03 repair evidence](E0-T03-repair.md). The initial investigation paragraphs above are historical, not the final implementation status.
