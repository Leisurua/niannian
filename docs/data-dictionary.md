# 念念（NianNian）数据字典

本字典是 [`database-design.md`](database-design.md) 的字段级配套文档。字段类型按 PostgreSQL/SQLAlchemy 2 表示；`timestamptz` 统一保存 UTC。敏感度沿用需求文档：S0 设备/普通配置，S1 普通家庭内容，S2 关系/照片/摘要，S3 原始音频、健康、紧急和高风险内容。

## 1. 约定

- 所有表默认有 `id uuid primary key`，由应用生成 UUIDv7；除非表格另有说明。
- `created_at timestamptz not null` 默认 `now()`；可变表通常有 `updated_at timestamptz not null`。
- 状态/类型使用 `varchar(32) + CHECK`，不使用难以演进的 PostgreSQL enum。
- `JSONB` 只用于设计文档规定的扩展配置，核心关联和权限字段均为结构化列。
- PII 以 `_ciphertext`、`_hash`、`_last4` 区分；密文和 hash 的具体算法属于应用安全实现，不在数据库中明文保存。

## 2. user

Purpose：全局身份、数据主体和可访问性偏好；不承载家庭内最终角色。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 用户标识 | S1 |
| global_status | varchar(16) | no | `ACTIVE` | CHECK ACTIVE/SUSPENDED/DELETED | 全局账户状态 | S1 |
| display_name | varchar(120) | no | - | CHECK length > 0 | 展示名称 | S1 |
| phone_ciphertext | text | yes | null | - | 应用层加密手机号 | S2 |
| phone_hash | char(64) | yes | null | UNIQUE when not null | 查找/去重 hash | S2 |
| phone_last4 | char(4) | yes | null | - | 脱敏展示 | S2 |
| accessibility_settings | jsonb | no | `{}` | JSON object | 字号、音量、语速、对比度 | S1 |
| timezone | varchar(64) | no | `Asia/Shanghai` | CHECK valid IANA in service | 用户本地时区 | S1 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |
| updated_at | timestamptz | no | now() | - | 更新时间 | S0 |
| deleted_at | timestamptz | yes | null | - | 业务删除标记，不代表审计删除 | S1 |

## 3. family

Purpose：家庭隔离边界和家庭级配置。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 家庭标识 | S1 |
| name | varchar(120) | no | - | CHECK length > 0 | 家庭名称 | S1 |
| created_by_user_id | uuid | no | - | FK user.id RESTRICT | 创建人 | S2 |
| status | varchar(16) | no | `ACTIVE` | CHECK ACTIVE/SUSPENDED/DELETED | 家庭状态 | S1 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |
| updated_at | timestamptz | no | now() | - | 更新时间 | S0 |
| deleted_at | timestamptz | yes | null | - | 家庭删除流程标记 | S1 |

## 4. family_member

Purpose：家庭成员、家庭角色和成员生命周期。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 成员关系标识 | S1 |
| family_id | uuid | no | - | FK family.id RESTRICT | 家庭 | S1 |
| user_id | uuid | no | - | FK user.id RESTRICT | 用户 | S1 |
| role | varchar(32) | no | - | CHECK ELDER/CHILD/CAREGIVER/EMERGENCY_CONTACT | 家庭内角色 | S2 |
| status | varchar(16) | no | `PENDING` | CHECK PENDING/ACTIVE/REVOKED/LEFT | 成员状态 | S1 |
| permission_codes | jsonb | no | `{}` | JSON object | 细粒度 UI/操作权限扩展；不替代 Consent | S2 |
| invited_by_user_id | uuid | yes | null | FK user.id SET NULL | 邀请人 | S2 |
| joined_at | timestamptz | yes | null | - | 生效时间 | S1 |
| left_at | timestamptz | yes | null | - | 离开/撤销时间 | S1 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |
| updated_at | timestamptz | no | now() | - | 更新时间 | S0 |

## 5. family_invitation

