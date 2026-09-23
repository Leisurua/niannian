# 念念（NianNian）API Permission Matrix

## 1. 读法与统一前置条件

本表是 `docs/api-spec.md` 的逐 endpoint 授权基线。除标记 `Public` 的登录/邀请兑换外，每项都必须同时满足：

```text
有效 Access Token
→ User ACTIVE + DeviceSession 未撤销
→ 路由 family 与 token/session 绑定一致
→ FamilyMember.status = ACTIVE
→ 角色/permission code
→ 资源 ownership 或有效 Consent scope
→ 资源未删除/撤回/过期
→ 需要时写 AuditLog
```

`Same family` 不是角色替代品；`CHILD` 是数据库稳定角色，需求中的 `FAMILY_MEMBER` 是泛称。系统动作使用 `SYSTEM`，不允许客户端伪造 system actor。

列含义：`Caller` 调用者；`Family` 是否需要同家庭；`Consent` 必须有效的 scope；`Owner` 是否要求 subject/owner；`Audit` 服务端是否必须追加审计。

## 2. Role and scope baseline

| 角色 | 默认能力边界 |
| --- | --- |
| `ELDER` | 查看/管理自己的会话、提醒反馈、自己的联系人和与自己相关的授权；可撤回自己授予的 scope；始终能进入紧急流程 |
| `CHILD` | 在 ACTIVE membership、细粒度 permission 和老人 Consent 下管理家庭记忆、提醒、SignalEvent、周报和联系 |
| `CAREGIVER` | 仅获得被授予的照护/提醒/健康 scope；默认不能查看完整对话或修改角色 |
| `EMERGENCY_CONTACT` | 只接收被授权紧急/高风险通知和联系结果；不获得家庭 Memory/Conversation 默认读取权 |
| `SYSTEM` | worker/provider/规则产生内部状态；无 bearer token，不提供模拟客户端角色 |

Consent scope：`VOICE`, `PORTRAIT`, `FAMILY_MEMORY`, `HEALTH_MEDICATION`, `CONVERSATION_SUMMARY`, `CAMERA_PROXIMITY`, `NOTIFICATION_TO_FAMILY`。

## 3. Endpoint matrix

### 3.1 Authentication and identity

| Method / endpoint | Caller | Family | Consent | Owner | Audit |
| --- | --- | --- | --- | --- | --- |
| `POST /v1/auth/login` | Public | No | No | Device proof | Failed/success security event |
| `POST /v1/auth/refresh` | Current refresh token | No | No | Token session | Rotation/reuse security event |
| `POST /v1/auth/logout` | Authenticated | No | No | Current DeviceSession | Yes |
| `POST /v1/auth/logout-all` | Authenticated | No | No | Current User | Yes |
| `GET /v1/me` | Authenticated | Memberships only | No | Current User | No content audit |

### 3.2 Family and invitations

| Method / endpoint | Caller | Family | Consent | Owner | Audit |
| --- | --- | --- | --- | --- | --- |
| `POST /v1/families` | Authenticated user | Creates scope | No | Creator | Yes |
| `GET /v1/families` | Authenticated | Own memberships only | No | Current User | No |
| `GET /v1/families/{family_id}` | ELDER/CHILD/CAREGIVER/EMERGENCY_CONTACT ACTIVE | Same family | No | Membership | No |
| `POST /v1/families/{family_id}/invitations` | Family creator or delegated member-admin | Same family | No | Family admin permission | Yes |
| `POST /v1/family-invitations/{token}/accept` | Authenticated invitee | Token-bound family, before membership | No | Invitee identity | Yes |
| `GET /v1/families/{family_id}/members` | Active member; member-read permission | Same family | No | Family scope | Yes if sensitive fields |
| `GET /v1/families/{family_id}/members/{member_id}` | Active member; member-read permission | Same family | No | Target relation | Yes |
| `PATCH /v1/families/{family_id}/members/{member_id}` | Creator/member-admin; self may edit allowed profile fields | Same family | No | Target relation | Yes |
| `POST /v1/families/{family_id}/members/{member_id}/leave` | Target member | Same family | No | Self only | Yes |
| `POST /v1/families/{family_id}/invitations/{id}/revoke` | Creator/member-admin | Same family | No | Invitation creator/admin | Yes |

