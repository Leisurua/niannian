# 第三周交付记录

完成日期：2026-10-13。软件交付 **PASS**；含真机的整周验收 **IN_PROGRESS**。

2026-10-14 真机续验：**PHONE-12 PASS**，见 [原照片记忆编辑后重新确认](phone-12-20261014.md)。本次小米 12 使用原 CI APK，唯一原 Memory ID 经手机编辑及人工确认完成 `CONFIRMED v1 → PENDING v2 → CONFIRMED v3`；双端列表隔离、新内容和原照片均取得界面/API/数据库证据。旧小米 15 的结果不移用为本机通过结论，整周真机验收仍未完成。

2026-10-14 独立补验：**PHONE-09 PASS**，见 [待确认候选展示隔离](phone-09-20261014.md)。新候选 `01a13a45-76f3-7382-af57-7717cb5922ee` 在 `PENDING v1` 时经双端分别刷新，已确认列表不可见、候选列表和详情可见；用户家人端人工确认后同一 ID 为 `CONFIRMED v2`，双端已确认列表可见、候选列表不可见。界面、完整鉴权 API 列表与只读数据库证据独立保存，整周真机验收仍为 INCOMPLETE；完整 RAG 门禁未由本用例关闭。

2026-10-14 照片异常路径独立真机验收：**FAIL**，见 [照片选择与上传异常路径](photo-errors-20261014.md)。测试 Memory `01a13a7f-505d-7da2-803c-322082945402` 取消选择通过；超限 PNG、GIF、损坏 PNG 和有效 PNG 实际选择后均无上传/错误反馈，无 File ID。校验/隔离下游和双端照片查看 NOT VERIFIED；原测试记忆 API/数据库保持 CONFIRMED/v1、无附件。未修改应用或执行物理删除、断网恢复、退出/Keystore，整周真机验收仍为 INCOMPLETE。

2026-10-14 照片选择修复后复验：**PHOTO-SELECT-01 PASS**，见 [修复与真实照片链路复验](photo-retest-20261014.md)。修复选择器返回时依赖已清空状态的问题；同一原测试记忆经手机实际取消、超限 PNG/GIF 拒绝、损坏 PNG 隔离及有效 PNG 上传。实际损坏文件 `01a13aa1-7a80-7a5b-b172-a95a7fe1112c / QUARANTINED`，有效文件 `01a13aa2-465c-7590-90c2-b32ad827f43e / AVAILABLE`；同一小米 12 上双端完整显示照片。9 项 JVM、照片模块 lint 和双端 Demo 构建通过，已安装 APK 哈希绑定本次构建。因签名差异重装 Demo 并恢复虚构登录，服务器 fixture 保留；旧长辈会话根因未核查，整周仍为 INCOMPLETE。

## Task

进度检查确认起点为第二周软件交付。本轮完成第三周 Memory/File 与双端页面、Reminder 后端骨架、Conversation REST/WSS 状态。第四周 AI 编排、第五周 RAG/离线提醒、第六周摘要不在本轮。

合同差异已由用户明确批准：“批准推荐方案，继续第三周实现”。见 [W3-01..05](../plan/week3-contract-review.md)。

## Changed

