# 第六周合同核对与已批准方案

日期：2026-10-17。状态：**ACCEPTED — 用户在本聊天回复“是”，批准 W6-01～04 的具体方案及继续实现**。

任务为“完成第六周任务的开发”，按 development-plan §20 限定：摘要/持续授权、主动陪伴
策略、SignalCandidate/规则；真实语音仅在 D-002/003/017 门禁通过后实施。
第七周 SignalEvent 持久化、通知与第八周家属动态不提前启动。

## 已确认的阻塞

| 编号 | 可核实的依据 | 影响 |
| --- | --- | --- |
| W6-01 | API §19 要求结束后摘要任务；ADR-007 要求持久 outbox。现有 `task_outbox.ck_task_kind` 仅允许 MEMORY_INDEX/MEMORY_CLEANUP/FILE_CLEANUP。 | 新增摘要任务需要修改数据库 CHECK 与新增迁移，不能静默增加任务类型或改用进程内 BackgroundTasks。 |
| W6-02 | D-002、retention R-003、字典 §12 的摘要期限仍 TBD。FR-044 要求家属明确理由；OpenAPI 的 GET conversation 和 POST summary 没有理由输入。本人 REST 读取豁免不等于同意 AI 摘要处理。 | 摘要生成、保存、家属读取理由和 self-grant 边界需确定；不能从第五周提醒缓存的 24h 推导摘要期限。 |
| W6-03 | ai-contracts §8 要求 category/action 是枚举，但未列完整取值；scam policy §19 SC-001 要求 VERIFICATION_CODE+SECRECY 命中，而 §5 只有 VERIFICATION_CODE+CREDENTIAL 等五组。 | 不自行发明 MISS_FAMILY/IMPORTANT_MEMORY 等候选取值，也不把 SC-001 冒充已通过。 |
| W6-04 | FR-014 要求共同设置时间窗、频率上限、今日暂停；现有 Reminder 有 COMPANIONSHIP、quiet_hours 和计划时间，但没有主动时间窗、共同确认版本、每日限次及今日暂停的存储/接口。 | 纯策略可实现；可跨进程执行的主动发起、设置和暂停 UI 需要补合同。不能挪用 accessibility_settings/escalation_policy JSON 来绕过评审。 |

依据 [AGENTS.md](../../AGENTS.md)：

> Do not change Requirements, OpenAPI/WSS, public enums/states, DB schema/constraints/migrations, Consent scope, family boundary, or Security Boundary without an approved Proposal/ADR and the required review.

> A Contract, enum, state-machine, or Security Boundary conflict stops the affected work and must be reported.

以下保留评审时的具体方案；现已获准实施并同步冻结文档、路由、模型和新迁移。

## W6-01：受控摘要任务

- 在**新迁移**扩展 task_outbox.kind CHECK：增加 CONVERSATION_SUMMARY 和
  CONVERSATION_SUMMARY_CLEANUP；现有租约、fence、超时、重试、DEAD 语义沿用。
- 增加 Conversation.summary_version：integer NOT NULL DEFAULT 1、CHECK > 0，
  用于摘要输入变更/撤权清理的旧任务隔离；任务 resource_version 对应它。
- 无逐字稿表、无音频持久化。在本人明确同意摘要处理后，已完成且通过后置校验的
  Mock 文本轮次生成最多 1,000 字的受控短摘要，写入既有 summary_text，状态 PENDING；
  PENDING 不提供读取。只保留脱敏主题，排除号码、凭证、原文引用和诊断。
  输入不复制到 provider_metadata、audit 或 outbox。
- 结束/显式请求使用同一摘要版本的唯一业务键入队；worker 再检查家庭、主体、授权和
  来源状态才生成 READY。失败是 FAILED/null，空会话不伪造内容；永不回退原文。
- 新轮次、删除、撤权导致版本变化；旧 worker 写回被拒绝。请求只返回既有
  ConversationSummaryJob 的 conversation_id/status，不增加历史列表或消息 CRUD。
- 摘要 GET 不调用 Provider；每次使用当前授权。DEAD 由 worker 对应为 FAILED，
  清理失败继续不可见，并可通过既有内部任务状态观察。

