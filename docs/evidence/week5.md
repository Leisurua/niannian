# 第五周 RAG、删除传播与离线提醒交付记录

交付记录日期：2026-10-17；后端与 Android 核心测试于 2026-10-16 完成。**第五周软件范围 PASS；含设备的整周验收仍为 IN_PROGRESS。**

## Task

继续并完成第五周 E2 RAG/delete propagation、E3 offline cache/timezone。W5-01..04 已由用户
在本聊天回复“继续实现”“继续”批准，见 [已批准方案](../plan/week5-contract-review.md)。
保留进入本任务时已有的 development-plan 修改；没有执行第六周摘要、Signal 或真实语音。

## Changed

- 新增 memory_chunk、memory_embedding、task_outbox 模型和第五周迁移，原迁移保持不变。
  pgvector ACTIVE 向量校验维度、非空与非零；内部任务使用业务唯一键、30 秒租约、token fence、
  20 秒执行上限、5 次尝试、退避与 DEAD 状态。Provider I/O 与数据库写回分开。
- 确认记忆经 Mock Embedding 建索引；检索在同家庭/主体、角色、当前显式 Consent、visibility、
  CONFIRMED、未删除/撤回/过期、ACTIVE chunk/vector 和 source_version 过滤后的 MATERIALIZED
  集合计算 exact cosine。生成完成及重复回复前重新授权。无检索缓存、无全库检索后过滤。
- 本人会话使用 subject=self/grantee=self 的显式分项授权，默认关闭；Android 有独立确认与撤回入口。
  不复用个人 REST 读取的 Consent 豁免，不推导子女授权。拒绝后基础 Mock 陪伴继续。
- Mock 引用只能来自本轮获准集合；非法引用、向量身份/格式、注入内容、超时和故障均有负例。
  prompt 版本为 1.1.0。保留 Mock 标志，不产生候选确认、通知、真实语音或其他敏感动作。
- 删除/撤回先不可见并失效派生数据，再执行有界清理任务。文件先清理一次，旧签名 PUT 窗口结束后
  再最终清理，防止原始对象重新写入。清理失败不恢复可读性；DEAD 可从内部任务状态观察。
- 增加 owner-only 离线 occurrence 反馈 API，服务端重算计划时间和 occurrence key，验证版本、
  家庭/归属、有效资源与 24h 反馈期限；与已有 ONLINE 行合并并保留原来源，禁止客户端 NO_RESPONSE。
  重试使用原幂等键，过期 LATER 不自动修改时间，也不把反馈/通知提交当作服药或送达事实。
- 双端接入提醒页面。家人端支持简单一次/每日提醒的创建、编辑、删除及反馈记录；用药二次核对。
  长辈端大字展示 DONE/LATER/SKIPPED、离线、待同步、冲突及过期状态。高级规则由既定算法读取执行，
  不增加高级编辑器或自动改医嘱。
- 长辈端使用 Room v1 密文快照，规则/occurrence/PendingAction 原子提交；Keystore AES-GCM，
  family/owner/version/expiry、payload hash、幂等键和重试状态均持久化。支持离线 LATER 后终态反馈
  的有序两步队列、校验匹配 ACK、进程重启恢复、时钟倒退拒绝、退出/切换家庭/已知撤权清理。
- 同一家庭的进程重启保留队列；家庭选择保存在加密登录状态内，并与 token 更新串行，避免清空
  离线反馈或覆盖刷新凭证。旧回调与旧快照不能恢复已擦除内容。
- 通知调度/开机与时间变更接收器只在 app-elder；使用 inexact AlarmManager，锁屏仅提示打开念念，
  无健康正文。app-family 不增加通知或开机权限。页面活跃时每分钟尝试同步，后台通知不上传动作。
- 新增 scripts/verify_week5.py 与第五周 CI；旧 PostgreSQL CI 镜像适配 pgvector。执行副本有源码 hash；
  CI 配置已写入，远端执行结果仍未验证。

## Tests

实际证据位于忽略目录 `artifacts/week5/`；只使用独立虚构测试库和私有测试桶。

| 检查 | 实际结果 | Evidence |
| --- | --- | --- |
| 完整后端/契约/源码隐私回归 | PASS：350 tests，0 failure/error/skip | `verification/summary.json`、`verification/backend-tests.xml` |
| 实际 PostgreSQL 16.15 / pgvector 0.8.6 | PASS，含 RAG 正负例、生成中撤权、并发离线重放、租约旧 token 拒绝 | `backend/tests/integration/test_week5_postgres.py`，包含在 350 项内 |
| 实际 MinIO | PASS，私有上传/下载代理撤权及 outbox 删除 | `backend/tests/integration/test_week3_storage.py`，包含在 350 项内 |
| 第五周迁移 | PASS：空 *_week5_test 库 upgrade→downgrade 到 week3→upgrade；两次 Alembic check 无差异 | 本轮实际命令输出；原业务测试库未回滚 |
| Android 全量构建 / JVM / lint | PASS：12 APK，128 次 JVM 测试，0 failure/error/skip；8 份 lint 报告无 Error/Fatal | `android-final-build.txt`、`android-final-summary.json`、`android-final-reports/` |
| Android 源码一致性 | PASS：80 个源码/配置文件 SHA-256 与构建副本一致 | `android-source.json` |
| APK 与最终源码隐私扫描 | PASS：7 tests，0 failure/error/skip；扫描全部 12 APK | `final-apk-source-scan.xml`、`final-source-hashes.json` |
| 双端 APK 权限 | PASS：家人端无通知/开机权限；仅长辈端声明 POST_NOTIFICATIONS、RECEIVE_BOOT_COMPLETED | `family-apk-permissions.txt`、`elder-apk-permissions.txt` |
| 后端 wheel | PASS：离线构建，源码目录外安装；16 个模型、dev/test/demo 配置及 prompt 1.1.0 Mock 调用实际运行 | `wheel-build-retry.txt`、`wheel-check.txt` |
| 最近一次设备检查（2026-10-16） | NO_AUTHORIZED_DEVICE；真实设备 NOT VERIFIED | `device-baseline.json` |

