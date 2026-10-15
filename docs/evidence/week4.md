# 第四周 Mock 对话交付记录

日期：2026-10-15。本周 Mock 软件路径已实现并验证；实际语音、真机 UI 和完整 E4 后续能力不据此标为通过。

## Task

按 development-plan 第四周完成 Mock AI 会话、身份/未知/失败话术、简化形象和长辈端控制入口。
基线为 [第三周 PR #5](https://github.com/Leisurua/niannian/pull/5) 的
`a1948c2702d3117e0185abb6cf47a736d59698f1`，本地分支 `codex/week4-mock-conversation`。
第三周已批准的 TEXT/Mock、音频拒绝、无逐字稿持久化边界继续有效。

开发期间已有的 `docs/development-plan.md` 语音主线/持续摘要授权修改由其他工作产生，本轮保留，没有把它当作修改冻结 API/DB 的授权。

## Changed

- `AIOrchestrator` 接入现有 Mock LLM/TTS/Avatar DTO；版本化 prompt 随 wheel 打包。结构、长度、引用、候选、动作和输出内容均校验；失败不使用 provider 原文兜底。
- 会话支持 Mock 闲聊、身份问答、未知家庭事实和不可用系统信息话术。默认 8 秒总预算；TTS/Avatar 各有最多 2 秒子预算。取消传播，错误不输出输入或异常正文。
- WSS 立即发送 THINKING，生成期间仍能处理打断、结束、断线和每秒重新鉴权；完成后再次鉴权再发送。只保存已有会话元数据中的无内容 trace，不保存输入、回复全文、音频或摘要。
- 同一会话短身份提示不因重连/打断重复。重复和慢速请求只重显当前连接最后一句安全文字；断线不重播历史，未确认输入不自动重发。
- 长辈端新增 `feature-conversation`：说话入口、无需打字的明确 Mock 话题按钮、大字状态、停止/重复/慢速/音量/结束控制及文字备用入口。未启用录音/播音时明确说明；慢速控件放大文字，不声称改变真实语速。
- 连接序号检查、缺帧后断开并通过 REST 校验后重连、旧回调隔离、超时、家庭切换和后台内容清理。家人端没有加入会话模块或硬件权限。
- 新增 `scripts/verify_week4.py`：对 Git 跟踪及未忽略的新源码建立 SHA-256 一致副本，使用独立 pytest 临时目录，运行回归和源码/fixture/Git 扫描，严格记录跳过和不可用项。

## Tests

实际证据位于忽略目录 `artifacts/week4/`。

| 检查 | 实际结果 | Evidence |
| --- | --- | --- |
| 后端综合回归 | **289 tests，0 failure/error/skip** | `verification/summary.json`、`verification/tests.xml` |
| PostgreSQL/WSS | PASS；包含在上述 289 项内；未知回复、重复、慢速、结束、重连不重播、生成中打断/退出/断线/注销取消 | `backend/tests/integration/test_week4_postgres.py` |
| 输出与故障负例 | PASS；畸形/超长/非法 enum、伪造引用/候选/动作、原文兜底、provider 身份、超时、取消、TTS/Avatar 失败 | `backend/tests/unit/test_week4_conversation.py` |
| 源码/fixture/Git 隐私与 Ruff | PASS；包含在综合入口中 | `verification/tests.xml`、`verification/lint.txt` |
| Android build/JVM/lint | PASS；12 APK，**82 次 JVM 测试，0 failure/error/skip**；7 份 lint XML 无 Error/Fatal | `android-build.txt`、`android-summary.json`、`android-tests/` |
| 构建源码一致性 | PASS；63 个源码/配置文件 SHA-256 与英文构建副本一致 | `android-summary.json` |
| APK 隐私扫描 | PASS；1 项扫描全部 12 APK，强制要求完整变体集合 | `apk-scan.xml` |
| 后端 wheel | PASS；离线构建，源码目录外安装；dev/test/demo health 和新 prompt 的 Mock 回复均实际执行 | `wheel-build.txt`、`wheel-check.txt` |
| 当前设备 | 0 个已授权 Android 设备；真机 NOT VERIFIED | `device-baseline.txt` |

后端入口：安装已锁定依赖，设置分别以 `_week2_test`、`_week3_test` 结尾的独立数据库 URL 到 `WEEK2_TEST_DATABASE_URL` / `WEEK3_TEST_DATABASE_URL`，运行 `python scripts/verify_week4.py`。不得指向真实家庭数据库。此入口明确排除本轮未修改的真实 MinIO 表面，不能据此重申存储验收。

最初直接扫描工作目录失败：已有 `artifacts/device/` 第三方工具测试数据被识别为电话模式，已有设备日志被识别为禁止源码产物；pytest 默认临时目录还出现权限错误。最终入口使用有 hash 证据的源码副本和全新临时目录，未删除旧设备证据、未弱化扫描模式。原始失败记录保留在 `backend-tests.txt`。

## Decisions

- 本周是 Mock 软件基线。完整 E4-T03 的授权 RAG/引用正例仍依赖第五周检索，当前检索集合始终为空，任何引用、候选或动作均拒绝；不把 PENDING 数据变成事实。
- 当前 Mock 输出仅接受经审查的固定话术，不宣称通用模型安全性、真实理解能力或真实紧急检测。帮助话术不会产生通知、呼叫或 SignalEvent。
- D-002/D-003/D-017 尚未批准实际音频/外部数据路径：WSS 音频仍拒绝，Mock TTS 没有音频，既不发假 tts.start，也不把文字状态当作实际播音。摘要保持诚实不可用，不回退逐字稿。
- 当前 provider DTO 没有端到端幂等键保证，保守使用零自动重试，避免重复回答。8 秒预算是实现配置，非真实 Provider 性能验收。
- Android 新增 OkHttp 4.12.0，用于既有 WSS 的 Bearer-header 连接；Okio JVM 3.6.0 为传递依赖，均 Apache-2.0。实际 JAR 大小分别为 789,531 / 359,580 bytes，不等于 APK 增量。版本已锁定；替代方案自写 RFC 6455 或 WebView 会增加协议/凭证处理复杂度。测试使用注入的 `ConversationGateway`，不需真实语音 Provider。依据：[Square WSS 接口说明](https://developer.squareup.com/blog/web-sockets-now-shipping-in-okhttp-3-5/)、[发布元数据](https://central.sonatype.com/artifact/com.squareup.okhttp3/okhttp/4.12.0)。

## Contract Changes

None。本轮未修改 Requirements、OpenAPI/WSS 类型/字段、DB 模型/迁移/约束、Consent 或家庭权限边界。

## Not Verified

- 真机 UI/TalkBack/生命周期、Keystore、屏幕布局及设备语音能力；无已授权设备。
- 实际录音→ASR→LLM→TTS→口型、真实慢速/音量/可听身份提示；按 E4-T06/E11-T05 门禁另行验收。
- 完整 RAG、G-002 已确认记忆引用正例、摘要、诈骗/紧急/通知完整 VS-03 闭环，按后续周排期；本周 Mock 测试不能关闭完整 AI-001..007 或 220 案例评估门禁。
- 本轮远端 CI、正式签名/发布及真实 Provider；远端 CI 以 PR 当前提交的实际结果为准。

## Issues

实际语音与端到端全功能仍未交付；界面始终标注 Mock/未启用能力。现有 Starlette/AnyIO 弃用警告和测试结束时脱敏日志 sink 提示未当作真实 Provider 或性能证据。

## Next

本次仅交付第四周 Mock 范围，不自动启动下一周。后续按计划完成授权 RAG、摘要与已批准的实际语音链路，并在指定设备验收。

本周演示：启动后端，长辈端使用虚构 DEMO 身份进入 ACTIVE 家庭，点击“说话”建立 Mock 会话，再点模拟话题按钮；检查未知事实回答、停止/重复/慢速/音量说明和结束后的摘要不可用提示。断网后重新连接不会重发输入或回放身份/历史。调试 APK 位于 `android/app-elder/build/outputs/apk/demo/debug/`，不随 Git 提交。