Purpose：一次性邀请码/二维码 token 生命周期。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 邀请标识 | S1 |
| family_id | uuid | no | - | FK family.id RESTRICT | 目标家庭 | S1 |
| created_by_user_id | uuid | no | - | FK user.id RESTRICT | 创建人 | S2 |
| token_hash | char(64) | no | - | UNIQUE | token hash；不保存明文 | S2 |
| target_role | varchar(32) | no | - | CHECK allowed FamilyMember role | 目标家庭角色 | S2 |
| expires_at | timestamptz | no | - | CHECK > created_at | 过期时间 | S1 |
| max_usage | integer | no | 1 | CHECK > 0 | 最大兑换次数 | S0 |
| used_count | integer | no | 0 | CHECK >= 0 and <= max_usage | 已兑换次数 | S0 |
| used_at | timestamptz | yes | null | - | 首次成功使用 | S1 |
| status | varchar(16) | no | `ACTIVE` | CHECK ACTIVE/USED/REVOKED/EXPIRED | 邀请状态 | S1 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |

## 6. consent

Purpose：分项、特定受授人的授权历史和当前有效授权。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 授权记录 | S2 |
| family_id | uuid | no | - | FK family.id RESTRICT | 授权家庭范围 | S2 |
| subject_user_id | uuid | no | - | FK user.id RESTRICT | 数据主体 | S3 |
| grantor_user_id | uuid | no | - | FK user.id RESTRICT | 实际确认/撤回者 | S2 |
| grantee_user_id | uuid | no | - | FK user.id RESTRICT | 被授权用户 | S2 |
| scope | varchar(40) | no | - | CHECK VOICE/PORTRAIT/FAMILY_MEMORY/HEALTH_MEDICATION/CONVERSATION_SUMMARY/CAMERA_PROXIMITY/NOTIFICATION_TO_FAMILY | 授权范围 | S2 |
| status | varchar(16) | no | `GRANTED` | CHECK GRANTED/REVOKED/EXPIRED | 当前记录状态 | S2 |
| version | integer | no | 1 | CHECK > 0 | 授权文案/版本 | S1 |
| source | varchar(24) | no | `SETTINGS` | CHECK ONBOARDING/SETTINGS/IMPORT | 授权来源 | S1 |
| granted_at | timestamptz | yes | null | Required when GRANTED | 生效时间 | S2 |
| revoked_at | timestamptz | yes | null | Required when REVOKED | 撤回时间 | S2 |
| expires_at | timestamptz | yes | null | - | 可选过期时间 | S2 |
| replaced_by_id | uuid | yes | null | FK consent.id SET NULL | 新版本授权 | S2 |
| audit_log_id | uuid | yes | null | FK audit_log.id SET NULL | 操作审计关联 | S2 |
| created_at | timestamptz | no | now() | - | 记录创建时间 | S0 |

## 7. device_session

Purpose：设备登录会话、refresh token 撤销和退出全部设备。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 会话标识 | S2 |
| user_id | uuid | no | - | FK user.id RESTRICT | 登录用户 | S2 |
| device_binding_id | uuid | yes | null | FK device_binding.id SET NULL | 设备绑定 | S1 |
| refresh_token_hash | char(64) | no | - | UNIQUE | refresh token hash | S3 |
| issued_at | timestamptz | no | now() | - | 签发时间 | S1 |
| expires_at | timestamptz | no | - | CHECK > issued_at | 过期时间 | S1 |
| revoked_at | timestamptz | yes | null | - | 撤销时间 | S1 |
| logout_reason | varchar(32) | yes | null | - | 退出/撤销原因 | S1 |
| last_seen_at | timestamptz | no | now() | - | 最近活动 | S0 |
| ip_hash | char(64) | yes | null | - | 脱敏来源 hash | S1 |
| user_agent_hash | char(64) | yes | null | - | 脱敏客户端 hash | S1 |

## 8. memory

