# 第六周策略准备与合同阻塞记录

**历史准备记录**：下文保留 2026-10-17 的评审前状态。用户随后已批准 W6-01..04，
2026-10-18 软件实现和验证完成，最终结果见 [第六周交付记录](week6-completion.md)。

日期：2026-10-17。**第六周 IN_PROGRESS；仅本轮策略准备及对应回归 PASS。**

## Task

用户请求完成第六周开发。范围按 development-plan §20：摘要、持续摘要授权、主动陪伴
策略、SignalCandidate/规则；真实语音受既有门禁约束。
发现必须评审的合同缺口后，完成可独立开发部分并提交
[W6-01..04 待批准方案](../plan/week6-contract-review.md)。未启动第七周。

## Changed

- `backend/app/ai/proactive.py`：纯策略，检查共同启用、时间窗、当地日计数、免打扰、
  今日暂停、忙碌/休息、最近互动、已拒内容和当前内容授权；合格结果携带退出话术。
  支持跨午夜与 DST，最短间隔按实际 UTC 时间；不修改计数、不调度、不发送。
- `backend/app/modules/safety/rules.py`：版本化代码规则包，覆盖合同 §5 的五组诈骗
  组合，最高匹配优先；显式紧急触发优先于诈骗组合。词汇解释与单指标不升级事件。
  仅返回规则决策/固定话术，不执行敏感动作，不创建通知、呼叫或事件。
- `backend/app/ai/signal_candidates.py`：暂态严格候选结构，最多三条；校验来源 UUID、
  六种 type、置信度范围、当前输入对应的已知 category/action，拒绝越权字段。
  支持已有明确词表的 SCAM_RISK 和 PHYSICAL_DISCOMFORT；其余类别失败关闭，等待
  W6-03 词表审查。对通过校验的候选替换为固定最小证据，不传播模型原始证据。
- 新增 70 项策略/候选测试和 `scripts/verify_week6.py`，复用既有带 SHA-256 的干净
  源码快照；清楚区分准备阶段 PASS 与整周 IN_PROGRESS。
- 未修改现有 App、业务路由、编排调用、模型、迁移、冻结合同或第五周已有工作。
  当前线上/本地 App 仍使用原有会话回复和摘要不可用行为。

## Tests

| 实际执行 | 结果 | 证据 |
| --- | --- | --- |
| 初次新增策略测试 | PASS：68 项；随后补充两个边界用例 | 本轮工具输出 |
| 干净源码副本策略/单元/契约/源码安全回归 | PASS：259 项，0 failure/error/skip，包含最终 70 项第六周测试 | `artifacts/week6/verification/tests.xml`、`tests.txt` |
| backend/scripts/tests Ruff | PASS | `artifacts/week6/verification/lint.txt` |
| 快照与原源码 SHA-256 | PASS，测试结束时核对 | `artifacts/week6/verification/source-hashes.json` |
| 准备范围汇总 | PASS；week6_status=IN_PROGRESS | `artifacts/week6/verification/summary.json` |

新增用例覆盖四道门失败、时间窗首尾/跨午夜、当地日暂停与限次、DST 重复小时及实际
时间差；五组规则/紧急优先/安全相似话术；候选伪造来源、过量、越权指令、NaN、非法
类别/动作、未被原文支持的语义、证据替换与本轮去重。

失败记录保留：原工作区回归 257 passed / 2 failed，失败来自扫描忽略的
`artifacts/device/` 下载 Go 工具中的数字串与旧设备 `.log`。未删旧成果、未改正则或
放宽测试，按既有第四/五周流程使用仅 Git 跟踪及未忽略源码的副本复验通过。
原工作区扫描失败的 JUnit 位于 `artifacts/week6/policy-regression.xml`。
两次沙箱内运行在进入既有异步用例后停滞并中断；本地执行成功。
第一次快照因系统 GBK 解码中文 Git 路径失败，使用 PYTHONUTF8=1 后成功。

复现（仓库根目录，使用新的空 ASCII 路径）：

```powershell
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe scripts/verify_week6.py --source <新的独立ASCII源码目录>
```

上述统计不包含 APK 扫描（本轮未更改 Android），也不包含 PostgreSQL/MinIO 或硬件测试。
文档证据在测试后补记；该轮 hash 对应测试当时源码。代码未在测试后改变。

## Decisions

- 按 AGENTS.md 在合同冲突处停止受影响实现，保留无冲突的纯策略代码与可复现测试。
- 确定性规则包是有限词法基线，不宣称任意自然语言理解或真实诈骗识别准确率。
- 高置信度不授予权限，候选不成为事实、SignalEvent、通知或呼叫。
- 策略输入未来必须由服务从当前授权和数据库状态构造；布尔标记本身不是鉴权机制。
  每日计数事务预占、调度和 UI 尚未接入，因此测试不证明并发限次或实际提醒。
- 所有新组件未接入生产执行路径；没有真实 Provider 或新增依赖。

## Contract Changes

None。W6-01..04 为 PROPOSED，未批准、未实施。没有改动 API/WSS、DB、公开状态或 Consent 边界。

## Not Verified

- 摘要生成/异步任务/物理清理；一次 grant 跨两会话的实际摘要读取、理由审计及撤权竞态。
- 六类完整候选提取、SC-001；只完成已有词表子集，不能关闭全部 SC/AI 门禁。
- 主动配置/共同确认/每日持久计数/暂停同步/实际发起和退出界面。
- PostgreSQL 集成、迁移、Android 构建/JVM/APK/设备；本轮未改动这些实现。
- 实际 ASR/TTS/LLM/可听语音、设备 UI/TalkBack、远端 CI、发布。

## Issues

W6-01：outbox 类型约束不允许摘要任务。
W6-02：摘要保留期/处理授权与家属明确查看理由尚未落实合同。
W6-03：候选 category/action 词表缺失；SC-001 与列出的组合规则不一致。
W6-04：自动主动陪伴需要的共同确认、每日计数和今日暂停缺存储/接口。
详细出处及建议字段/接口/隐私策略见待批准方案，不把准备测试当整周完成。

## Next

请项目负责人审查 W6-01..04。批准后继续当前第六周任务及相应数据库/双端验证；
不自动执行第七周。真实语音另需 D-002/003/017 的实际 Provider、数据与音频路线证据。