| 范围 | 交付行为 |
| --- | --- |
| Memory | 同家庭 ACTIVE 成员、权限和当前 Consent 检查；AI_CANDIDATE 只能 PENDING；人工确认/拒绝、乐观锁编辑、错误反馈、撤回和删除；默认列表只返回已确认可见事实，修改事实需重新确认 |
| File | 上传必须关联已授权 Memory；短签名、长度/SHA-256/类型/像素限制、实际解码及无元数据重编码；安全副本与上传键隔离；无效图片 QUARANTINED；下载代理每次检查登录、签名、Consent 和资源状态 |
| Cleanup | 删除先不可见；worker 清理原对象和安全副本，失败保留 DELETE_REQUESTED 并记审计；上传窗口结束后清理重放 PUT 可能重建的原对象 |
| Reminder | 明确家庭、IANA 时区、本地周期、DST 与免打扰；唯一 occurrence；DONE/LATER/SKIPPED 幂等反馈；worker 生成 NO_RESPONSE，仅表示尚未收到反馈 |
| Conversation | 长辈主动开始 TEXT 会话；REST 状态/结束；WSS envelope、单会话数据库连接锁、跨重连双向序号、逐条及空闲周期重新鉴权；身份说明标识 Mock |
| Android | 新增 feature-memory；双端列表/详情/候选确认、编辑、反馈、撤回/删除、照片上传/查看；切换家庭、后台或访问拒绝时清除敏感显示；未知写入结果保留原幂等 key |
| Engineering | 新迁移、依赖锁、fixture 合同同步、第三周统一验证与 PostgreSQL CI；第二周入口明确分离第三周集成环境 |

照片处理是限定格式的解码/重编码，不声称通用杀毒服务。WSS 本周完成状态协议，AI 回复、音频和摘要明确不可用。提醒执行记录代表服务端可提供提醒，不代表设备已播出或用户实际服药。

## Tests

实际证据位于忽略目录 `artifacts/week3/`；不把跳过当通过。

| 检查 | 结果 | Evidence |
| --- | --- | --- |
| 后端总回归，含第二/三周 | **243 tests，0 failure/error/skip**；APK 独立验收 | `ci-fix-verification/summary.json` / `backend-tests.xml` |
| PostgreSQL API/权限/并发/worker/WSS | PASS，包含在总回归；同 key 并发写和 occurrence 唯一、撤权拒绝、重连/重放/连接互斥实际执行 | `backend/tests/integration/test_week3_postgres.py` |
| 真实 MinIO | PASS：签名 PUT、匿名读取 403、确认/去元数据、代理下载、已签链接撤权 404、物理清理 | `backend/tests/integration/test_week3_storage.py` 与总回归 XML |
| Ruff | PASS | `ci-fix-verification/lint.txt` |
| 13 表迁移 | upgrade/模型一致性 PASS；独立空库升级→回滚→重升级 PASS，回滚后业务表为 0 | `migration-summary.json` / `migration-rehearsal.txt` |
| 虚构数据备份恢复 | pg_dump→独立空库 pg_restore PASS，13 表行数一致 | `backup-restore.json` |
| Android 离线锁定构建 | 12 APK，**68 次 JVM 测试执行，0 failure/error/skip**；6 份 lint 报告无 error | `android-summary.json` / `android-build.txt` / `android-tests/` |
| 构建副本一致性 | 57 个源码/配置文件 SHA-256 与交付目录一致 | `android-summary.json` |
| 源码/fixture/Git/APK 隐私 | PASS，7 tests，扫描 12 APK | `artifact-scan.txt` |
| 后端 wheel | 打包及源码目录外安装运行 dev/test/demo health PASS | `wheel-check.txt` |
| 当前 ADB | NO_AUTHORIZED_DEVICE，硬件 NOT VERIFIED | `device-baseline.json` |

Windows 使用英文路径构建副本，最终源码 hash 绑定报告。新增模块锁文件已交付，最终构建不使用 `--write-locks`。既有依赖版本和应用图标 lint 警告未屏蔽。

已修复：幂等响应时区差异统一为 UTC；旧 fixture 补齐明确的虚构 source/family_id。跨会话停止的测试服务已恢复并重新验证。官方 MinIO 二进制地址返回 410，未下载成功；实际验收使用官方固定源码 `7aac2a2c5b7c` 构建的隔离服务。

