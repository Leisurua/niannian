# 念念（NianNian）Design Freeze Review

## 1. Review Scope

本次审计是文档级 `Design Freeze Review`，不是新一轮 Architecture Design。检查目标是：Requirements → Traceability → Consistency → Gap → Decision Classification → ADR Review → Development Breakdown → P0 Readiness。未修改任何既有需求、OpenAPI、数据库、UI、AI、Device 或 Security 文档。

## 2. Documents Reviewed

完整阅读并交叉检查：

- `nian-nian-requirements-design.md`
- `docs/system-design.md`、`database-design.md`、`data-dictionary.md`
- `docs/ui-interaction-spec.md`
- `docs/api-spec.md`、`api-permission-matrix.md`、`openapi.yaml`
- `docs/ai-design.md`、`ai-contracts.md`、`ai-evaluation.md`
- `docs/scam-signal-policy.md`
- `docs/device-integration.md`、`device-test-matrix.md`
- `docs/privacy-security.md`、`threat-model.md`、`security-test-matrix.md`、`data-retention-policy.md`
- `docs/adr/ADR-001`～`ADR-014`

## 3. Architecture Summary

冻结候选架构为：两个原生 Kotlin + Compose Android App（`app-elder`、`app-family`）和共享多 Module；FastAPI/Pydantic/SQLAlchemy/Alembic 模块化单体，API 与独立 worker 进程；PostgreSQL + pgvector；MinIO/S3-compatible 私有对象存储；REST + conversation WSS；AI/Weather/Push/Avatar/WakeWord Adapter + Mock；Consent + family-scoped authorization；设备能力通过本地 adapter 暴露。

逻辑模块为 `auth`、`family`、`consent`、`memory`、`conversation`、`reminder`、`safety`、`signal`、`notification`、`report`、`emergency`、`device`、`audit`、`integrations`。不拆微服务、不引入独立向量库、Kafka、Redis/Celery 或自研模型。

## 4. Requirement Coverage

完整矩阵见 [`requirements-traceability.md`](requirements-traceability.md)。

| Coverage | Count | Evidence |
| --- | ---: | --- |
| `READY` | 20 | UI/API/DB/AI/Device/Security/Test target 已存在 |
| `PARTIALLY_READY` | 13 | 可使用 Mock/default 开发，但依赖 D1/D2/D3 决定或真机证据 |
| `BLOCKED` | 0 | 没有 FR 因缺少信息而无法可靠开始 |

所有 33 个实际 FR（001～005、010～016、020～023、030～033、040～044、050～053、060～063）都有 implementation target 和 verification target。`FR-032` 明确为 `No dedicated persistence`，不是 Missing。

## 5. NFR Coverage

| NFR | Design evidence | Test evidence | Status |
| --- | --- | --- | --- |
| Usability | 3-step core task、Elder tokens、voice fallback | usability tasks + 5 users | READY |
| Accessibility | TalkBack、字号/对比度/音量/语速、非颜色状态 | manual + accessibility test | READY |
| Latency | wake/first-audio/BLE targets | PERF p50/p95 suites not executed | PARTIALLY_READY |
| Reliability | idempotency、worker lease、fallback、truthful states | retry/duplicate/failure suites | READY |
| Explainability | rule/policy/evidence/source labels、missing data | signal/report/UI tests | READY |
| Privacy | S0-S3、Consent、redaction、private bucket、delete propagation | P0 security + deletion matrix | PARTIALLY_READY |
| Maintainability | adapters、module boundaries、versioned prompts/rules | contract/module-boundary tests | READY |
| Compatibility | named tablet/BLE/OS acceptance boundary | device matrix, currently NOT_RUN | PARTIALLY_READY |
| Offline degradation | cached reminders/contact/local wake/BLE fallback | offline transition tests | PARTIALLY_READY |

## 6. Consistency Findings