## W6-02：摘要处理、保留与读取理由

- **建议新增的隐私决策**：本轮仅虚构 Demo/Mock 摘要，最长保存 **24 小时**，从首次
  创建受控摘要起算，后续轮次、重复请求和失败重试不延长；到期立即停止返回内容，
  清理任务置空 summary_text。该期限待本方案批准，不继承提醒缓存决策。
  不增加本地摘要缓存、导出或真实 Provider 数据处理。
- 本人明确 subject=self/grantee=self/CONVERSATION_SUMMARY 才启用摘要生成；
  UI 独立说明“生成我的会话回顾”，默认关闭。拒绝不影响基础陪伴。
  授予家人的 CONVERSATION_SUMMARY 仅是读取授权，不能替代本人的处理授权；
  家人仍须 SUMMARY_READ、有效角色/成员、同家庭、指定 grantee 与当前有效授权。
  不新增 ConsentScope，不默认开启 NOTIFICATION_TO_FAMILY。
- 撤回 self-grant 立即隐藏所有相关摘要并排队清理；撤回某家属 grant 立即拒绝该家属
  下一次读取，保留本人及其他仍获准读者的访问。过期、删除、成员失效同样重验。
  不添加永久缓存，不以客户端隐藏代替服务端检查。
- 为既有 GET `/conversations/{id}` 和 POST `/conversations/{id}/summary` 增加
  可选 HTTP header `X-Access-Reason`，值仅为 `FAMILY_CHECK_IN` 或 `FOLLOW_UP`。
  **非 owner 请求必填**；缺失/非法返回 422，未授权仍按既有权限拒绝。
  UI 分别显示“关心近况”“跟进本次交流”；每次家属访问选理由，但不重复申请 Consent。
  使用既有 AuditLog.reason 存该代码，不接收自由文本，避免在日志里存敏感解释。
  owner 无须理由；接口返回 Cache-Control: no-store。OpenAPI 明确条件必填规则。
- 验收：一次指定家属授权→两次独立会话摘要→每次带理由读取且有审计→撤回后拒绝；
  缺理由、非 grantee、无 SUMMARY_READ、跨家庭、过期、删除、成员失效、生成中撤权负例。

## W6-03：补齐候选词表与 SC-001

建议冻结以下候选 category/action 对（不是新的 SignalType/Severity）：

| Type | trigger_category | recommended_action |
| --- | --- | --- |
| SCAM_RISK | 现有五组 category，以及新增 VERIFICATION_CODE_AND_SECRECY | PAUSE_AND_VERIFY_WITH_FAMILY |
| PHYSICAL_DISCOMFORT | SELF_REPORTED_DISCOMFORT | CHECK_IN_AND_OFFER_CONTACT |
| EMOTION_EXPRESSION | SAD_EXPRESSION/LONELY_EXPRESSION/HAPPY_EXPRESSION/WORRIED_EXPRESSION | OFFER_COMPANIONSHIP |
| MISS_FAMILY | EXPLICIT_MISS_FAMILY/EXPLICIT_CONTACT_REQUEST | OFFER_FAMILY_CONTACT |
| IMPORTANT_MEMORY | LIFE_STORY/PREFERENCE_OR_TABOO/PHOTO_BACKGROUND | OFFER_MEMORY_REVIEW |
| EMERGENCY | EXPLICIT_HELP_REQUEST | OFFER_EMERGENCY_CONTACT |

- SC-001 增加版本化规则 SCAM_CODE_SECRECY：VERIFICATION_CODE + SECRECY，L2，
  阻止分享验证码并建议核实；不推断对方身份，不发送通知。
- category、action、证据、来源引用和最多三条限制都由确定性验证器复核。
  confidence 仅作为内部候选属性，不决定严重程度、权限、推送或呼叫。
- 本周只输出暂态候选/规则结果、Mock 提取和安全回退；SignalEvent 表、去重落库、
  WITHHELD/通知等留在第七周。不自动确认 Memory，不产生医疗/心理诊断。
- 针对固定 Mock 验收语句实现可复现提取；不声称任意自然语言理解准确率。
  规则优先于 LLM，LLM/TTS 故障仍能得到规则结果。

## W6-04：最小主动陪伴配置与计数

