# 第七周合同核对与待批准方案

日期：2026-10-19。状态：**ACCEPTED — 项目负责人在本聊天回复“是”，批准 W7-01～04 并继续实施**。

任务：完成 development-plan §20 第七周 E5 Scam/SignalEvent 与 E6
Mock/IN_APP Notification，验收“warning → 家属最小事件”和摘要/通知授权独立。
第八周家属处理动作、Emergency 联系闭环不提前执行。

## 已确认的阻塞

| 编号 | 可复核依据 | 受影响实现 |
| --- | --- | --- |
| W7-01 | data-dictionary §17 没有 trigger_category，但 scam-signal-policy §11 要求每个事件保存类别，API §21 返回 reason.category。task_outbox.ck_task_kind 只接受五个已批准任务类型。SignalEvent、Notification、Attempt 尚无模型/迁移。 | 类别不能塞进 evidence 文本或挪用 resolution_code；可靠通知不能冒用摘要任务或进程内后台任务。 |
| W7-02 | retention R-002/R-008/R-011 未冻结；signal_event/notification 没有 retention_until/deleted_at。source_message_id 是未实现 conversation_message 的外键，而当前候选 ID 仅在内存生成。 | 不擅定事件/通知保留期，不保存完整输入或创建悬空来源引用，不无限保留待发内容。 |
| W7-03 | API §21 对 SCAM_RISK/PHYSICAL_DISCOMFORT/EMERGENCY 使用“健康/通知 scope”概括；permission matrix §3.6 和 scam policy §9 是 health scope for health signal。scam policy §8 的 hash 字段没有 severity，但同节要求新严重度新事件。 | 必须确定逐类型权限和去重规则，不能自行选择较宽权限。 |
| W7-04 | FR-041 和 scam policy §10 要求渠道偏好/免打扰，但没有 NotificationPreference 的接口或表；ProactivePreference 属于老人主动陪伴共同确认，不能复用作家属通知设置。 | 家属选择 IN_APP/MockPush、免打扰和状态真值需要具体契约。ADR-008 仍为 Proposed；D-004 仅允许 Mock 基线，不自动批准新接口。 |

仓库规则依据：[AGENTS.md](../../AGENTS.md)：

> Do not change Requirements, OpenAPI/WSS, public enums/states, DB schema/constraints/migrations, Consent scope, family boundary, or Security Boundary without an approved Proposal/ADR and the required review.

> A Contract, enum, state-machine, or Security Boundary conflict stops the affected work and must be reported.

以下保留已批准的评审方案。下文“建议/待批准”描述提出时状态；本轮用户批准已覆盖
W7-01～04 的具体字段、权限、留存与状态解释。按此同步合同与实现。

## W7-01：事件与持久通知

- 新迁移按字典实现 SignalEvent、Notification、NotificationAttempt；既有枚举保持。
  SignalEvent 增加 `trigger_category varchar(64) NOT NULL`，取值沿用已批准 W6-03
  候选词表；固定证据、推荐动作和人话解释通过已版本化策略映射，不存原始文本。
- 事件只能由已认证、当前 ACTIVE 本人会话的应用服务创建；校验当前家庭、来源、
  候选类型和规则，LLM 候选不能直接插表。无授权时采用现有允许的本地安全提示路径，
  不保存不必要的敏感证据；事件/通知服务不导入其他模块私有模型。
- outbox CHECK 增加 `NOTIFICATION_DISPATCH`、`SIGNAL_CLEANUP`、
  `NOTIFICATION_CLEANUP`。复用现有租约、唯一业务键、超时、有限重试/退避和 DEAD。
  事件与通知入队同事务；每次尝试再次检查来源、收件人和当前授权。
  不为每次重试增加公共 API；旧 worker 的写回必须验证任务租约和来源仍有效。
- NotificationAttempt 仅保存固定错误码、provider=mock 和次数/时间；不复制请求、
  Provider 原始异常或正文。同一 notification/attempt_no 唯一；重试不重复创建收件箱项。
- 本周实现现有 SignalEvent list/detail、Notification list/detail/read；
  ack/contact/false-positive/resolve/action 仍按第八周排期，不伪装为已完成。

## W7-02：Mock 留存与来源

- **本次建议的新隐私决策**：仅虚构 Demo/Mock 事件和通知最多保留 **7 天**，
  从首次创建起算，重复命中、重试、阅读不续期；待发通知最多 **24 小时**，超时取消。
  这些是本提案待批准的新期限，不继承摘要或提醒的期限。
- SignalEvent 增加 `retention_until timestamptz NOT NULL` 和
  `deleted_at timestamptz NULL`；Notification 增加同样字段及
  `dispatch_deadline timestamptz NOT NULL`；期限不得早于对应创建时间。
  查询、派发先过滤失效记录，清理任务再物理删除 Notification/Attempt 和事件。
  外键清理顺序为 Attempt → Notification → Signal；审计继续 append-only 且不存正文。
- 本轮 `source_conversation_id` 绑定真实会话；`source_message_id`、evidence_hash
  为 null。不把内存 UUID 当作已持久化消息，不新建 ConversationMessage/逐字稿。
  本周创建 SignalEvent 时仍验证候选 message ID 属于当前已验证轮次；审计保存事件 ID
  和规则版本，不保存输入。需要将“来源消息引用可空”的 Mock 限制同步到策略解释。
- 删除来源会话或主体、撤回通知/健康 scope 后立即停止相应读/发；撤回仅某收件人授权
  不影响其他有效收件人。摘要授权的撤回不单独关闭不依赖摘要的安全通知。
  清理失败期间继续隐藏；旧 worker 不能恢复内容。Android 通知本周只在前台内存展示，
  后台/退出/换家庭/离线/已知授权变更清空，不新增磁盘缓存。
