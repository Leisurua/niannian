# 念念（NianNian）Development Checklist

这是开发期间的门禁清单，不是新的设计文档。每项填写 `NOT_STARTED / IN_PROGRESS / PASS / FAIL / BLOCKED`，并附 evidence path。

## Batch 0 Gate

- [ ] `E0-T01` 两个 Android App、backend、worker、tests skeleton 可构建 — `IN_PROGRESS`; prior workspace evidence: Android clean build (exit 0), `backend/tests` (13 passed), Android unit test XML under `android/core-common/build/test-results/` and `android/core-telemetry/build/test-results/` (10 executions, 0 failures). Current rerun: Python suite 21 passed; Android clean build `NOT VERIFIED` because Android SDK is absent. `.git` is absent, so a clean Git checkout remains `NOT VERIFIED`.
- [x] Python/Gradle/Compose 版本和 dependency lock 已记录 — `PASS`; evidence: `README.md` (Python 3.12, Gradle 8.11.1, AGP 8.7.3, Kotlin 2.0.21, Compose BOM 2024.12.01); `backend/requirements.lock`; `android/app-elder/gradle.lockfile`, `android/app-family/gradle.lockfile`, `android/core-common/gradle.lockfile`, `android/core-telemetry/gradle.lockfile`.
- [ ] dev/test/demo 配置分离；demo 使用 fictional seed — `IN_PROGRESS`; evidence: Android `RuntimeConfigTest` (debug/release, 4 executions, 0 failures), backend config tests in `backend/tests` (included in 13 passed). Demo is configured for mock providers, but fictional seed belongs to E0-T08 and is not verified here.
- [x] PostgreSQL + pgvector + MinIO Compose health pass — `PASS`; evidence: `pwsh -NoProfile -File infra/smoke.ps1` (current rerun, exit 0); PostgreSQL and MinIO healthy, `vector` extension present, `nianian-private` bucket initialized privately, anonymous bucket listing denied with HTTP 403.
- [ ] OpenAPI 74 operations、WSS 9/11 message contract tests pass
- [ ] MockASR/LLM/Embedding/TTS/Avatar/WakeWord/Push/Weather 标记 `provider=mock`
- [ ] 日志、Git、APK、fixture secret scan pass — `IN_PROGRESS`; evidence: `python -m unittest discover -s tests/security -p "test_*.py" -v` (8 passed). Automated source and 12 existing APK scans include full-phone and secret patterns; structured fixture scans reject nonempty transcript/audio fields. `.git` is absent, and a full runtime/crash log inspection was not performed, so the combined gate is not marked PASS.
- [ ] Device baseline 表、Spike owner、evidence path 已建立

## Batch 1 Gate

- [ ] DEMO login/refresh/logout/logout-all 和 session revoke pass
- [ ] Family invitation token hash、过期、重放、双方确认 pass
- [ ] `FamilyRole` 使用 `ELDER/CHILD/CAREGIVER/EMERGENCY_CONTACT`
- [ ] Consent immutable grant/revoke and audit pass
- [ ] 跨家庭、缺 permission、缺 Consent 的 negative tests pass
- [ ] VS-01 Login → Family → Consent → Elder/Family Home smoke pass

## P0 Security Gate

- [ ] AUTH-001..007/015..017 pass
- [ ] CONS-001..008 pass
- [ ] RAG-001..007 pass
- [ ] FILE-001/007/008 and private bucket checks pass
- [ ] WS-001/002/006/008/009 pass
- [ ] AI-001..007 pass; LLM cannot execute privileged actions
- [ ] PRIV-001/002/003/005/007/008/009 pass
- [ ] EMG-002/003/004/005/010 pass; no false `CONNECTED`
- [ ] BLE-001/002 and DEV-001..005 pass or approved visible fallback
- [ ] DEL-001..003 pass; partial failure is observable

## Device Gate

- [ ] ENV-001/002 evidence names model, API, patch, app build
- [ ] Kiosk only reports ACTIVE after observed Device Owner/Lock Task
- [ ] BLE protocol and press semantics captured; duplicate guard verified
- [ ] Wake Word, ASR and Call have one audio owner
- [ ] Camera stores/uploads no frame or biometric template
- [ ] SIM/permission/no-answer outcomes map to observed Emergency states
- [ ] 10 reboot/exit or approved fallback documented

## Release / Demo Gate

- [ ] VS-01 through VS-04 run on a clean demo namespace
- [ ] No real personal data, provider secret or full phone in artifacts
- [ ] Mock/Real/DEMO labels visible where user could infer delivery/connection
- [ ] Memory revoke/delete is invisible before async cleanup completes
- [ ] Reminder `NO_RESPONSE` never displays “未服药”
- [ ] Weekly report says “交流观察线索” and includes missing data
- [ ] Known issues list names all NOT_RUN/BLOCKED tests
- [ ] Relevant docs/task status updated; no unreviewed contract change
