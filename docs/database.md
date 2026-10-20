# 当前数据库设计

PostgreSQL/pgvector 是唯一事实库，异步 SQLAlchemy 模型注册于 [platform/models.py](../backend/app/platform/models.py)。当前只有以下 22 张业务/平台表；Alembic 自带的 alembic_version 不计入。没有 conversation_message、weekly_report、emergency_contact、interaction_metric 等规划表。

## 关系和约定

- User 通过 FamilyMember 加入 Family；Consent 连接家庭、主体和指定 grantee。角色属于家庭关系，不属于全局用户身份。
- Memory → MemoryChunk → MemoryEmbedding；FileAsset 关联主体、家庭和 Memory。向量/文件读取仍检查源资源和当前授权，不独立授予访问权。
- Reminder → ReminderExecution；Conversation → SignalEvent → Notification → NotificationAttempt。
- ProactivePreference / DailyCounter、NotificationPreference 按家庭、主体或收件人隔离；Task 使用业务键和资源版本协作。
- 主键通常 UUIDv7，计数/共同设置使用复合主键；时间为带时区时间戳，调度另保存本地日期、时间、IANA 时区。FamilyMember 的公开 version 根据 updated_at 计算，不是独立列。
- 外键和 CHECK/唯一约束保护结构；家庭/Consent/状态授权由服务查询执行，不能只依靠外键或 UI。

## 字段字典

下列是当前模型字段，不复制 API DTO。PK 为主键，NULL 表示可空；默认值区分数据库 SQL 与应用创建时赋值。未列默认值不代表 API 可省略。完整 SQL 与建表顺序以 [Alembic 迁移](../backend/alembic/versions/) 为准。

### user