Invitation acceptance shows inviter identity and intended role/scope before activation.老人确认/双方确认才可转 `ACTIVE`；expired/revoked token is not distinguishable from an invalid token to unauthorised callers.

### 3.3 Consent

| Method / endpoint | Caller | Family | Consent | Owner | Audit |
| --- | --- | --- | --- | --- | --- |
| `GET /v1/consents` | Subject, grantee, family-admin only within visible scope | Same family | Existing visibility rule | Subject or relevant member | Yes for health/summary views |
| `GET /v1/consents/{id}` | Subject, grantee, authorized admin | Same family | Existing consent history | Relation participant | Yes |
| `POST /v1/consents` | Subject user; delegated flow only when product rule permits | Same family | Creates requested scope | Subject must match | Yes |
| `POST /v1/consents/{id}/revoke` | Grantor/subject; emergency safety exception only if separately documented | Same family | No extra scope; revoke is allowed | Original consent participant | Yes |

`grantee_user_id` 必须是同家庭 ACTIVE member；health/medication、conversation summary、family memory 不因“同家庭”自动授权。Consent history immutable，不能 PATCH status。

### 3.4 Memory and files

| Method / endpoint | Caller | Family | Consent | Owner | Audit |
| --- | --- | --- | --- | --- | --- |
| `GET /v1/memories` | Subject or member with memory-read permission | Same family | `FAMILY_MEMORY`; `HEALTH_MEDICATION` for health content | Subject/authorized family | Sensitive read yes |
| `POST /v1/memories` | Subject or delegated CHILD/CAREGIVER | Same family | Required scope based on type | `subject_user_id` must be authorized | Yes |
| `GET /v1/memories/{id}` | Same as list, resource-filtered | Same family | Required scope | Owner/authorized grantee | Yes |
| `PATCH /v1/memories/{id}` | Creator/verifier or delegated memory-editor | Same family | Required scope | Resource owner/editor | Yes |
| `POST /v1/memories/{id}/confirm` | CHILD/CAREGIVER with confirmation permission; subject may confirm own fact | Same family | `FAMILY_MEMORY` or type-specific scope | Authorized verifier | Yes |
| `POST /v1/memories/{id}/reject` | Same as confirm | Same family | Same | Authorized verifier | Yes |
| `POST /v1/memories/{id}/revoke` | Subject/grantor or memory-admin under policy | Same family | No new scope | Subject/admin | Yes |
| `DELETE /v1/memories/{id}` | Subject or explicitly delegated data editor | Same family | No new scope; deletion itself allowed | Owner/editor | Yes |
| `POST /v1/memories/{id}/feedback` | Elder/authorized reader | Same family | Existing read scope | Reader | Yes |
| `POST /v1/files/upload-requests` | Authorized memory editor | Same family | `FAMILY_MEMORY`/`PORTRAIT`; `HEALTH_MEDICATION` for health asset | File owner/linked memory | Yes |
| `POST /v1/files/{id}/confirm` | Upload requester or service callback | Same family | Same as upload request | Asset owner | Yes |
| `GET /v1/files/{id}/download-url` | Same as linked Memory reader | Same family | Current scope rechecked at request time | Owner/authorized grantee | Yes |
| `DELETE /v1/files/{id}` | Asset owner or delegated data editor | Same family | No new scope | Owner/editor | Yes |

`MemoryEmbedding`、`MemoryChunk` 和 object-store bucket 无公共 endpoint；删除先撤销可读性，再异步清理。

### 3.5 Reminder and conversation