| Pair | Result | Finding / required handling |
| --- | --- | --- |
| Requirements ↔ UI | Aligned | 33 FR map to E-001~016/F-001~018; FR-032 has no dedicated page by design |
| Requirements ↔ API | Aligned with open auth/provider decisions | FR-060~063 use local capability plus status APIs; no fake `/button-event` endpoint |
| Requirements ↔ DB | Aligned | 22 entities cover persistent needs; candidate/game state intentionally transient |
| Requirements ↔ AI | Aligned | LLM proposes; application decides; unknown facts and safety boundaries preserved |
| Requirements ↔ Device | Partially aligned | Required hardware is P0, but model/SIM/BLE protocol/OS evidence absent |
| Requirements ↔ Security | Aligned baseline | Consent, minimal notification, no diagnosis and no impersonation are repeated consistently |
| UI ↔ API | Aligned with capability fallback | Every Screen has REST/WSS/local source; provider failure remains visible |
| API ↔ DB | Aligned | Public DTOs do not expose Chunk/Embedding/Attempt/Session as CRUD |
| API ↔ Security | Aligned with implementation gates | OpenAPI `allOf` update DTOs require server-side whitelist; device proof must be implemented |
| AI ↔ DB | Aligned | Candidate is transient; confirmed Memory/Signal/Metric/Report use existing tables |
| AI ↔ API/WSS | Aligned | 9 client and 11 server WSS messages carry ASR/state/warning/signal/reply/TTS state |
| AI ↔ Security | Aligned | redaction, citation validation, no tool authority and provider gate are explicit |
| Device ↔ UI | Aligned | capability states map to human-readable `UNKNOWN/DEGRADED/CONFIG_ERROR` paths |
| Device ↔ API | Aligned | register/heartbeat/emergency contracts do not claim local hardware success |
| Device ↔ AI | Aligned | wake word is local trigger, not identity; audio ownership is explicit |
| Device ↔ Security | Partially ready | Keystore, device proof, kiosk escape, BLE replay and local wipe still require tests |

### Material Conflicts

1. **Role naming:** Requirements uses “子女/家属/FAMILY_MEMBER” as product language; DB/API canonical wire enum is `CHILD`. Resolution: wire uses `CHILD`; UI may say “家属/子女”; do not add a second enum.
2. **Conversation state granularity:** UI/device have local `WAKING`, `TRANSCRIBING`, `INTERRUPTED`, `FAILED`; API exposes stable backend `IDLE/LISTENING/THINKING/SPEAKING/WARNING/OFFLINE/ERROR`. Resolution: local states derive from the stable API/WSS state and must not become a new public enum without review.
3. **Capability vs binding status:** Device local `SUPPORTED/DEGRADED/PERMISSION_REQUIRED` and server `kiosk/wakeword/ble/camera/phone` status are different layers. Resolution: keep local capability detail and map only observed server fields; never treat `ACTIVE` binding as hardware support.
4. **EmergencyCase naming:** System/device/security prose uses `EmergencyCase`, while public API/OpenAPI uses `EmergencyCall` and the 22-table database design has no dedicated `EmergencyCase` table. Resolution: implementation task uses an internal domain case/aggregate backed by existing emergency call/Signal/Notification records; adding a persistent table requires an ADR/DB review.
5. **Retention:** multiple documents intentionally leave raw audio, transcript, summary, AuditLog, backup and provider retention as TBD. Resolution: privacy-preserving defaults are frozen for development; final durations remain D1/D3 decisions.
6. **Provider availability:** ADR-008/009 and device telephony remain Proposed. Resolution: MockPush/MockAvatar/Mock call state are valid demo providers; no real delivery/Avatar/connected claim until Spike evidence.

## 7. Enum Findings