Purpose：家庭事实、来源、确认状态和 RAG 权限入口。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 记忆标识 | S2 |
| family_id | uuid | no | - | FK family.id RESTRICT | 家庭边界 | S2 |
| subject_user_id | uuid | no | - | FK user.id RESTRICT | 记忆涉及/归属老人 | S2 |
| source_user_id | uuid | no | - | FK user.id RESTRICT | 提供者/创建者 | S2 |
| type | varchar(24) | no | - | CHECK PERSON/RELATIONSHIP/EVENT/PLACE/PREFERENCE/TABOO/PHOTO | 记忆类型 | S2 |
| title | varchar(240) | no | - | CHECK length > 0 | 可读标题 | S2 |
| content | text | no | - | - | 短文本事实内容 | S2/S3 by type |
| attributes | jsonb | no | `{}` | JSON object | 类型扩展字段 | S2 |
| required_consent_scope | varchar(40) | no | `FAMILY_MEMORY` | CHECK Consent scope | 检索所需 scope | S2 |
| verification_status | varchar(16) | no | `PENDING` | CHECK PENDING/CONFIRMED/REJECTED/REVOKED/DELETED | 事实可信状态 | S2 |
| verified_by | uuid | yes | null | FK user.id SET NULL | 确认人 | S2 |
| verified_at | timestamptz | yes | null | Required when CONFIRMED | 确认时间 | S2 |
| visibility | varchar(24) | no | `AUTHORIZED_SCOPE` | CHECK OWNER_ONLY/AUTHORIZED_SCOPE/SPECIFIC_CONSENT | 可见策略 | S2 |
| expires_at | timestamptz | yes | null | - | 事实过期时间 | S2 |
| revoked_at | timestamptz | yes | null | - | 授权/发布撤回时间 | S2 |
| deleted_at | timestamptz | yes | null | - | 业务删除时间 | S2 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |
| updated_at | timestamptz | no | now() | - | 更新时间 | S0 |

## 9. memory_chunk

Purpose：一个 Memory 的可检索片段和顺序。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | chunk 标识 | S2 |
| memory_id | uuid | no | - | FK memory.id CASCADE | 来源记忆 | S2 |
| ordinal | integer | no | 0 | UNIQUE(memory_id, ordinal), CHECK >= 0 | 片段顺序 | S0 |
| content | text | no | - | - | 检索片段文本 | S2/S3 |
| content_hash | char(64) | no | - | - | 去重/重建 hash | S2 |
| status | varchar(16) | no | `ACTIVE` | CHECK ACTIVE/STALE/DELETED | chunk 状态 | S1 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |
| deleted_at | timestamptz | yes | null | - | 删除/失效时间 | S2 |

## 10. memory_embedding

Purpose：provider/model/version 可替换的向量索引记录。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | embedding 标识 | S2 |
| memory_chunk_id | uuid | no | - | FK memory_chunk.id CASCADE | chunk | S2 |
| provider | varchar(64) | no | - | - | embedding provider | S0 |
| model | varchar(128) | no | - | - | 模型名称 | S0 |
| model_version | varchar(64) | no | - | - | 版本 | S0 |
| dimension | integer | no | - | CHECK > 0 | 向量维度 | S0 |
| embedding | vector | yes | null | Required when ACTIVE | pgvector 向量；部署时固定维度 | S2 |
| status | varchar(16) | no | `PENDING` | CHECK PENDING/ACTIVE/STALE/DELETED/FAILED | 索引状态 | S1 |
| metadata | jsonb | no | `{}` | JSON object, redacted | provider metadata | S0 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |
| invalidated_at | timestamptz | yes | null | - | 撤回/模型失效时间 | S1 |

## 11. file_asset

Purpose：MinIO/S3 对象的受控 metadata；不保存公开 URL。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 文件资产标识 | S2/S3 |
| owner_user_id | uuid | no | - | FK user.id RESTRICT | 数据主体/上传者 | S2 |
| family_id | uuid | no | - | FK family.id RESTRICT | 家庭范围 | S2 |
| memory_id | uuid | yes | null | FK memory.id SET NULL | 可选记忆归属 | S2 |
| conversation_id | uuid | yes | null | FK conversation.id SET NULL | 可选会话归属 | S3 |
| object_key | varchar(512) | no | - | UNIQUE | 私有 bucket key | S2 |
| media_type | varchar(24) | no | - | CHECK PHOTO/AUDIO/OTHER | 业务媒体类型 | S2/S3 |
| mime_type | varchar(120) | no | - | - | MIME | S0 |
| size_bytes | bigint | no | - | CHECK >= 0 | 文件大小 | S0 |
| checksum | char(64) | no | - | - | 完整性校验 | S0 |
| status | varchar(24) | no | `PENDING_UPLOAD` | CHECK PENDING_UPLOAD/AVAILABLE/QUARANTINED/DELETE_REQUESTED/DELETED/FAILED | 存储状态 | S1 |
| retention_until | timestamptz | yes | null | - | 清理时间，期限 TBD | S2/S3 |
| deleted_at | timestamptz | yes | null | - | 删除时间 | S2/S3 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |

