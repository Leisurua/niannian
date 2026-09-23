# 念念（NianNian）需求追踪矩阵

| 项目 | 结论 |
| --- | --- |
| Review 类型 | Design Freeze Review |
| 需求来源 | [`nian-nian-requirements-design.md`](../nian-nian-requirements-design.md) v1.1 |
| 设计来源 | system / database / data dictionary / API / UI / AI / device / privacy-security / threat-model / ADR |
| 状态定义 | `READY` = P0 实现所需设计充分；`PARTIALLY_READY` = 可开发但有非阻塞决定或 Spike；`BLOCKED` = 缺失信息会阻止可靠实现 |
| 审计结论 | 所有 FR 均有 implementation target 与 verification target；无 FR 处于 `BLOCKED` |

## Source Of Truth

| 领域 | Source of Truth | 审计用法 |
| --- | --- | --- |
| Requirements | `nian-nian-requirements-design.md` | FR/NFR、范围、优先级和验收行为 |
| Architecture | `docs/system-design.md` + accepted ADR | 模块边界、进程和部署约束 |
| Persistent data | `docs/database-design.md` + `docs/data-dictionary.md` | 实体、字段、生命周期和索引 |
| Client/server contract | `docs/api-spec.md` + `docs/openapi.yaml` + permission matrix | REST/WSS、DTO、错误、权限 |
| User interaction | `docs/ui-interaction-spec.md` | Screen、状态、话术和可访问性 |
| AI behavior | `docs/ai-design.md` + `docs/ai-contracts.md` + evaluation | Adapter、RAG、候选、规则、降级 |
| Device integration | `docs/device-integration.md` + device test matrix + ADR-010~014 | Android 硬件边界、能力状态和 Spike |
| Security boundary | `docs/privacy-security.md` + threat model + security matrix + retention policy | Consent、最小披露、威胁控制和删除 |

## FR Traceability

