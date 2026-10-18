# 第六周摘要、主动陪伴与线索候选交付记录

日期：2026-10-18。**已批准的第六周 Mock 软件范围 PASS；实际设备/语音验收仍未关闭。**

## Task

完成 development-plan §20 第六周：E4 受控摘要、持续摘要授权、主动陪伴策略与在线入口，
E5 六类暂态候选和版本化规则。用户已对 [W6-01..04](../plan/week6-contract-review.md)
回复“是”，随后要求继续。未执行第七周 SignalEvent 持久化、家庭通知或第八周动态闭环。

## Changed

- 摘要接入既有 Conversation、REST/WSS 和持久 worker。仅把已完成且通过校验的轮次
  转成固定脱敏主题，最多四条/1000 字；不保存逐字稿或原始音频，不把家庭事实复制进摘要。
  `PENDING` 不可读，结束或显式请求后由 worker 完成；空内容/失败不会回退原文。
- 本人显式 self `CONVERSATION_SUMMARY` 授权才开始处理，与指定家属读取授权及
  `NOTIFICATION_TO_FAMILY` 分开。当前授权可跨会话复用，每次读取仍检查身份、家庭、
  ACTIVE 成员、角色、SUMMARY_READ、指定 grantee、当前授权和资源状态。
- 家属每次访问选择 `FAMILY_CHECK_IN` / `FOLLOW_UP` 理由，保存到 AuditLog.reason；
  无理由/非法理由拒绝，审计不含摘要正文。接口返回 no-store；没有历史会话列表。
- 摘要从首次受控内容起最多 24h，已知 self-grant 到期可缩短期限，重试不续期。
  self 撤回先隐藏并入队清理；只撤回某位家属授权则只拒绝该读者。版本 fence 防止
  旧任务恢复内容。删除、过期、无期限异常、成员失效、无处理授权均不返回摘要。
- 新迁移增加 summary_version、两个摘要任务类型、proactive_preference 和
  proactive_daily_counter。旧迁移保留，现有 outbox 租约、超时、重试与 DEAD 沿用。
- 主动陪伴默认关闭；家人提出时间窗、时区、免打扰和每日 0..3 次上限，长辈确认
  当前版本后生效。修改设置需要重新确认，暂停仅本人可操作，命令幂等且写审计。
  时区变化携带已消费次数和当日暂停；计数最多保留 48h。
- worker 仅对持有活跃 WSS 租约的本人会话预占次数，以 PostgreSQL NOTIFY 发临时
  版本/时间提示；API 消费时重查当前策略和授权，再发固定 Mock 邀请。未连接不计数，
  失败/丢失可能消耗一次机会但不宣称已显示/播报；重连不回放。监听故障会关闭连接
  并释放租约，允许重连。当前邀请只谈一般生活，不捏造天气或引用未授权记忆。
- 时间窗、日上限、免打扰、暂停、最近互动与内容授权由确定性代码控制。默认最近互动
  间隔为 30 分钟；忙碌/休息/今日少打扰的固定文字入口可暂停当日主动互动。
  必要提醒、紧急入口及安全规则不受主动暂停影响。
- 六类 SignalCandidate 通过有限的确定性 Mock 语句提取和来源/类别/动作校验；
  最多三条，不保存原始证据。规则 v1.1.0 补齐 SC-001 验证码+保密，紧急触发优先；
  LLM/TTS 故障仍返回固定安全提示。候选不成为事实、事件、通知或实际呼叫。
- 双端加入主动设置和会话回顾入口。长辈可显式允许生成摘要、确认设置、今日暂停，
  当前会话编号自动带入，无需手输；家属仅通过已知编号和明确理由查看。
  摘要不落本地磁盘，短暂前台展示后隐藏；后台、家庭切换、已知授权变化或离线状态
  清除内容，失败不回退旧摘要。仍明确标注 Mock、未启用录音/播音/自动联系。
- 没有新增依赖版本、硬件权限、真实 Provider 或生产部署；保留进入任务时的第五周改动。

## Tests

| 实际执行 | 结果 | 证据（均在忽略目录 artifacts/week6/） |
| --- | --- | --- |
| 完整后端、契约、AI/策略、源码隐私回归 | PASS：453 项，0 failure/error/skip | `backend-delivery/summary.json`、`tests.xml`、`tests.txt` |
| 新增第六周覆盖 | 84 项纯策略/候选测试、18 项实际 PostgreSQL/WSS 集成、1 项合同测试，包含在 453 项内 | `backend/tests/unit/test_week6_policies.py`、`backend/tests/integration/test_week6_postgres.py`、`backend/tests/contract/test_week6_contract.py` |
| 实际 PostgreSQL/pgvector 与 MinIO | PASS，独立虚构测试库/私有桶；含前五周回归 | 同上完整回归，`storage-config.json` 仅本地不提交 |
| 第六周迁移 | PASS：新库 upgrade，空库 downgrade 到 week5/re-upgrade；两次 Alembic check 无差异 | 本聊天实际命令输出；使用本机 59006 的 nian6_*_test 库 |
| Android 两端全量构建/JVM/lint | PASS：138 次 JVM 执行，0 failure/error/skip；8 份 lint 无 Error/Fatal | `android-verified.txt`、`android-summary.json`、`android-reports/` |
| Android 构建源码一致性 | PASS：83 个源码/配置文件 SHA-256 一致 | `build-source-hashes.json`、`android-summary.json` |
| APK 完整性/源码/Git 历史隐私扫描 | PASS：7 项，完整扫描 12 个 APK | `apk-source-verified.xml`；文件 hash 见 `android-summary.json` |
| 后端 wheel | PASS：离线构建，源码目录外安装，dev/test/demo 健康及 Mock 会话调用 | `wheel-build.txt`、`wheel-check.txt` |
| 当前设备检查 | NOT VERIFIED：NO_AUTHORIZED_DEVICE | `device-baseline.json` |