## 12. reminder

Purpose：可查询的提醒规则、时间、周期和升级配置。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 提醒标识 | S2 |
| owner_user_id | uuid | no | - | FK user.id RESTRICT | 提醒对象 | S2 |
| created_by_user_id | uuid | no | - | FK user.id RESTRICT | 设置人 | S2 |
| type | varchar(24) | no | - | CHECK CALENDAR/WEATHER/MEDICATION/WATER/CLOTHING/COMPANIONSHIP | 提醒类型 | S2/S3 |
| title | varchar(240) | no | - | - | 提醒标题 | S2 |
| content | text | no | - | - | 播报内容 | S2/S3 |
| schedule_time_local | time | no | - | - | 当地时间 | S1 |
| timezone | varchar(64) | no | - | IANA validated in service | 规则时区 | S1 |
| start_date | date | no | - | - | 生效日期 | S1 |
| end_date | date | yes | null | CHECK >= start_date | 结束日期 | S1 |
| recurrence_kind | varchar(24) | no | `ONCE` | CHECK ONCE/DAILY/WEEKLY/INTERVAL | 重复类型 | S1 |
| recurrence_interval | integer | no | 1 | CHECK > 0 | 间隔 | S0 |
| days_of_week | smallint[] | no | `{}` | values 0..6 | 每周日期 | S0 |
| quiet_hours_start | time | yes | null | paired with end | 免打扰开始 | S1 |
| quiet_hours_end | time | yes | null | paired with start | 免打扰结束 | S1 |
| quiet_hours_timezone | varchar(64) | yes | null | IANA validated in service | 免打扰时区 | S1 |
| escalation_policy | jsonb | no | `{}` | JSON object | 渠道/延迟/级别扩展 | S2 |
| active | boolean | no | true | - | 是否启用 | S1 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |
| updated_at | timestamptz | no | now() | - | 更新时间 | S0 |
| deleted_at | timestamptz | yes | null | - | 删除标记 | S1 |

## 13. reminder_execution

Purpose：每次提醒触发的幂等记录和反馈。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 执行标识 | S2 |
| reminder_id | uuid | no | - | FK reminder.id RESTRICT | 提醒规则 | S2 |
| owner_user_id | uuid | no | - | FK user.id RESTRICT | 冗余查询/隔离字段 | S2 |
| occurrence_key | varchar(96) | no | - | UNIQUE(reminder_id, occurrence_key) | 幂等 occurrence | S0 |
| scheduled_at | timestamptz | no | - | - | UTC 计划时间 | S1 |
| local_date | date | no | - | - | 本地统计日期快照 | S1 |
| local_time | time | no | - | - | 本地计划时间快照 | S1 |
| triggered_at | timestamptz | yes | null | - | 实际触发 | S1 |
| feedback_status | varchar(20) | no | `PENDING` | CHECK PENDING/DONE/LATER/SKIPPED/NO_RESPONSE | 老人反馈 | S2/S3 |
| feedback_at | timestamptz | yes | null | - | 反馈时间 | S2 |
| feedback_note | text | yes | null | - | 跳过原因/备注，最小化 | S3 |
| source | varchar(16) | no | `ONLINE` | CHECK ONLINE/OFFLINE | 触发来源 | S1 |
| next_due_at | timestamptz | yes | null | - | LATER 下一次时间 | S1 |
| attempt_count | integer | no | 0 | CHECK >= 0 | 触发尝试次数 | S0 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |

## 14. conversation