| FR | Requirement | UI | API | DB | AI | Device | Security | Test | Demo | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FR-001 | 老人、子女、紧急联系人角色和隔离首页 | E-001/F-001/F-012/F-013 | auth, `/me`, family/member | User, FamilyMember, DeviceSession | role 不由 LLM 决定 | 设备会话绑定 | family + role + ownership | AUTH-016/017, UI role tests | 登录后双端首页差异 | PARTIALLY_READY |
| FR-002 | 邀请码/二维码绑定，双方确认 | E-003/F-013 | invitation create/accept/revoke | FamilyInvitation, FamilyMember, AuditLog | N/A | N/A | 一次性 token、同家庭校验 | family invitation/expiry/replay | 子女建家、老人确认 | READY |
| FR-003 | 首次完整 AI/隐私声明，新会话短提示 | E-003/E-002 | consent + conversation session | Consent, Conversation | identity prompt/state | local playback | consent version、不得冒充 | UI identity regression, AI G-001 | 首次说明与第二次会话 | READY |
| FR-004 | 分项授权、查看和撤回 | E-014/F-014 | consent list/create/revoke | Consent immutable history, AuditLog | context/notification re-check | camera/voice capability gating | revoke propagation | CONS-001..008 | 撤回照片/摘要后不可见 | READY |
| FR-005 | 导出、删除和异步结果 | E-014/F-017/F-018 | export/delete jobs | FileAsset, Memory, Conversation, AuditLog, retention fields | provider deletion contract | Room/DataStore wipe | invisible-first、partial failure | PRIV-009, DEL-001..006 | 提交删除并观察结果 | PARTIALLY_READY |
| FR-010 | 按钮、点击、语音唤醒 | E-001/E-002 | conversation REST/WSS | Conversation, DeviceBinding | WakeWordAdapter/intent | button/wake word | mic permission and ownership | AUD-001..007, WS-001 | 三种入口启动会话 | READY |
| FR-011 | ASR→编排→TTS→Avatar 实时链路 | E-002 | conversation + WSS 9/11 messages | Conversation/Message metadata | all adapters + orchestrator | audio focus/speaker | redaction, timeout, no fake answer | provider contract, UI state | Mock end-to-end conversation | PARTIALLY_READY |
| FR-012 | 打断、重复、放慢、音量/字体 | E-002/E-013 | WSS interrupt/repeat/slow_down | User accessibility settings | TTS controls | audio focus | no sensitive side effect on repeat | WSS action/idempotency, accessibility | 说“停一下/再说一遍” | READY |
| FR-013 | 低置信/未知事实诚实回答 | E-002/E-007/E-012 | conversation response source labels | Memory verification state | fact policy/citation guard | N/A | no hallucinated family fact | AI G-001/G-002/G-013 | 查询未知家庭事实 | READY |
| FR-014 | 主动陪伴时间窗、频率上限、免打扰 | E-001/F-009/F-010 | reminders + device settings | Reminder, User settings, worker task | ProactiveCompanionPolicy | local quiet/offline scheduler | consent and quiet-hour policy | reminder policy/timezone | 今日少打扰我 | READY |
| FR-015 | 新会话回顾本会话摘要 | E-011 | conversation summary endpoint | Conversation summary fields | summary prompt/redaction | local cache only if authorized | summary scope, no transcript fallback | summary/retention tests | 结束后查看摘要 | PARTIALLY_READY |
| FR-016 | 第三方/简化 Avatar，基础表情口型 | E-002 | state only; no provider CRUD | provider metadata | AvatarAdapter/MockAvatar | GPU/performance validation | no identity impersonation | avatar contract/device perf | TTS + Avatar demo | PARTIALLY_READY |
| FR-020 | 照片、人物、关系、地点、事件、偏好、忌讳 | E-006/E-007/F-005~F-007 | memory + file APIs | Memory, FileAsset, Chunk/Embedding internal | candidate normalization | camera not required for upload | scope, private object | memory/file contract | 上传照片与故事 | READY |
| FR-021 | 家属确认后写入，候选不可当事实 | F-008/E-012 | confirm/reject actions | Memory verification_status | MemoryCandidate→PENDING | N/A | LLM cannot confirm | RAG-002, AI-003 | 待确认后发布 | READY |
| FR-022 | 按需检索授权记忆并标注来源 | E-006/E-007/E-002 | memory list; RAG internal | Memory + active chunk/vector | hard-filter RAG, citation guard | N/A | same-family + Consent | RAG-001..007 | 老人问照片人物 | READY |
| FR-023 | 过期、纠错、撤回、删除 | E-007/E-012/F-006 | update/revoke/delete/feedback | Memory lifecycle + cleanup | invalidate retrieval | local cache invalidation | invisible-first | CONS/RAG/DEL suites | 删除后刷新不可检索 | READY |
| FR-030 | 日历、天气、用药、喝水、衣物提醒 | E-001/E-004/E-005/F-009/F-010 | reminder CRUD | Reminder, Execution | WeatherAdapter only | WorkManager/AlarmManager | medication scope | REM-001..012 | 创建并播报提醒 | READY |
| FR-031 | DONE/LATER/SKIPPED/NO_RESPONSE 反馈 | E-004/E-005/F-011 | feedback endpoint | ReminderExecution | no medical inference | offline pending sync | “未收到反馈” wording | REM-003..005 | 三种反馈和未响应 | READY |
| FR-032 | 轻量记忆游戏/回忆引导 | E-001/E-002 (no dedicated entity) | N/A/local conversation | InteractionMetric optional | prompt/content only | N/A | clearly not diagnosis | UI smoke/accessibility | 开始、退出、重试 | READY |
| FR-033 | 断网播报缓存提醒，不调用联网模型 | E-016/E-004 | reminder sync when online | Reminder/Execution source | offline fallback | Room + scheduler | no fake online result | NET-002/REM-002/012 | 断网仍播报 | PARTIALLY_READY |
| FR-040 | 识别往事、不适、情绪、思念线索 | E-008/F-002/F-003 | SignalEvent detail/actions | SignalEvent, Conversation refs | SignalCandidate pipeline | deterministic emergency entry | consent + no diagnosis | AI signal cases, SIG tests | 产生可解释关注提示 | READY |
| FR-041 | 规则化通知策略和升级 | F-002/F-003/F-014 | notification list/action | Notification/Attempt | policy only, no LLM permission | push/local fallback | minimal payload + consent | PRIV-001, notification contract | 应用内/推送 Mock | PARTIALLY_READY |
| FR-042 | 家属确认、忽略、联系、误报 | F-002/F-003 | ack/contact/false-positive/resolve | SignalEvent action + AuditLog | N/A | emergency contact capability | action authorization | signal action matrix | 子女联系/误报闭环 | READY |
| FR-043 | 子女周报和观察线索文案 | F-004 | report list/detail/generate | InteractionMetric, WeeklyReport | metrics first, guarded narrative | N/A | per-metric consent, no diagnosis | report/AI evaluation | 查看周报和缺失说明 | READY |
| FR-044 | 默认不发送完整敏感对话 | F-002/F-003/F-017 | summary/detail scope | Conversation summary, AuditLog | redaction | local transcript not shared | minimal disclosure | PRIV-001/002/007 | 动态只见摘要 | READY |
| FR-050 | 规则+AI 辅助识别诈骗 | E-009/F-003 | WSS warning + SignalEvent | SignalEvent rule/policy fields | deterministic RuleEngine + semantic indicators | N/A | LLM not sole verdict | SCAM-001..010, AI-005 | 转账+保密演示 | READY |
| FR-051 | 高风险阻止敏感动作 | E-009/E-010 | no transfer API; warning | SignalEvent/audit | blocked_action policy | local action gate | deny by deterministic rule | AI-003, EMG safety | 不点击/不转账 | READY |
| FR-052 | 按规则通知家属，建议核实 | F-002/F-003 | Notification + policy | Notification, Attempt | explainable reason | provider/local fallback | consent + generic copy | PRIV-001, notification | 家属收到最小摘要 | PARTIALLY_READY |
| FR-053 | 紧急按钮/语音/电话/事件推送 | E-010/F-015/F-016 | emergency contacts/calls | EmergencyContact, DeviceBinding, Notification | deterministic emergency policy | BLE/Telecom/Push | actual outcome only | EMG-001..012 | 触发并展示失败原因 | PARTIALLY_READY |
| FR-060 | Kiosk、开机自启、单应用锁定 | E-015/E-016/F-016 | device register/heartbeat | DeviceBinding, DeviceSession | N/A | Device Owner/LockTask/Boot | physical escape controls | KIO-001..009 | 指定平板重启演示 | PARTIALLY_READY |
| FR-061 | 离线唤醒和缓存提醒 | E-002/E-004/E-016 | device status + reminder sync | Reminder/DeviceBinding | WakeWordAdapter | audio ownership/local SDK | no fake answer | AUD-002/003, REM-002 | 断网唤醒 | PARTIALLY_READY |
| FR-062 | 人员接近唤醒，不做人脸识别 | E-015/E-016/F-016 | consent + device settings/status | Consent, DeviceBinding | detector only | CameraX/presence | no frames/biometrics | CAM-001..011 | 人靠近唤醒 | PARTIALLY_READY |
| FR-063 | BLE 实体按钮触发紧急联系 | E-010/F-016 | emergency call after local event | DeviceBinding, EmergencyContact, AuditLog | N/A | BLE GATT/protocol/reconnect | replay/dedupe/idempotency | BLE-001..014, EMG-003/004 | 按钮、断连、低电量 | PARTIALLY_READY |

