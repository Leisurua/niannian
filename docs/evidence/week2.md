# 第二周交付记录

日期：2026-10-09。范围：E1-T01..06，以及 E9-T01..05 的设备 Spike 记录。
同日复查后的恢复逻辑与测试结果见 [第二周复查与优化](week2-review.md)；下方保留首次交付的验证记录，APK 链接指向最新重建版本。
本记录接续已有的 Auth/Family/Consent 后端与迁移，保留本轮开始时的 Android 和家庭确认修改。
第三周业务不在本次范围。整周状态为 **IN_PROGRESS**，真机验收不能由软件检查替代。

## 实现与验收

| Task | 当前实现 | 验证 / 边界 |
| --- | --- | --- |
| E1-T01 | User / DeviceSession、刷新凭证仅存 hash、身份与 session 关联、撤销检查 | PostgreSQL 集成 PASS；丢失设备与本地擦除真机验收待测 |
| E1-T02 | 虚构 DEMO allowlist、刷新轮换、重用撤销本用户 session、本机退出/退出全部、登录限流 | 单元与 PostgreSQL 并发/失效测试 PASS；SMS/OAuth/真实凭证未接入 |
| E1-T03 | 创建家庭、邀请码 hash/有效期/次数、PENDING 与本人身份确认、成员权限/撤销/退出、版本并发、幂等与分页 | PostgreSQL PASS；邀请码不隐式授予 Consent；PENDING 不读家庭详情 |
| E1-T04 | 由主体授予授权、GRANTED/REVOKED 追加不可变历史、scope/grantee/有效期检查与审计 | PostgreSQL PASS；撤回或退出后的下一次判定拒绝访问；缓存/RAG/通知传播属后续任务 |
| E1-T05 | 服务层的有效身份、同家庭 ACTIVE 成员、管理/成员读取权限、主体与 grantee、当前 Consent 与资源状态检查 | 当前 E1 表面跨家庭、缺权限、错误主体、过期/撤回负例 PASS；未实现业务 endpoint 不宣称通过 AUTH-001..007 |
| E1-T06 | 双端 Compose 登录、邀请/本人确认、家庭管理、授权/撤回、loading/error/offline、退出；Keystore AES-GCM 与禁止备份 | 双端构建、24 次 JVM 单测执行与 lint PASS；真机 UI/Keystore/进程恢复 smoke NOT VERIFIED |
| E9-T01..05 | ADB 基线重新采集、各 Spike 的依赖、证据与关闭状态已记录 | NO_AUTHORIZED_DEVICE；硬件 gate 全部 NOT VERIFIED，见 [设备记录](week2-device-spikes.md) |

本轮修复：

- Windows 下异步 psycopg 需要 selector 事件循环。新增 `python -m app` 入口在创建循环前配置；真实 HTTP 的登录→家庭→授权→撤回→退出测试通过。
- 邀请确认与已读取的家庭 ID 绑定。切换家庭不能使用另一家庭的邀请码确认身份。
- 网络结果不明时，幂等写入保留原请求和 key；另一写入不能覆盖它。明确的拒绝响应清理待重试内容；离线和待重试时禁用新修改。
- 第二周验证入口要求显式 PostgreSQL `*_week2_test` 数据库；拒绝不符合条件的库，并检查实际测试数量和跳过项。CI 保留原有空库 downgrade/re-upgrade，增加全套后端与迁移一致性检查。

## 已执行证据

| 检查 | 结果 | 本地 evidence |
| --- | --- | --- |
| Ruff | PASS | `artifacts/week2/verification/lint.txt` |
| 后端单元/contract/integration/源码、fixture、Git 历史与日志隐私 | PASS：100 tests，0 failure，0 error，0 skipped；APK 检查作为独立门禁明确 deselect | `artifacts/week2/verification/backend-tests.xml` / `summary.json` |
| PostgreSQL API/并发/权限与真实 HTTP 启动 | PASS：15 integration cases，包含在上述 100 项内 | `backend/tests/integration/test_week2_postgres.py` 与同一 XML |
| Alembic upgrade 与模型一致性 | PASS：`No new upgrade operations detected` | `artifacts/week2/verification/migration-upgrade.txt` / `migration-parity.txt` |
| 独立空库 upgrade→downgrade→re-upgrade | PASS；downgrade 后 business table count=0 | `artifacts/week2/migration-rehearsal.txt` |
| 虚构数据 pg_dump→独立库 pg_restore | PASS；8 表行数一致，包含授权历史 | `artifacts/week2/migration-restore.json` |
| Android 双端所有 variant / unit / lint | PASS：12 APK、24 次单测执行，0 failure/error/skip；lint 0 error | `artifacts/week2/android-build-verified.txt` / `android-summary.json` / `android-tests/` / `android-reports/` |
| 交付源码与 Android 构建副本一致性 | PASS：49 个源文件 SHA-256 比对一致；包含锁文件和构建脚本 | `artifacts/week2/android-summary.json` |
| 离线锁定依赖构建 | PASS：不使用 `--write-locks`，`--offline --no-daemon build` 成功 | `artifacts/week2/android-locked-build.txt` |
| APK、源码、fixture 与 Git 历史隐私门禁 | PASS：7 tests；12 APK 均扫描 | `artifacts/week2/apk-privacy.txt` |
| 后端 wheel 构建与源码目录外安装运行 | PASS：三环境 profile / health，包含新增启动入口 | `artifacts/week2/backend-wheel.txt` / `installed-wheel.txt` |
| 本次 ADB 基线 | NOT_RUN：NO_AUTHORIZED_DEVICE | `artifacts/week2/device-baseline.json` |

