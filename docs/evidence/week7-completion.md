# 第七周事件与家属通知交付记录

日期：2026-10-19。**W7-01～04 已批准的 Mock 软件范围 PASS；真实推送和指定设备验收未关闭。**

## Task

完成 development-plan §20 第七周：E5 规则警告/SignalEvent、E6 Mock/IN_APP Notification，
验证“警告 → 最小事件 → 授权家属收件箱”，摘要与通知授权独立。
项目负责人在本聊天回复“是”，批准 [W7-01..04](../plan/week7-contract-review.md)，并要求继续。
[审批前记录](week7.md)保留历史状态；本轮没有启动第八周家属处理动作或紧急联系闭环。

## Changed

- 新增 SignalEvent、Notification、NotificationAttempt、NotificationPreference 和迁移。
  事件保存已批准的触发类别、规则/策略版本与固定最小证据，不保存当前输入、逐字稿、
  原始音频、来源消息正文或 evidence hash。source_message_id 为 null，会话引用真实存在。
- 六类暂态候选继续使用有限、确定性的 Mock 语句。应用服务复验当前轮次、来源、家庭、
  长辈角色、成员状态和词表；五类非紧急事件可以持久化。EMERGENCY 仍为本地提示，
  第八周才处理紧急事件/联系人。LLM 不决定权限、严重度或发送。
- 本地 warning 先于 AI 回复，模型/TTS 不可用仍可提示；实际创建事件后才发 signal.created。
  长辈端支持这两种既有消息，保持顺序校验与等待轮次状态，不宣称已通知或送达。
  旧兜底话术已更新为“关注提示需单独授权，推送仅为 Mock 模拟”。
- 家庭事务锁与 family/owner/type/category/severity/30 分钟桶防并发重复；来源轮次的
  幂等审计防跨桶重放。重复不延长保留期、不重复入队；类别/严重度变化可产生新事件。
- 家属必须满足当前同家庭 ACTIVE 成员、角色/SIGNAL_READ、指定 grantee 的
  NOTIFICATION_TO_FAMILY；身体不适另需 HEALTH_MEDICATION。SCAM 不自动要求健康授权。
  仅分享摘要不产生事件或通知；仅通知授权不能读取摘要；撤回摘要不关闭独立通知。
  IMPORTANT_MEMORY 只展示待核实模板，不读取 PENDING Memory 或暴露实际记忆内容。
- 实现既有 Signal list/detail、Notification list/detail/read。列表在分页前过滤授权；
  隐藏对象详情返回 404，敏感详情/已读审计，响应 no-store。长辈只见自己的有限安全状态；
  家属确认、联系、误报、resolve/action 留在第八周，不显示成已实现能力。
- 通知与事件分开持久化。新增三个 outbox kind，复用独立 worker、租约、有限重试、
  退避和 DEAD；每次派发前后复查来源、授权、偏好版本和租约，旧 worker 不可写回。
  在途撤回会取消/隐藏相应通知；重新授权不恢复旧任务。一个收件人撤回不影响其他有效收件人。
- IN_APP 发布为 SENT，显式读取才 READ；MockPush 仅模拟接受，delivery_observed=false，
  从不自动填写 delivered_at 或标 DELIVERED。错误使用固定脱敏码；尝试有独立次数、
  状态和时间。全部渠道失败才 NOTIFICATION_FAILED，任一有效渠道发布为 NOTIFIED，
  该事件状态不等于设备到达或家属已读。
- 新增两个通知偏好接口，收件人从登录身份推导；PUT If-Match，缺省 version=0。
  默认仅 IN_APP，PUSH 默认关闭；本轮只支持 Mock。免打扰默认 22:00–08:00，IANA 时区；
  现有 Family 没有时区字段，使用项目 Demo 的 Asia/Shanghai 默认，用户可显式修改。
  非紧急通知含 L3 均遵守免打扰；等待不消耗 Provider 尝试次数，也不延长派发期限。
