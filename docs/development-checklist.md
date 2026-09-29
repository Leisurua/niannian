# 念念（NianNian）Development Checklist

这是开发期间的门禁清单，不是新的设计文档。每项填写 `NOT_STARTED / IN_PROGRESS / PASS / FAIL / BLOCKED`，并附 evidence path。

## Week 1 current checkout — 2026-09-29

本次代码来自 GitHub `Leisurua/niannian` 的 `616d972`，与下方早期本地快照记录区分。完整结果见 [第一周交付记录](evidence/week1.md)。第一周总体为 `IN_PROGRESS`，不以历史 Android/Compose PASS 替代本机或当前提交的验证。

- [x] 后端、三环境、worker、Mock/REST/WSS contract、fixture、日志/源码/历史扫描：`PASS`；本次 pytest **69 passed / 1 skipped**。
- [x] 后端 wheel 构建及源码目录外安装运行：`PASS`；补齐三个配置文件，排除测试与 Alembic 源码。
- [x] 第一周 CI 与统一验证入口已实现，本地工具测试 `PASS`；[运行说明](evidence/week1-tooling.md)。
- [x] 设备基线表、Spike 责任角色与 evidence path 已建立：记录工作 `PASS`；[设备记录](evidence/week1-device-baseline.md)。用户确认暂无设备，真机操作人待设备到位后指定。
- [ ] 当前检出 Android 构建/单测/lint/APK 扫描：`BLOCKED`，缺 JDK 17 / Android SDK 35；pytest 的唯一跳过项为 APK 扫描。
- [ ] 当前检出 Compose 运行验收：`BLOCKED`，缺 Docker。
- [ ] GitHub Actions 实跑：`NOT_STARTED`，工作流尚未发布。
- [ ] 指定设备 ENV-001/002 与硬件验收：`BLOCKED`，无真机；不影响本周记录与 Mock 开发。

## Batch 0 Gate

- [x] `E0-T01` 两个 Android App、backend、worker、tests skeleton 可构建 — `PASS`; Android SDK 35 / Build Tools 35.0.0 已可用；原目录与本地快照 `ba719fd` 的干净检出均执行 `android/gradlew.bat --offline --no-daemon clean build` 成功。干净检出生成 12 个 APK，共享模块单元测试 XML 为 10 次执行、0 failure、0 error；`python -m pytest backend/tests tests -q` 为 21 passed（含 APK scan）；backend wheel 构建成功，worker 输出 `WORKER_READY`，Git 工作树干净。原始远端仓库地址与历史仍不可核实，本次干净检出来源是当前源码创建的本地快照。
- [x] Python/Gradle/Compose 版本和 dependency lock 已记录 — `PASS`; evidence: `README.md` (Python 3.12, Gradle 8.11.1, AGP 8.7.3, Kotlin 2.0.21, Compose BOM 2024.12.01); `backend/requirements.lock`; `android/app-elder/gradle.lockfile`, `android/app-family/gradle.lockfile`, `android/core-common/gradle.lockfile`, `android/core-telemetry/gradle.lockfile`.
- [ ] dev/test/demo 配置分离；demo 使用 fictional seed — `IN_PROGRESS`; evidence: [E0-T02 configuration and secret scan](evidence/E0-T02.md), [E0-T08 fictional seed](evidence/E0-T08.md). E0-T08 fixture smoke and artifact scan passed; live DB replay is NOT VERIFIED because business tables are not yet migrated.
- [x] PostgreSQL + pgvector + MinIO Compose health pass — `PASS`; evidence: `pwsh -NoProfile -File infra/smoke.ps1` (current rerun, exit 0); PostgreSQL and MinIO healthy, `vector` extension present, `nianian-private` bucket initialized privately, anonymous bucket listing denied with HTTP 403.
- [x] OpenAPI 74 operations、WSS 9/11 message contract tests pass — PASS; evidence: backend/tests/contract/operations.json, backend/tests/contract/websocket_messages.json, python -m pytest backend/tests/contract backend/tests/test_openapi_source.py -q -p no:cacheprovider.
- [x] MockASR/LLM/Embedding/TTS/Avatar/WakeWord/Push/Weather 标记 `provider=mock` — `PASS`; evidence: [E0-T07 adapter contracts and mocks](evidence/E0-T07.md), 15 adapter contract tests passed.
- [ ] 日志、Git、APK、fixture secret scan pass — `IN_PROGRESS`; evidence: [E0-T02](evidence/E0-T02.md), [E0-T03 structured logging and scans](evidence/E0-T03.md). Backend runtime/crash redaction, source/fixture/reachable Git blob scan, and 12 rebuilt APK scans passed. Android Logcat/system crash inspection and PRIV-002 full app flow remain NOT VERIFIED (no device/emulator).
- [x] Device baseline 表、Spike owner role、evidence path 已建立 — 记录工作 `PASS`; evidence: [Week 1 device kickoff](evidence/week1-device-baseline.md)。实际硬件测试与操作人指派仍待设备到位。

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
