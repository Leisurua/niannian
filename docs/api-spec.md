# 念念（NianNian）API Contract

| 项目 | 内容 |
| --- | --- |
| 文档状态 | Contract baseline / v1 |
| 适用范围 | 12 周比赛版 Android Elder/Family App、FastAPI 模块化单体、Mock Server |
| API 版本 | `/v1` |
| 成功响应 | 资源直接返回；列表使用统一分页对象 |
| 失败响应 | `{ error, request_id }` |

> 本文只定义 API Contract，不实现 FastAPI、Service、Repository、SQLAlchemy、Android 或 Provider。数据库 Entity 与 API DTO 有意分离。未决事项集中在第 34 节，不把 Proposed ADR 假设写成事实。

## 1. Purpose

为 Android Agent、Backend Agent 和 Mock Server 提供同一套稳定的 HTTP/WebSocket 契约，覆盖认证、家庭、授权、记忆、文件、提醒、对话、SignalEvent、通知、周报、紧急联系、设备、审计和数据生命周期。

## 2. Source Documents

优先级：`nian-nian-requirements-design.md` > 已确认 ADR > `docs/system-design.md` > `docs/database-design.md` > `docs/ui-interaction-spec.md`。

已使用的 ADR：ADR-001 Android、ADR-002 Backend、ADR-003 PostgreSQL/pgvector、ADR-004 模块化单体、ADR-005 AI Adapter、ADR-006 S3/MinIO、ADR-007 worker、ADR-008 PushProvider（Proposed）、ADR-009 Avatar（Proposed）。

## 3. API Principles

- 所有公共 HTTP 路径以 `/v1` 开头；Breaking change 才新增 major version。
- JSON 默认 `Content-Type: application/json`；文件上传使用签名 URL，不把对象字节流塞入业务 JSON。
- 所有时间使用 RFC 3339 UTC 字符串；用户输入的本地日历时间同时传 IANA `timezone`。
- 所有 ID 使用应用生成 UUIDv7 字符串，客户端不得从 ID 推断权限或顺序。
- Family scope 从 access token/session 与资源服务端交叉确认，不信任客户端单独传入的 `family_id`。
- 业务 DTO 只返回最小必要字段；不返回 ORM、embedding、内部 prompt、Chain of Thought、provider secret 或完整原始对话。
- 客户端根据稳定 `error.code` 展示人话，不展示技术异常、堆栈或 provider 名称。

## 4. Base URL / Version

开发环境示例：`https://api.example.invalid/v1`。实际 host 由部署配置提供，OpenAPI 的 `servers` 使用相对 `/v1`，便于 Mock 和反向代理。

## 5. Authentication

请求除登录、刷新和邀请 token 兑换外，使用：

```http
Authorization: Bearer <access_token>
X-Request-Id: <optional-client-correlation-id>
```

Access token 是短期 bearer token；refresh token 只在登录/刷新响应返回给当前设备，服务端只保存哈希/版本信息，不能被其他用户查询。`DeviceSession` 负责轮换、撤销当前设备和撤销全部设备。

### 5.1 Auth endpoints

| Method | Path | Auth | Idempotency | 说明 |
| --- | --- | --- | --- | --- |
| POST | `/auth/login` | No | No | 返回 access/refresh token 和当前设备 session |
| POST | `/auth/refresh` | Refresh token | No | 轮换 refresh token；旧 token 失效 |
| POST | `/auth/logout` | Access | No | 撤销当前 device session，204 |
| POST | `/auth/logout-all` | Access | No | 撤销当前用户所有 device session，204 |
| GET | `/me` | Access | No | 当前用户和可选家庭成员摘要 |

登录凭证方式在 ADR/需求中尚未定稿。当前 Contract 允许 Mock 使用 `credential.type=DEMO`，生产实现可替换为 `VERIFICATION_CODE`；不引入 OAuth。

## 6. Authorization

每次请求至少执行：

```text
Authenticated
 + active User/DeviceSession
 + same Family and ACTIVE FamilyMember
 + role/permission code
 + resource ownership or valid Consent scope
 + resource state (not deleted/revoked/expired)
 + audit requirement
```

角色放在 `FamilyMember.role`：`ELDER`、`CHILD`、`CAREGIVER`、`EMERGENCY_CONTACT`。同一用户在不同家庭可以有不同角色。`CHILD` 是数据库和现有文档的稳定值；需求中 `FAMILY_MEMBER` 是泛称，见 Open Decisions。

紧急入口在 UI 可始终显示，但联系人、事件详情、健康/用药和摘要仍需要相应资源权限。服务端不使用“按钮隐藏”作为授权。

## 7. Common Types

### 7.1 Resource metadata

```json
{
  "id": "0192f1e4-6ed8-7c21-a4c1-5d58db7c1001",
  "created_at": "2026-09-22T06:00:00Z",
  "updated_at": "2026-09-22T06:00:00Z"
}
```

`created_at`/`updated_at` 仅在资源语义需要时出现；只读快照（WeeklyReport、AuditLog）不承诺 `updated_at`。

### 7.2 ID / time / enum