早期 44 项时间测试和 50 项源码扫描为准备阶段记录，不与当前回归累计。修复过的失败包括：
测试中的 revoke HTTP 预期、operation 清单顺序、租约时间精度边界；Android 通知代码共享导致
家人端 lint 报权限错误，已移到长辈端；恢复测试误将包含次日提醒的列表假定为单条，改为按 key 核对。
最终另补齐了实际 DB 向量/任务约束负例，以及 PendingAction payload hash、ACK 资源匹配和
持久家庭绑定重启测试；重启回到同一家庭不会擦掉未同步反馈。
没有关闭 lint、放宽隐私正则或将跳过测试称为 PASS。

环境记录：临时构建目录消失、Windows Gradle transform 移动失败和沙箱临时目录权限影响过运行；
最终使用任务专属 ASCII 路径、独立缓存与已有 JDK/SDK/Gradle 存档。一次设备检查因自动审批额度
不足未执行，正常重试后确认无已授权设备。实际 Postgres/pgvector 来自官方文档推荐的
[conda-forge 安装方式](https://github.com/pgvector/pgvector#conda-forge)，仅运行于本机隔离端口。
新增 Room runtime/compiler 锁定 2.6.1，Java annotation processor 生成并纳入版本管理的 schema；
用法见 [Android Room 文档](https://developer.android.com/training/data-storage/room)。

## Decisions

- 仅交付 Mock 软件路径。Mock Embedding 是确定性 hash 向量；正例证明授权/引用流程，不证明通用
  语义检索准确率。演示匹配记录时使用相同虚构文本；未知问题仍诚实回退。
- W3 时间策略继续有效：星期一=0、周间隔按开始周、DST 重复取首次、缺失跳过、相同免打扰起止禁用。
- 24h 是本地读取与发送上限。远端撤权在完全离线设备上于恢复连接或本地 expiry 生效；系统暂停
  应用可能延迟物理擦除至下一次允许的唤醒/启动，恢复后过期数据不能展示/发送。该设备能力边界
  不据 JVM 测试宣称已经通过。
- 不添加真实 Provider、真实播音、摘要、Signal、家庭推送或真实服药判断。家人端仅在线读取。

## Contract Changes

已按批准的 W5-01..04 同步：新增 Chunk/Embedding 与内部 task_outbox 迁移；一个
`POST /v1/reminders/{id}/offline-feedback` operation（REST 总数 76）；本人 RAG 显式 self-grant
说明和 24h 本地提醒/反馈期限。实现模型总数 16。API、权限矩阵、字典、DB、隐私、留存与设备
文档、契约清单已同步。WSS 类型、ConsentScope 和现有公开业务状态保持原值。

## Not Verified

- 真机 UI/TalkBack、实际 Room/Keystore I/O、系统通知授权、重启/杀进程/Doze、OEM 闹钟时序和
  缓存清理；最近一次检查无已授权设备。JVM 使用注入 store/clock，不能替代设备验收。
- 实际 ASR/TTS/LLM/Embedding、语义检索性能及大规模延迟；没有真实语音或送达证据。
- 正式签名发布、生产数据库迁移、远端 CI；没有提交、推送或发布动作。

## Issues

整周设备门禁尚未关闭。现有 Starlette/AnyIO 弃用提示和测试退出时的脱敏日志 sink 提示仍可见，未作为真实 Provider 或性能证据。后台闹钟可能延迟，通知权限未授予时不提交通知；待反馈自动同步仅在提醒
页面活跃时进行，后台不会开启网络会话。实际硬件表现以指定设备结果为准。

## Next

在指定设备执行 REM-001..012 中的设备场景和 Keystore/退出擦除验证；不自动启动第六周。

复现后端：安装锁定依赖，设置独立 `_week2_test`/`_week3_test` URL，以及端口 59003、桶名
`niannian-week3-test` 的 WEEK3_STORAGE_CONFIG，运行 `python scripts/verify_week5.py --source <独立ASCII源码副本>`。
此入口缺数据库/存储时会显示 NOT VERIFIED，不以跳过表示完成。Android 见 feature-reminder/README。

演示：使用虚构 DEMO 家庭；家人创建提醒，长辈联网缓存后断网，完成/稍后/跳过先显示待同步，
恢复连接按原 key 同步。RAG：长辈显式允许“用于我与念念的交流”，确认虚构 Memory，运行 worker，
在 Mock 文字备用入口输入匹配文本；撤回后下轮/重复回复不再引用该事实。原始音频不落盘。

交付文件：`artifacts/week5/apks/app-elder-demo-debug.apk`、`app-family-demo-debug.apk`；后端 wheel 位于 `artifacts/week5/wheel/`。所有二进制和本地测试服务配置均不提交 Git。最终汇总见 `artifacts/week5/delivery-summary.json`。