- task_outbox/AuditLog 继续原有元数据策略，本提案不替其决定最终保留期；真实数据、
  备份和外部 Provider 副本仍需独立隐私门禁，不能用本次 Mock 期限宣布通过。

## W7-03：权限、去重与最小披露

- 建议明确：家属访问所有类型都必须有同家庭 ACTIVE 成员资格、指定 grantee 的当前
  `NOTIFICATION_TO_FAMILY` 和相应 signal-read 能力；PHYSICAL_DISCOMFORT 另需
  `HEALTH_MEDICATION`。SCAM_RISK 不因名称自动要求健康 scope；EMERGENCY 的健康
  内容同样需健康授权，本周仅本地紧急提示，完整紧急事件/联系人策略留第八周。
- IMPORTANT_MEMORY 另需 `FAMILY_MEMORY` 才能暴露相关记忆内容；本周只用固定
  “有待核实的往事线索”模板，不从 PENDING Memory 取事实。情绪、思念均无诊断、
  置信数字、原文或 family internal note。本人只能查看自己的有限安全状态。
- `CONVERSATION_SUMMARY` 从不替代通知授权；只授摘要时，通知列表为空且不入队。
  只授通知时，可读已授权最小事件，但摘要仍拒绝。拒绝分享不影响本地固定警告。
- 建议去重键为 family/owner/type/category/**severity**/30 分钟时间桶的稳定 hash；
  在同一家庭/主体的事务锁内确定主事件，跨桶允许新事件。重复来源如落库只保存最小
  duplicate_of 关联且不再通知；不得从模型 confidence 推导严重度。
  同一来源轮次重放幂等；不同严重度新建事件。通知另按 event/recipient/channel 去重。
  30 分钟可按 D-013 配置校准，但加入 severity 的契约澄清需本次评审。
- 任何读取和派发均复查 recipient、来源会话/事件、期限及当前授权；列表过滤、详情
  隐藏返回 404，敏感读取审计；响应 no-store。不通过 UI 隐藏代替服务端检查。

## W7-04：IN_APP、MockPush 与设置

- 建议新增 `notification_preference`：id、family_id、owner_user_id、recipient_user_id、
  channels、timezone、quiet_hours_start/end、version、created_at/updated_at；
  UNIQUE(family_id, owner_user_id, recipient_user_id)，version > 0；时区为 IANA。
  channels 是既有 NotificationChannel 子集，本周支持 IN_APP 和 PUSH(Mock)。
- 建议新增 GET/PUT `/families/{family_id}/notification-preferences/{owner_user_id}`。
  收件人由当前登录身份推导，不能提交其他 recipient；仅同家庭 ACTIVE CHILD/CAREGIVER
  且具 signal-read 能力可管理自己的偏好。PUT 使用 If-Match，缺省版本 0，更新递增；
  返回上述配置，未知字段拒绝。选择渠道不创建/代授 Consent。
- 缺省 IN_APP，推送默认关闭。默认 quiet hours 22:00–08:00，时区取家庭时区；
  用户可关闭或修改。情绪/思念/待核实记忆仅应用内，SCAM L2/L3 和不适可按已授权
  渠道发送；本轮所有非紧急通知遵守免打扰，包括 L3，不启用自动升级或阈值 Push。
  免打扰只延后派发，不延长 dispatch_deadline；超时取消。
- IN_APP 发布进入 SENT（仅表示可在收件箱读取），不自动标 DELIVERED/READ；显式
  read 才 READ。MockPush 模拟接受可记录 SENT/provider=mock，但 delivery_observed=false，
  不写 delivered_at。失败重试耗尽为 FAILED；撤权/超时/来源失效为 CANCELLED。
  家属端在列表、详情和同步状态明确显示“Mock 演示，未验证设备推送到达”。
- SignalEvent 的 NOTIFIED 仅指至少一条有效业务通知已发布/SENT，不表示真实 Push 到达
  或家属已看；全部有效渠道失败才 NOTIFICATION_FAILED，没有授权则 WITHHELD/本地提示。
  上述既有状态的精确解释同步契约并测试，不扩充公共枚举。
- 应用前台轮询 30 秒，手动刷新可用；后台暂停，失败显示同步失败并清空敏感内容，
  不把陈旧内容冒充当前授权结果。不添加真实 Push SDK、硬件权限或外部服务。

## 批准后的验收清单

- 实际 PostgreSQL 迁移升级/回滚/再升级和模型 parity；事件/通知/尝试约束。
- SC-001..010；跨家庭、错误主体/收件人、无权限、过期/撤回/成员失效、删除来源。
- 摘要 only → 零通知；通知 only → 摘要拒绝；健康 scope 单独检验；排队后撤权拒发。
- 并发/重放/跨窗口/严重度变化去重；独立 worker 租约/重试/死信/旧写回拒绝。
- IN_APP SENT/read、MockPush 成功/失败/超时不伪造 DELIVERED；最小 payload/日志检查。
- Android 轮询/切换家庭/后台/失败和 Mock 状态测试；构建/JVM/lint 与实际设备验收分开。
- WSS 警告不等候 LLM/TTS；未创建事件不发送 signal.created；不宣称真实拨号或送达。

本轮已可实施：既有 warning WSS 消息的固定类别/文案发送与客户端接收，不涉及
SignalEvent 持久化或通知。现已获准继续完整第七周闭环，不能凭局部测试标完成。