- `Id`: UUIDv7 string；`Timestamp`: RFC 3339 UTC；`LocalDate`: `YYYY-MM-DD`；`TimeOfDay`: `HH:mm:ss`。
- Consent scope：`VOICE`, `PORTRAIT`, `FAMILY_MEMORY`, `HEALTH_MEDICATION`, `CONVERSATION_SUMMARY`, `CAMERA_PROXIMITY`, `NOTIFICATION_TO_FAMILY`。
- Memory type：`PERSON`, `RELATIONSHIP`, `EVENT`, `PLACE`, `PREFERENCE`, `TABOO`, `PHOTO`。
- Memory status：`PENDING`, `CONFIRMED`, `REJECTED`, `REVOKED`, `DELETED`。
- Reminder type：`CALENDAR`, `WEATHER`, `MEDICATION`, `WATER`, `CLOTHING`, `COMPANIONSHIP`。
- Reminder feedback：客户端只能提交 `DONE`, `LATER`, `SKIPPED`；`NO_RESPONSE` 由 worker 产生。
- Signal type：`PHYSICAL_DISCOMFORT`, `EMOTION_EXPRESSION`, `IMPORTANT_MEMORY`, `MISS_FAMILY`, `SCAM_RISK`, `EMERGENCY`。
- Signal severity：`L0`、`L1`、`L2`、`L3`、`L4`；Signal status：`DETECTED`, `VALIDATED`, `NOTIFIED`, `ACKNOWLEDGED`, `CONTACTED`, `FALSE_POSITIVE`, `RESOLVED`, `WITHHELD`, `NOTIFICATION_FAILED`。
- Notification channel：`IN_APP`, `PUSH`, `SMS`, `PHONE`；业务状态：`PENDING`, `QUEUED`, `SENT`, `DELIVERED`, `READ`, `FAILED`, `CANCELLED`。
- Avatar/backend conversation state：`IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `WARNING`, `OFFLINE`, `ERROR`。客户端可从更细的 `WAKING`/`TRANSCRIBING` 推导 UI，但后端不控制纯动画。

## 8. Response Convention

单资源成功直接返回 resource，不增加无意义的 `data` 包装：

```json
{ "id": "...", "name": "..." }
```

列表统一返回：

```json
{
  "items": [],
  "page": { "limit": 20, "next_cursor": "...", "has_more": false },
  "request_id": "req_..."
}
```

`request_id` 在所有有 body 的成功和失败响应中返回；`204` 无 body 时通过响应头 `X-Request-Id` 返回。资源本身不把 request id 持久化为业务字段。创建返回 `201`，异步命令返回 `202`，成功无 body 返回 `204`。

## 9. Error Model

```json
{
  "error": {
    "code": "MEMORY_NOT_FOUND",
    "message": "这条家庭记忆已不存在或你没有查看权限。",
    "details": [{ "field": "type", "reason": "unsupported_value" }]
  },
  "request_id": "req_01J..."
}
```

`message` 是可安全显示的默认文案；`details` 不得含 SQL、stack trace、token、完整电话、原始健康内容或 provider 响应。资源不存在与故意隐藏的未授权资源都可返回 404，避免 ID 枚举。

### 9.1 Stable error codes

| 类别 | 代码 |
| --- | --- |
| AUTH | `AUTH_INVALID_CREDENTIALS`, `AUTH_TOKEN_EXPIRED`, `AUTH_REFRESH_REUSED`, `AUTH_SESSION_REVOKED`, `AUTH_LOGIN_RATE_LIMITED` |
| PERMISSION | `PERMISSION_DENIED`, `PERMISSION_CONSENT_REQUIRED`, `PERMISSION_FAMILY_SCOPE_REQUIRED`, `PERMISSION_RESOURCE_HIDDEN` |
| FAMILY | `FAMILY_NOT_FOUND`, `FAMILY_MEMBER_NOT_FOUND`, `FAMILY_INVITATION_INVALID`, `FAMILY_INVITATION_EXPIRED`, `FAMILY_MEMBER_STATE_INVALID` |
| CONSENT | `CONSENT_NOT_FOUND`, `CONSENT_ALREADY_REVOKED`, `CONSENT_SCOPE_INVALID`, `CONSENT_SUBJECT_MISMATCH` |
| MEMORY | `MEMORY_NOT_FOUND`, `MEMORY_PENDING_CONFIRMATION`, `MEMORY_CONFLICT`, `MEMORY_ALREADY_DELETED`, `MEMORY_SEARCH_UNAVAILABLE` |
| REMINDER | `REMINDER_NOT_FOUND`, `REMINDER_INVALID_SCHEDULE`, `REMINDER_EXECUTION_NOT_FOUND`, `REMINDER_FEEDBACK_CONFLICT` |
| CONVERSATION | `CONVERSATION_NOT_FOUND`, `CONVERSATION_NOT_ACTIVE`, `CONVERSATION_OFFLINE`, `CONVERSATION_PROVIDER_UNAVAILABLE`, `CONVERSATION_SEQUENCE_CONFLICT` |
| SIGNAL | `SIGNAL_EVENT_NOT_FOUND`, `SIGNAL_ACTION_CONFLICT`, `SIGNAL_ACTION_NOT_ALLOWED`, `SIGNAL_DETAIL_WITHHELD` |
| NOTIFICATION | `NOTIFICATION_NOT_FOUND`, `NOTIFICATION_ALREADY_READ`, `NOTIFICATION_DELIVERY_UNAVAILABLE` |
| REPORT | `REPORT_NOT_FOUND`, `REPORT_NOT_READY`, `REPORT_DATA_INSUFFICIENT` |
| EMERGENCY | `EMERGENCY_CONTACT_NOT_FOUND`, `EMERGENCY_CONTACT_UNVERIFIED`, `EMERGENCY_CALL_NOT_FOUND`, `EMERGENCY_CHANNEL_UNAVAILABLE` |
| DEVICE | `DEVICE_NOT_FOUND`, `DEVICE_ALREADY_BOUND`, `DEVICE_HEARTBEAT_STALE`, `DEVICE_CAPABILITY_UNAVAILABLE` |
| FILE | `FILE_NOT_FOUND`, `FILE_TYPE_NOT_ALLOWED`, `FILE_TOO_LARGE`, `FILE_CHECKSUM_MISMATCH`, `FILE_UPLOAD_EXPIRED`, `FILE_NOT_AVAILABLE` |
| PROVIDER | `PROVIDER_TEMPORARILY_UNAVAILABLE`, `PROVIDER_TIMEOUT`, `PROVIDER_QUOTA_EXCEEDED` |
| VALIDATION | `VALIDATION_ERROR`, `INVALID_CURSOR`, `INVALID_TIMEZONE`, `IDEMPOTENCY_KEY_REUSED`, `ETAG_MISMATCH` |

### 9.2 HTTP status

| Status | 用途 |
| --- | --- |
| 200 | 成功读取、更新、动作结果 |
| 201 | 新建资源 |
| 202 | 已接受异步任务（导出、删除、文件处理、报告生成） |
| 204 | 成功登出、删除或无 body 的动作 |
| 400 | 请求语义错误、状态机不允许 |
| 401 | 未认证、token 无效/过期；不表示已认证但无权 |
| 403 | 已认证但角色、家庭、Consent 或 ownership 不允许 |
| 404 | 资源不存在，或为防枚举而隐藏的未授权资源 |
| 409 | 并发冲突、重复资源、幂等键冲突 |
| 422 | JSON/schema/字段校验失败 |
| 429 | 超出 rate limit |
| 500 | 未预期服务错误，客户端只显示通用提示 |
| 502 | 外部依赖返回不可用结果 |
| 503 | 当前服务或 provider 暂不可用，可重试 |

## 10. Pagination / Sorting / Filtering

列表统一使用 cursor pagination：`limit` 默认 20，最大 100，`cursor` 为不透明 base64url，不能由客户端解码或修改。排序由 endpoint 固定，通常 `created_at desc, id desc`；客户端不得传任意 SQL 字段。过滤参数只接受文档列出的 enum/日期范围。适用于 memories、signal-events、notifications、audit-logs、reminders、executions、reports。

## 11. Idempotency

需要幂等的 POST 必须传 `Idempotency-Key`（1-128 ASCII 字符，服务端保留窗口由实现配置）：创建 family、邀请、consent、memory、file confirm、reminder、reminder feedback、Signal action、notification action、emergency contact、emergency call、device register、data export/delete。相同 key + 相同请求重放原响应；相同 key + 不同请求返回 `409 IDEMPOTENCY_KEY_REUSED`。GET/普通 PATCH 不要求。

## 12. Concurrency

可编辑资源响应提供整数 `version`；更新请求带 `If-Match: "<version>"`（或 `expected_version`）。版本不一致返回 `409` / `ETAG_MISMATCH`，客户端重新读取并让用户合并。Consent 不 PATCH，撤回追加 immutable history；Signal action 和 reminder feedback 使用状态机 + 幂等键。禁止分布式锁作为客户端契约。

## 13. Auth API

### `POST /auth/login`

请求：`{ "credential": { "type": "DEMO", "identifier": "demo-elder" }, "device": { "device_id": "client-generated-id", "name": "Elder tablet", "app_version": "0.1.0" } }`。生产允许 `VERIFICATION_CODE`，字段由最终认证决策补充。响应 `201`：`access_token`、`refresh_token`、`expires_in`、`token_type`、`device_session`、`user`、`families`。

### `POST /auth/refresh`

请求 `{ "refresh_token": "..." }`；响应返回新的 access/refresh token。refresh token 不出现在日志、审计详情或任何查询 API。

### `POST /auth/logout` / `POST /auth/logout-all`

无 body；`204`。logout-all 只撤销当前用户会话，不能影响家庭其他成员。

### `GET /me`

返回 `MeResponse { user, family_memberships[], active_device_session }`。不返回其他用户 token、完整电话或内部 global role 以外的运营数据。

## 14. Family API

| Method | Path | Request/response | 关键规则 |
| --- | --- | --- | --- |
| POST | `/families` | `FamilyCreate` -> `FamilyResponse` (201) | 登录用户成为创建者；幂等 |
| GET | `/families` | 分页 `FamilySummary` | 只列当前用户的成员关系 |
| GET | `/families/{family_id}` | `FamilyResponse` | ACTIVE/PENDING membership |
| POST | `/families/{family_id}/invitations` | `InvitationCreate` -> `InvitationResponse` (201) | 允许角色由 caller 权限决定；token 只返回一次、过期/次数限制 |
| POST | `/family-invitations/{token}/accept` | `InvitationAccept` -> `FamilyMemberResponse` | token 兑换后创建/更新 PENDING；双方确认后 ACTIVE |
| GET | `/families/{family_id}/members` | 分页 | 隐藏被撤销成员的敏感资料 |
| GET | `/families/{family_id}/members/{member_id}` | `FamilyMemberResponse` | 同家庭 + 成员关系 |
| PATCH | `/families/{family_id}/members/{member_id}` | `FamilyMemberUpdate` -> response | 仅允许 role/status/permission_codes 白名单字段；不能 mass assignment |
| POST | `/families/{family_id}/members/{member_id}/leave` | action -> 204 | 自己离开；管理员撤销使用 revoke action，避免伪造删除 |
| POST | `/families/{family_id}/invitations/{invitation_id}/revoke` | action -> 204 | 创建者/授权管理员 |

Invitation DTO 不返回明文 `token_hash`；二维码/深链由客户端用一次性 `token` 展示。

## 15. Consent API

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/consents` | 按 `family_id`、`subject_user_id`、`grantee_user_id`、`scope`、`status` 过滤；只返回 caller 有权知道的授权 |
| GET | `/consents/{id}` | 详情和撤回影响 |
| POST | `/consents` | `ConsentCreate` -> immutable `ConsentResponse` (201)；同一 scope 新授权可替代旧 GRANTED |
| POST | `/consents/{id}/revoke` | `ConsentRevoke` -> 新历史版本 (201/202)；原记录不修改、不删除 |