Purpose：会话生命周期、摘要和 AI 调用上下文。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 会话标识 | S2/S3 |
| owner_user_id | uuid | no | - | FK user.id RESTRICT | 老人/会话主体 | S2 |
| family_id | uuid | no | - | FK family.id RESTRICT | 家庭范围 | S2 |
| device_binding_id | uuid | yes | null | FK device_binding.id SET NULL | 设备 | S1 |
| started_at | timestamptz | no | - | - | 开始时间 | S2 |
| ended_at | timestamptz | yes | null | CHECK >= started_at | 结束时间 | S2 |
| status | varchar(20) | no | `ACTIVE` | CHECK ACTIVE/COMPLETED/INTERRUPTED/FAILED/DELETED | 会话状态 | S2 |
| summary_status | varchar(20) | no | `NOT_REQUESTED` | CHECK NOT_REQUESTED/PENDING/READY/FAILED/DELETED | 摘要状态 | S2 |
| summary_text | text | yes | null | - | 受控摘要，不默认分享 | S3 |
| summary_retention_until | timestamptz | yes | null | - | 摘要清理时间，TBD | S3 |
| provider_metadata | jsonb | no | `{}` | redacted JSON | provider/model/prompt/latency | S1 |
| deleted_at | timestamptz | yes | null | - | 业务删除 | S2 |

## 15. conversation_message

Purpose：受控消息引用、顺序和 SignalEvent 来源；不是永久逐字稿表。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 消息标识 | S3 |
| conversation_id | uuid | no | - | FK conversation.id CASCADE | 会话 | S3 |
| sequence_no | integer | no | - | UNIQUE(conversation_id, sequence_no) | 顺序 | S0 |
| role | varchar(16) | no | - | CHECK USER/ASSISTANT/SYSTEM | 消息角色 | S2 |
| content_text | text | yes | null | optional redacted text | 仅在策略允许时保存 | S3 |
| content_hash | char(64) | yes | null | - | 不可逆关联 hash | S2 |
| sensitivity | varchar(8) | no | `S2` | CHECK S0/S1/S2/S3 | 数据级别 | S1 |
| asr_confidence | numeric(5,4) | yes | null | CHECK 0..1 | ASR 置信度 | S1 |
| provider_metadata | jsonb | no | `{}` | redacted JSON | 模型版本/延迟 | S1 |
| created_at | timestamptz | no | now() | - | 消息时间 | S2 |
| retention_until | timestamptz | yes | null | - | 清理时间，TBD | S3 |
| deleted_at | timestamptz | yes | null | - | 删除时间 | S3 |

## 16. interaction_metric

Purpose：按用户/日期生成周报所需结构化指标。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 聚合记录 | S1 |
| owner_user_id | uuid | no | - | FK user.id RESTRICT | 用户 | S2 |
| metric_date | date | no | - | UNIQUE(owner_user_id, metric_date, timezone_snapshot) | 本地统计日期 | S1 |
| timezone_snapshot | varchar(64) | no | - | IANA validated in service | 聚合时区 | S1 |
| interaction_count | integer | no | 0 | CHECK >= 0 | 互动次数 | S1 |
| conversation_seconds | integer | no | 0 | CHECK >= 0 | 交流秒数 | S1 |
| first_interaction_at | timestamptz | yes | null | - | 首次互动 | S1 |
| last_interaction_at | timestamptz | yes | null | - | 最后互动 | S1 |
| night_interaction_count | integer | no | 0 | CHECK >= 0 | 夜间互动次数，不推断睡眠 | S1 |
| reminder_done_count | integer | no | 0 | CHECK >= 0 | 已反馈完成 | S1 |
| reminder_later_count | integer | no | 0 | CHECK >= 0 | 稍后 | S1 |
| reminder_skipped_count | integer | no | 0 | CHECK >= 0 | 跳过 | S1 |
| reminder_no_response_count | integer | no | 0 | CHECK >= 0 | 未收到反馈 | S1 |
| emotion_signal_counts | jsonb | no | `{}` | JSON object | 交流观察分类计数 | S2 |
| interaction_time_distribution | jsonb | no | `{}` | JSON object | 时间桶分布 | S1 |
| repeated_topic_stats | jsonb | no | `{}` | JSON object | 相似主题统计 | S2 |
| source_cutoff_at | timestamptz | no | - | - | 统计截止时间 | S0 |
| computed_at | timestamptz | no | now() | - | 计算时间 | S0 |

## 17. signal_event

