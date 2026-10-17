# 第五周合同核对与已批准实施方案

日期：2026-10-15。状态：**ACCEPTED — 用户在本聊天回复“继续实现”，随后“继续”，批准按本方案实施**。

当前请求为“继续完成第五周的任务”。范围按 development-plan §20：E2 RAG/delete
propagation、E3 offline cache/timezone；不执行第六周摘要、真实语音或通知工作。
开发计划已有的未提交修改保留，不将它解释为数据库或接口变更批准。

## 已核对的阻塞

| 编号 | 事实与依据 | 为什么必须评审 |
| --- | --- | --- |
| W5-01 | 字典 §9/10 已定义 MemoryChunk/Embedding，但当前迁移只有第三周基础表，尚未实现两表。ADR-007 要求持久任务/唯一业务键/租约/重试/死信，而字典没有 task/outbox 表。 | 前两表按冻结定义落地仍涉及新增迁移；持久任务则缺少完整 schema，不能挪用 AuditLog 或 JSON metadata 充当未审查的任务表。 |
| W5-02 | `POST /reminder-executions/{id}/feedback` 只能处理服务端已存在的 execution；请求只有 status/note/next_due_at。设备离线生成未来 occurrence 时没有服务端 ID，接口也不能记录其 OFFLINE 来源。 | device §20 与 REM-002/003/004 要求本地生成、持久反馈和恢复后一次 ACK；按时间猜 ID、改现有请求字段或伪装 ONLINE 都不符合合同。 |
| W5-03 | device §20 要求 Room 缓存的 family/owner/version/expiry 及 PendingAction；REM-012 引用 configured freshness，但实际期限和超期队列处置尚未冻结。 | 新增本地数据保留期限属于 AGENTS.md 指定的评审事项，不能随代码写死。断网设备也不能声称立即获知远端撤权。 |
| W5-04 | privacy §10 要求 RAG 的当前有效 Consent；现有 `authorize(... allow_self=True)` 支持资源主体自行读写，Consent 又是 subject→指定 grantee 的分项授权。当前 AI 检索集合为空，尚无实施中的 RAG 主体授权规则。 | 不能直接把本人 REST 读取豁免推广为 AI 处理授权，也不能把授予子女的授权视为授予 AI。需要明确已有 Consent 模型在本人会话 RAG 中的使用方式。 |

依据 [AGENTS.md](../../AGENTS.md)：

> A Contract, enum, state-machine, or Security Boundary conflict stops the affected work and must be reported.

> Do not change Requirements, OpenAPI/WSS, public enums/states, DB schema/constraints/migrations, Consent scope, family boundary, or Security Boundary without an approved Proposal/ADR and the required review.

## 推荐批准的最小方案

### W5-01：既有向量表与最小持久任务

1. 新增第五周迁移，不改旧迁移。MemoryChunk/Embedding 严格按字典 §9/10 字段、外键、状态与唯一性实施；Mock 仍用已有 8 维向量与 `provider=mock`，校验 ACTIVE 向量非空、长度与 dimension 一致、数值有限且非零。向量不是语义准确性或真实 Provider 验收。
2. 新增仅内部使用的 `task_outbox`，无 public CRUD。建议字段及约束：

| 字段 | 拟冻结定义 |
| --- | --- |
| id | uuid PK，应用 UUIDv7 |
| family_id | uuid NOT NULL FK family.id RESTRICT |
| resource_id | uuid NOT NULL；按 kind 由对应模块 public service 解析，不允许调用者指定表名 |
| resource_version | integer NOT NULL CHECK > 0 |
| kind | varchar(32) NOT NULL CHECK MEMORY_INDEX / MEMORY_CLEANUP / FILE_CLEANUP；只用于本周任务 |
| business_key | varchar(200) NOT NULL UNIQUE；包含 kind、资源 ID、来源版本 |
| status | varchar(16) NOT NULL DEFAULT PENDING；CHECK PENDING/RUNNING/RETRY/SUCCEEDED/DEAD |
| attempts / max_attempts | integer NOT NULL DEFAULT 0 / 5；CHECK attempts >= 0、max_attempts > 0、attempts <= max_attempts |
| available_at | timestamptz NOT NULL DEFAULT now()；下一次可领取时间 |
| lease_token / lease_until | uuid / timestamptz，均可空；RUNNING 时必须同时非空，其他状态均为空 |
| last_error_code | varchar(64) NULL，仅固定脱敏码，不写异常正文、记忆内容或凭证 |
| created_at / updated_at | timestamptz NOT NULL DEFAULT now() |