| Method / endpoint | Caller | Family | Consent | Owner | Audit |
| --- | --- | --- | --- | --- | --- |
| `GET /v1/reminders` | Elder owner, CHILD/CAREGIVER with reminder-read | Same family | `HEALTH_MEDICATION` for medication | Owner/authorized manager | Yes for health filters |
| `POST /v1/reminders` | CHILD/CAREGIVER reminder-manager; elder may create non-health personal reminder | Same family | Health scope for medication | `owner_user_id` must be in family | Yes |
| `GET /v1/reminders/{id}` | Owner/authorized manager | Same family | Health scope when needed | Owner/manager | Yes for medication |
| `PATCH /v1/reminders/{id}` | Creator/manager; elder may change own notification preference | Same family | Health scope when needed | Owner/manager | Yes |
| `DELETE /v1/reminders/{id}` | Creator/manager/owner per policy | Same family | Health scope when needed | Owner/manager | Yes |
| `GET /v1/reminders/{id}/executions` | Elder owner; authorized family manager | Same family | `HEALTH_MEDICATION` for medication | Owner/authorized manager | Yes for health |
| `POST /v1/reminder-executions/{id}/feedback` | Elder owner/device session only | Same family | No family read consent required to submit | Execution owner | Yes |
| `POST /v1/conversations` | Elder owner/device, or authorized client starting an explicit bridge | Same family | `VOICE` if audio; summary scope only for later sharing | Owner/device | Start/end audit |
| `GET /v1/conversations/{id}` | Owner; family member only with `CONVERSATION_SUMMARY` and summary permission | Same family | `CONVERSATION_SUMMARY` for non-owner | Owner/authorized grantee | Sensitive read yes |
| `POST /v1/conversations/{id}/end` | Conversation owner/device | Same family | Existing session scope | Owner/device | Yes |
| `POST /v1/conversations/{id}/summary` | Owner or authorized family reader | Same family | `CONVERSATION_SUMMARY` | Owner/authorized grantee | Yes |
| WSS `/v1/ws/conversations/{id}` | Owner/device session; family bridge only by explicit policy | Same family | `VOICE` for audio; summary not implied | Conversation owner | Connect/end/security events |

Family members never receive raw transcript by default. If the client ASR/TTS is local, WSS carries state/text only and `VOICE` governs any server processing.

### 3.6 Signal, notification and reports

| Method / endpoint | Caller | Family | Consent | Owner | Audit |
| --- | --- | --- | --- | --- | --- |
| `GET /v1/signal-events` | CHILD/CAREGIVER with signal-read; elder sees only own safety status | Same family | `NOTIFICATION_TO_FAMILY`; health scope for health signal | Event owner/authorized recipient | Yes for detail |
| `GET /v1/signal-events/{id}` | Authorized family recipient or event subject | Same family | Same; `HEALTH_MEDICATION` for health | Event owner/recipient | Yes |
| `POST /v1/signal-events/{id}/ack` | Authorized family recipient | Same family | Notification scope | Recipient | Yes |
| `POST /v1/signal-events/{id}/contact` | Authorized recipient or event owner | Same family | Notification scope; emergency contact policy | Actor may act, not change owner | Yes |
| `POST /v1/signal-events/{id}/false-positive` | Authorized recipient | Same family | Notification scope | Recipient | Yes |
| `POST /v1/signal-events/{id}/resolve` | Authorized recipient/system transition | Same family | Relevant scope | Event manager | Yes |
| `GET /v1/notifications` | Recipient user only | Family inferred from notification | Notification scope | Recipient | Read action audit |
| `GET /v1/notifications/{id}` | Recipient user only | Inferred | Notification scope | Recipient | Yes for sensitive |
| `POST /v1/notifications/{id}/read` | Recipient user only | Inferred | Existing notification authorization | Recipient | Yes |
| `POST /v1/notifications/{id}/action` | Recipient with signal action permission | Inferred | Notification scope | Recipient | Yes |
| `GET /v1/reports/weekly` | CHILD/CAREGIVER with report-read; elder only if product enables self view | Same family | Summary/health scopes reflected per metric | Report owner | Yes |
| `GET /v1/reports/weekly/{id}` | Same as list | Same family | Per-metric scope; missing data if denied | Report owner/reader | Yes |
| `POST /v1/reports/weekly` | Report manager/system; client cannot submit metrics | Same family | Required scopes for selected period | Report owner | Yes |

Signal details never include raw conversation, chain of thought, prompt, confidence number, provider secret or family internal note. `NOTIFICATION_TO_FAMILY` denial creates `WITHHELD`/no notification, not an implicit grant.

### 3.7 Emergency and device