摘要集成实际覆盖：一次家属 grant→两个会话读取；缺理由、非指定读者、缺 SUMMARY_READ、
跨家庭、到期、撤回、成员失效、删除、期限缺失、空摘要、DEAD、旧版本写回和不续期。
主动集成实际覆盖：共同确认、过期版本、命令重放、无连接不计数、并发预占、暂停、
时区携带、过期通知拒绝、真实 LISTEN/NOTIFY/WSS 邀请及监听故障释放。JVM 另覆盖
理由传递、PENDING/失败隐藏、家庭切换旧回调拒绝和自动当前会话回顾定位。

失败与恢复记录保留：

- 准备阶段 70 项新增和 259 项局部回归是历史证据，不与 453 项累计。
- 初轮完整回归 15 项因 Windows 默认 pytest 临时目录权限在 setup 报错；改为任务
  专属临时目录后通过。新增权限测试曾把 JSON 内的冒号写成 SQL bind，改用参数化 JSON。
- 451 项通过后复查新增删除状态/监听故障守卫，旧快照 hash 检查正确报不一致；最终
  453 项及源码 hash 全部通过。没有放宽断言、跳过失败用例或关闭 lint。
- 上次 APK 扫描因自动审批服务额度不足未执行；继续后扫描发现三个长辈 Debug APK
  缺失，实际报 FAIL。恢复同版本 Gradle 8.11.1 和 API 35 revision 2 官方归档与缺失
  的锁定依赖后补建成功，再次扫描 12 个 APK 全部通过。Gradle 归档 SHA-256 与第五周
  记录一致；SDK 归档 SHA-1 与 Google 官方索引一致，未升级依赖或改锁文件。
  日志：`android-apk-restore.txt`、`android-apk-restored-runtime.txt`、
  `android-apk-recovery.txt`、`android-apk-complete.txt`、`apk-source-scan.xml`。
- 收尾检查没有发现仍在运行且命令行指向本轮目录的 PostgreSQL/MinIO 进程，未停止
  其他服务、未删除数据：`test-service-cleanup.json`。

## Decisions

按已批准 W6-01..04 实施。摘要和候选采用有限、可复现的 Mock 主题/语句，不宣称
开放域语义理解质量；主动邀请采用一般话题，真实天气、播音和后台唤醒没有被模拟为成功。
通知仍是第七周范围，本轮不发送。所有授权仍在服务端判断，LLM 不做权限或敏感动作决策。

## Contract Changes

已批准并同步：Conversation.summary_version、两个内部摘要任务类型、两张主动陪伴表、
四个主动设置 operation（REST 总数 80，已实现模型 18）、家属摘要访问理由 header、
24h Mock 摘要/48h 主动计数期限、明确摘要 self-grant、候选 category/action 词表与
SC-001 组合规则。API、OpenAPI、字典、DB、权限、隐私、留存、AI、规则和 UI 说明已同步。
WSS 类型、ConsentScope、SignalType、公开会话和提醒状态保持原值。

## Not Verified

实际设备 UI/TalkBack、生命周期/后台表现、Keystore I/O 和完整设备门禁；当前没有
已授权设备。实际录音→ASR→LLM→TTS→口型、真实语音暂停/播报仍受 D-002/003/017
门禁限制，未启用。远端 CI、正式签名发布、生产迁移和真实 Provider 性能未验证。

## Issues

软件测试已通过，以上设备与真实语音门禁保持开放。现有 Starlette/AnyIO 弃用提示及
pytest 退出时的脱敏 LOG_SINK_FAILED 提示仍有记录，未据此声明生产或性能验收。
摘要只展示固定主题，候选只保证列出的 Mock 语句；不是通用模型质量结论。
主动邀请丢失不会自动返还配额或回放，近期互动会抑制邀请；这是减少重复打扰的保守策略。

## Next

只记录：指定设备到位后执行第六周 UI/无障碍与设备用例；真实语音须先完成既有门禁。
本任务不自动启动第七周，不提交、推送或发布。

交付：`artifacts/week6/apks/app-elder-demo-debug.apk`、`app-family-demo-debug.apk`，
另有其余 10 个构建变体（release 为 unsigned）；后端 wheel 在 `artifacts/week6/wheel/`。

复现完整后端：先在显式隔离测试库迁移至 head，提供 WEEK2_TEST_DATABASE_URL、
WEEK3_TEST_DATABASE_URL、WEEK3_STORAGE_CONFIG（MinIO 本机 59003/niannian-week3-test），
设置 PYTHONUTF8=1，然后运行 `python scripts/verify_week6.py --integration --source <新的空ASCII源码目录>`。
缺少测试基础设施会保留 NOT VERIFIED，跳过不算 PASS。Android 使用已锁定 JDK 17、
SDK 35、Gradle 8.11.1；先 build，再运行 APK 扫描。

演示顺序：虚构 Demo 家庭→长辈分别允许“生成我的会话回顾”和指定家属“交流摘要”→
长辈 Mock 文字对话并结束→worker 完成摘要→长辈直接查看/家属输入已知编号并选理由→
再次对话复用授权→撤回后验证拒绝。主动陪伴：家人提出设置→长辈确认→保持本人会话在线，
满足时间窗和最近互动间隔后收到 Mock 邀请→点“今天少打扰我”。
