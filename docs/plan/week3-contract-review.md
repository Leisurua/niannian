# 第三周实施前合同核对与待批准方案

日期：2026-10-09；实施续接：2026-10-10。状态：**ACCEPTED — 用户已批准推荐方案**。

用户已授权推进一周；范围按 development-plan §20 为 E2 Memory/File、E3 Reminder
骨架、E4 Conversation/WSS 状态。不启动第四周 AI 会话。第二周软件已交付，设备验收仍未关闭。

## 必须先解决的冲突

| 编号 | 现有依据与冲突 | 推荐的具体处理 | 受影响工作 |
| --- | --- | --- | --- |
| W3-01 | OpenAPI MemoryResponse 必填 `version`、包含 `source`；data-dictionary §8 两列均不存在。API §12 要求 If-Match 乐观锁。 | Memory 增加 `version integer NOT NULL DEFAULT 1 CHECK > 0` 和 `source varchar(24) NOT NULL`（FAMILY_MEMBER/USER/AI_CANDIDATE/IMPORT）；旧数据不凭空推断来源。原有迁移不改，新迁移建新表。 | E2-T01、E2-T05 |
| W3-02 | ReminderResponse 必填 `version`；DB §23/data-dictionary §24 索引引用 `reminder.next_due_at`，但 §12 没有这两列。 | Reminder 增加 `version integer NOT NULL DEFAULT 1 CHECK > 0`、`next_due_at timestamptz NULL`。每次修改规则递增版本并重算下次触发；execution occurrence key 不受重试影响。 | E3-T01、E3-T02 |
| W3-03 | 提醒列表按 family 过滤，ReminderCreate 与 reminder 表均无 family_id；同一用户可属于多个家庭。文件请求无 owner/family 字段且 memory_id 可选，但 file_asset 强制两者存在。 | Reminder 增加 family_id FK family.id RESTRICT；ReminderCreate/Response 增加可选 family_id。省略时仅在唯一有效家庭时推导，否则拒绝并要求明确家庭。File 上传首期要求关联已授权 Memory，以它推导 family/subject；支持独立照片上传须另行冻结请求字段。 | Reminder/File 家庭隔离，须同步 OpenAPI/字典/权限说明 |
| W3-04 | API §17 要求已签发下载 URL 在撤权后立即拒绝，DB §10/ADR-006 描述对象存储直签 URL 到期后再授权。直接 S3/MinIO 签名无法逐次检查 Consent。 | 下载 URL 指向受控后端代理，签名绑定文件/用户/有效期；每次下载仍需有效登录并重新检查 Consent、Memory 与 File 状态；对象不公开。上传保持私有对象存储短签名。需增补下载代理 operation 及安全测试。 | E2-T02，不能把缩短 TTL 当作立即撤权 |
| W3-05 | ConversationResponse 有 backend_state，数据库无相应字段；WSS sequence 要求“按会话单调递增”，未区分收发方向与跨重连持久化。 | Conversation 增加 backend_state（冻结的 7 值）、input_mode（冻结的 3 值）、client_sequence/server_sequence（bigint >= 0）；各方向独立严格递增，跨重连保留，拒绝已用客户端 sequence。不保存全文/音频。必须同步字典与 WSS 语义。 | E4-T01、E4-T02 |

以上均是实际合同差异，不是代码风格选择。依据 AGENTS.md：
> A Contract, enum, state-machine, or Security Boundary conflict stops the affected work and must be reported.

> Anything affecting an API/WSS field or operation, DB entity/constraint/enum/migration, Requirement, Consent/family boundary, cross-module contract, security boundary, data retention, identity/biometric behavior, or public state is a Proposal/ADR only. Stop and report; do not implement it as an incidental fix.

## 评审后实施与验收范围

1. 同步上述合同后新增第三周迁移，保留第二周迁移；仅在显式隔离的第三周测试库演练 upgrade、downgrade/re-upgrade、Alembic parity 与约束负例。不得作用于真实家庭数据。
2. Memory：同家庭/当前 Consent/角色校验；AI 只能 PENDING；有权主体或确认者才可确认；撤回/删除先不可见；读写审计、分页、If-Match、幂等；Android 列表/详情/确认/错误反馈。
3. File：两步上传、真实对象完整性检查、类型/大小限制；未经实际扫描和元数据清理不置 AVAILABLE；已签 URL 撤权后再次读取拒绝。存储不可用明确失败，不返回假签名 URL。
4. Reminder：IANA 时区与本地日期快照、唯一 occurrence、幂等反馈；NO_RESPONSE 仅 worker 产生。第五周 Android 离线缓存与完整 RAG 不提前执行。
5. Conversation：owner/device/family 校验、TEXT/Mock 状态；默认拒绝音频（D-002/D-017）；连接及每条消息重新鉴权；状态/序号恢复，不重播文本或音频；真实 ASR/LLM/TTS 属后续周。

## 可独立推进的代码

在评审前可以实现和测试不接入生产路由/数据库的内部校验组件：冻结 DTO 的
Memory 候选输入校验、文件完整性预检、提醒时间/周期计算、WSS envelope/payload
解析和有界输入检查。这些组件不作授权决定，不创建公共 endpoint，不模拟持久化成功，
也不能据此将整周标为 PASS。

时间算法实现选择：星期一=0；每周间隔以 start_date 所在周为锚；INTERVAL 按本地日
间隔；DST 重复时刻选第一次、缺失时刻跳过；跨午夜 quiet hours 在指定时区判定且不
改变原 occurrence 身份。上述选择需在第三周接入前随本方案确认。

## 审批记录

- Reviewer：用户/项目负责人（本聊天）。
- Decision：APPROVED，原文：“批准推荐方案，继续第三周实现”；随后“继续”。
- 批准范围：W3-01..05、相应合同同步、第三周迁移、数据库/接口/双端接入与验证。
- 不再因同一方案重复请求批准；迁移只在隔离测试库执行。