Purpose：可解释、可追踪的关注/诈骗/紧急事件。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 事件标识 | S3 |
| owner_user_id | uuid | no | - | FK user.id RESTRICT | 事件主体 | S3 |
| family_id | uuid | no | - | FK family.id RESTRICT | 家庭范围 | S2 |
| type | varchar(32) | no | - | CHECK PHYSICAL_DISCOMFORT/EMOTION_EXPRESSION/IMPORTANT_MEMORY/MISS_FAMILY/SCAM_RISK/EMERGENCY | 事件类型 | S3 |
| severity | varchar(8) | no | `L1` | CHECK L0/L1/L2/L3/L4 | 风险级别 | S3 |
| source_conversation_id | uuid | yes | null | FK conversation.id SET NULL | 来源会话 | S3 |
| source_message_id | uuid | yes | null | FK conversation_message.id SET NULL | 受控来源消息 | S3 |
| evidence_summary | text | yes | null | minimal evidence only | 最小必要证据摘要 | S3 |
| evidence_hash | char(64) | yes | null | - | 原始证据关联 hash | S3 |
| confidence | numeric(5,4) | yes | null | CHECK 0..1 | 分类置信度 | S2 |
| rule_id | varchar(96) | yes | null | - | 规则标识/策略代码 | S0 |
| rule_version | varchar(64) | yes | null | - | 规则版本 | S0 |
| policy_version | varchar(64) | no | - | - | 通知/授权策略版本 | S0 |
| consent_check_result | varchar(16) | no | - | CHECK ALLOWED/DENIED/WITHHELD | 授权检查结果 | S2 |
| status | varchar(24) | no | `DETECTED` | CHECK DETECTED/VALIDATED/NOTIFIED/ACKNOWLEDGED/CONTACTED/FALSE_POSITIVE/RESOLVED/WITHHELD/NOTIFICATION_FAILED | 事件状态 | S3 |
| dedupe_key | char(64) | yes | null | - | 去重窗口 hash | S2 |
| duplicate_of_id | uuid | yes | null | FK signal_event.id SET NULL | 重复事件指向 | S2 |
| detected_at | timestamptz | no | now() | - | 检测时间 | S3 |
| validated_at | timestamptz | yes | null | - | 规则/人工验证 | S3 |
| notified_at | timestamptz | yes | null | - | 首次通知 | S2 |
| last_action_by | uuid | yes | null | FK user.id SET NULL | 最近操作人 | S2 |
| last_action_at | timestamptz | yes | null | - | 最近动作时间 | S2 |
| resolution_code | varchar(32) | yes | null | - | 解决/误报原因 | S2 |
| resolved_at | timestamptz | yes | null | - | 解决时间 | S2 |

## 18. notification

Purpose：业务通知，与具体 Push/SMS/PHONE provider 解耦。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 通知标识 | S2/S3 |
| signal_event_id | uuid | yes | null | FK signal_event.id SET NULL | 事件来源 | S3 |
| reminder_execution_id | uuid | yes | null | FK reminder_execution.id SET NULL | 提醒来源 | S2 |
| recipient_user_id | uuid | yes | null | FK user.id SET NULL | 注册收件人 | S2 |
| recipient_contact_snapshot | jsonb | yes | null | redacted, for external contact | 外部联系人最小快照 | S3 |
| channel | varchar(16) | no | - | CHECK IN_APP/PUSH/SMS/PHONE | 业务渠道 | S1 |
| status | varchar(20) | no | `PENDING` | CHECK PENDING/QUEUED/SENT/DELIVERED/READ/FAILED/CANCELLED | 业务状态 | S1 |
| summary | text | no | - | CHECK minimal content | 最小必要摘要 | S2/S3 |
| policy_version | varchar(64) | no | - | - | 通知策略 | S0 |
| provider | varchar(64) | yes | null | - | provider 名称 | S0 |
| action | varchar(24) | no | `NONE` | CHECK NONE/ACKNOWLEDGED/CONTACTED/FALSE_POSITIVE | 收件人动作 | S2 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |
| sent_at | timestamptz | yes | null | - | 发送时间 | S1 |
| delivered_at | timestamptz | yes | null | - | 到达时间 | S1 |
| read_at | timestamptz | yes | null | - | 已读时间 | S1 |
| action_at | timestamptz | yes | null | - | 动作时间 | S2 |
| error_code | varchar(64) | yes | null | - | 脱敏错误码 | S0 |
| dedupe_key | char(64) | yes | null | UNIQUE where active | 幂等/去重键 | S0 |

## 19. notification_attempt