`ConsentCreate` 至少包含 `family_id, subject_user_id, grantee_user_id, scope, expires_at?, source`。健康/用药、对话摘要、家庭记忆等 scope 每次单独确认。有效授权查询需 ACTIVE FamilyMember；客户端不得从角色自行推断授权。

## 16. Memory API

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/memories` | filters: `family_id`, `subject_user_id`, `type`, `verification_status`, `visibility`, `pending_confirmation`, `q`, `cursor`, `limit`；不接受 vector/embedding |
| POST | `/memories` | `MemoryCreate` -> PENDING/CONFIRMED `MemoryResponse` (201)；模型抽取只能 PENDING |
| GET | `/memories/{id}` | `MemoryDetailResponse`；照片使用受控 file reference |
| PATCH | `/memories/{id}` | `MemoryUpdate` + `If-Match`；只允许白名单字段 |
| POST | `/memories/{id}/confirm` | 家属确认待确认事实，写 AuditLog |
| POST | `/memories/{id}/reject` | 拒绝模型/成员候选 |
| POST | `/memories/{id}/revoke` | 业务不可见并使 RAG/cache 失效 |
| DELETE | `/memories/{id}` | 软删除并异步清理 chunk/embedding/file；返回 202 `DeletionTaskResponse` |
| POST | `/memories/{id}/feedback` | 老人/授权用户报告内容错误；不直接改事实 |

Memory response 只含 `id,family_id,subject_user_id,type,title,content,source,verification_status,visibility,required_consent_scope,verified_by,expires_at,version,created_at,updated_at,attachments[]`。不含 embedding、chunk 文本、rule/provider metadata。只有 `CONFIRMED + authorized + not deleted/revoked/expired` 记忆进入服务端 RAG；RAG 是内部函数，不提供普通客户端 search endpoint。

## 17. File API

采用 ADR-006 的两步上传：

| Method | Path | 说明 |
| --- | --- | --- |
| POST | `/files/upload-requests` | `FileUploadRequest`（media_type/mime/size/checksum/owner/memory_id?）-> `SignedUploadResponse` (201)；私有 key、短时 URL、大小/MIME 白名单 |
| POST | `/files/{file_id}/confirm` | `FileUploadConfirm` -> `FileAssetResponse` (202/200)；校验 checksum、对象存在和病毒/类型状态 |
| GET | `/files/{file_id}/download-url` | 每次重新授权后返回短时 signed URL，不是永久 public URL |
| DELETE | `/files/{file_id}` | 标记删除并排队对象清理；不可恢复可读性 |

孤儿文件由 worker 按状态/retention 清理；撤回 Consent 后 signed URL 立即拒绝，即使对象尚未物理删除。允许类型默认 `image/jpeg,image/png,image/webp`，上限由部署配置返回 `max_size_bytes`；音频仅在最终保留决策允许时启用。

## 18. Reminder API

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/reminders` | family/owner/type/active 过滤，分页 |
| POST | `/reminders` | `ReminderCreate` -> 201；用药内容由家属录入，API 不自动改医嘱 |
| GET | `/reminders/{id}` | 规则和下次触发 |
| PATCH | `/reminders/{id}` | 白名单 + `If-Match` |
| DELETE | `/reminders/{id}` | 软删除/停用 |
| GET | `/reminders/{id}/executions` | 分页；返回 `NO_RESPONSE` 为“尚未收到反馈”，不等于未服药 |
| POST | `/reminder-executions/{id}/feedback` | `{status:DONE|LATER|SKIPPED,note?,next_due_at?}`；NO_RESPONSE 不能由客户端提交 |

