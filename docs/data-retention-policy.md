# 念念（NianNian）数据保留与删除决策表

| 项目 | 内容 |
| --- | --- |
| 状态 | Decision Register / v1.0 |
| 适用范围 | 课程/竞赛原型；不替代正式法律、合同或生产保留政策 |
| 结论 | 现有设计未冻结最终时间；所有未签字项目保持 `TBD / Decision Required` |

## 1. Rules Before a Decision

1. 不以实现方便为理由永久保存 S2/S3。
2. 先让数据从 API/RAG/cache/export/notification 不可见，再做异步物理清理。
3. `retention_until`、状态和 deletion job 是执行载体；没有最终期限前不能硬编码任意天数。
4. provider、对象存储、日志、AuditLog、导出和备份各自记录生命周期，不能用主库期限代替外部副本期限。
5. 调试/演示数据必须是虚构数据；真实 S3 数据不得进入 demo seed、截图或测试日志。

## 2. Retention Decision Table

| ID | Data / system | Default posture now | Retention decision required | Deletion evidence |
| --- | --- | --- | --- | --- |
| R-001 | Raw Audio | 默认不保存；仅允许经批准的临时处理 | 是否允许调试保存、最长期限、provider 副本/备份、访问角色 | object/task/provider deletion receipt 或“不落盘”证明 |
| R-002 | Transcript / ConversationMessage | 仅在会话/摘要必要时保存受控文本 | 保留期、逐字稿是否可导出、owner/家属可见范围 | DB/cache/export/provider 清理记录 |
| R-003 | Conversation Summary | 受控 summary，不默认家属可见 | summary 保留期、撤权后历史是否 REDACTED、导出范围 | summary status + deletion job evidence |
| R-004 | Memory / Chunk | 与事实生命周期和删除请求绑定 | 过期规则、撤回与删除区别、拒绝候选保留期 | memory/chunk status、list/RAG negative test |
| R-005 | Embedding / topic embedding | 与来源 Memory 同步；不可单独长期保留 | provider/model cache、失效后物理清理期限 | embedding invalidated/deleted + vector negative |
| R-006 | Photo/Object | private bucket、`retention_until` 字段待填 | 照片/缩略图/孤儿对象/EXIF 清理时间 | object HEAD/GET denied、lifecycle receipt |
| R-007 | Reminder/Medication/Execution | 按业务历史保存，尚未定稿 | 普通提醒、用药、feedback_note、离线缓存期限 | DB + Room query/wipe evidence |
| R-008 | SignalEvent/Evidence | 最小摘要和状态 | severity/健康/诈骗事件期限、聚合重算 | event redaction/deletion + notification check |
| R-009 | WeeklyReport/InteractionMetric | 结构化报告和 metrics | report、narrative、重复主题 embedding、export copy | report REDACTED/delete + export exclusion |
| R-010 | Presence Result/Device telemetry | capability/status 最小值 | event time、heartbeat、lost device 元数据期限 | server/local state cleanup |
| R-011 | Notification/NotificationAttempt | 收件箱和尝试记录分离 | 已读/失败 payload、provider error、队列/死信期限 | queue re-evaluation + provider policy |
| R-012 | EmergencyContact/EmergencyCase | 联系关系/结果状态 | 禁用联系人、电话密文、case/attempt 期限 | encrypted field/cache/provider cleanup |
| R-013 | AuditLog | append-only；不含敏感原文 | 审计期限、读取审计递归、legal hold | retention job/append-only evidence |
| R-014 | Access/Refresh/DeviceSession | 过期/撤销后不可用 | token/session metadata、IP/UA hash、stale session | revoked/expired query and wipe |
| R-015 | Export package/download URL | 短期受控，但时间未定 | package、URL、失败中间文件、审计期限 | URL expired、object deleted、scope recheck |
| R-016 | Backend logs/crash/metrics | 结构化脱敏 | 日志、crash、provider cost/latency、request id | fixture scan + retention config |
| R-017 | Provider-side data | 未确认，不得发送真实 S2/S3 | training、API log、retention、support、delete API、region | provider contract/config/response |
| R-018 | Database/object backups | 可能包含敏感数据 | frequency、加密、访问、删除后 retention、恢复测试 | backup inventory + purge/restore |
| R-019 | Android local Room/DataStore | 最小离线能力 | token、提醒、summary、photo、notification 本地期限 | Keystore/DB wipe + consent test |
| R-020 | Demo/test fixtures | 只允许虚构数据 | fixture、截图/录屏/CI artifact 清理 | secret/content scan + artifact deletion |