如按第六周交付可实际触发和暂停的主动陪伴，建议：

1. 新增 `proactive_preference`，主键 `(family_id, owner_user_id)`，两者为既有外键；
   timezone varchar(64)、window_start/end time、quiet_start/end time（成对可空）、
   daily_cap smallint（0..3，0 为关闭）、version integer > 0、
   proposed_by_user_id/confirmed_by_user_id UUID 外键、confirmed_version integer 可空、
   paused_on date 可空、created_at/updated_at timestamptz。
   改时间窗/上限等设置递增 version 并清空确认；仅老人可确认当前版本或设置今日暂停。
   CHILD/CAREGIVER 必须拥有既有 REMINDER_WRITE 才可提出设置，不能代确认。
   默认关闭，无共同确认不发起。
2. 新增 `proactive_daily_counter`，主键 `(family_id, owner_user_id, local_date)`，
   FK 到 preference；used_count smallint 0..3、updated_at timestamptz。
   事务锁 preference 和当日计数后检查并预占，每次机会即计数；进程崩溃不退还机会，
   避免反复打扰。没有保存对话正文或行为画像；计数最多保留 48h，UTC 时间比较。
3. 既有 worker 执行纯策略；第六周只向**已认证且活跃的本人会话**使用已有
   assistant.text 发送标注 Mock 的轻量邀请，不后台唤醒、不推送、不启动真实音频。
   没有连接不消耗次数；发送失败记录已尝试而不声称已播报。消费前再次重验当前策略和授权。
   天气无可用 Mock 系统数据则不报天气事实，Memory 必须经过现有 RAG 授权复验。
4. 增加 GET/PUT `/v1/families/{family_id}/proactive-preferences/{owner_user_id}`：
   GET 返回上述公开设置和 version/是否待老人确认，不返回内部计数行；PUT 使用 If-Match，
   请求仅含 timezone、window_start/end、quiet_start/end、daily_cap。
   POST 同路径 `/confirm`（body `{version}`）和 `/pause-today`（无正文），仅本人，
   使用 Idempotency-Key，返回更新后的设置。所有操作写脱敏审计、同家庭和成员检查。
   不新增权限代码；服务通过既有 family/consent 公共服务检查。
5. 暂停仅限主动陪伴；不关闭必要到点提醒、紧急联系或安全提示。
   本轮主动服务只在线运行；离线今日暂停的持久同步另行评审，UI 不宣称已同步。
   时区改变后不返还已消费机会，跨日/DST/并发/进程重启须负例验证。

W6-04 的接口/表是必要补充提案，不在本轮准备代码里创建。若第六周仅验收纯策略，
可只批准 W6-01..03，并明确主动陪伴服务接入仍未完成。

## 已能独立完成的准备

- 纯 `ProactiveSnapshot → decision`：时间窗、限次、免打扰/暂停、授权、退出话术、
  跨午夜和 DST；服务必须以数据库实际状态构建快照，LLM 不能提供授权布尔值。
- 五组无歧义的规则及显式紧急优先级，固定风险话术；没有生产路由接入或副作用。
- 已有明确词表的 SCAM_RISK/PHYSICAL_DISCOMFORT 候选校验：拒绝越权字段、
  错误来源、超量、非法置信度；替换为最小固定证据，不保存模型证据原文。
- 相关测试、回归与证据。完整六类候选、SC-001、摘要和自动主动服务不能据此标 PASS。

## 批准后实施与验证

只对显式隔离测试库执行新迁移及 downgrade/re-upgrade/parity；同步相关 API、字典、
权限、留存和契约清单。执行实际 PostgreSQL 授权/竞态/幂等/任务测试、Mock AI 负例、
Android JVM/build/lint/源码与 APK 隐私扫描；真实设备及语音门禁单独记实测结果。
不接入真实 Provider，不执行第七周通知/事件、不提交或发布。

审批记录：**APPROVED**。项目负责人在本聊天对“是否批准具体方案 W6-01～04，继续完成第六周剩余实现？”回复“是”。范围为 W6-01..04、必要合同同步、隔离测试迁移及双端实现验证；不含真实 Provider、生产数据迁移、第七周任务、提交或发布。