提醒创建字段：`owner_user_id,type,title,content,schedule_time_local,timezone,start_date,end_date?,recurrence_kind,recurrence_interval,days_of_week,quiet_hours?,escalation_policy?`。服务端校验 IANA timezone、周期和 owner family scope。

## 19. Conversation API

| Method | Path | 说明 |
| --- | --- | --- |
| POST | `/conversations` | `{family_id?,device_id?,input_mode}` -> `ConversationResponse` (201)，播放新会话短 AI 身份提示一次 |
| GET | `/conversations/{id}` | session metadata、backend state、summary_status、受控 summary（需 `CONVERSATION_SUMMARY`） |
| POST | `/conversations/{id}/end` | `{reason?:USER|TIMEOUT|ERROR}` -> response；触发 summary 任务（若授权） |
| POST | `/conversations/{id}/summary` | 显式请求受控摘要；202/200；不返回逐字稿 |

REST 不用于上传大量音频 chunk；实时状态见 WSS。Conversation response 的 `backend_state` 与 UI AvatarState 对应，但动画细节由客户端派生。

## 20. Conversation WebSocket

连接：`wss://host/v1/ws/conversations/{conversation_id}`，使用同一 bearer token（首选 header；不把 token 放 URL）。连接建立后服务端再次校验 conversation owner/family/Consent。所有消息 envelope：