身份与可访问状态；实际登录仍为虚构 Demo，手机号字段不代表短信能力。 模型：[User](../backend/app/modules/auth/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `global_status` | `VARCHAR(16)` | NOT NULL | SQL: ACTIVE |
| `display_name` | `VARCHAR(120)` | NOT NULL | — |
| `phone_ciphertext` | `TEXT` | NULL | — |
| `phone_hash` | `CHAR(64)` | NULL | — |
| `phone_last4` | `CHAR(4)` | NULL | — |
| `accessibility_settings` | `JSONB` | NOT NULL | SQL: {} |
| `timezone` | `VARCHAR(64)` | NOT NULL | SQL: Asia/Shanghai |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `deleted_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |

约束与索引：

- CHECK `global_status IN ('ACTIVE','SUSPENDED','DELETED')`
- CHECK `jsonb_typeof(accessibility_settings) = 'object'`
- CHECK `length(display_name) > 0`
- UNIQUE `phone_hash`

### family

家庭边界与创建者。 模型：[Family](../backend/app/modules/family/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `name` | `VARCHAR(120)` | NOT NULL | — |
| `created_by_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `status` | `VARCHAR(16)` | NOT NULL | SQL: ACTIVE |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `deleted_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |

约束与索引：

- CHECK `length(name) > 0`
- CHECK `status IN ('ACTIVE','SUSPENDED','DELETED')`

### audit_log

安全、敏感访问和幂等元数据；业务追加，不存正文。 模型：[AuditLog](../backend/app/modules/audit/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `actor_user_id` | `UUID` | NULL | → user.id，ON DELETE SET NULL |
| `family_id` | `UUID` | NULL | → family.id，ON DELETE SET NULL |
| `action` | `VARCHAR(64)` | NOT NULL | — |
| `target_type` | `VARCHAR(48)` | NOT NULL | — |
| `target_id` | `UUID` | NULL | — |
| `reason` | `VARCHAR(240)` | NULL | — |
| `request_id` | `VARCHAR(96)` | NULL | — |
| `result` | `VARCHAR(16)` | NOT NULL | SQL: SUCCEEDED |
| `metadata_redacted` | `JSONB` | NOT NULL | SQL: {} |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `jsonb_typeof(metadata_redacted) = 'object'`
- CHECK `result IN ('SUCCEEDED','FAILED','DENIED')`
- INDEX `ix_audit_actor_created` (audit_log.actor_user_id, audit_log.created_at)

### family_member

家庭内角色、状态和细粒度权限。 模型：[FamilyMember](../backend/app/modules/family/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `family_id` | `UUID` | NOT NULL | → family.id，ON DELETE RESTRICT |
| `user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `role` | `VARCHAR(32)` | NOT NULL | — |
| `status` | `VARCHAR(16)` | NOT NULL | SQL: PENDING |
| `permission_codes` | `JSONB` | NOT NULL | SQL: {} |
| `invited_by_user_id` | `UUID` | NULL | → user.id，ON DELETE SET NULL |
| `joined_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `left_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `jsonb_typeof(permission_codes) = 'object'`
- CHECK `role IN ('ELDER','CHILD','CAREGIVER','EMERGENCY_CONTACT')`
- CHECK `status IN ('PENDING','ACTIVE','REVOKED','LEFT')`
- INDEX `ix_member_family_status` (family_member.family_id, family_member.status)
- UNIQUE INDEX `uq_member_current` (family_member.family_id, family_member.user_id) WHERE `status IN ('PENDING','ACTIVE')`

### family_invitation

一次邀请的摘要、目标角色、次数和期限。 模型：[FamilyInvitation](../backend/app/modules/family/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `family_id` | `UUID` | NOT NULL | → family.id，ON DELETE RESTRICT |
| `created_by_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `token_hash` | `CHAR(64)` | NOT NULL | — |
| `target_role` | `VARCHAR(32)` | NOT NULL | — |
| `expires_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | — |
| `max_usage` | `INTEGER` | NOT NULL | SQL: 1 |
| `used_count` | `INTEGER` | NOT NULL | SQL: 0 |
| `used_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `status` | `VARCHAR(16)` | NOT NULL | SQL: ACTIVE |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `expires_at > created_at`
- CHECK `max_usage > 0 AND used_count >= 0 AND used_count <= max_usage`
- CHECK `status IN ('ACTIVE','USED','REVOKED','EXPIRED')`
- CHECK `target_role IN ('ELDER','CHILD','CAREGIVER','EMERGENCY_CONTACT')`
- UNIQUE `token_hash`

### consent

按主体/grantee/scope 追加的授权历史，以最新记录判定有效性。 模型：[Consent](../backend/app/modules/consent/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `family_id` | `UUID` | NOT NULL | → family.id，ON DELETE RESTRICT |
| `subject_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `grantor_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `grantee_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `scope` | `VARCHAR(40)` | NOT NULL | — |
| `status` | `VARCHAR(16)` | NOT NULL | SQL: GRANTED |
| `version` | `INTEGER` | NOT NULL | SQL: 1 |
| `source` | `VARCHAR(24)` | NOT NULL | SQL: SETTINGS |
| `granted_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `revoked_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `expires_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `replaced_by_id` | `UUID` | NULL | → consent.id，ON DELETE SET NULL |
| `audit_log_id` | `UUID` | NULL | → audit_log.id，ON DELETE SET NULL |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `scope IN ('VOICE','PORTRAIT','FAMILY_MEMORY','HEALTH_MEDICATION','CONVERSATION_SUMMARY','CAMERA_PROXIMITY','NOTIFICATION_TO_FAMILY')`
- CHECK `source IN ('ONBOARDING','SETTINGS','IMPORT')`
- CHECK `status <> 'GRANTED' OR granted_at IS NOT NULL`
- CHECK `status <> 'REVOKED' OR revoked_at IS NOT NULL`
- CHECK `status IN ('GRANTED','REVOKED','EXPIRED')`
- CHECK `version > 0`
- INDEX `ix_consent_granted` (consent.family_id, consent.subject_user_id, consent.grantee_user_id, consent.scope) WHERE `status = 'GRANTED'`

### device_binding

登录设备绑定；不是公开设备注册/心跳功能。 模型：[DeviceBinding](../backend/app/modules/device/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `device_id_hash` | `CHAR(64)` | NOT NULL | — |
| `owner_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `device_type` | `VARCHAR(32)` | NOT NULL | — |
| `app_version` | `VARCHAR(64)` | NOT NULL | — |
| `os_version` | `VARCHAR(64)` | NOT NULL | — |
| `kiosk_status` | `VARCHAR(24)` | NOT NULL | SQL: UNKNOWN |
| `wakeword_status` | `VARCHAR(24)` | NOT NULL | SQL: UNKNOWN |
| `ble_status` | `VARCHAR(24)` | NOT NULL | SQL: DISCONNECTED |
| `camera_permission` | `VARCHAR(16)` | NOT NULL | SQL: UNKNOWN |
| `phone_permission` | `VARCHAR(16)` | NOT NULL | SQL: UNKNOWN |
| `capabilities` | `JSONB` | NOT NULL | SQL: {} |
| `status` | `VARCHAR(16)` | NOT NULL | SQL: ACTIVE |
| `last_seen_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `last_state_change_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `ble_status IN ('DISCONNECTED','CONNECTING','CONNECTED','LOW_BATTERY','ERROR')`
- CHECK `camera_permission IN ('UNKNOWN','GRANTED','DENIED')`
- CHECK `device_type IN ('ANDROID_TABLET','ANDROID_PHONE','OTHER')`
- CHECK `jsonb_typeof(capabilities) = 'object'`
- CHECK `kiosk_status IN ('UNKNOWN','ACTIVE','CONFIG_ERROR','DISABLED')`
- CHECK `phone_permission IN ('UNKNOWN','GRANTED','DENIED')`
- CHECK `status IN ('ACTIVE','UNBOUND','LOST','DISABLED')`
- CHECK `wakeword_status IN ('UNKNOWN','READY','DISABLED','ERROR')`
- INDEX `ix_device_owner_seen` (device_binding.owner_user_id, device_binding.last_seen_at)
- UNIQUE `device_id_hash`

### device_session

用户登录会话和刷新令牌摘要；退出/复用可撤销。 模型：[DeviceSession](../backend/app/modules/auth/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `device_binding_id` | `UUID` | NULL | → device_binding.id，ON DELETE SET NULL |
| `refresh_token_hash` | `CHAR(64)` | NOT NULL | — |
| `issued_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `expires_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | — |
| `revoked_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `logout_reason` | `VARCHAR(32)` | NULL | — |
| `last_seen_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `ip_hash` | `CHAR(64)` | NULL | — |
| `user_agent_hash` | `CHAR(64)` | NULL | — |

约束与索引：

- CHECK `expires_at > issued_at`
- UNIQUE `refresh_token_hash`

### memory

版本化家庭记忆；候选不是事实，字段内容仍属于敏感数据。 模型：[Memory](../backend/app/modules/memory/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `family_id` | `UUID` | NOT NULL | → family.id，ON DELETE RESTRICT |
| `subject_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `source_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `type` | `VARCHAR(24)` | NOT NULL | — |
| `title` | `VARCHAR(240)` | NOT NULL | — |
| `content` | `TEXT` | NOT NULL | — |
| `source` | `VARCHAR(24)` | NOT NULL | — |
| `version` | `INTEGER` | NOT NULL | SQL: 1 |
| `attributes` | `JSONB` | NOT NULL | SQL: {} |
| `required_consent_scope` | `VARCHAR(40)` | NOT NULL | SQL: FAMILY_MEMORY |
| `verification_status` | `VARCHAR(16)` | NOT NULL | SQL: PENDING |
| `verified_by` | `UUID` | NULL | → user.id，ON DELETE SET NULL |
| `verified_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `visibility` | `VARCHAR(24)` | NOT NULL | SQL: AUTHORIZED_SCOPE |
| `expires_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `revoked_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `deleted_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `jsonb_typeof(attributes) = 'object'`
- CHECK `required_consent_scope IN ('VOICE','PORTRAIT','FAMILY_MEMORY','HEALTH_MEDICATION','CONVERSATION_SUMMARY','CAMERA_PROXIMITY','NOTIFICATION_TO_FAMILY')`
- CHECK `source IN ('FAMILY_MEMBER','USER','AI_CANDIDATE','IMPORT')`
- CHECK `type IN ('PERSON','RELATIONSHIP','EVENT','PLACE','PREFERENCE','TABOO','PHOTO')`
- CHECK `verification_status <> 'CONFIRMED' OR verified_at IS NOT NULL`
- CHECK `verification_status IN ('PENDING','CONFIRMED','REJECTED','REVOKED','DELETED')`
- CHECK `version > 0 AND length(title) > 0`
- CHECK `visibility IN ('OWNER_ONLY','AUTHORIZED_SCOPE','SPECIFIC_CONSENT')`
- INDEX `ix_memory_scope` (memory.family_id, memory.subject_user_id, memory.verification_status)

### file_asset

私有对象元数据；当前只提供关联记忆的照片流程。 模型：[FileAsset](../backend/app/modules/memory/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `owner_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `family_id` | `UUID` | NOT NULL | → family.id，ON DELETE RESTRICT |
| `memory_id` | `UUID` | NULL | → memory.id，ON DELETE SET NULL |
| `conversation_id` | `UUID` | NULL | → conversation.id，ON DELETE SET NULL |
| `object_key` | `VARCHAR(512)` | NOT NULL | — |
| `media_type` | `VARCHAR(24)` | NOT NULL | — |
| `mime_type` | `VARCHAR(120)` | NOT NULL | — |
| `size_bytes` | `BIGINT` | NOT NULL | — |
| `checksum` | `CHAR(64)` | NOT NULL | — |
| `status` | `VARCHAR(24)` | NOT NULL | SQL: PENDING_UPLOAD |
| `retention_until` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `deleted_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `media_type IN ('PHOTO','AUDIO','OTHER')`
- CHECK `size_bytes >= 0`
- CHECK `status IN ('PENDING_UPLOAD','AVAILABLE','QUARANTINED','DELETE_REQUESTED','DELETED','FAILED')`
- INDEX `ix_file_memory_status` (file_asset.memory_id, file_asset.status)
- UNIQUE `object_key`

### reminder

结构化周期/时区及当前版本；next_due_at 供 worker 调度。 模型：[Reminder](../backend/app/modules/reminder/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `family_id` | `UUID` | NOT NULL | → family.id，ON DELETE RESTRICT |
| `owner_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `created_by_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `type` | `VARCHAR(24)` | NOT NULL | — |
| `title` | `VARCHAR(240)` | NOT NULL | — |
| `content` | `TEXT` | NOT NULL | — |
| `schedule_time_local` | `TIME WITHOUT TIME ZONE` | NOT NULL | — |
| `timezone` | `VARCHAR(64)` | NOT NULL | — |
| `start_date` | `DATE` | NOT NULL | — |
| `end_date` | `DATE` | NULL | — |
| `recurrence_kind` | `VARCHAR(24)` | NOT NULL | SQL: ONCE |
| `recurrence_interval` | `INTEGER` | NOT NULL | SQL: 1 |
| `days_of_week` | `SMALLINT[]` | NOT NULL | SQL: {} |
| `quiet_hours_start` | `TIME WITHOUT TIME ZONE` | NULL | — |
| `quiet_hours_end` | `TIME WITHOUT TIME ZONE` | NULL | — |
| `quiet_hours_timezone` | `VARCHAR(64)` | NULL | — |
| `escalation_policy` | `JSONB` | NOT NULL | SQL: {} |
| `active` | `BOOLEAN` | NOT NULL | SQL: true |
| `version` | `INTEGER` | NOT NULL | SQL: 1 |
| `next_due_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `deleted_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |

约束与索引：

- CHECK `(quiet_hours_start IS NULL AND quiet_hours_end IS NULL AND quiet_hours_timezone IS NULL) OR (quiet_hours_start IS NOT NULL AND quiet_hours_end IS NOT NULL AND quiet_hours_timezone IS NOT NULL)`
- CHECK `days_of_week <@ ARRAY[0,1,2,3,4,5,6]::smallint[]`
- CHECK `end_date IS NULL OR end_date >= start_date`
- CHECK `jsonb_typeof(escalation_policy) = 'object'`
- CHECK `recurrence_interval > 0 AND version > 0`
- CHECK `recurrence_kind IN ('ONCE','DAILY','WEEKLY','INTERVAL')`
- CHECK `type IN ('CALENDAR','WEATHER','MEDICATION','WATER','CLOTHING','COMPANIONSHIP')`
- INDEX `ix_reminder_due` (reminder.owner_user_id, reminder.active, reminder.next_due_at)
- INDEX `ix_reminder_family_owner` (reminder.family_id, reminder.owner_user_id)

### reminder_execution

一次发生和反馈；occurrence_key 保证幂等，不等于真实服药或送达。 模型：[ReminderExecution](../backend/app/modules/reminder/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `reminder_id` | `UUID` | NOT NULL | → reminder.id，ON DELETE RESTRICT |
| `owner_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `occurrence_key` | `VARCHAR(96)` | NOT NULL | — |
| `scheduled_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | — |
| `local_date` | `DATE` | NOT NULL | — |
| `local_time` | `TIME WITHOUT TIME ZONE` | NOT NULL | — |
| `triggered_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `feedback_status` | `VARCHAR(20)` | NOT NULL | SQL: PENDING |
| `feedback_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `feedback_note` | `TEXT` | NULL | — |
| `source` | `VARCHAR(16)` | NOT NULL | SQL: ONLINE |
| `next_due_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `attempt_count` | `INTEGER` | NOT NULL | SQL: 0 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `attempt_count >= 0`
- CHECK `feedback_status IN ('PENDING','DONE','LATER','SKIPPED','NO_RESPONSE')`
- CHECK `source IN ('ONLINE','OFFLINE')`
- INDEX `ix_execution_owner_time` (reminder_execution.owner_user_id, reminder_execution.scheduled_at, reminder_execution.feedback_status)
- UNIQUE `reminder_id, occurrence_key`

### conversation

本人文字会话、受控摘要与序号/租约元数据；没有持久逐字消息表。 模型：[Conversation](../backend/app/modules/conversation/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `owner_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `family_id` | `UUID` | NOT NULL | → family.id，ON DELETE RESTRICT |
| `device_binding_id` | `UUID` | NULL | → device_binding.id，ON DELETE SET NULL |
| `started_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `ended_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `status` | `VARCHAR(20)` | NOT NULL | SQL: ACTIVE |
| `summary_status` | `VARCHAR(20)` | NOT NULL | SQL: NOT_REQUESTED |
| `summary_text` | `TEXT` | NULL | — |
| `summary_version` | `INTEGER` | NOT NULL | SQL: 1 |
| `summary_retention_until` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `provider_metadata` | `JSONB` | NOT NULL | SQL: {} |
| `deleted_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `backend_state` | `VARCHAR(16)` | NOT NULL | SQL: IDLE |
| `input_mode` | `VARCHAR(24)` | NOT NULL | SQL: TEXT |
| `client_sequence` | `BIGINT` | NOT NULL | SQL: 0 |
| `server_sequence` | `BIGINT` | NOT NULL | SQL: 0 |

约束与索引：

- CHECK `backend_state IN ('IDLE','LISTENING','THINKING','SPEAKING','WARNING','OFFLINE','ERROR')`
- CHECK `client_sequence >= 0 AND server_sequence >= 0`
- CHECK `ended_at IS NULL OR ended_at >= started_at`
- CHECK `input_mode IN ('VOICE','TEXT','LOCAL_WAKEWORD')`
- CHECK `jsonb_typeof(provider_metadata) = 'object'`
- CHECK `status IN ('ACTIVE','COMPLETED','INTERRUPTED','FAILED','DELETED')`
- CHECK `summary_status IN ('NOT_REQUESTED','PENDING','READY','FAILED','DELETED')`
- CHECK `summary_version > 0`
- INDEX `ix_conversation_owner_started` (conversation.owner_user_id, conversation.started_at)

### memory_chunk

可失效的文本分块，由源记忆级联关联。 模型：[MemoryChunk](../backend/app/modules/memory/index_models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `memory_id` | `UUID` | NOT NULL | → memory.id，ON DELETE CASCADE |
| `ordinal` | `INTEGER` | NOT NULL | SQL: 0 |
| `content` | `TEXT` | NOT NULL | — |
| `content_hash` | `CHAR(64)` | NOT NULL | — |
| `status` | `VARCHAR(16)` | NOT NULL | SQL: ACTIVE |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `deleted_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |

约束与索引：

- CHECK `ordinal >= 0`
- CHECK `status IN ('ACTIVE','STALE','DELETED')`
- UNIQUE `memory_id, ordinal`

### memory_embedding

当前为 8 维 Mock 向量，metadata 保存源版本，不单独构成可读事实。 模型：[MemoryEmbedding](../backend/app/modules/memory/index_models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `memory_chunk_id` | `UUID` | NOT NULL | → memory_chunk.id，ON DELETE CASCADE |
| `provider` | `VARCHAR(64)` | NOT NULL | — |
| `model` | `VARCHAR(128)` | NOT NULL | — |
| `model_version` | `VARCHAR(64)` | NOT NULL | — |
| `dimension` | `INTEGER` | NOT NULL | — |
| `embedding` | `VECTOR` | NULL | — |
| `status` | `VARCHAR(16)` | NOT NULL | SQL: PENDING |
| `metadata` | `JSONB` | NOT NULL | SQL: {} |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `invalidated_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |

约束与索引：

- CHECK `dimension > 0`
- CHECK `jsonb_typeof(metadata) = 'object'`
- CHECK `status <> 'ACTIVE' OR (embedding IS NOT NULL AND vector_dims(embedding) = dimension AND vector_norm(embedding) > 0)`
- CHECK `status IN ('PENDING','ACTIVE','STALE','DELETED','FAILED')`

### task_outbox

后台任务、唯一业务键、租约、重试和 DEAD。 模型：[Task](../backend/app/platform/tasks.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `family_id` | `UUID` | NOT NULL | → family.id，ON DELETE RESTRICT |
| `resource_id` | `UUID` | NOT NULL | — |
| `resource_version` | `INTEGER` | NOT NULL | — |
| `kind` | `VARCHAR(32)` | NOT NULL | — |
| `business_key` | `VARCHAR(200)` | NOT NULL | — |
| `status` | `VARCHAR(16)` | NOT NULL | SQL: PENDING |
| `attempts` | `INTEGER` | NOT NULL | SQL: 0 |
| `max_attempts` | `INTEGER` | NOT NULL | SQL: 5 |
| `available_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `lease_token` | `UUID` | NULL | — |
| `lease_until` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `last_error_code` | `VARCHAR(64)` | NULL | — |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `(status = 'RUNNING' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR (status <> 'RUNNING' AND lease_token IS NULL AND lease_until IS NULL)`
- CHECK `attempts >= 0 AND max_attempts > 0 AND attempts <= max_attempts`
- CHECK `kind IN ('MEMORY_INDEX','MEMORY_CLEANUP','FILE_CLEANUP','CONVERSATION_SUMMARY','CONVERSATION_SUMMARY_CLEANUP','NOTIFICATION_DISPATCH','SIGNAL_CLEANUP','NOTIFICATION_CLEANUP')`
- CHECK `resource_version > 0`
- CHECK `status IN ('PENDING','RUNNING','RETRY','SUCCEEDED','DEAD')`
- INDEX `ix_task_lease` (task_outbox.status, task_outbox.lease_until)
- INDEX `ix_task_ready` (task_outbox.status, task_outbox.available_at)
- UNIQUE `business_key`

### proactive_preference

家属提议/老人确认的共同版本和本人暂停。 模型：[ProactivePreference](../backend/app/modules/conversation/proactive_models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `family_id` | `UUID` | PK | → family.id，ON DELETE RESTRICT |
| `owner_user_id` | `UUID` | PK | → user.id，ON DELETE RESTRICT |
| `timezone` | `VARCHAR(64)` | NOT NULL | — |
| `window_start` | `TIME WITHOUT TIME ZONE` | NOT NULL | — |
| `window_end` | `TIME WITHOUT TIME ZONE` | NOT NULL | — |
| `quiet_start` | `TIME WITHOUT TIME ZONE` | NULL | — |
| `quiet_end` | `TIME WITHOUT TIME ZONE` | NULL | — |
| `daily_cap` | `SMALLINT` | NOT NULL | SQL: 0 |
| `version` | `INTEGER` | NOT NULL | SQL: 1 |
| `proposed_by_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `confirmed_by_user_id` | `UUID` | NULL | → user.id，ON DELETE RESTRICT |
| `confirmed_version` | `INTEGER` | NULL | — |
| `paused_on` | `DATE` | NULL | — |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `(confirmed_by_user_id IS NULL AND confirmed_version IS NULL) OR (confirmed_by_user_id IS NOT NULL AND confirmed_version IS NOT NULL AND confirmed_by_user_id = owner_user_id AND confirmed_version = version)`
- CHECK `(quiet_start IS NULL) = (quiet_end IS NULL)`
- CHECK `daily_cap BETWEEN 0 AND 3`
- CHECK `version > 0`

### proactive_daily_counter

按家庭、主体和本地日期计算的使用额度。 模型：[ProactiveDailyCounter](../backend/app/modules/conversation/proactive_models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `family_id` | `UUID` | PK | → proactive_preference.family_id，ON DELETE CASCADE |
| `owner_user_id` | `UUID` | PK | → proactive_preference.owner_user_id，ON DELETE CASCADE |
| `local_date` | `DATE` | PK | — |
| `used_count` | `SMALLINT` | NOT NULL | SQL: 0 |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `used_count BETWEEN 0 AND 3`

### signal_event

受规则验证的有限非紧急事件；当前 source_message_id 留空，不创建伪持久化消息。 模型：[SignalEvent](../backend/app/modules/signal/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `owner_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `family_id` | `UUID` | NOT NULL | → family.id，ON DELETE RESTRICT |
| `type` | `VARCHAR(32)` | NOT NULL | — |
| `severity` | `VARCHAR(8)` | NOT NULL | SQL: L1 |
| `source_conversation_id` | `UUID` | NULL | → conversation.id，ON DELETE SET NULL |
| `source_message_id` | `UUID` | NULL | — |
| `evidence_summary` | `TEXT` | NULL | — |
| `evidence_hash` | `VARCHAR(64)` | NULL | — |
| `confidence` | `NUMERIC(5, 4)` | NULL | — |
| `rule_id` | `VARCHAR(96)` | NULL | — |
| `rule_version` | `VARCHAR(64)` | NULL | — |
| `policy_version` | `VARCHAR(64)` | NOT NULL | — |
| `trigger_category` | `VARCHAR(64)` | NOT NULL | — |
| `consent_check_result` | `VARCHAR(16)` | NOT NULL | — |
| `status` | `VARCHAR(24)` | NOT NULL | SQL: DETECTED |
| `dedupe_key` | `VARCHAR(64)` | NULL | — |
| `duplicate_of_id` | `UUID` | NULL | → signal_event.id，ON DELETE SET NULL |
| `detected_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `validated_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `notified_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `last_action_by` | `UUID` | NULL | → user.id，ON DELETE SET NULL |
| `last_action_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `resolution_code` | `VARCHAR(32)` | NULL | — |
| `resolved_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `retention_until` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | — |
| `deleted_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |

约束与索引：

- CHECK `confidence BETWEEN 0 AND 1`
- CHECK `consent_check_result IN ('ALLOWED','DENIED','WITHHELD')`
- CHECK `retention_until >= detected_at`
- CHECK `severity IN ('L0','L1','L2','L3','L4')`
- CHECK `source_message_id IS NULL AND evidence_hash IS NULL`
- CHECK `status IN ('DETECTED','VALIDATED','NOTIFIED','ACKNOWLEDGED','CONTACTED','FALSE_POSITIVE','RESOLVED','WITHHELD','NOTIFICATION_FAILED')`
- CHECK `type IN ('PHYSICAL_DISCOMFORT','EMOTION_EXPRESSION','IMPORTANT_MEMORY','MISS_FAMILY','SCAM_RISK','EMERGENCY')`
- INDEX `ix_signal_dedupe` (signal_event.dedupe_key)
- INDEX `ix_signal_family_owner` (signal_event.family_id, signal_event.owner_user_id, signal_event.detected_at)

### notification

指定收件人的最小通知及派发/保留期限；SENT 不代表设备送达。 模型：[Notification](../backend/app/modules/notification/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `signal_event_id` | `UUID` | NULL | → signal_event.id，ON DELETE SET NULL |
| `reminder_execution_id` | `UUID` | NULL | → reminder_execution.id，ON DELETE SET NULL |
| `recipient_user_id` | `UUID` | NULL | → user.id，ON DELETE SET NULL |
| `recipient_contact_snapshot` | `JSONB` | NULL | — |
| `channel` | `VARCHAR(16)` | NOT NULL | — |
| `status` | `VARCHAR(20)` | NOT NULL | SQL: PENDING |
| `summary` | `TEXT` | NOT NULL | — |
| `policy_version` | `VARCHAR(64)` | NOT NULL | — |
| `provider` | `VARCHAR(64)` | NULL | — |
| `action` | `VARCHAR(24)` | NOT NULL | SQL: NONE |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `sent_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `delivered_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `read_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `action_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `error_code` | `VARCHAR(64)` | NULL | — |
| `dedupe_key` | `VARCHAR(64)` | NULL | — |
| `retention_until` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | — |
| `dispatch_deadline` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | — |
| `deleted_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |

约束与索引：

- CHECK `action IN ('NONE','ACKNOWLEDGED','CONTACTED','FALSE_POSITIVE')`
- CHECK `channel IN ('IN_APP','PUSH','SMS','PHONE')`
- CHECK `length(summary) <= 240`
- CHECK `retention_until >= created_at AND dispatch_deadline >= created_at`
- CHECK `status IN ('PENDING','QUEUED','SENT','DELIVERED','READ','FAILED','CANCELLED')`
- INDEX `ix_notification_recipient` (notification.recipient_user_id, notification.created_at)
- UNIQUE INDEX `ux_notification_active_dedupe` (notification.dedupe_key) WHERE `status <> 'CANCELLED' AND deleted_at IS NULL`

### notification_attempt

尝试号、固定错误和重试时间，不保存 Provider 私有正文。 模型：[NotificationAttempt](../backend/app/modules/notification/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `notification_id` | `UUID` | NOT NULL | → notification.id，ON DELETE CASCADE |
| `attempt_no` | `INTEGER` | NOT NULL | — |
| `provider` | `VARCHAR(64)` | NOT NULL | — |
| `status` | `VARCHAR(16)` | NOT NULL | SQL: STARTED |
| `started_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `finished_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |
| `provider_message_id` | `VARCHAR(160)` | NULL | — |
| `error_code` | `VARCHAR(64)` | NULL | — |
| `error_detail_redacted` | `TEXT` | NULL | — |
| `retry_at` | `TIMESTAMP WITH TIME ZONE` | NULL | — |

约束与索引：

- CHECK `attempt_no > 0`
- CHECK `status IN ('STARTED','SUCCEEDED','FAILED','RETRY_SCHEDULED')`
- UNIQUE `notification_id, attempt_no`

### notification_preference

收件人通知渠道/时区/免打扰，与老人主动邀请设置独立。 模型：[NotificationPreference](../backend/app/modules/notification/models.py)。

| 字段 | PostgreSQL 类型 | NULL / 键 | 默认或关联 |
| --- | --- | --- | --- |
| `id` | `UUID` | PK | 应用: uuid7() |
| `family_id` | `UUID` | NOT NULL | → family.id，ON DELETE RESTRICT |
| `owner_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `recipient_user_id` | `UUID` | NOT NULL | → user.id，ON DELETE RESTRICT |
| `channels` | `JSONB` | NOT NULL | — |
| `timezone` | `VARCHAR(64)` | NOT NULL | — |
| `quiet_hours_start` | `TIME WITHOUT TIME ZONE` | NULL | — |
| `quiet_hours_end` | `TIME WITHOUT TIME ZONE` | NULL | — |
| `version` | `INTEGER` | NOT NULL | SQL: 1 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | SQL: now() |

约束与索引：

- CHECK `(quiet_hours_start IS NULL) = (quiet_hours_end IS NULL)`
- CHECK `jsonb_typeof(channels) = 'array' AND channels <@ '["IN_APP","PUSH"]'::jsonb`
- CHECK `version > 0`
- UNIQUE `family_id, owner_user_id, recipient_user_id`

## 迁移和生命周期

保留现有全部 Alembic 历史，当前迁移头为 `20261019_week7_notifications`。从 backend/ 运行 `python -m alembic upgrade head`；修改数据库时新增兼容迁移，不因为文档整理重写旧迁移或删除已有数据。普通功能修改不要求空库回退演练。

撤权/删除先隐藏，后台清理向量、对象和通知；已删除行、外部字节和副本的清理是不同步骤。保留期和隐私规则只在 [security](security.md) 维护。真实账户删除/导出和备份期限尚未完成，见 [roadmap](roadmap.md)。

当前向量类型为 vector(8)，使用获准子集内的距离查询，没有独立向量服务或已实现的通用语义模型。换模型/维度需修改相应实现和迁移，不能只改文档。