3. 索引 `(status, available_at)`、`(status, lease_until)`；API 业务写入和任务入队同事务。worker 用 SKIP LOCKED 短事务领取，外部 I/O 不占 DB 长锁，完成按 lease_token 比较更新，过期租约可以重领，最后一次失败进入 DEAD。重试/超时配置有界，重复任务不重复副作用；不在本周实现通用管理后台。
4. Memory 修改为 PENDING、撤回、删除及过期时，先通过来源状态排除所有读取；在对应事务失效已有派生索引并排队清理。删除不删除 append-only audit。Consent 撤回在下一次查询与发送前检查中立即拒绝；后台删除相关派生数据，不能因清理失败恢复可见性。
5. 检索先限定当前 family、subject、角色/permission、当前 Consent、visibility、CONFIRMED、有效期以及 ACTIVE chunk/embedding，再在该集合计算 exact cosine distance。不加 ANN、不加全文检索替代品、不搜索全库后过滤。无检索缓存，生成前及发送前重验引用；撤回后不重复播放含旧记忆的最后一句。
6. 与现有 conversation/AI 的连接只通过 memory 的 public service 与现有 adapter DTO；不引入跨模块私有模型导入、不增加 WSS 类型。保留 Mock 标志，输出只能引用本次获准检索集合；无结果、非法引用和故障使用未知话术。真实 Embedding/LLM 继续受 D-003 门禁。

### W5-02：离线 occurrence 反馈入口

建议增加 **一个** operation：`POST /v1/reminders/{id}/offline-feedback`，operationId
`submitOfflineReminderFeedback`。要求 Bearer + `Idempotency-Key`，只允许提醒本人/本人设备
会话；家属无代报权。原有 execution feedback 接口保持不变。

请求：`reminder_version: integer > 0`、`scheduled_at: UTC timestamp`、
`feedback_at: UTC timestamp`、`status: DONE|LATER|SKIPPED`，可选
`next_due_at: UTC timestamp`（仅 LATER）。不收药名、剂量、全文、客户端 owner/family、
客户端 occurrence_key 或任意 execution ID。成功返回既有 ReminderExecutionResponse，HTTP 200。

服务端从当前规则与身份推导 family/owner，重新鉴权；规则删除/停用拒绝，版本不一致
返回现有 409 ETag 冲突类错误，客户端不自动套用新规则。按 W3 已批准时间规则重新计算
scheduled_at 与 occurrence_key：非法时间/未来 occurrence 返回 422，不从客户端信任 hash。
反馈时间仅为客户端申报时间，不当作服药事实或送达证据；不得晚于服务端当前时间，且不得
早于 scheduled_at。原有 feedback_at 保存服务端接受时间，申报时间仅用于验证，不新增历史
定位/行为记录字段。超过 W5-03 同步期限返回 422，客户端明确显示未同步。

以现有唯一 `(reminder_id, occurrence_key)` 与事务锁合并在线/离线同一 occurrence。
没有行时插入 source=OFFLINE；已有在线行不改写原触发来源。`triggered_at` 不凭离线请求
伪造为已验证播报。DONE/SKIPPED 不被不同请求覆盖，重复相同幂等键返回已确认结果；不同
payload 复用 key 拒绝。LATER 的 next_due_at 如果恢复联网时已经过去，明确拒绝并要求用户
重新选择，不静默改为当前时间。NO_RESPONSE 仍仅由 worker 判定。

同步 OpenAPI、API spec、permission matrix、contract operation inventory 与新增负例；不改
公开 ReminderFeedbackStatus、数据库 ReminderExecution 结构或用药含义。

### W5-03：最小离线缓存和持久反馈策略

本次批准并实施以下上限：

- 长辈本人且当前 ACTIVE 家庭的已授权提醒规则/occurrence，缓存最多 **24 小时**；
  expires_at 取同步时间 + 24 小时、已知规则结束时间及适用授权到期时间的最早值。
  family/owner/resource version、同步时间、expiry 与密文一起存储。家人端离线隐藏敏感数据。
- Room 事务保存 occurrence 与 PendingAction；敏感 payload 由 Keystore AES-GCM 加密，
  非敏感索引也限制在对应账户/家庭，排除备份。首次展示后的记录用于防止重启重复提示。
  无可靠时钟/发现时间倒退或缓存过期时停止展示旧内容，显示需联网更新；不声称时钟防篡改。