```json
{
  "type": "conversation.state",
  "conversation_id": "...",
  "sequence": 15,
  "occurred_at": "2026-09-22T06:01:00Z",
  "payload": {}
}
```

`sequence` 按会话单调递增；客户端发现间隙应 REST GET session 后重连。服务端不保证音频消息必达，断线后可结束或恢复 metadata。

### 20.1 Client -> Server

`session.start {client_session_id,input_mode}`、`audio.chunk {content_type,base64_data,chunk_no}`（仅在最终音频策略允许时）、`audio.end`、`text.input {text}`、`interrupt`、`repeat`、`slow_down`、`session.end {reason}`、`ping`。

### 20.2 Server -> Client

`session.ready {backend_state}`、`asr.partial {text_redacted}`、`asr.final {text_redacted,confidence_band}`、`assistant.state {state}`、`assistant.text {text,source_labels[]}`、`tts.start {duration_ms?}`、`tts.end`、`signal.created {signal_event_id,type,severity}`、`warning {reason_category,display_text,blocked_action?}`、`error {code,retryable}`、`pong`。

不发送 raw provider metadata、prompt、chain of thought、完整敏感 transcript 或 token。`confidence_band` 只能为 `LOW|MEDIUM|HIGH`，不向普通 UI 暴露数值。

## 21. SignalEvent API

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/signal-events` | family/owner/type/severity/status/date 过滤；默认最小 summary |
| GET | `/signal-events/{id}` | detail：type、severity、summary、reason `{category,display_text}`、time、status、recommended_action；原始对话默认隐藏 |
| POST | `/signal-events/{id}/ack` | 家属确认；幂等，状态机校验 |
| POST | `/signal-events/{id}/contact` | 记录已发起联系和可选 contact channel；不宣称接通 |
| POST | `/signal-events/{id}/false-positive` | 记录误报 reason；审计；不删除事实 |
| POST | `/signal-events/{id}/resolve` | 具备权限的家属/系统结束事件 |

`SCAM_RISK`、`PHYSICAL_DISCOMFORT` 和 `EMERGENCY` 额外检查健康/通知 scope。`WITHHELD` 只返回有限状态，不泄露被保护 evidence。reason 使用人话类别（如 `TRANSFER_AND_SECRECY`），不只给 confidence 数字。

## 22. Notification API

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/notifications` | 当前用户收件箱，按 status/channel/date 分页 |
| GET | `/notifications/{id}` | 授权的最小摘要和业务状态 |
| POST | `/notifications/{id}/read` | 标记已读；幂等 |
| POST | `/notifications/{id}/action` | `{action:ACKNOWLEDGED|CONTACTED|FALSE_POSITIVE}`；动作写回 SignalEvent |

Push 仅传 event id/最小摘要；客户端随后通过 REST 拉取授权详情。`NotificationAttempt` 无公共 CRUD，provider/error_detail 只在服务端日志/受限审计中存在。

## 23. WeeklyReport API

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/reports/weekly` | family/owner/period_start/period_end 分页，默认最新 READY |
| GET | `/reports/weekly/{id}` | `WeeklyReportResponse`；GENERATING/FAILED 返回状态和 missing_data |
| POST | `/reports/weekly` | 可选显式生成请求，202；不允许客户端提交 metrics |

Response 分开 `metrics`（结构化：interaction_count、conversation_duration_seconds、reminder_*、signal_counts、interaction_time_distribution、repeated_topic_stats）与 `narrative`、`observations[]`、`missing_data[]`、`generated_at`、`version`。禁止 `cognitive_decline_score`、`depression_probability`、`sleep_quality_score` 等医疗化字段。

## 24. Emergency API

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/emergency/contacts` | 当前老人授权联系人，电话仅 last4 |
| POST | `/emergency/contacts` | 添加注册用户或外部联系人；敏感电话只提交 TLS body，响应脱敏 |
| PATCH | `/emergency/contacts/{id}` | 更新姓名/优先级/channel/enabled，不能 mass assignment |
| DELETE | `/emergency/contacts/{id}` | 禁用/删除关系，保留审计 |
| POST | `/emergency/calls` | `{source:VOICE|BLE|SCREEN|SIGNAL_EVENT,contact_id?}` -> 202 `EmergencyCallResponse` |
| GET | `/emergency/calls/{id}` | 状态 `INITIATED|CONNECTING|CONNECTED|NO_ANSWER|FAILED|CANCELLED`、failure_reason、next_action |