PostgreSQL 17.11 为本机隔离测试实例，仅监听 loopback；CI 保持原 PostgreSQL 16
配置，尚未在 GitHub 执行本轮修改。运行资源置于本聊天的可写工作区中，未修改系统安装、
信任库、服务注册或防火墙。测试库只含虚构数据。Android 使用 JDK 17、Gradle 8.11.1
与 SDK 35，英文路径副本用于避开 Windows 中文路径限制；最终以源码 hash 比对和
构建报告验证交付目录与副本一致。Gradle Kotlin 编译之后的 JAR 访问曾被沙箱阻止，
后续构建在同一测试副本中运行，原失败证据保留。

双端 demo 调试安装包：

- [长辈端 APK](../../android/app-elder/build/outputs/apk/demo/debug/app-elder-demo-debug.apk)
- [家人端 APK](../../android/app-family/build/outputs/apk/demo/debug/app-family-demo-debug.apk)

两个 APK 均约 9.07 MiB，是 debug/Mock 包。release variant 只验证编译与打包，
不宣称正式签名或商店发布。lint 保留既有的依赖新版提示与缺应用图标警告；没有隐藏
lint 错误或升级冻结版本。`feature-auth` 未新增外部供应商 SDK，使用 AndroidX/
Compose/Coroutine（Apache-2.0）与平台 Keystore/HttpURLConnection；对应 dependency
lock 已交付。未建立旧版 APK 体积基线，不能推算单模块增量。

## 可复现后端检查

在一次性 PostgreSQL 实例先创建名称以 `_week2_test` 结尾的空库。测试会截断其中
8 张基础表，绝不要指向应用家庭数据库。

```powershell
$env:WEEK2_TEST_DATABASE_URL = 'postgresql+psycopg://<test-user>:<local-password>@127.0.0.1:<port>/niannian_week2_test'
.venv/Scripts/python.exe scripts/verify_week2.py
```

入口自动执行现有迁移、`alembic check`、lint 和相关后端测试。没有数据库时退出 2
并标记 NOT VERIFIED；检查失败退出 1。APK 独立检查见 Android 构建后执行的
`NIANNIAN_REQUIRE_APKS=1 python tests/security/test_artifact_scan.py`。
`--device` 可同时采集设备库存，但不能据此通过实际硬件 Spike。

## 双端演示步骤（待真机 UI smoke）

1. 应用数据库执行现有 `alembic upgrade head`；配置本地随机 `AUTH_SIGNING_KEY`
   （至少 32 字符，保存在忽略的 `.env` 或进程环境）。在 `backend/` 执行 `python -m app`。
   重启时保留同一密钥；不要把密钥放进源码、截图或聊天。
2. 模拟器调试包服务地址填写 `http://10.0.2.2:8000`。真机使用可信 HTTPS，
   或明确配置 ADB loopback forwarding 后的调试地址；release 强制 HTTPS。
3. 家人端以虚构 DEMO 身份登录，创建家庭，生成长辈邀请码。
4. 长辈端以虚构 DEMO 身份登录，读取邀请，与提供邀请码的家人核对家庭名称和角色，
   点击本人确认。未确认时看不到家庭成员内容；加入不会打开任何数据授权。
5. 长辈主动打开“家庭记忆”等单项授权。家人端刷新可查看授权状态，不能代为授予。
6. 长辈撤回授权；家人端刷新显示已撤回。历史授权保留，服务端下一次 scope 判定拒绝。
7. 断网显示已加载信息尚未确认，新修改禁用。网络恢复后重新读取；结果不明的写入
   通过“重试上次请求”显式使用同一幂等 key。
8. 退出本机或本账号所有设备，再尝试访问应要求重新登录。实际 Keystore/缓存擦除、
   杀进程、权限拒绝和旋转恢复必须在设备上另外验收。

## 决策、限制与后续

沿用 2026-09-30 已接受的 ACTIVE-only 家庭详情决策。不改需求、OpenAPI/WSS、
公共 enum、Consent scope、数据库约束或现有 migration。新增运行入口、测试与 UI
实现细节无需合同变更。无新增生产依赖，`feature-auth` 使用已经采用的 Compose/
AndroidX/Coroutine 技术栈；锁文件随验证后的实现交付。

待验：实际 Android UI/Keystore/生命周期 smoke、指定平板/BLE/SIM/摄像头/音频/
kiosk 门禁，以及更新后的 GitHub Actions。设备记录仍为 UNKNOWN，不宣称真实 Provider、
通知送达、电话接通、麦克风/摄像头或离线 AI 能力。E4-T01/E8-T01 等后续 Spike
前置任务按原开发计划安排，本轮不启动第三周任务。