| Canonical Enum | Defined In | Finding |
| --- | --- | --- |
| FamilyRole = `ELDER`, `CHILD`, `CAREGIVER`, `EMERGENCY_CONTACT` | data dictionary, DB, API/OpenAPI, permission matrix | `FAMILY_MEMBER` remains UI/product alias only |
| ConsentScope = `VOICE`, `PORTRAIT`, `FAMILY_MEMORY`, `HEALTH_MEDICATION`, `CONVERSATION_SUMMARY`, `CAMERA_PROXIMITY`, `NOTIFICATION_TO_FAMILY` | DB, API, UI, security | Aligned |
| MemoryType = `PERSON`, `RELATIONSHIP`, `EVENT`, `PLACE`, `PREFERENCE`, `TABOO`, `PHOTO` | DB, API, AI | Aligned |
| MemoryStatus = `PENDING`, `CONFIRMED`, `REJECTED`, `REVOKED`, `DELETED` | Requirements, DB, API, AI | Aligned; only CONFIRMED is factual/RAG eligible |
| ReminderFeedback = `PENDING`, `DONE`, `LATER`, `SKIPPED`, `NO_RESPONSE` | DB/API/UI | Client submits first three; worker owns NO_RESPONSE |
| SignalType = `PHYSICAL_DISCOMFORT`, `EMOTION_EXPRESSION`, `IMPORTANT_MEMORY`, `MISS_FAMILY`, `SCAM_RISK`, `EMERGENCY` | DB/API/AI/Scam | Aligned |
| SignalSeverity = `L0`…`L4` | Requirements, DB, API, Scam | UI uses human copy, not L-levels |
| SignalStatus = `DETECTED`, `VALIDATED`, `NOTIFIED`, `ACKNOWLEDGED`, `CONTACTED`, `FALSE_POSITIVE`, `RESOLVED`, `WITHHELD`, `NOTIFICATION_FAILED` | DB/API/AI | Extended state set is deliberate and documented |
| NotificationStatus = `PENDING`, `QUEUED`, `SENT`, `DELIVERED`, `READ`, `FAILED`, `CANCELLED` | DB/API | Aligned; delivery is not event truth |
| EmergencyStatus = `INITIATED`, `CONNECTING`, `CONNECTED`, `NO_ANSWER`, `FAILED`, `CANCELLED` | API/OpenAPI/UI/device | `CONNECTED` only from observed outcome |
| DeviceCapabilityState = `SUPPORTED`, `UNSUPPORTED`, `PERMISSION_REQUIRED`, `DISABLED`, `DEGRADED`, `UNKNOWN` | device integration | Local adapter enum; not interchangeable with server status |
| AvatarState = `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `WARNING`, `OFFLINE`, `ERROR` | UI, API, AI contracts | Aligned public state |

No third enum should be introduced for these concepts. New local-only detail must be explicitly scoped and mapped.

## 8. State Machine Findings

| Domain | Canonical lifecycle | Finding / invariant |
| --- | --- | --- |
| Memory | `PENDING → CONFIRMED/REJECTED`; `CONFIRMED → REVOKED/DELETED`; expired is not retrievable | Pending/rejected/revoked/deleted never facts or RAG |
| Reminder | rule active → occurrence `PENDING → DONE/LATER/SKIPPED/NO_RESPONSE` | NO_RESPONSE means no feedback, never not-taken |
| SignalEvent | `DETECTED → VALIDATED → NOTIFIED → ACKNOWLEDGED/CONTACTED/FALSE_POSITIVE → RESOLVED`; `WITHHELD` or `NOTIFICATION_FAILED` side paths | Notification failure does not change event truth |
| Emergency | `INITIATED → CONNECTING → CONNECTED/NO_ANSWER/FAILED/CANCELLED` | Intent launched is not connected; idempotent source/case required |
| Device | local `BOOTING → INITIALIZING → READY → ACTIVE/DEGRADED/RECOVERY`; server binding `ACTIVE/UNBOUND/LOST/DISABLED` | Do not merge app lifecycle with binding status |
| Conversation | local `Idle/Wake/Listening/Processing/Speaking/Warning/Offline/Error`; public backend stable states | Local detail maps to stable contract |

State-machine gap is not a design blocker; it is an implementation rule and test task.

## 9. Security Findings

| Security control | Classification | Implementation/Test mapping |
| --- | --- | --- |
| Cross-family authorization predicates | IMPLEMENTATION_REQUIREMENT | every service/query; AUTH-001..007/016/017 |
| Consent revoke invisible-first propagation | IMPLEMENTATION_REQUIREMENT | consent service + cache/vector/file/export/notification recheck; CONS-001..008 |
| Pending/revoked Memory excluded from RAG | IMPLEMENTATION_REQUIREMENT | memory repository/RAG filter; RAG-001..007 |
| Access/refresh rotation, TTL, reuse response | OPEN_DECISION + IMPLEMENTATION_REQUIREMENT | D-001, Auth service; AUTH-008..013 |
| Sensitive notification minimal payload | IMPLEMENTATION_REQUIREMENT | Notification DTO/provider; PRIV-001 |
| Prompt injection/untrusted Memory boundary | IMPLEMENTATION_REQUIREMENT | AI context builder/citation validator; AI-001..007 |
| Private bucket, MIME/checksum/quarantine, Signed URL | IMPLEMENTATION_REQUIREMENT | File service; FILE-001..008 |
| Raw audio default no persistence | CONFIGURATION + TEST_REQUIREMENT | D-002, PRIV-005, DEL-002 |
| Provider no-train/retention/region gate | OPEN_DECISION + TEST_REQUIREMENT | D-003, AI-006/007 |
| BLE replay/dedup and Emergency idempotency | IMPLEMENTATION_REQUIREMENT + TEST_REQUIREMENT | device coordinator; BLE/EMG tests |
| Keystore-backed token/local cache wipe | IMPLEMENTATION_REQUIREMENT | D-016, DEV-001/002/007 |
| Secret scanning and redacted logs | TEST_REQUIREMENT | PRIV-002/003/008 |
| Audit append-only and read auditing | IMPLEMENTATION_REQUIREMENT | audit service; PRIV-007 |
| Backup/AuditLog retention | OPEN_DECISION + CONFIGURATION | D-011; DEL-005/006 |

没有需要新增架构文档的 Security Agent change。Runtime Consent 检查、DTO 白名单、redaction、重试、日志脱敏和测试均属于实现/测试要求。

## 10. Open Decisions

详见 [`open-decisions.md`](open-decisions.md)。D0 为 0；D1/D2/D3 均有开发默认值或局部 Feature gate。

## 11. ADR Status

| ADR | Topic | Current Status | Evidence | Recommended Status |
| --- | --- | --- | --- | --- |
| ADR-001 | Android Kotlin/Compose, two apps | Accepted | system §4; UI inventories; device boundary | Accepted |
| ADR-002 | FastAPI/Pydantic/SQLAlchemy/Alembic | Accepted | system §3/6 | Accepted |
| ADR-003 | PostgreSQL + pgvector | Accepted | DB/RAG hard filters | Accepted |
| ADR-004 | Modular monolith | Accepted | module ownership and no private cross-import | Accepted |
| ADR-005 | Adapter + provider + Mock | Accepted | AI contracts and failure matrix | Accepted |
| ADR-006 | MinIO/S3-compatible storage | Accepted | private bucket + Signed URL lifecycle | Accepted |
| ADR-007 | worker + APScheduler + PostgreSQL task/outbox | Accepted | reminder/delete/notification task semantics | Accepted |
| ADR-008 | Push provider | Proposed | FCM/network/fee/retention unresolved; MockPush baseline | Proposed until provider Spike |
| ADR-009 | Avatar | Proposed | SDK/license/performance unresolved; MockAvatar baseline | Proposed until device Spike |
| ADR-010 | Kiosk/Device Owner | Proposed | target strategy clear; hardware/OEM evidence absent | Proposed until KIO gate |
| ADR-011 | BLE button | Proposed | protocol and press semantics TBD | Proposed until BLE gate |
| ADR-012 | CameraX presence | Proposed | detector/power/false trigger unresolved | Proposed until CAM gate |
| ADR-013 | Offline wake word | Proposed | SDK/audio ownership/latency unresolved | Proposed until AUD gate |
| ADR-014 | Emergency telephony | Proposed | SIM/Telecom/permission/outcome unresolved | Proposed until EMG gate |

**ADR summary:** Accepted 7, Proposed 7. 只有不依赖硬件/provider 证据的 7 个 ADR 已达到 Accepted；不为“冻结”强制接受 ADR-008～014。

## 12. Architecture Freeze

### Frozen

- Native Kotlin + Jetpack Compose, two Android apps plus shared modules.
- FastAPI Python modular monolith with API/worker process boundary.
- PostgreSQL + pgvector; no separate vector DB.
- MinIO/S3-compatible private object storage and Signed URL access.
- REST for CRUD and WSS for conversation state/audio contract.
- AI Adapter + Orchestrator; deterministic safety/Consent before and after LLM; Mock providers first.
- Confirmed + authorized + same-family + not-deleted RAG invariant.
- FamilyMember role + Consent scope + ownership authorization.
- Minimal notification, append-only AuditLog, no raw audio by default, no diagnosis/impersonation.

### Not Frozen

- Login credential provider/TTL values (D-001).
- Real ASR/LLM/TTS/Embedding/Push/Avatar/WakeWord providers and their retention (D-003~005/009).
- Tablet model/OEM policy, BLE protocol, CameraX detector, Telephony path (D-006~010).
- Final retention durations, backup/legal hold, thresholds (D-011/013).

## 13. Allowed Implementation Freedom

Minor implementation decisions may be made inside the frozen boundary: class/file names, repository query composition, DTO mapper placement, test fixture IDs, worker retry backoff within configured limits, Compose component internals, local cache key format, prompt wording that preserves schema/safety, and conservative threshold defaults. These decisions must not change public enums, API/DB fields, Consent scope, security boundary, or user-visible truth states.

## 14. Design Change Policy

| Change type | Examples | Required action |
| --- | --- | --- |
| Minor | layout spacing, class split, repository helper, mock fixture | task review + relevant tests |
| Implementation Decision | timeout/backoff/config value, prompt copy, local cache detail | record in task/CHANGELOG; no new architecture doc |
| Design Change | API field/operation, DB entity/constraint, Consent scope, family boundary, cross-module behavior, requirement/enum/state change | stop affected task, write proposal/ADR, review before coding |
| Security Boundary Change | raw audio/provider data, role/Consent bypass, external disclosure, identity/biometric behavior | security review + threat/test matrix update |

Coding Agent must stop and report a Contract conflict; it may not silently “pick the most convenient” document.

## 15. Development Readiness

### Result: `READY_WITH_NON_BLOCKING_DECISIONS`

Evidence:

- 33/33 FR traced; 20 READY, 13 PARTIALLY_READY, 0 BLOCKED.
- 74 REST operations have module ownership; 16 Elder + 18 Family screens have UI owners.
- 22 DB entities have owners; internal entities are not exposed as CRUD.
- AI adapter/RAG/signal contracts and Mock strategy exist.
- Security P0 threats have controls and test IDs.
- Hardware/provider uncertainty is isolated behind adapters, fallback states and Spike gates.

### Can Start Now

Batch 0 foundation, two Android skeletons, backend skeleton, configuration/logging, PostgreSQL/pgvector/MinIO/worker, OpenAPI contract tests, Mock adapters, seed fixtures, auth interfaces/DEMO login, Family/Consent services and security test fixtures.

### Must Wait for Feature Gate

Real login credential/provider integration (D-001), real S2/S3 AI provider (D-003), polished Avatar (D-005), kiosk/boot (D-006), BLE (D-007), CameraX (D-008), offline wake word (D-009), local telephony (D-010), final retention with non-fictional data (D-011).

## 16. Risks

| Risk | Impact | Mitigation | Trigger | Owner |
| --- | --- | --- | --- | --- |
| Hardware/OEM behavior | FR-060~063 cannot be honestly accepted | Batch 0 Spike, visible fallback, named-device gate | KIO/BLE/CAM/AUD/EMG fail | Device owner |
| Provider availability/retention | Data exposure or unstable demo | Mock first, provider checklist, no real S2/S3 before D-003 | provider contract absent | Security/Integration |
| Authorization/Consent propagation | cross-family or revoked data leak | query predicates, invisible-first, P0 security tests | any negative test fails | Backend/Security |
| RAG stale derived data | deleted facts returned | invalidation before cleanup, negative tests | post-revoke retrieval | Memory/AI |
| Scam false negatives/positives | safety or trust harm | deterministic combinations, safe-similar eval, no certainty claim | evaluation regression | Safety/AI |
| Schedule pressure | 12-week overload | Batch 0/1 vertical slices, Mock external services, protect P0 | backlog slips >1 week | Program lead |
| Integration failure | demo cannot close loop | stable DTO/WSS, seed, CI, weekly vertical smoke | contract drift | Tech lead |

## 17. Final Recommendation

冻结已确认的架构与安全边界，停止继续扩写架构文档，进入工程初始化和 Batch 0。所有 Provider/Device 不确定性通过 `open-decisions.md` 的默认值、Spike 和可见 fallback 管理；一旦变更 API、DB、Consent 或跨模块安全行为，按 Design Change Policy 先提案再编码。
