# 第七周安全提示与合同评审记录

日期：2026-10-19。本文件保留**审批前局部实现快照**。随后用户批准 W7-01～04，
当前结果见 [第七周完成记录](week7-completion.md)；下文的阻塞状态是历史状态。

## Task

按 development-plan §20 执行第七周 E5 Scam/SignalEvent、E6 Mock/IN_APP Notification。
事件/通知实施需要 [W7-01..04](../plan/week7-contract-review.md) 评审，状态仍为
PROPOSED，未把“完成第七周”解释为批准具体 DB/权限/留存变更。

## Changed

- Conversation 在已鉴权且通过帧校验的当前 text.input 上运行既有确定性规则。
  命中诈骗组合时，先于 AI 回复发送既有 WSS `warning`：reason_category 和固定
  display_text；不含原文、confidence、模型输出、虚构 event ID 或通知成功声明。
  可选 blocked_action 未填，因为本次没有执行任何转账、分享验证码或打开链接的能力；
  固定警告明确提示不要执行这些操作。没有增加 WSS 类型、字段或公共枚举。
- Android feature-conversation 接收 warning，显示安全文案和 WARNING 状态；不再
  因不支持该消息而断开。保留当前轮次 busy/deadline，防止警告到达后提交重复轮次。
  无效或超长 warning 安全断开，换家庭/清理后移除内容。
- 新增 13 项规则→warning 单元场景和 2 项 PostgreSQL/WSS 集成场景；后者实际验证
  无摘要/通知授权仍可本地警告、先 warning 后回复、序号连续、ping 可用、LLM/TTS/
  Avatar 不可用仍提示、不保存原文或生成摘要。它们不证明通知授权或事件持久化已实现。
- 新增 2 项 Android JVM 用例，覆盖连接保持/等待轮次/重复输入拦截/换家庭清空、
  malformed/超长 warning 不展示。补充具体待批准提案与开发状态。
- 保留任务开始时第五、六周所有工作区改动；未提交、推送或执行第八周。

## Tests

| 实际执行 | 结果 | 证据（忽略目录 artifacts/week7/） |
| --- | --- | --- |
| 后端 unit + contract + OpenAPI source | PASS：273 项，0 failure/error/skip | unit-contract-verified.xml |
| PostgreSQL/WSS：week7_warning、week4、week6 | PASS：26 项，0 failure/error/skip | wss-postgres.xml |
| 日志/源码/Git 历史安全检查 | PASS：14 项；明确 deselect 1 项 APK 检查 | security.xml |
| Android feature-conversation Debug 编译/JVM | PASS：10 项，0 failure/error/skip | android-verified.txt、TEST-org.example.niannian.feature.conversation.ConversationModelTest.xml |
| Android feature-conversation Debug lint | PASS：0 Error/Fatal | lint-results-debug.xml |
| ruff backend/scripts/tests、git diff --check | PASS | 本聊天实际命令输出；换行转换提示非检查失败 |
| 本次 6 个实现/测试文件与构建快照 SHA-256 一致 | PASS | source-hashes.json |

合计本轮 313 项后端/安全测试和 10 项 JVM 测试；不把历史验证累加成本轮结果。
机器可读汇总：summary.json。只验证本次修改的 feature-conversation 模块，未声称
双端完整构建、APK 或真实设备通过。

使用当前锁定 Python 3.12.14、PostgreSQL 16.15/pgvector、JDK 17、Gradle 8.11.1 和
SDK 35。源码复制到本轮 ASCII 工作目录后测试，6 个修改文件与原目录 hash 一致。
创建独立 `nian7_week3_test` 虚构测试库（127.0.0.1:59007），只应用已有批准迁移至
week6 head，未修改迁移。验证后已停止本轮 PostgreSQL 实例，保留数据/日志供复核。

失败及恢复记录：沙箱初轮 Python 没有返回，已中断；Gradle 初轮报无法连接本机 daemon；
PostgreSQL 初轮后台进程没有持续就绪。经自动审批允许后在沙箱外执行同一隔离验证，
上述最终测试通过。没有放宽断言或跳过失败用例，没有安装新依赖。
android-check.txt 保留失败记录，android-verified.txt 是最终成功记录。

复现（在独立源码快照，PYTHONPATH 包含 backend 和快照根，PYTHONUTF8=1）：

```text
python -m pytest backend/tests/unit backend/tests/contract backend/tests/test_openapi_source.py -q
python -m pytest backend/tests/integration/test_week7_warning_postgres.py backend/tests/integration/test_week4_postgres.py backend/tests/integration/test_week6_postgres.py -q
python -m pytest tests/security -k "not test_built_apks_contain_no_secret_patterns" -q
gradle --offline --no-daemon :feature-conversation:testDebugUnitTest :feature-conversation:lintDebug
```

集成测试必须显式设置 WEEK3_TEST_DATABASE_URL 指向全新、已迁移的 `*_week3_test`
测试库，fixture 会清理该测试库；不设置时跳过，必须记 NOT VERIFIED。Windows 上
为 pytest 配置任务专属可写 basetemp；Gradle 在 android 目录使用锁定运行时及缓存。

## Decisions

仅实现无需变更契约的本地警告路径。通知缺失不会阻止本地警告；未创建 SignalEvent
时不发送 signal.created。六类候选仍沿用第六周 Mock 范围，紧急联系闭环留第八周。
W7-01..04 提案涵盖类别/表/outbox、最小来源与留存、逐类型权限/去重、偏好/状态。
提案中的 7 天留存、24 小时派发期限等均未获批准，未写入实现或冻结合同。

## Contract Changes

None。OpenAPI/WSS、ConsentScope、数据库模型/迁移和权限矩阵均未因本轮修改。

## Not Verified

SignalEvent/Notification/Attempt 持久化、并发去重、worker 派发/重试/死信、排队后撤权、
完整摘要-only/通知-only 闭环、家属收件箱/轮询；这些受 W7-01..04 评审阻塞。
未重建 APK、未运行 APK 扫描、实际设备 UI/TalkBack/后台、实际语音、真实 Push、
远端 CI 和生产迁移均 NOT VERIFIED。

## Issues

现有 outbox 不支持通知任务，事件类别没有落库字段，留存/通知偏好和部分权限语义
未冻结。按 AGENTS.md 的 Design Change Policy 停止这些受影响实现，不能静默补合同。
完整第七周仍 IN_PROGRESS，阻塞部分 BLOCKED；本记录不是完整交付证明。
测试仍出现既有 Starlette/AnyIO 弃用提示及 pytest 退出时脱敏 LOG_SINK_FAILED 提示，
未修改无关日志组件，也不据此宣称生产验收。

## Next

等待负责人审批 W7-01..04 后继续本周事件/通知实现与对应验收；本轮不自动批准提案、
不启动第八周、不提交/推送。指定设备与真实 Provider 继续沿用原门禁。