- 获批 Mock 事件/通知最长 7 天、待发最长 24 小时，从首次创建起不续期。读取/派发先隐藏，
  worker 再按 Attempt → Notification → Signal 清理。来源删除、成员失效、过期、撤权均
  拒绝后续访问；清理失败不会重新可见。任务/审计元数据的最终期限仍沿用原门禁。
- 家属端加入前台 30 秒轮询、手动刷新、已读、渠道/免打扰设置；显示 Mock、同步失败和
  未验证设备推送到达。前台短暂展示，后台、换家庭、退出、离线/失败、已知授权变化清空。
  已读使用幂等键但不写本地待办、通知 ID 或正文缓存。沿用现有可见长辈选择入口。
- 同步 OpenAPI、DB/字典、权限、隐私、留存、规则、AI/UI 合同及历史 Demo 必填字段。
  新增 verify_week7.py 入口，交付双端 Demo Debug APK 与后端 wheel。未添加依赖或硬件权限。

## Tests

| 实际执行 | 结果 | 证据（忽略目录 artifacts/week7/） |
| --- | --- | --- |
| 最终完整后端/契约/AI/安全/Demo 回归 | PASS：513 项，0 failure/error/skip | backend-verified/summary.json、tests.xml、tests.txt |
| 第七周用例 | 60 项包含在完整回归内；13 warning、13 纯策略、1 契约、33 PostgreSQL/WSS | backend/tests/unit/test_week7*、contract/test_week7_contract.py、integration/test_week7* |
| 实际 PostgreSQL/pgvector、真实本机 MinIO | PASS，独立虚构测试库/私有测试桶 | 完整回归中的数据库/存储用例 |
| 独立 worker 进程 | PASS，子进程 --once 实际发布 IN_APP 通知 | test_standalone_worker_process_publishes_inapp_notification |
| 最终迁移升级/空库回滚/重升级/parity | PASS | migration.txt |
| 双端 Demo Debug 构建 | PASS：两个 APK | android-verified-delivery.txt、android-summary.json |
| 修改相关 Android JVM 测试 | PASS：36 项，0 failure/error/skip | android-reports/、android-summary.json |
| Android lint | PASS：3 份报告，0 Error/Fatal | android-reports/ |
| APK/源码/Git 历史隐私扫描 | PASS：7 项，完整扫描本轮 2 个 APK | apk-source.xml |
| 构建源码一致性 | PASS：86 个 Android 文件与原目录一致；最终运行时代码 hash 一致 | android-source-hashes.json、final-code-hashes.json |
| wheel 离线构建、源码外安装/导入/健康/路由 | PASS | wheel-final-build.txt、wheel-final-check.txt |
| ruff、git diff --check | PASS | backend-verified/lint.txt、本聊天实际命令输出 |
| 本轮测试服务清理 | PASS：核对进程命令行后仅停止 week7 PostgreSQL/MinIO；保留数据和日志 | service-cleanup.json |

这些是本轮各范围证据，重复回归不累计为新用例。没有用第六周 APK 或历史设备证据
替代本次结果。最终文档收尾与代码测试分开；运行时代码 hash 对应最后通过的快照。

关键集成覆盖：摘要 only/通知 only、健康 scope、指定收件人、跨家庭、缺权限、
到期/撤回/重新授权、成员/主体/家庭/来源失效、长辈角色变化、未验证事件拒绝、分页绑定、
并发去重、跨桶重放、新类别/严重度、免打扰/过期队列、Mock 成功/失败/超时/虚假送达拒绝、
重试耗尽、遗失租约、旧完成拒绝、过期物理清理和独立 worker。
JVM 覆盖前台轮询启动、失败清空、旧回调隔离、家庭切换、设置版本、消息解析与已读不落盘。

