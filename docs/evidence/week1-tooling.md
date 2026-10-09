# Week 1 verification and CI tooling

## Scope and reproducibility

Only the Week 1 engineering foundation is covered: E0-T01..08 and the initial
E11-T04 CI baseline, plus E9 device kickoff records. E1 business features,
production migrations, provider integration and actual device Spikes are later work.

Run from the repository root with native CPython 3.12:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend/requirements.lock -r requirements-ci.txt
.venv\Scripts\python.exe scripts/verify_week1.py
```

On Linux/macOS use `.venv/bin/python` instead. Individual gates can be selected:

```text
python scripts/verify_week1.py --checks backend
python scripts/verify_week1.py --checks android
python scripts/verify_week1.py --checks infra
python scripts/verify_week1.py --checks device
```

Default gates are backend, Android and infrastructure. Hardware collection is
explicit because first-week CI is not a real-device environment. Reports are
written under ignored `artifacts/week1/`; use `--output` to retain separate runs.
Exit codes are 0 (selected checks passed), 1 (failure), 2 (missing prerequisite /
not verified). This does not mean all product or device acceptance has passed.

Backend checks run bounded Ruff rules (invalid Python, control flow and undefined
names), compilation, all current pytest suites, fictional seed validation, wheel
build and installed-wheel smoke. The wheel includes the three checked-in profiles
and excludes test and Alembic source; installation is tested outside the checkout.
This is not a full formatter/type-checker gate. Schema migrations remain plan-only.

Android requires JDK 17 and Android SDK 35; set `JAVA_HOME` and `ANDROID_HOME`.
Gradle `clean build` runs unit and Android lint checks and builds all 12 APKs.
The subsequent scan requires one APK for every app/flavor/build-type combination;
an absent APK cannot silently skip to green. `NIANNIAN_BUILD_ROOT` must be unset
for this gate because APK evidence is intentionally collected at standard paths.

Infrastructure requires Docker Engine/Compose and PowerShell 7 (`pwsh`). The
existing `infra/smoke.ps1` starts local services, initializes the private bucket,
checks pgvector and asserts that anonymous listing returns 403. It performs no
business migration. Local services remain available after the check; CI removes
only its disposable runner services and volumes in an always-run teardown.

## CI

`.github/workflows/week1.yml` has independent backend, Android and infrastructure
jobs on Ubuntu 24.04. It runs for push, pull request and manual dispatch, uses
read-only repository permission, no project secrets and pinned action commits.
Every job preserves check evidence for seven days, including failure evidence.
Android additionally uploads test/lint reports and the two demo debug APKs.
The backend/Android checkout includes history for the repository privacy scan.

Action revisions were resolved from official repository tags on 2026-09-29.
The hosted run for commit `85d2fdd` passed all three jobs; see
[the verified run](https://github.com/Leisurua/niannian/actions/runs/36539054178)
and [closeout evidence](week1.md). Every later commit must still pass its own
checks. Branch protection settings are not changed by this workflow.

## Development-only dependencies

These pinned tools implement the Week 1 lint and reproducible wheel gates. They
are not application runtime dependencies and are excluded from the backend wheel.

| Tool | Pin | License | Installed size observed on Windows | Reason / alternative / Mock path |
| --- | --- | --- | --- | --- |
| Ruff | 0.11.13 | MIT | 32.2 MiB | Fast lint baseline; compileall alone cannot find undefined names. Runs locally without providers |
| setuptools | 75.8.0 | MIT | 8.4 MiB | Existing build backend, now pinned for CI; isolated unpinned downloads were the alternative. No provider |
| wheel | 0.45.1 | MIT | 0.56 MiB | Reproducible local wheel build with the existing backend; alternative source-only execution cannot test packaging. No provider |

Sizes are the sum of installed distribution files on this host, not APK/runtime
size or a cross-platform guarantee. Existing runtime/test dependency pins are
unchanged. All application profiles used in these gates select Mock.

## Known boundaries

- OpenAPI inventory checks prove the 74 frozen operation definitions and 9/11 WSS
  message definitions; they do not claim those business operations are implemented.
- Mock adapter checks do not establish real ASR/LLM/TTS/Push/Avatar availability.
- Seed fixture checks do not apply the seed to non-existent business tables.
- Source/history pattern scanning is bounded by its known patterns. It does not
  replace Android Logcat or real-flow privacy testing.
- Device evidence remains in [the kickoff record](week1-device-baseline.md); the
  collector does not certify kiosk, BLE, camera, audio or telephony.