## 3. Decisions Required Before Production-like Data

- 隐私负责人确认 R-001 至 R-003 的 raw audio/transcript/summary 政策。
- 产品/安全负责人确认 Health/Medication、Signal、WeeklyReport、AuditLog 和 Export 是否按数据主体/严重度区分期限。
- 基础设施负责人确认 provider、Object Storage、日志和 backup 的留存、区域、删除 API 与合同边界。
- Android 负责人确认 Room/DataStore、Keystore、丢失设备和撤权离线同步后的本地擦除。
- 法务/项目负责人决定 legal hold 或课程评审保存例外；未确认前不实现永久保留。

## 4. Deletion Verification Checklist

```text
INACCESSIBLE_AT
API_FILTERED
RAG_INVALIDATED
CACHE_INVALIDATED
SIGNED_URL_DENIED
OBJECT_CLEANUP
EXPORT_EXCLUDED
NOTIFICATION_REEVALUATED
LOCAL_CACHE_WIPED
PROVIDER_ACTION (if controllable)
BACKUP_EXCEPTION (if applicable)
COMPLETED / PARTIAL_FAILURE
```

不能把 AuditLog 或备份清除失败隐藏为 `COMPLETED`；也不能因为异步物理清理尚未完成而继续返回已撤权数据。


## W5-03 approved local reminder limits

Owner reminder cache: at most 24h from sync, shortened by known rule/authorization expiry. Encrypted PendingAction: at most 24h from local feedback; expire and erase content with an unsynced notice. Clear matching data on logout, family switch, unbind or known revocation. No new server transcript/audio/summary retention. Full offline devices cannot observe remote revocation before reconnect/expiry.


## Week 6 approved implementation (W6-01..04, 2026-10-18)

Approval: [W6-01..04](plan/week6-contract-review.md), project owner replied “是” in this chat.
This section supersedes earlier Week 3/4 “summary unavailable” implementation notes for the reviewed Mock path only.

- Conversation adds summary_version > 0; outbox permits CONVERSATION_SUMMARY and CONVERSATION_SUMMARY_CLEANUP.
  Store curated Mock themes only, at most 1000 characters; PENDING is unreadable. First input starts a non-renewable
  maximum 24h lifetime, shortened by known self-grant expiry. No transcript/audio/summary export or local disk cache.
- Explicit self CONVERSATION_SUMMARY grant enables generation; named family grant enables authorized reads separately.
  Every read requires current family/member/role/SUMMARY_READ/grantee/scope/resource checks. Self revoke hides and
  schedules cleanup; revoking one reader does not revoke other readers. Summary grants never enable notifications.
- GET conversation and POST summary require X-Access-Reason FAMILY_CHECK_IN/FOLLOW_UP for non-owners (422 when
  absent/invalid after access check), persisted as AuditLog.reason without content. Responses use no-store.
  The known-id view exposes no history list, transcript or discovery API. Failure/empty/expired never falls back to raw input.
- Four proactive operations: GET/PUT /families/{family_id}/proactive-preferences/{owner_user_id}, POST same path
  /confirm and /pause-today. PUT requires If-Match; POST commands require Idempotency-Key. CHILD/CAREGIVER with
  REMINDER_WRITE proposes; only ELDER owner confirms current version or pauses. GET needs owner/REMINDER_READ.
  Default disabled, cap 0..3, IANA timezone, local minute times, paired quiet hours. No new permission codes.
- ProactivePreference and ProactiveDailyCounter are the approved tables. Counter reservation is transactional and
  survives failure/restart; retains no text, expires after 48h. Timezone changes carry recent usage and today's pause.
  Worker sends only transient id/version/time hints through PostgreSQL NOTIFY to a currently connected owner WSS;
  API rechecks current authorization/settings before a fixed Mock invitation. No offline/background wake or push.
  Reconnect does not replay notifications. Failed/lost invitation can consume a slot and is never labelled delivered.
  Necessary reminders and emergency access are independent of proactive pause. No new WSS message type/state.
- Full candidate category/action vocabulary and SCAM_CODE_SECRECY are frozen in W6-03. Six types remain temporary
  Mock candidates, not facts/events/notifications. Deterministic emergency/scam copy survives LLM/TTS failure.
  SignalEvent persistence and notification delivery remain Week 7. Real voice/provider gates remain unapproved.