服务器记录事件、审计、通知和结果同步；系统电话由 Android Telecom/Intent 执行，服务端不承诺接通。普通 rate limit 不得阻断 emergency，但仍做滥用保护和审计。

## 25. Device API

| Method | Path | 说明 |
| --- | --- | --- |
| POST | `/devices/register` | `DeviceRegister` -> 201；绑定当前老人，device_id 只存 hash |
| GET | `/devices` | 当前用户可见设备分页 |
| GET | `/devices/{id}` | 最新 kiosk/wakeword/BLE/camera/phone 状态 |
| POST | `/devices/{id}/heartbeat` | 仅上传 online、app_version、kiosk、ble、wakeword、critical permissions；建议正常 60 秒最多一次 |
| PATCH | `/devices/{id}/settings` | 设备显示/免打扰/能力开关白名单 + version |
| POST | `/devices/{id}/unbind` | 管理员解绑，204 |

BLE button event 若本地直接进入 Emergency，不创建公共 `/button-event`；设备端先显示本地状态，再调用 emergency call。服务器不接收摄像头图像、人脸特征或高频无意义 telemetry。

## 26. Audit API

`GET /audit-logs` 支持 `family_id`（仅当前 membership）、`action`、`target_type`、`from`、`to`、`cursor`、`limit`。不支持任意 `user_id=someone_else`；actor/target 只在 caller 有权范围内返回。DTO 是人话 `actor_display_name_masked, action, target_type, target_label, reason, result, created_at`，不返回 metadata secrets、全文对话、token 或完整电话。AuditLog append-only，无公共删除/写入 endpoint，业务动作由服务端自动记录。

## 27. Data Export / Delete

| Method | Path | 说明 |
| --- | --- | --- |
| POST | `/data-exports` | `{scope:ACCOUNT|FAMILY_DATA,format:JSON|ZIP}` -> 202 `DataJobResponse` |
| GET | `/data-exports/{id}` | `PENDING|RUNNING|READY|FAILED|EXPIRED`；READY 时返回短时受控下载链接 |
| POST | `/account-deletion-requests` | 二次确认后的 `{reason?,confirm:true}` -> 202 |
| GET | `/account-deletion-requests/{id}` | `PENDING|RUNNING|PARTIAL_FAILURE|COMPLETED|CANCELLED` 和阶段/结果 |
| POST | `/account-deletion-requests/{id}/cancel` | 仅尚未开始时允许；不能撤销已完成清理 |

删除顺序：业务不可见 -> Consent/Memory/RAG/cache/file 失效 -> worker 清理 -> 结果通知；失败显示部分清理而不是假装完成。审计事实、法律/备份保留期遵从最终隐私决定。

## 28. Rate Limits

默认按 user + IP + endpoint bucket：login 5/min、invitation 10/hour、conversation start 30/hour、file upload 20/hour/100MB、普通列表 120/min、emergency 10/min。响应 `429` 带 `Retry-After`。Emergency 使用独立 bucket，并在达到阈值时仍允许进入本地联系流程；服务端拒绝只返回 `EMERGENCY_RATE_LIMITED` 并保留替代路径。

## 29. Security

- IDOR：所有 `{id}` 先按 token 家庭、membership、ownership、Consent、状态过滤；未授权可统一 404。
- Broken access control：角色只是一层，必须叠加同家庭、ACTIVE、scope、资源所有权和状态机。
- Mass assignment：每个 create/update/action 使用显式 DTO 白名单，不接受 `owner_user_id`、`family_id` 作为越权依据、status/verified_by 等服务端字段。
- Replay：Idempotency-Key、一次性 invitation、refresh rotation、sequence/ETag、signed URL 过期。
- Token leakage：不放 query、日志、AuditLog、错误 details；Refresh token 只在认证响应出现。
- File upload：MIME/扩展名/大小/checksum/对象 key 服务端校验；私有 bucket、quarantine、短 URL；不执行用户上传文件。
- Enumeration：登录错误不区分用户存在性；资源详情的隐藏对象返回 404；邀请 token 只返回统一错误。
- Privacy：Notification/Signal 只最小摘要；健康、对话摘要、照片需要 scope；embedding、provider metadata、raw audio 无公共接口。
- Logging：允许 `request_id, endpoint, status, latency, actor_id, resource_id, error_code`；禁止 Authorization、完整电话、完整 conversation、原始健康文本、signed URL。

## 30. Screen -> API Matrix

