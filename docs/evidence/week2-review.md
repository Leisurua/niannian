# 第二周复查与优化

日期：2026-10-09。范围：第二周 Android 登录/家庭/授权的恢复路径，以及本地验证入口。
在已有未提交工作上修复；不涉及第三周业务或新的 API/数据库设计。

## 修复的问题

| 问题与触发条件 | 修复后的行为 | 回归证据 |
| --- | --- | --- |
| 待重试写入存在时重启或刷新，错误文本清空，重试按钮随之消失，其他写操作仍禁用 | 待处理状态独立显示恢复入口；断网启动保留已有登录与待处理请求 | `restoredAndReloadedPendingWriteRemainsRecoverableWithoutAnError`、`offlineStartupPreservesTheExistingSessionAndPendingWrite` |
| access token 到期，刷新成功，但原请求重放收到 401/403/409，未执行原有清理规则 | 初次请求与重放共用清理：401 清除本地登录；明确拒绝清理待处理写入；503/网络未知结果保留原幂等 key | `terminalReplayRejectionAfterRefreshUsesTheSameCleanupRules`、`temporaryReplayFailureKeepsTheOriginalKeyForAnExplicitRetry` |
| 刷新响应丢失，继续使用旧 refresh token 可能触发服务端重用检测并撤销其他设备会话 | 刷新结果无法确认时清除本地凭证，要求重新登录；不自动重复发送旧 refresh token | `lostRefreshResponseRequiresLoginInsteadOfReusingARotatedToken` |
| 家庭 A 的邀请写入超时后切到 B，再重试，把 A 的邀请码显示在 B 下 | 按重试响应的家庭 ID 返回对应家庭；切换/重载清除旧邀请码 | `retryingAnInvitationAfterSwitchingFamilyReturnsToItsOwnFamily` |
| 普通 ACTIVE 成员没有 MEMBER_READ，主页仍读取成员列表，403 导致家庭页整体清空 | 从 `/me` 的成员权限判断成员列表读取和管理入口；服务端仍做最终鉴权 | `ordinaryActiveMemberCanLoadTheirFamilyWithoutMemberReadPermission` |
| 授权、家庭、成员列表只读取前 100 条，旧 scope 可能误显示为缺少授权 | 按冻结的 cursor contract 读取后续页；重复/缺失 cursor 或超过 100 页时明确失败，不把部分结果当完整结果 | `consentOnLaterPageIsNotShownAsMissing`、`repeatedPaginationCursorFailsInsteadOfLoopingOrShowingPartialData` |
| 授权开启/撤回缺少影响确认 | 操作前显示具体范围、接收者与撤回影响；取消不会发送请求，确认绑定当前家庭 | Compose 编译/lint；实际对话框点击 smoke 待设备 |
| 测试库 URL 路径虽有 `_week2_test`，查询中的 `dbname/service/options` 仍可能覆盖连接目标 | 用 SQLAlchemy URL 解析，限定数据库名、驱动并拒绝查询参数；统一入口与截断 fixture 均检查 | `test_disposable_database_guard` 等工具测试 |
| 旧 JUnit XML 残留，或新报告缺失/损坏/没有测试时可能误报通过 | 执行前清除旧报告，检查本次报告与实际数量；缺失/跳过为 NOT VERIFIED，报告失败为 FAIL | `test_missing_empty_invalid_or_skipped_report_cannot_pass` |

## 验证

- 后端：**PASS，110 tests，0 failure/error/skip**，包含 15 项实际 PostgreSQL 集成。
  证据：`artifacts/week2-review/backend/summary.json`、`backend-tests.xml`。
- 迁移一致性与 Ruff：**PASS**，沿用既有迁移，未产生 schema 差异。
- Android 离线锁定依赖构建、单测与 lint：**PASS，42 次 JVM 单测执行，0 failure/error/skip，12 APK**。
  其中新增 9 个恢复用例分别在 Debug/Release 执行。50 个源码文件与构建副本的 SHA-256 一致。
  证据：`artifacts/week2-review/android-summary.json`、`android-verified.txt`。
- APK/源码/fixture/Git 隐私检查：**PASS，7 tests**；12 个 APK 均扫描。
  证据：`artifacts/week2-review/apk-privacy.txt`。首次交付记录中的安装包链接已更新为本轮产物。
- JVM 恢复测试使用真实 JSON 编解码与内存 SessionStore、可控 HTTP 连接；模拟断网、
  响应丢失、鉴权拒绝、权限不足、切换家庭和分页。它不替代设备上的 Keystore 与 UI 验收。

本轮唯一新增依赖为 `testImplementation("org.json:json:20240303")`，用于 JVM 执行
Android 标准 JSONObject 的实际请求/会话路径。Android SDK 的单测 stub 会抛异常，
自行伪造 JSON 实现又会掩盖序列化问题；因此使用与 API 兼容的真实实现。
下载的 POM 标明 Public Domain，JAR 大小 **78,332 bytes**，锁文件仅包含四个 JVM
unit-test classpath，不进入 App 的生产 runtime 或 APK。网络通过可控连接 Mock，
无需额外 Mock 框架、设备或真实账户。

## 合同与待验边界

Contract Changes：None。没有修改 Requirement、OpenAPI/WSS、Consent scopes、成员角色、
数据库 migration 或既有服务端授权边界。客户端权限判断仅减少必然被拒绝的请求，
不替代服务端鉴权。

仍待验：实际设备 UI/Keystore、杀进程恢复与硬件 Spike；本轮 GitHub Actions 未发布执行。
依赖新版、应用图标等既有 lint 警告不在本轮升级范围。第二周整体验收继续保留真机待验项。