| Method / endpoint | Caller | Family | Consent | Owner | Audit |
| --- | --- | --- | --- | --- | --- |
| `GET /v1/emergency/contacts` | Elder owner; delegated CHILD/CAREGIVER contact-manager | Same family | `NOTIFICATION_TO_FAMILY` for family visibility | Contact owner | Yes |
| `POST /v1/emergency/contacts` | Elder or delegated contact-manager | Same family | Notification scope for family contact | Owner | Yes |
| `PATCH /v1/emergency/contacts/{id}` | Owner/contact-manager | Same family | Same | Contact owner | Yes |
| `DELETE /v1/emergency/contacts/{id}` | Owner/contact-manager | Same family | Same | Contact owner | Yes |
| `POST /v1/emergency/calls` | Elder/device; authorized family may initiate bridge | Same family | Emergency policy; no raw conversation scope implied | Elder or event owner | Yes |
| `GET /v1/emergency/calls/{id}` | Call initiator, elder owner, authorized recipient | Same family | Notification scope for family status | Call owner | Yes |
| `POST /v1/devices/register` | Elder owner or delegated device-admin; device proof required | Same family | `CAMERA_PROXIMITY` only when enabling camera; no image upload | Device owner | Yes |
| `GET /v1/devices` | Device owner; family device-read permission | Same family | Camera state disclosure only, no image | Owner/admin | Yes |
| `GET /v1/devices/{id}` | Same as list | Same family | Same | Device owner/admin | Yes |
| `POST /v1/devices/{id}/heartbeat` | Bound device session with device proof | Bound family | No content consent; only capability fields | Device itself | State change audit |
| `PATCH /v1/devices/{id}/settings` | Device owner/device-admin | Same family | Relevant camera/notification scope | Device owner/admin | Yes |
| `POST /v1/devices/{id}/unbind` | Device owner/family admin | Same family | No | Device owner/admin | Yes |

Camera proximity only stores permission/capability/event time, never frames or biometric features. BLE button events remain local until emergency flow is submitted.

### 3.8 Audit and data lifecycle

| Method / endpoint | Caller | Family | Consent | Owner | Audit |
| --- | --- | --- | --- | --- | --- |
| `GET /v1/audit-logs` | Actor reviewing own actions; family admin only within family; subject may view own data-access records | Explicit family filter from membership | Sensitive target scope required | Actor/subject scoped | Read itself audited |
| `POST /v1/data-exports` | User for own account; family admin only for authorized family export | Same family for family scope | Export includes only granted/owned scopes | Requesting user | Yes |
| `GET /v1/data-exports/{id}` | Request creator only | Inferred | Same as export | Request creator | Yes |
| `POST /v1/account-deletion-requests` | Current user + recent re-auth | Own account/family consequences | No new scope; invalidates data | Current user | Yes |
| `GET /v1/account-deletion-requests/{id}` | Request creator only | Inferred | No | Request creator | Yes |
| `POST /v1/account-deletion-requests/{id}/cancel` | Request creator before execution | Inferred | No | Request creator | Yes |

## 4. Authorization decision examples

### Daughter reads Memory

```text
Bearer valid?
→ FamilyMember ACTIVE?
→ role/permission memory-read?
→ Memory family matches server session?
→ verification_status CONFIRMED and not deleted/revoked/expired?
→ Consent(subject=elder, grantee=daughter, scope=FAMILY_MEMORY) GRANTED?
→ allow + MEMORY_READ audit
```

### Health reminder history

Even if daughter is `CHILD`, `GET /reminders/{id}/executions` for `MEDICATION` requires `HEALTH_MEDICATION`; otherwise return 403 or a redacted 404 according to enumeration policy.

### Memory delete and revoke

The subject or delegated data editor can request deletion/revoke. The service immediately removes the resource from API/RAG/cache results, appends AuditLog, and queues object/embedding cleanup. Physical worker completion does not restore visibility.

### Signal contact

`POST /signal-events/{id}/contact` checks recipient membership, event status, notification consent and emergency policy. It writes an audit action and creates a contact/emergency record; it never changes `NO_ANSWER` to `CONNECTED`.

## 5. Privacy and IDOR checklist

- No endpoint accepts arbitrary `user_id` as an authorization bypass; subject/user filters are intersected with token membership.
- No public endpoint exists for `MemoryEmbedding`, `MemoryChunk`, `DeviceSession`, `NotificationAttempt`, provider config or raw conversation.
- 404 may intentionally hide cross-family UUIDs; error bodies never confirm whether a hidden ID exists.
- Sensitive GETs write audit records without persisting raw content in audit metadata.
- UI permission denial does not create a server-side grant; client-side cached data is invalidated on revoke.

