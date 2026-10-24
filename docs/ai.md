# AI 与会话

## 当前可用范围

文字会话支持可配置的 OpenAI 兼容 Chat Completions 服务（JSON 模式），默认仍为明确标记的 Mock。开发环境通过 `LLM_PROVIDER=openai_compatible`、URL、模型及密钥显式启用。已接入 DeepSeek V4.1 Flash（`deepseek-flash`），通过虚构输入的真实供应商调用及隔离库 WebSocket 两轮对话验证。Android 老人端已接入设备语音识别 → 现有 LLM → 系统中文朗读，真机语音联调尚未验证。配置见 [部署说明](deployment.md#真实-llm-文字联调)。

| 能力 | 实现入口 | 当前行为 |
| --- | --- | --- |
| 文字编排 | `backend/app/ai/conversation.py` | 透明 AI 身份、结构化回复校验、规则警告优先、失败兜底、授权记忆复验 |
| LLM | `backend/app/integrations/openai_compatible.py` | DeepSeek 官方 HTTPS 服务、关闭深度思考、非流式 JSON 回复；未配置时使用 Mock |
| Embedding | `backend/app/integrations/mock/adapters.py` | 仍为 8 维 Mock，不能作为通用语义准确率证据 |
| Android ASR / TTS | `android/shared/.../conversation/AndroidConversationVoice.kt` | 系统 SpeechRecognizer 收音识别，TextToSpeech 中文朗读；依赖已安装的服务，可能联网 |
| Android 基础数字人 | `android/shared/.../conversation/PersimmonCompanionOrb.kt` | Compose Canvas 2D 柿子形象；待机、听您说话、思考中、正在回答；口型随设备实际播放启停 |
| 后端 ASR / TTS / Avatar | `backend/app/integrations/mock/adapters.py` | 仍为 Mock 占位，不解码/返回音频；Android 语音不调用它们 |
| Push | 同上，MockPush | 仅模拟派发，不声明设备送达 |
| 摘要 | `backend/app/modules/conversation/summary.py` | 从受控主题生成最多四条回顾，不存逐字稿 |
| 关注候选 / 主动邀请 | `backend/app/ai/signal_candidates.py`、`proactive.py` | 有限演示短语提取、确定性邀请资格判断 |

## 接口与编排边界

DTO 的唯一字段定义是 [integrations/contracts.py](../backend/app/integrations/contracts.py)，不在 Markdown 复制完整类。请求使用 request_id；LLM 另带 task、system_policy、conversation_context、authorized_memory、user_input、safety_context、output_schema、prompt_id/version。返回包含状态、结构化结果和 provider/model/prompt 元数据。

Mock 编排超时 8 秒，真实 LLM 默认 20 秒（`LLM_TIMEOUT_SECONDS`，上限 20 秒）；TTS/Avatar 降级调用各最多 2 秒。没有自动重试，避免重复生成；用户可编辑后重新发送。LLM 输出通过严格 Pydantic 校验：文本长度、引用集合、空候选数组及无操作权限；Mock 另校验固定话术。异常、超时、非 JSON、截断或非法输出使用固定兜底，原始响应体及异常不发布、不记录。

每个 WebSocket 连接仅在内存保存最近最多 6 轮、共 12000 字的上下文，不写数据库。断线后上下文清空；Android 最多显示 20 条临时消息，后台、断线、换家庭或结束后清空。历史涉及的记忆在下一次外发前及回复发布前重新校验，撤权后丢弃受影响上下文。为限制依赖集合，超过 30 条记忆依赖时清空历史。真实 LLM 接口接收当前输入、短期历史及已授权记忆；不能据结构校验宣称自由回复完全无幻觉。

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

WSS 保持本人文字/状态通道。Android 点击说话后由系统 ASR 收音，最终识别结果以 `text.input` 提交；最终 `assistant.text` 交给系统 TTS。后端不接收原始音频，`audio.chunk`、`audio.end` 等消息名仍返回不可用。语音能力与 `llm_mode` 独立，Mock 回复也可以朗读，不能据此声称用了真实 LLM。

`ConversationModel` 管理录音、识别、等待和播放状态。语音由本人对自己的显式 VOICE 授权控制，握手返回 `voice_allowed`，撤回或到期通过 `voice.permission` 停止音频；规则见安全说明。单次收音最多 30 秒，点击“说完了”停止收音并等待最终结果最多 10 秒；空白、超长、超时或服务失败不自动重发。点击“停止”或“打断并说话”立即取消本地识别/朗读并发送 `interrupt` 取消后端任务。后端用 `in_reply_to` 标记请求序号，客户端校验服务器连续序号后丢弃旧轮次；设备回调使用递增代次丢弃迟到结果。断线、后台、结束和切换家庭同样停止音频。当前支持按钮打断，不做持续监听或自动人声打断。

重播重新请求服务器复验记忆权限，不直接朗读缓存回答；主动邀请不自动播音。语音实现遵循 Android [SpeechRecognizer](https://developer.android.com/reference/android/speech/SpeechRecognizer) 和 [TextToSpeech](https://developer.android.com/reference/android/speech/tts/TextToSpeech) 生命周期。具体协议在 [openapi.yaml](openapi.yaml)，传输与留存边界见 [security](security.md)。

老人首页和聊天入口共用 `ConversationPanel`，移除了聊天页固定示例回复和持续“正在听”的模拟状态。`ConversationState.companionPhase` 由本地录音、识别、请求等待、待播和实际播音派生；服务端 `LISTENING` / `SPEAKING` 不能单独让形象显示收音或动嘴。TTS `onStart` 才标记实际播音，`onDone`、`onStop`、失败、按钮打断、切后台、断线和 VOICE 撤权立即清除待播/播音标记并丢弃旧回调。ASR 自动结束收音后进入识别等待。基础口型是播放期间的开合循环，不是音素对齐或音量分析。

聊天页持续显示“念念 AI 陪伴”、当前状态和停止按钮；点击形象复用麦克风权限与语音授权检查，保留文字输入。当前为代码与构建验证，真机语音和动画观感仍待验证。

回顾采用固定主题，生成需要本人的 CONVERSATION_SUMMARY 显式授权。家属读取还需指定家属的该 scope、SUMMARY_READ 和访问理由。主题最多四条，失败不回退为全文；保留期和撤权处理只在安全文档维护。

主动邀请默认关闭，由家属提议、老人确认共同版本，受时间窗、免打扰、每日 0～3 次、最近交互和“今天少打扰”约束。只给活跃本人会话发送 Mock 文字邀请，不后台唤醒或播音；保留/展示前重查当前偏好，未成功保留不能消耗额度。

## 关注与风险规则

候选类型为身体不适、情绪表达、往事、思念、诈骗风险、紧急求助。每批最多三个，携带当前 conversation/message 来源、类别和固定建议；置信度不是医疗概率或授权。非法/跨会话来源、未知类别、注入属性会被拒绝。短语词表只在 [signal_candidates.py](../backend/app/ai/signal_candidates.py) 维护。

[safety/rules.py](../backend/app/modules/safety/rules.py) 用组合指标识别敏感操作，固定规则优先给本地警告；不是对人或交易作确定诈骗结论。事件持久化及通知另行检查来源、去重、授权和收件人。明确求助当前只显示联系提示，不创建真实呼叫，不声称接通。

## 日志与修改时检查

记录 request/conversation id、provider/model、prompt/rule version、状态、延迟和候选计数，禁止输入全文、原始音频、完整健康/家庭记忆与模型思考过程。完整数据保护规则见 [security](security.md)。

改动编排/RAG 时运行关联 conversation、embedding、summary、safety 测试；涉及授权、索引失效或任务写回时补对应集成测试。测试路径见 [测试说明](../tests/README.md)，不另建分周 AI 评估报告。
