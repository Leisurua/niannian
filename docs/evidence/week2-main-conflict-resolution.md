# 第二周 PR 与主分支的冲突解决

范围：PR #3 的主分支同步与冲突解决。

主分支处理期间从 `690ee635171044058652e644797be71f95b0619f` 推进到
`d82b0528efbbe8f9fc1276a738caf29644af062b`，后者包含已合并 PR #2 的 E0 验收与日志保护。
采用普通合并提交保留历史，不覆盖主分支。

- 清单保留第一周收尾、最新 E0 记录、第二周进度与 Batch 1 门禁；未验证的真机项保持待验。
- 两个 MainActivity 同时保留 `AppExecutionBoundary`、脱敏 `APP_STARTED` 事件及第二周登录/家庭/授权入口。
- README 保留 Mock/DEMO 登录说明与虚构 seed 检查；明确八张基础表尚不覆盖完整业务 seed。
- 后端自动合并保留 E0 的失败日志关联标识修复及 E1 的路由注册。

合并后本地验证：

| 检查 | 实际结果 / evidence |
| --- | --- |
| Ruff、Alembic upgrade / 模型一致性、后端测试 | PASS：141 tests，0 failure/error/skip；`artifacts/week2-conflict/latest-backend-pass/` |
| 双端离线构建与 lint | PASS；`artifacts/week2-conflict/latest-android.txt` |
| Android 单测 | PASS：60 次执行，0 failure/error/skip；构建副本的 `*/build/test-results/` |
| 双方记录、业务入口与启动保护保留 | PASS；`artifacts/week2-conflict/latest-validation.json` |

首次尝试的沙箱端口限制、旧 pytest 临时目录权限错误不计为 PASS。使用既有一次性
PostgreSQL 测试库及全新工作区临时目录后重跑通过；保留最初失败日志，未弱化测试。
当前新版本的 GitHub CI 以该版本的实际检查为准，不沿用旧提交的绿灯。
本次未执行真机、硬件能力验收或 PR 合并。
