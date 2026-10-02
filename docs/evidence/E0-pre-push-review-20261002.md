# E0 push and PR review — 2026-10-02

## Task

Review the existing E0 working-tree changes and related PR before pushing. No subsequent development task is started.

## Changed

- Based the review branch on `origin/main` at `690ee635171044058652e644797be71f95b0619f`, which contains merged [PR #1](https://github.com/Leisurua/niannian/pull/1).
- Preserved both sides of the checklist and infrastructure smoke conflicts: the merged CI/source-image build, the newer E0/device records, the configurable health timeout, and the real existing-object privacy/cleanup checks.
- Reviewed backend redacted failure handling and request identifiers, the owner-approved Android fatal execution boundary, fictional fixture/replay safety, evidence privacy, and retained historical failures. The two Demo screenshots were visually inspected; they contain static Demo/Mock labels and no personal content.
- Scoped staging excludes `.task-temp/`, virtual environments, build outputs, APKs, and local settings. The original working changes remain recoverable in the local `pre-push E0 acceptance snapshot 2026-10-02` stash.

## Tests

| Executed check | Result |
| --- | --- |
| Related PR #1 metadata, review submissions and inline threads | Already merged; no review submissions or inline threads returned. This is not a human approval claim. |
| PR #1 latest head `5bc8db2dd7cc376c2e03ed5f4d78d7b8174e4400` CI | PASS: [run 36730199543](https://github.com/Leisurua/niannian/actions/runs/36730199543), completed/success. This result belongs to PR #1, not this new branch. |
| `backend/.venv/Scripts/python.exe scripts/verify_week1.py --checks backend --output artifacts/pre-push-review/backend-pass` | PASS: lint, compile, 101 tests with no failures/errors/skips, 28-row fictional fixture check, wheel build and package installation/health outside the source tree in all three profiles. |
| Gradle 8.11.1/JDK 17, offline, `:core-telemetry:testDebugUnitTest :core-telemetry:testReleaseUnitTest :app-elder:build :app-family:build --rerun-tasks -q` | PASS: exit 0; lint and all variants; 8 JUnit reports, 32 executions, zero failures/errors/skips; 12 production APKs. |
| `NIANNIAN_REQUIRE_APKS=1`, `pytest tests/security` after rebuilding | PASS: 15 tests, including source/fixture/Git history and all 12 rebuilt APK scans. |
| Changed infrastructure smoke with cached upstream images at the same existing release versions | PASS: actual PostgreSQL/pgvector/MinIO, authenticated object existence, anonymous bucket listing and existing-object GET HTTP 403, cleanup; injected GET HTTP 200 prevents success and leaves no probe objects. |
| `git diff --check` and `git diff --cached --check` | PASS before final staging; repeated before committing. |

Local logs and generated reports are under ignored `artifacts/pre-push-review/`. The backend final command used workspace-local `TEMP`/`TMP` and `PYTEST_ADDOPTS` to avoid inaccessible pre-existing Windows temporary directories. Missing check tools were installed at the existing `requirements-ci.txt` versions. Old generated `backend/build` contents initially contaminated the wheel; cleaning that verified generated directory restored the expected package contents and the final unified check passed. These initial environment/artifact failures are not counted as PASS.

## Decisions

Push an ordinary review branch based on current main, preserving the original snapshot. Keep the approved option A scope and the old unmanaged-thread FAIL visible. Do not include the independent week-two branch or implement migrations/business flows. Open a draft PR so the new head receives its own hosted CI before merge consideration.

## Contract Changes

No new contract decision in this review. The submitted privacy/security wording records the existing owner-approved [E0-T03 option A](E0-T03-repair-proposal.md); it is not an unconditional crash-privacy guarantee. Requirements, API/WSS, DB schema/migrations, public states, Consent/family and retention rules are unchanged.

## Not Verified

- The complete production `infra/smoke.ps1` was attempted but failed at the unchanged source-image build: Docker Hub's `auth.docker.io` connection timed out fetching the pinned Go image. Source-image building is NOT VERIFIED on this host in this review. The passing cached-image probe explicitly omitted that build and used a temporary Compose override with the already installed upstream images; it is not a full source-build PASS.
- New-branch hosted CI is not established by the old PR's passing result; inspect the actual pushed head separately.
- No new device test or installation occurred in this review. Submitted device records remain dated observations of their recorded source/APK fingerprints. Full PRIV-002, unmanaged/framework/native/OEM crash privacy, hardware gates and business flows remain unverified.
- Live demo persistence/replay remains blocked by the absent reviewed business migration. Real providers, delivery, call connection and performance acceptance remain unverified.

## Issues

No additional blocking code/contract finding was identified in the reviewed changes. Local source-image build connectivity remains unresolved. The recorded unmanaged-thread privacy residual and full-business-flow gates remain open.

## Next

Inspect the new PR head's CI and retain its actual outcome. Business migrations, live seed replay, full application/device/privacy acceptance and merge are follow-up work, not authorized development tasks performed by this review.