**FR 计数：** `READY 20`，`PARTIALLY_READY 13`，`BLOCKED 0`。

## NFR Traceability

| NFR | Design | Verification | Status |
| --- | --- | --- | --- |
| Usability | UI 3-step core tasks、老人端大字/大按钮、语音入口 | usability tasks、5 名非技术用户、Elder smoke | READY |
| Accessibility | Compose tokens、TalkBack、对比度、字体/音量/语速、颜色不作为唯一信号 | accessibility test、screen reader/manual contrast | READY |
| Latency | FR target: wake <=1s, first audio <=4s, BLE local <=500ms | PERF-002/003/004 + backend p50/p95 benchmark | PARTIALLY_READY |
| Reliability | idempotency、outbox/worker、retry、state truth/fallback | integration retry/duplicate/failure suites | READY |
| Explainability | rule/policy/evidence summary、source labels、missing_data | Signal/Report/UI explanation tests | READY |
| Privacy | S0-S3、Consent、redaction、private bucket、invisible-first | security P0、provider checklist、delete evidence | PARTIALLY_READY |
| Maintainability | adapters、modular monolith、typed DTO、prompt/rule versions | architecture lint、contract tests、module boundary review | READY |
| Compatibility | 指定 Android 平板/BLE/OS 作为验收基线 | ENV/KIO/BLE/CAM/AUD/EMG matrix | PARTIALLY_READY |
| Offline degradation | cached reminders, time, contacts, local wake/BLE fallback | NET/REM/AUD/EMG offline transitions | PARTIALLY_READY |

## Coverage Cross-Checks

- **UI：** Elder `E-001`～`E-016`（16）和 Family `F-001`～`F-018`（18）均有 owner；E-012 为反馈 sheet，不能漏算。
- **API：** `openapi.yaml` 有 74 个 `operationId`；每个 operation 均归属 auth/family/consent/memory/file/reminder/conversation/signal/notification/report/emergency/device/audit/lifecycle 模块。WSS 为 9 client / 11 server message，不计入 REST operation。
- **DB：** 22 entities 均有 owner module；`MemoryChunk`、`MemoryEmbedding`、`NotificationAttempt`、`DeviceSession` 为内部/认证实现，不开放普通 CRUD。
- **AI：** Adapter、Orchestrator、RAG hard filter、MemoryCandidate、SignalCandidate、AITrace 和 evaluation 均有 task；Candidate 不需要新增表。
- **Device：** kiosk、BLE、wake word、CameraX、telephony、boot 均有 test matrix 和对应 Spike。
- **Security：** P0 threats T-001/002/003/004/005/006/007/008/009/010/017/019 均有控制和测试映射。
