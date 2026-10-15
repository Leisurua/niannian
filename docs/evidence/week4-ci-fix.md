# PR #8 第二周 CI 修复

## Task

2026-10-15，修复 PR #8 第二周 PostgreSQL 检查在 push/pull_request 两种触发下的失败。

## Changed

`verify_week2.py` 明确排除第四周专用 PostgreSQL 测试，沿用现有第三周测试的分组方式。第二周仍执行自己的数据库集成测试；第三周和完整第四周入口继续执行第四周用例。

增加真实 pytest 收集回归：第二周数据库用例必须存在，第三/四周专用文件不能被误收集。没有修改业务实现、workflow 或跳过检查规则。

## Tests

- [原失败运行](https://github.com/Leisurua/niannian/actions/runs/38670675112)：JUnit 共 279 项，0 failure/error、6 skipped；库存检查正确返回 `NOT VERIFIED`，脚本退出 2。
- 新回归在旧代码上实际失败，修复后通过；工具测试共 16 项通过，包含缺失/无效/空/跳过报告不能通过的原有负例。
- 仅配置 `WEEK2_TEST_DATABASE_URL` 的实际独立门禁：274 项，0 failure/error/skip；迁移、模型一致性和 lint 通过。
- 完整第四周入口：292 项，0 failure/error/skip；包含六项第四周 PostgreSQL/WSS 场景。
- 证据位于忽略目录 `artifacts/week4-ci-fix/`：`regression-before.xml`、`regression-after.xml`、`week2-local/`、`full-local/`。

## Decisions

这是本 PR 新增数据库测试后的分组遗漏，属于确定性 CI 回归，不按基础设施偶发故障重跑。保留“任何已选择用例跳过都不能算 PASS”的验收规则。

## Contract Changes

None。

## Not Verified

新提交的远端 CI 以 GitHub 当前运行结果为准。此次没有修改 Android/硬件/Provider 表面，不重申真实设备或语音验收。

## Issues

没有已知本次软件修复阻塞；原失败记录保留。

## Next

推送到同一 PR，核验新提交的 push 和 pull_request 检查结果。