2026-10-13 CI 补验：远端 push 工作流曾暴露 WSS 取消清理竞争。断开时的异步 rollback/close 可能再次被取消，遗留连接计数与租约。现以屏蔽外层取消的清理作用域释放数据库资源，计数在 finally 中释放；新增两条回归均已证明在旧提交清理代码上失败、修复后通过。完整 243 项回归和真实 MinIO 再次通过。机制参考 [AnyIO finalization](https://anyio.readthedocs.io/en/stable/cancellation.html#finalization)。

## Decisions

- D-002/D-003/D-017：不保存原始音频，不接真实 AI Provider，不将输入全文写入会话表。
- 星期一=0，WEEKLY 以开始日所在周为锚，INTERVAL 按本地天；DST 重复选首次、缺失跳过，免打扰起止相同表示关闭。
- 删除/撤权在下一次服务端判定生效；不能收回客户端此前已读到的内容。
- 新增 Pillow 12.3.0（MIT-CMU）、boto3 1.43.111（Apache-2.0）、APScheduler 3.11.3（MIT），传递依赖已锁定。Android 复用 AndroidX/Compose/Coroutines。
- MinIO 是独立 AGPLv3 测试工具；构建物、数据库、凭证和照片不进 Git。处理参考 [Pillow 安全文档](https://pillow.readthedocs.io/en/stable/handbook/security.html) 与 [Boto3 短签名文档](https://docs.aws.amazon.com/boto3/latest/guide/s3-presigned-urls.html)。

## Contract Changes

应用已批准 W3-01..05：Memory source/version，Reminder family/version/next_due_at，Conversation backend_state/input_mode/双向 sequence，关联 Memory 的上传请求，以及鉴权照片下载 operation。OpenAPI 75 operations，WSS 类型保持 9/11；字典、设计、权限矩阵、API 说明、ADR-006 已同步。

新迁移 `20261010_week3_core` 接续原八表迁移，新增五表；原迁移不改。13 表尚不覆盖完整 12 周 seed，不把完整业务 seed 重放标为通过。

## Not Verified

实际 Android UI/照片选择器、杀进程恢复、Keystore 和硬件门禁待指定设备。本机检查不替代真机或远端 CI。远端 CI 以 PR 当前 head 结果为准；新 CI 的 `--postgres-only` 明确不包含 MinIO，本地真实 MinIO 证据独立保留。debug APK 不代表正式签名或商店发布。

## Issues

无已知本轮软件验收阻塞。真机缺失仍为未验收，不关闭综合设备门禁。RAG、摘要、通知和完整删除传播按原周计划继续。

## Next

按用户要求推送任务分支并创建 PR；链接与远端状态由本聊天最终交付。第四周留待下一次任务，不提前实施。

### 运行和演示

1. 安装 `backend/requirements.lock`；在 `backend/` 应用迁移，配置随机 `AUTH_SIGNING_KEY` 与私有 S3 设置，执行 `python -m app`。
2. 设置设备可访问的 `PUBLIC_BASE_URL` 和 S3 上传地址；正式网络使用 HTTPS。另开终端执行 `python -m app.worker.main --serve`。
3. 双端登录虚构 DEMO 身份；邀请/本人确认后，由长辈主动授予 FAMILY_MEMORY。
4. 家人选择长辈、保存候选，再核对确认。长辈默认列表显示已确认记忆；照片实际检查后可见，编辑后需重新确认。
5. 撤回授权后家人刷新或重新打开被拒绝；删除立即不可读，worker 继续物理清理。提醒和 WSS 本周通过 API/集成用例演示。

调试包：[长辈端](../../android/app-elder/build/outputs/apk/demo/debug/app-elder-demo-debug.apk)、[家人端](../../android/app-family/build/outputs/apk/demo/debug/app-family-demo-debug.apk)。本地构建产物不随 Git 提交。

统一验证：配置 `WEEK2_TEST_DATABASE_URL`、`WEEK3_TEST_DATABASE_URL` 与 `WEEK3_STORAGE_CONFIG`，运行 `python scripts/verify_week3.py`。数据库名分别必须以 `_week2_test`、`_week3_test` 结尾，无连接覆盖查询参数。存储配置 JSON 包含 `endpoint,bucket,access_key,secret_key`，实际门禁限定 loopback 59003 与 `niannian-week3-test` 桶；不要指向现有家庭存储。