| Screen | Data requirement | Contract |
| --- | --- | --- |
| E-001 今日 | me、设备、下一个 reminder、联系人、天气能力 | `GET /me`, `GET /devices/{id}`, `GET /reminders`, `GET /emergency/contacts` |
| E-002 Conversation | session state、WSS events、授权记忆上下文 | `POST/GET /conversations/{id}`, WSS `/ws/conversations/{id}` |
| E-003 首次说明 | consent 状态和创建 | `GET/POST /consents` |
| E-004/E-005 Reminder | execution 和反馈 | `GET /reminders/{id}/executions`, `POST /reminder-executions/{id}/feedback` |
| E-006/E-007/E-012 记忆 | confirmed memory、附件、错误反馈 | `GET /memories`, `GET /memories/{id}`, `POST /memories/{id}/feedback` |
| E-008 身体不适 | warning、安全联系 | WSS `warning`, `POST /emergency/calls` |
| E-009 Scam Warning | reason、blocked action、事件 | WSS `warning`, `GET /signal-events/{id}`, `POST /signal-events/{id}/contact` |
| E-010 Emergency | 联系人和 call 状态 | `GET /emergency/contacts`, `POST/GET /emergency/calls` |
| E-011 Session Recap | 受控 summary | `GET /conversations/{id}`, `POST /conversations/{id}/summary` |
| E-013/E-015/E-016 设置/能力 | me、device、consent | `GET /me`, `GET/PATCH /devices/{id}/settings`, `GET /consents` |
| F-001 登录/家庭选择 | auth/family memberships | `/auth/*`, `GET /families` |
| F-002/F-003 动态/事件 | notifications、SignalEvent | `GET /notifications`, `GET /signal-events/{id}`, action endpoints |
| F-004 周报 | weekly report | `GET /reports/weekly`, `GET /reports/weekly/{id}` |
| F-005~F-008 Memory | list/detail/form/pending | Memory CRUD/action + File API |
| F-009~F-011 Reminder | rules/executions | Reminder API |
| F-012/F-013 Family | family/member/invite | Family API |
| F-014 Consent | scope history/revoke | Consent API |
| F-015 Contacts | contact CRUD/verification | Emergency contacts API |
| F-016 Device | capability/heartbeat state | Device API |
| F-017/F-018 Privacy | audit/export/delete | Audit + Data lifecycle API |

## 31. FR -> API Matrix

| FR | API / WebSocket / Local capability |
| --- | --- |
| FR-001 | Auth + Family membership + `GET /me`; server role gating |
| FR-002 | Family create/invitation/accept/member confirmation |
| FR-003 | Consent API + Conversation session prompt state |
| FR-004 | Consent list/create/revoke |
| FR-005 | Data export/delete jobs |
| FR-010~016 | Conversation REST/WSS + local Avatar/TTS/Accessibility |
| FR-020~023 | Memory API + File API + internal permission-filtered RAG |
| FR-030~033 | Reminder/Execution API + local cached reminder |
| FR-040~044 | SignalEvent/Notification/Report + Consent/Audit |
| FR-050~052 | WSS warning + SignalEvent + Notification; RuleEngine internal |
| FR-053 | Emergency contacts/calls + Device status + Android Telecom/BLE local capability |
| FR-060 | Device API status + Android Device Owner/LockTask local capability |
| FR-061 | Device wakeword status + local cached reminder; no fake online answer |
| FR-062 | Consent `CAMERA_PROXIMITY` + Device status; camera presence local only |
| FR-063 | Device BLE status + local button event -> Emergency API |

## 32. Database Entity -> API Exposure

| Entity | Exposure |
| --- | --- |
| User | Public DTO through `/me` only |
| Family, FamilyMember, FamilyInvitation | Public Family API |
| Consent | Public Consent API, immutable history |
| DeviceSession | No direct CRUD; auth login/refresh/logout only |
| Memory | Public Memory API |
| MemoryChunk, MemoryEmbedding | Internal only; no HTTP |
| FileAsset | Narrow File API; no public object URL |
| Reminder, ReminderExecution | Public Reminder API |
| Conversation | Public metadata/summary; messages controlled via WSS, no message CRUD |
| InteractionMetric | Embedded in authorized WeeklyReport; no general CRUD |
| SignalEvent | Public minimum detail + actions |
| Notification | Public recipient inbox/action; NotificationAttempt internal |
| EmergencyContact | Public owner-scoped CRUD |
| DeviceBinding | Public owner/family-scoped status/heartbeat/settings |
| WeeklyReport | Public read and generation request |
| AuditLog | Read-only filtered public API |

## 33. Demo Contract

1. 老人开始对话：create conversation -> WSS `session.ready`/states -> text/audio -> `assistant.text`/TTS -> end/summary。
2. 查询家庭记忆：family member GET memories -> only confirmed + consented result -> source label。
3. Reminder feedback：GET execution -> POST feedback DONE/LATER/SKIPPED -> idempotent result。
4. 思念家人：conversation WSS `signal.created` -> GET detail -> family notification -> contact/ack。
5. 诈骗：RuleEngine emits `warning` -> sensitive action blocked -> SignalEvent/Notification with explainable reason。
6. 子女联系老人：SignalEvent contact -> emergency/contact flow -> actual result state, never fake connected。
7. WeeklyReport：GET report -> metrics/narrative/missing_data separated。
8. BLE emergency：local BLE event -> `POST /emergency/calls` -> poll call state; offline fallback visible。
9. Consent revoke：POST revoke -> subsequent memory/file/RAG requests fail/omit immediately。
10. Memory delete：DELETE -> 202 task -> list/RAG/cache omit before physical cleanup completes。

## 34. Open Decisions

### Conflict: Authentication method

**Documents:** Requirements section 8, System Design section 11, ADR-002。