- pending 反馈最多保留 **24 小时（从本地反馈时刻起）**，只含执行定位与三种反馈所需最少字段。
  超期不自动上传，移除内容并显示“反馈未同步，请联网核对”；服务端也验证该期限。
  反馈提交前必须仍处于有效缓存期。不得为保留失败证据长期存放用药内容。
- 已验证连接恢复后重验身份、家庭与规则版本再同步，沿用同一幂等键；最多 5 次自动尝试，
  指数退避，明确展示失败/冲突；仅收到 durable ACK 后移除待发送记录。HTTP 超时不能显示成功。
  本地已知撤权/退出/解绑/家庭切换立即隐藏并清理对应缓存及队列；不能在新家庭重放旧动作。
- 远端撤权在完全断网设备上的传播只能在恢复连接或本地有效期到达时生效，必须在隐私文档
  说明这一限制；本方案仅允许本人提醒的有界离线副本，不允许离线 RAG、摘要或家属健康查看。
- 复用第三周时间规则。Alarm/进程恢复只报告实际能力；没有精确闹钟权限就显示时间可能延迟。
  真机 REM-002/006/008/010/011 仍需指定设备，JVM 计算或模拟时钟不是硬件 PASS。

### W5-04：本人会话 RAG 授权

建议在现有 Consent 模型内，由本人显式创建 **subject=self、grantee=self、相应 scope** 的
授权以允许本人会话 RAG（FAMILY_MEMORY；健康记忆依其 required_consent_scope）。
现有 grant service 允许同家庭 ACTIVE 的本人 grantee，但当前 Android UI 仅提供授予家庭创建者
的操作；需要独立呈现“用于我与念念的交流”的分项说明，默认关闭，且不自动分享给子女。

RAG 不复用 `allow_self=True` 的免 Consent 路径。使用已有 Consent 版本、到期和撤回历史，
每轮/输出前重查同一授权；拒绝后基础闲聊仍可用。个人 REST 读写语义保持原样。
本方案不新增 ConsentScope、不创建机器用户、不推断子女授权能用于本人 AI。
该解释涉及 Consent 边界，必须随本 Proposal 明确批准后才能实现；若不认可，则保持 RAG
关闭并另议授权设计，不能自行选择宽松解释。

## 批准后的验收与迁移范围

1. 仅显式隔离测试库执行第五周 migration upgrade、downgrade/re-upgrade、模型 parity、
   外键/状态/向量约束；不修改真实家庭库。
2. PostgreSQL 验证 RAG-001..007、Consent 撤回、删除尚未物理清理、旧版本索引、生成期间撤权、
   伪造引用/注入文字、索引失败与任务死信；Mock 正例与未知兜底分别记录。
3. 任务并发领取、过期租约、旧 worker 回写拒绝、超时、有界重试、进程重启与部分清理失败。
4. 离线同步合同测试与实际 PostgreSQL 并发/幂等：同 occurrence 在线/离线竞争、跨家庭、
   非 owner、删除/停用/规则改版、非法时间、过期反馈、过去的 LATER、ACK 丢失后重试。
5. Android Room/JVM/构建/lint/隐私扫描；缓存有效期、跨家庭隔离、撤权/退出清理、队列恢复、
   既定时区/设备时区/DST。设备测试单独记实测结果；不通过文本注入证明实际提醒播报。
6. 正式同步字典和权限等合同的动作仅发生在批准后；本文件不会自称 Accepted。

## 本轮可以独立实施的准备工作

已批准 W3 时间规则的 Android 纯计算组件及跨语言固定测试向量：ONCE/DAILY/WEEKLY/
INTERVAL、当地时间快照、UTC 幂等键、DST、quiet hours、窗口边界、设备时区变化。
不接入 App、Room、系统闹钟、网络、RAG 或生产路由，不新增权限和数据保留行为。

## 审批记录

- Reviewer：用户/项目负责人（本聊天）。
- Decision：**APPROVED**，原文：“继续实现”；随后“继续”。批准 W5-01..04 及对应实施/验证。
- 请求批准范围：W5-01..04、必要合同同步、第五周隔离测试迁移、对应后端/双端实现和测试。
- 不含：第六周及以后业务、真实 Provider、原始音频持久化、正式部署或真实家庭数据迁移。

实施说明：阻塞说明保留评审时发现；W5-01..04 已获批准并实施，结果见 ../evidence/week5.md。未扩展到下一周。
