## Task

Week 1 engineering foundation closeout, reviewed on 2026-09-30. Scope follows
`docs/development-plan.md` §20: E0-T01..08, initial E11-T04 CI, E9 kickoff records.
Week 2 Auth/Family/Consent business implementation is outside this delivery.

**Engineering gates: PASS on the verified CI head below.** Device acceptance and
live business-table seed replay remain NOT VERIFIED. This record corrects the
earlier local-only evidence; it does not claim all product capabilities are done.

## Changed

- Two Android Compose placeholders and shared modules, FastAPI health endpoint
  and independent worker, dev/test/demo profiles, redacted structured logs.
- PostgreSQL/pgvector and private MinIO development storage; initial 22-entity
  Alembic ordering/review/rollback plan, without creating business migrations.
- Frozen inventory tests for 74 REST operations and 9/11 client/server WSS types;
  eight deterministic Mock adapters and fictional seed fixtures.
- Local/CI verification runner, lint/contract/security checks, installed-wheel
  smoke, mandatory APK scanning and reproducible build evidence.
- Android setup explicitly requests `platform-tools` instead of the removed
  legacy `tools` package; setup failures still produce an outcome artifact.
- MinIO and mc use local source builds of the original upstream release commits
  because the original registries reject anonymous pulls. See
  [source versions, licenses and build requirements](../../infra/minio/README.md).
- Read-only device baseline collector and [kickoff record](week1-device-baseline.md).

## Tests

Verified remote head: `85d2fdd0bee68ad8b56fd6e173377ce96c7071b3`.
[GitHub Actions run 36539054178](https://github.com/Leisurua/niannian/actions/runs/36539054178)
completed successfully on 2026-09-29. All three job summaries and their downloaded
artifacts were inspected on 2026-09-30; this is not an inference from a green badge.

| Check | Result | Evidence |
| --- | --- | --- |
| Python lint and compilation | PASS | Backend job summary and logs |
| Backend pytest | 69 passed, 1 skipped; 0 failures/errors | `backend-tests.xml`: 70 cases; source-only APK scan skipped here |
| Profiles, live HTTP health and separate worker startup | PASS | Full pytest includes dev/test/demo process tests |
| Mock, REST/WSS, redaction, source/history privacy | PASS | Backend tests and frozen fixtures |
| Fictional demo fixture | PASS, 24 deterministic rows | `demo-seed.txt`; no live business-table replay claimed |
| Backend wheel and installed profiles/health outside checkout | PASS | `backend-wheel.txt`, `installed-wheel.txt` |
| Android `clean build` / lint | PASS | Android job and `android-build.txt` |
| Shared Android unit tests | 14 executions, 0 failures/errors/skips | Six debug/release JUnit XML reports |
| APK completeness and privacy | PASS, all 12 expected variants; 7 scan tests, no skips | `apk-privacy.txt`; required-APK mode checks both apps and all variants |
| Compose, pgvector and private object storage | PASS | `infra-smoke.txt`: healthy services, vector, private bucket and HTTP 403 anonymous denial |
| Evidence publication | PASS | Three artifact bundles, including two demo debug APKs |
| Device kickoff documentation | Prepared | Capability fields remain UNKNOWN; no device supplied |

Job evidence:

- [Backend](https://github.com/Leisurua/niannian/actions/runs/36539054178/job/109309831216),
  [artifact](https://github.com/Leisurua/niannian/actions/runs/36539054178/artifacts/11019333353).
- [Android](https://github.com/Leisurua/niannian/actions/runs/36539054178/job/109309830932),
  [artifact](https://github.com/Leisurua/niannian/actions/runs/36539054178/artifacts/11019294067).
- [Infrastructure](https://github.com/Leisurua/niannian/actions/runs/36539054178/job/109309831326),
  [artifact](https://github.com/Leisurua/niannian/actions/runs/36539054178/artifacts/11019114712).

Artifacts have seven-day retention and are scheduled to expire on 2026-10-06.
The measured results above remain in Git; binary artifacts are not committed.
Later documentation/review commits require their own CI before merge. Use the
current PR/run state for current-head readiness; this historical run cannot
certify a different commit.

## Decisions

- Preserve the frozen API/WSS, database, Consent and family/security contracts.
- Keep the first migration plan-only and the seed fixture-only until reviewed
  business tables exist. Do not invent a temporary schema to force acceptance.
- Retain Mock labels and fictional data. Eight adapter tests do not prove real
  ASR/LLM/TTS/Push/Avatar availability or any actual delivery/call connection.
- Treat the backend APK skip together with the independent, mandatory Android
  scan. It is no longer an unverified APK gate for the verified remote head.
- Local Windows lacking SDK/Docker does not invalidate the observed hosted build;
  neither hosted builds nor unit tests establish physical-device behavior.

## Contract Changes

None. No requirements, public DTOs/enums, DB schema, permission boundaries,
retention rules or accepted/proposed ADR statuses are changed.

## Not Verified

- ENV-001/002 actual named-device inventory and installed-app build identity.
- Android Logcat/system crash inspection and full business-flow privacy tests.
- Kiosk/Device Owner, ten reboot/exit cycles, BLE, camera, audio ownership,
  offline wake word and telephony on physical hardware.
- Real AI/Push/Weather providers, actual notification delivery and call outcomes.
- Seed replay/idempotency against a real migrated business database.

## Issues

The original Android SDK and MinIO pull failures are resolved in the verified
run. The remaining acceptance limits above are not fixed by CI and stay explicit.
An upstream Starlette/AnyIO deprecation warning remains; no runtime dependency
upgrade is included in this closeout.

## Next

Complete the PR review and current-head CI before merging this first-week change.
Once equipment is available, assign the device operator and execute the existing
matrix. Implement and review business migrations before database seed replay.
These follow-ups do not start Week 2 automatically.