Purpose：通知重试、provider 错误和多渠道尝试。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 尝试标识 | S1 |
| notification_id | uuid | no | - | FK notification.id CASCADE | 业务通知 | S1 |
| attempt_no | integer | no | - | UNIQUE(notification_id, attempt_no), CHECK > 0 | 尝试序号 | S0 |
| provider | varchar(64) | no | - | - | provider | S0 |
| status | varchar(16) | no | `STARTED` | CHECK STARTED/SUCCEEDED/FAILED/RETRY_SCHEDULED | 尝试状态 | S1 |
| started_at | timestamptz | no | now() | - | 开始时间 | S0 |
| finished_at | timestamptz | yes | null | - | 结束时间 | S0 |
| provider_message_id | varchar(160) | yes | null | - | provider 返回 ID | S1 |
| error_code | varchar(64) | yes | null | - | provider 错误码 | S0 |
| error_detail_redacted | text | yes | null | - | 脱敏错误详情 | S1 |
| retry_at | timestamptz | yes | null | - | 下次重试 | S0 |

## 20. emergency_contact

Purpose：支持已注册 User 或仅电话号码的紧急联系人。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 联系人关系标识 | S2 |
| owner_user_id | uuid | no | - | FK user.id RESTRICT | 联系人所属老人 | S2 |
| contact_user_id | uuid | yes | null | FK user.id SET NULL | 可选注册用户 | S2 |
| name | varchar(120) | no | - | - | 联系人姓名 | S2 |
| phone_ciphertext | text | yes | null | Required for external contact | 应用层加密电话 | S3 |
| phone_hash | char(64) | yes | null | - | 去重 hash | S3 |
| phone_last4 | char(4) | yes | null | - | 脱敏展示 | S3 |
| priority | smallint | no | 1 | CHECK > 0 | 联系顺序 | S1 |
| channel | varchar(16) | no | `PHONE` | CHECK PHONE/PUSH/SMS/IN_APP | 联系渠道 | S1 |
| enabled | boolean | no | true | - | 是否启用 | S1 |
| verified | boolean | no | false | - | 联系方式是否验证 | S1 |
| verified_at | timestamptz | yes | null | - | 验证时间 | S1 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |
| updated_at | timestamptz | no | now() | - | 更新时间 | S0 |

## 21. device_binding

Purpose：Android 平板和设备能力/权限最新状态。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 绑定标识 | S1 |
| device_id_hash | char(64) | no | - | UNIQUE | 设备 ID hash | S1 |
| owner_user_id | uuid | no | - | FK user.id RESTRICT | 设备归属老人 | S2 |
| device_type | varchar(32) | no | - | CHECK ANDROID_TABLET/ANDROID_PHONE/OTHER | 设备类型 | S0 |
| app_version | varchar(64) | no | - | - | 客户端版本 | S0 |
| os_version | varchar(64) | no | - | - | Android 版本 | S0 |
| kiosk_status | varchar(24) | no | `UNKNOWN` | CHECK UNKNOWN/ACTIVE/CONFIG_ERROR/DISABLED | kiosk 状态 | S1 |
| wakeword_status | varchar(24) | no | `UNKNOWN` | CHECK UNKNOWN/READY/DISABLED/ERROR | 离线唤醒状态 | S1 |
| ble_status | varchar(24) | no | `DISCONNECTED` | CHECK DISCONNECTED/CONNECTING/CONNECTED/LOW_BATTERY/ERROR | BLE 状态 | S1 |
| camera_permission | varchar(16) | no | `UNKNOWN` | CHECK UNKNOWN/GRANTED/DENIED | Camera 权限 | S1 |
| phone_permission | varchar(16) | no | `UNKNOWN` | CHECK UNKNOWN/GRANTED/DENIED | 电话权限 | S1 |
| capabilities | jsonb | no | `{}` | JSON object | 设备差异能力 | S0 |
| status | varchar(16) | no | `ACTIVE` | CHECK ACTIVE/UNBOUND/LOST/DISABLED | 绑定状态 | S1 |
| last_seen_at | timestamptz | yes | null | - | 最近心跳 | S0 |
| last_state_change_at | timestamptz | yes | null | - | 最近状态变化 | S0 |
| created_at | timestamptz | no | now() | - | 绑定时间 | S0 |
| updated_at | timestamptz | no | now() | - | 更新时间 | S0 |