失败及恢复均保留：第一轮发现已读时间首次/重放的时区表示不同，已统一 UTC；测试对
既有撤回接口返回码和网络 IOException 的预期已修正。完整回归发现历史 Demo fixture
缺新增必填字段，补齐类别/期限，并移除 Mock 的虚假 delivered_at。没有放宽权限断言。
旧兜底文案对齐新能力后重新验证；期间会话中断使隔离 PostgreSQL/MinIO 退出，连接失败
批次已停止且未记 PASS。恢复原任务测试目录、确认就绪后，最终完整回归通过。
沙箱初轮 daemon/Python 问题及中间失败日志均保留，没有跳过失败用例。

## Decisions

严格按已批准 W7-01..04 实施。当前仍是有限 Mock 语句、固定证据与通用通知提示，
不表示开放域识别质量。IN_APP 是应用内可查看，MockPush 不是实际设备到达。
“未授权则仅本地提示”采用方案允许的路径，不为了演示状态而保存敏感 WITHHELD 证据。
家属偏好不代授 Consent，摘要与通知独立；框架和跨模块调用沿用公开服务。

## Contract Changes

已获批并同步：四张事件/通知相关表、trigger_category、事件/通知期限与通知派发期限、
三个 outbox kind、两项偏好 REST operation（总数 82）、逐类型权限/去重和既有状态解释。
当前已实现模型 22 个，迁移头 20261019_week7_notifications。Mock 来源消息/hash 为 null；
未新增 ConversationMessage/逐字稿表。WSS 类型、ConsentScope、SignalType、公开状态枚举不变。

## Not Verified

指定设备 UI/TalkBack、真实前后台/OEM 行为与性能；真实 Push/SMS/电话/语音 Provider；
本轮未构建的 dev/qa/release 变体、正式签名、远端 CI、生产迁移与部署。Mock 不能证明
真实网络已送达或电话已接通。第八周家属动作与 Emergency、第九周报告未提前执行。

## Issues

获批 Mock 软件范围无未解决测试失败。当前采用课程规模的权限过滤，未作大数据量性能验收。
跨授权变更仍以服务端下一次判定及前台刷新为准，实际第三方已发出的数据不能追回；本轮
不启用真实外部发送。现有 Starlette/AnyIO 弃用提示与 pytest 退出时脱敏 LOG_SINK_FAILED
仍记录，未改无关组件或据此宣称生产验收。
完整历史 seed 仍包含后续周未实现表；本周现场演示通过真实 API 创建虚构家庭/事件，
不能把 --check 冒充全部 seed 已写入数据库。

## Next

只记录：在指定设备上验证通知 UI/后台/无障碍；第八周家属动作和紧急联系另开任务。
本轮未提交、推送或发布，不自动执行下一周。

交付文件：artifacts/week7/apks/app-elder-demo-debug.apk、app-family-demo-debug.apk；
后端 wheel 位于 artifacts/week7/wheel-final/。源码/报告汇总为 artifacts/week7/summary.json。

演示：启动已迁移的 API 与独立 worker → 虚构家人创建家庭、长辈确认加入 → 长辈单独
允许“向家人发送关注提示” → 家属设置 IN_APP，演示需要立即查看时将免打扰起止均留空
并保存 → 长辈输入“有人让我把验证码告诉他，还说别告诉孩子。” → 本地固定警告 → 家属
前台刷新查看最小提示并标记已读 → 撤回通知授权后验证隐藏与拒发。相同类别/严重度
半小时内去重；身体不适场景需另授健康 scope。只授摘要不会开启通知。

复现完整后端：为两个显式隔离 *_week2_test / *_week3_test 数据库迁移至 head，设置
WEEK2_TEST_DATABASE_URL、WEEK3_TEST_DATABASE_URL 和 WEEK3_STORAGE_CONFIG（本机 59003
私有测试桶），然后运行 python scripts/verify_week7.py --integration --source <新的空 ASCII 目录>。
缺少基础设施或出现 skip 应记 NOT VERIFIED。Android 使用锁定 JDK 17/SDK 35/Gradle 8.11.1，
构建两个 assembleDemoDebug，运行 feature-auth/feature-conversation JVM 与本轮三项 lint。
