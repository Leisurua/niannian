# AI 与会话

## 当前可用范围

当前是明确标记的文字 Mock，不是已接入真实大模型或语音的产品。仅设置 API key 或 `PROVIDER_MODE=real` 不会启用真实供应商；会话编排仍拒绝非 Mock 适配器。

| 能力 | 实现入口 | 当前行为 |
| --- | --- | --- |
| 文字编排 | `backend/app/ai/conversation.py` | 透明 AI 身份、固定话术、未知事实/失败兜底、已授权记忆引用 |
| LLM / Embedding | `backend/app/integrations/mock/adapters.py` | 可复现 Mock；向量为 8 维，不能作为通用语义准确率证据 |
| ASR | 同上，MockASR | 占位模拟结果，不解码音频，未接入会话语音链路 |
| TTS / Avatar | 同上，MockTTS / MockAvatar | 不返回音频，仅文字/状态降级 |
| Push | 同上，MockPush | 仅模拟派发，不声明设备送达 |
| 摘要 | `backend/app/modules/conversation/summary.py` | 从受控主题生成最多四条回顾，不存逐字稿 |
| 关注候选 / 主动邀请 | `backend/app/ai/signal_candidates.py`、`proactive.py` | 有限演示短语提取、确定性邀请资格判断 |

## 接口与编排边界

DTO 的唯一字段定义是 [integrations/contracts.py](../backend/app/integrations/contracts.py)，不在 Markdown 复制完整类。请求使用 request_id；LLM 另带 task、system_policy、conversation_context、authorized_memory、user_input、safety_context、output_schema、prompt_id/version。返回包含状态、结构化结果和 provider/model/prompt 元数据。

编排默认总超时 8 秒，可配置但不超过 20 秒；TTS/Avatar 降级调用各最多 2 秒。当前没有为会话请求实现通用自动重试。LLM 输出通过严格 Pydantic 校验，限制话术、引用和候选；异常、超时或非法输出使用固定兜底，不把原始模型文本直接发布。

安全规则先于模型。LLM 不决定家庭权限、事实、通知收件人、诈骗裁决、医疗诊断、紧急状态、转账或电话。接真实 Provider 时仍需超时、适当的有限重试/降级、schema 校验和脱敏；先确认供应商的数据使用/留存，再发送真实敏感数据。

## 授权 RAG

检索、索引和引用复验实现于 [memory/rag.py](../backend/app/modules/memory/rag.py)：

1. 先得到当前家庭、主体、ACTIVE 成员和有效 scope，不能全库取向量后再过滤。
2. 源记忆必须 CONFIRMED、已核实、未撤回/删除/过期；OWNER_ONLY 限本人。PENDING、拒绝和未知内容都不是家庭事实。
3. AI 处理需要指定 grantee 的显式授权，包含主体本人；普通本人 REST 读取权限不自动授予 AI 使用权。
4. 只检索有效 chunk/embedding 与当前源版本，验证向量 provider/model/version、维度和有限数值。
5. 生成后、重复回答和任务写回再次验证引用。撤权或源变化使旧向量/候选失效，不能在迟到回复中继续发布。

记忆内容作为数据，不能充当指令。缺少授权依据、冲突或未知事实明确说不确定，不编造家人信息。

## 会话、回顾与主动邀请

已实现的 WSS 是本人文字/状态通道。`audio.chunk`、`audio.end` 等消息名虽保留在协议枚举里，当前返回不可用；没有录音→ASR→TTS 播放链路。具体消息格式与限制在 [openapi.yaml](openapi.yaml)，连接权限见 [security](security.md)。

回顾采用固定主题，生成需要本人的 CONVERSATION_SUMMARY 显式授权。家属读取还需指定家属的该 scope、SUMMARY_READ 和访问理由。主题最多四条，失败不回退为全文；保留期和撤权处理只在安全文档维护。

主动邀请默认关闭，由家属提议、老人确认共同版本，受时间窗、免打扰、每日 0～3 次、最近交互和“今天少打扰”约束。只给活跃本人会话发送 Mock 文字邀请，不后台唤醒或播音；保留/展示前重查当前偏好，未成功保留不能消耗额度。

## 关注与风险规则

候选类型为身体不适、情绪表达、往事、思念、诈骗风险、紧急求助。每批最多三个，携带当前 conversation/message 来源、类别和固定建议；置信度不是医疗概率或授权。非法/跨会话来源、未知类别、注入属性会被拒绝。短语词表只在 [signal_candidates.py](../backend/app/ai/signal_candidates.py) 维护。

[safety/rules.py](../backend/app/modules/safety/rules.py) 用组合指标识别敏感操作，固定规则优先给本地警告；不是对人或交易作确定诈骗结论。事件持久化及通知另行检查来源、去重、授权和收件人。明确求助当前只显示联系提示，不创建真实呼叫，不声称接通。

## 日志与修改时检查

记录 request/conversation id、provider/model、prompt/rule version、状态、延迟和候选计数，禁止输入全文、原始音频、完整健康/家庭记忆与模型思考过程。完整数据保护规则见 [security](security.md)。

改动编排/RAG 时运行关联 conversation、embedding、summary、safety 测试；涉及授权、索引失效或任务写回时补对应集成测试。测试路径见 [测试说明](../tests/README.md)，不另建分周 AI 评估报告。