## 22. weekly_report

Purpose：结构化统计快照 + 可选自然语言叙述；报告版本不可变。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 报告标识 | S2 |
| owner_user_id | uuid | no | - | FK user.id RESTRICT | 老人/报告主体 | S2 |
| family_id | uuid | no | - | FK family.id RESTRICT | 家庭范围 | S2 |
| period_start | date | no | - | - | 统计开始 | S1 |
| period_end | date | no | - | CHECK >= period_start | 统计结束 | S1 |
| version | integer | no | 1 | UNIQUE(owner, period, version) | 报告版本 | S0 |
| status | varchar(16) | no | `GENERATING` | CHECK GENERATING/READY/FAILED/REDACTED | 生成状态 | S1 |
| generated_at | timestamptz | yes | null | - | 生成完成时间 | S1 |
| metrics_snapshot | jsonb | no | `{}` | JSON object from structured metrics | 生成时数值快照 | S2 |
| narrative | text | yes | null | - | LLM/模板叙述 | S2 |
| missing_data | jsonb | no | `[]` | JSON array | 数据缺失说明 | S1 |
| source_cutoff_at | timestamptz | no | - | - | 数据截止时间 | S0 |
| supersedes_id | uuid | yes | null | FK weekly_report.id SET NULL | 被新版本替代 | S1 |
| created_at | timestamptz | no | now() | - | 创建时间 | S0 |

## 23. audit_log

Purpose：授权、敏感读取、删除、导出、联系和设备动作的不可变审计。

| Column | Type | Nullable | Default | Constraint | Description | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| id | uuid | no | app UUIDv7 | PK | 审计记录 | S2 |
| actor_user_id | uuid | yes | null | FK user.id SET NULL | 操作人；系统动作可为空 | S2 |
| family_id | uuid | yes | null | FK family.id SET NULL | 家庭范围 | S2 |
| action | varchar(64) | no | - | - | 例如 CONSENT_REVOKED/MEMORY_READ/DATA_EXPORT | S1 |
| target_type | varchar(48) | no | - | - | 目标实体类型 | S0 |
| target_id | uuid | yes | null | - | 目标实体 ID | S1 |
| reason | varchar(240) | yes | null | - | 操作理由，不放敏感正文 | S2 |
| request_id | varchar(96) | yes | null | - | 请求关联 ID | S0 |
| result | varchar(16) | no | `SUCCEEDED` | CHECK SUCCEEDED/FAILED/DENIED | 操作结果 | S1 |
| metadata_redacted | jsonb | no | `{}` | redacted JSON | 脱敏上下文 | S1 |
| created_at | timestamptz | no | now() | append-only | 操作时间 | S1 |

## 24. Cross-table constraints and index summary

以下索引属于实现时的最小集合，完整策略见 [`database-design.md`](database-design.md)：

| Table | Index / constraint |
| --- | --- |
| family_member | active/pending partial unique `(family_id, user_id)`；查询 `(family_id, status)`。 |
| consent | granted partial index `(family_id, subject_user_id, grantee_user_id, scope)`。 |
| memory | `(family_id, verification_status, deleted_at, revoked_at)`；`(subject_user_id, type)`。 |
| memory_embedding | `(memory_chunk_id, status, provider, model_version)`；向量索引在确定维度后评估。 |
| reminder | `(owner_user_id, active, next_due_at)`；ReminderExecution occurrence unique。 |
| conversation/message | owner/time、family/time、`(conversation_id, sequence_no)`。 |
| signal_event/notification | owner/status/time、recipient/status/time、dedupe partial index。 |
| device_binding/report/audit_log | owner/last_seen、owner/period、actor/created_at。 |

## 25. PII and retention review checklist

- 不保存永久公开对象 URL；Signed URL 每次授权后生成。
- 不默认保存原始音频；音频允许与否及期限为 Decision Required。
- Message、summary、evidence_summary、notification summary 都有敏感度和清理路径。
- Consent 撤回保留历史，但立即影响 Memory/RAG/Notification authorization。
- AuditLog 不保存完整内容、token、完整电话或未脱敏健康信息。
- 备份、AuditLog、WeeklyReport 和对话摘要的具体保留期需在隐私/威胁模型文档中确认。
