## Task

Complete the Week 1 scope in `docs/development-plan.md` §20: E0 engineering
foundation, backend/Compose/Android placeholders, CI baseline, Mock contracts and
device baseline kickoff. Date: 2026-09-29.

Baseline: `Leisurua/niannian`, commit
`616d972b8f59b0b94e5a94ae7b12c498455a8c23`, cloned from GitHub. Work is on local
branch `feat/week1-foundation`; no push, PR or hosted CI run has been performed.
Existing Web MVP files in the parent directory are a different project and are
not the basis for this delivery.

**Overall: implementation prepared; full Week 1 acceptance remains IN_PROGRESS.**
Missing build/infrastructure tools prevent current-host Android/Compose evidence.
Device kickoff records are complete; actual hardware tests are NOT_RUN by the
project owner's confirmation that no test device is available.

## Changed

- Reused existing E0-T01..08 implementations: two Android apps, FastAPI/worker,
  three environments, redacted logging, Compose/private storage, migration plan,
  REST/WSS inventories, eight deterministic Mock adapters and fictional seed.
- Added three CI jobs with pinned action revisions, read-only permissions,
  bounded runtimes and evidence upload: backend, Android, infrastructure.
- Added `scripts/verify_week1.py` for the same local/CI gates. Missing tools return
  NOT VERIFIED; independent executable checks still run.
- Added actual HTTP and separate worker-process startup tests in dev/test/demo.
- Fixed backend wheel contents: include the three environment profiles, exclude
  tests and Alembic source. Installed-wheel smoke runs outside the checkout.
- Made the Android gate require every one of the 12 expected APKs before scanning.
  Source-only tests may still explicitly skip APK scanning.
- Added a read-only, allowlisted ADB baseline collector and negative tests for
  absent/unauthorized/multiple devices, sensitive fields and failed commands.
- Established the [device baseline and E9 kickoff records](week1-device-baseline.md),
  including evidence paths, responsible roles, dependencies and ten reboot slots.
- Recorded [tool dependencies, licenses, sizes and commands](week1-tooling.md).

## Tests

Verified on this checkout using an isolated native CPython 3.12.14 environment.

| Check | Current result | Evidence |
| --- | --- | --- |
| Python lint and compile | PASS | `artifacts/week1/lint.txt`, `python-compile.txt` |
| Full pytest suites | **69 passed, 1 skipped; 0 failures/errors** | `artifacts/week1/backend-tests.xml` |
| REST and WSS frozen inventories | PASS within pytest; 74 REST, 9 client / 11 server messages | Existing contract fixtures |
| Mock adapter, profiles, redaction and source/history scan | PASS within pytest | Full pytest XML |
| dev/test/demo HTTP `/health` and worker startup | PASS, three profile tests | `backend/tests/test_startup.py` and pytest XML |
| Fictional fixture | PASS, 24 deterministic rows | `artifacts/week1/demo-seed.txt` |
| Backend wheel build | PASS | `artifacts/week1/backend-wheel.txt` |
| Installed wheel outside checkout | PASS, three profiles and health | `artifacts/week1/installed-wheel.txt` |
| CI structure/pinned action references and failure handling | PASS in local tooling tests | `tests/unit/test_week1_tools.py` |
| Android build, Android lint/unit, 12 APKs | NOT VERIFIED on this host | JDK 17 / Android SDK 35 unavailable |
| PostgreSQL/pgvector/MinIO live smoke | NOT VERIFIED on this host | Docker unavailable |
| Named physical device | NOT_RUN | `artifacts/week1/device-baseline.json`; no device / ADB |
| Hosted Actions | NOT VERIFIED | Workflow exists locally only |

The unified run selects backend, Android, infrastructure and device checks.
`artifacts/week1/summary.json` reports `NOT VERIFIED`, not a complete PASS.
The one skipped pytest is the APK content scan because no APKs were built on this
host. The Android gate treats missing APKs as a failure rather than a skip.

## Decisions

- Follow the remote FastAPI/Android repository and freeze. Do not continue the
  unrelated parent's Web MVP roadmap or begin E1/Week 2.
- Keep E0-T05 plan-only; do not create business migrations or apply seed data to
  a missing schema to force an artificial pass.
- Keep all providers Mock and all fixtures fictional; real capability acceptance
  requires separate evidence. No real provider keys are needed for this delivery.
- Added only development check/build tools; no new application dependency.
- Preserve historical E0 evidence as history; it does not certify this host.

## Contract Changes

None. Requirements, OpenAPI/WSS, database schemas/enums, consent/security boundaries,
and all accepted/proposed ADR statuses are unchanged.

## Not Verified

Current-host Android/JDK/SDK build and APK scan; Docker service smoke; hosted CI;
device inventory, installed-app build identity, Logcat, kiosk/BLE/camera/audio/
telephony and ten-reboot gate; real providers; seed replay against business tables.
No mock result is substituted for these checks.

## Issues

- This host has no configured JDK 17, SDK 35 or Docker. The new CI supplies those
  toolchains for verification after authorized publication; it has not run yet.
- No physical test device is available, as confirmed by the project owner.
  Device operator assignment is deferred until equipment arrives.
- Pytest reports one upstream Starlette/AnyIO deprecation warning. No dependency
  upgrade or frozen runtime pin change is included in this Week 1 task.

## Next

After JDK/SDK and Docker are available, run the Android and infrastructure gates;
after publishing the branch, retain the matching Actions run URL and artifacts.
When hardware arrives, complete the named-device record and run the matrix.
Week 2 Auth/Family/Consent implementation has not started.