**Requirement:** 至少支持登录、刷新、登出和 device session；比赛版没有确认真实短信/OAuth 方案。

**Problem:** 如果把手机号、密码或短信供应商写死，Android 与后端会被迫采用未批准的商业认证方案。

**Impact:** `LoginRequest`、rate limit、账号找回和安全测试会改变；Mock Server 也会被不必要地绑定。

**Recommended Resolution:** 先实现 `DEMO` contract 和可替换的 `VERIFICATION_CODE` discriminator；不引入 OAuth。真实登录方式确认后只扩展 request schema，保持 token/session contract。

**Decision Required:** 确认比赛版最终登录凭证、手机号验证、风控和演示账号策略。

### Conflict: Family member role naming

**Documents:** Requirements FR-001/permission wording、Database Design section 7、Data Dictionary `family_member.role`。

**Requirement:** 产品需要“子女/家属”角色；数据库稳定 enum 是 `ELDER/CHILD/CAREGIVER/EMERGENCY_CONTACT`。

**Problem:** 将泛称 `FAMILY_MEMBER` 直接作为 enum 会与既有数据库约束和同一用户多家庭角色模型冲突。

**Impact:** Retrofit/Pydantic enum、权限矩阵和 seed 数据可能出现不同名称，造成越权或兼容问题。

**Recommended Resolution:** API 使用数据库稳定值 `CHILD`；UI 文案可显示“家属/子女”，但不改变 wire enum。

**Decision Required:** 确认是否需要仅在展示层提供 `FAMILY_MEMBER` 别名。

### Conflict: Raw audio and summary retention

**Documents:** Requirements FR-015、Database Design section 20、UI Interaction Spec section 18。

**Requirement:** 支持会话回顾和删除个人数据；默认不保存永久原始音频，但保留期限尚未确认。

**Problem:** WSS 是否传输音频、summary 是否进入导出包和何时物理清理无法凭空确定。

**Impact:** Conversation/File schema、导出完成语义、隐私验收和存储成本会变化。

**Recommended Resolution:** 默认只保存受控 summary/status，不提供原始音频公共读取；若本地 ASR，WSS 只传文本/状态。保留期限确认后再细化字段。

**Decision Required:** 确认 raw audio 是否允许、summary 保留期、调试例外和导出范围。

### Conflict: Push/phone provider availability

**Documents:** Requirements FR-041/FR-053、ADR-008（Proposed）、System Design section 10。

**Requirement:** 家属通知和紧急联系需要多渠道降级，但供应商、网络和费用未定。

**Problem:** 公共 API 不能把 FCM、短信或某电话服务的到达能力当成业务事实。

**Impact:** Notification 只能表达业务状态，Emergency 只能表达发起/接通/未接/失败，Demo 可能依赖应用内轮询。

**Recommended Resolution:** `PushProvider`/渠道保持抽象；MockPush + IN_APP 轮询为基线，真实 provider 只作为可替换实现。

**Decision Required:** 确认比赛网络、可用 provider、费用、数据留存和 Android 权限。

| Conflict / Decision Required | Impact | Recommended resolution |
| --- | --- | --- |
| 登录是 demo、短信验证码还是其他 phone proof 尚未由系统设计确认 | `LoginRequest` 生产字段和风控不同 | 先按 `DEMO` Mock + 可替换 `VERIFICATION_CODE` contract；人工确认后冻结 |
| 数据库角色是 `CHILD`，需求正文使用 `FAMILY_MEMBER` 泛称 | Android enum/权限矩阵命名可能漂移 | 保留 `CHILD` 作为稳定值；确认是否增加仅展示别名 |
| 原始音频和 summary retention TBD | Conversation/File DTO 生命周期与导出范围 | 默认不保存 raw audio；确认 summary/调试音频期限后更新 contract |
| ADR-008 Push provider Proposed | `PUSH/SMS/PHONE` 只可作为渠道，不承诺到达 | MockPush + 应用内轮询为基线；确认供应商/费用/网络/合规 |
| ADR-009 Avatar SDK Proposed | 不影响 API，仅影响客户端 provider metadata | 使用 AvatarState/MockAvatar，确认 SDK 后再扩展能力字段 |
| FR-053 指定设备 SIM、Telecom、BLE 权限未知 | 只能保证联系流程和结果状态 | 以 INITIATED/NO_ANSWER/FAILED 为真实契约，不承诺接通 |
| AuditLog、backup、report、summary 具体保留期 TBD | 删除完成定义和合规证明 | 在隐私/威胁模型文档中冻结保留策略 |

## 35. Risks

- OAuth/短信等认证选择改变后，登录风控、验证码 endpoint 和 OpenAPI schema 需同步更新。
- Consent 撤回后的 cache/vector/object 清理如果不是事务外可靠任务，可能造成短时旧数据可检索；需集成测试证明“先不可见、后清理”。
- WSS 音频 chunk 契约依赖最终 raw audio 保留与 Android 端 ASR 位置；若 ASR 在本地，删掉 `audio.chunk` 并只传状态/文本。
- Push、电话和短信均可能失败，Notification/Call 状态必须与事件事实分离。
- 12 周内不应给 MemoryChunk、Embedding、DeviceSession、NotificationAttempt、Provider config 增加公共 CRUD。
