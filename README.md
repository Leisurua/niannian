# 念念（NianNian）——银发 AI 数字陪伴系统

面向独居、空巢老人及异地家属的双端 Android AI 陪伴原型。念念以透明的 AI 身份、老人分项授权和家庭记忆为基础，帮助老人表达需求，也让真实家人在获得授权后参与陪伴。

项目采用 **12 周课程/竞赛开发计划**，目标是逐步验证“日常陪伴 → 关注线索 → 家属响应 → 反馈老人”的闭环。自然语音、生活提醒、亲情桥接和安全协同属于完整原型的建设目标；当前交付进度如下。

## 当前进度

截至 **2026-10-18，已完成第六周 Mock 软件范围**。当前可以分别验证家庭记忆、授权检索、离线提醒、受控摘要及在线主动陪伴等路径：

**虚构 DEMO 登录 → 家庭绑定与分项授权 → 家庭记忆/照片管理 → 授权 RAG 与长辈端 Mock 会话 → 本次会话回顾。**

双端提供提醒管理与反馈；长辈端支持有期限的离线缓存和待同步反馈。主动陪伴默认关闭，由家人提出设置、长辈确认，在活跃的本人会话中展示 Mock 文字邀请。第六周功能与合同变更见 [交付记录](docs/evidence/week6-completion.md)及 [PR #11](https://github.com/Leisurua/niannian/pull/11)；合并状态以 GitHub 为准。

长辈端按语音交互方向组织入口，提供大字状态、明显按钮、无需打字的模拟话题和文字备用入口。**当前录音、真实语音识别和播音尚未启用**；Mock 回复是经审查的确定性话术，不能作为真实 AI Provider 或完整语音链路的验收证据。

| 能力 | 当前状态 | 已交付内容与边界 |
| --- | --- | --- |
| 账号、家庭与授权 | 已实现 | DEMO 登录、凭证刷新/退出、家庭邀请与本人确认、角色权限、分项授权和撤回、敏感操作审计 |
| 家庭记忆 | 已实现 | 候选录入、人工确认/拒绝、版本化编辑、错误反馈、撤回和删除；待确认内容不作为家庭事实 |
| 私有照片 | 已实现，局部真机通过 | 上传检查、限格式/大小/像素、去除附加元数据、安全副本与鉴权下载；不提供永久公开链接 |
| 长辈端会话 | Mock 软件已实现 | 身份提示、未知事实/失败兜底、大字状态、打断、重复、结束、重连与撤销检查；慢速目前放大文字，音量入口说明无音频播放 |
| 家庭记忆 RAG | Mock 检索已实现 | 仅使用同家庭、当前获准、已确认且有效的记忆；本人 AI 处理需显式授权，生成后复验引用；Mock 向量不证明通用语义准确率 |
| 生活与用药提醒 | 双端软件已实现 | 周期/时区、完成/稍后/跳过反馈、长辈端加密离线缓存及幂等回传；缓存与待同步反馈按批准策略最多保留 24 小时；“尚未收到反馈”不等于“未服药”，系统不自动改医嘱 |
| 受控会话摘要 | Mock 软件已实现 | 本人明确允许后生成最多四条脱敏主题，最长保留 24 小时；指定家属授权可跨会话复用，每次访问仍鉴权、选择理由并审计；摘要授权与通知授权分开，失败不回退逐字稿 |
| 主动陪伴 | 在线 Mock 邀请已实现 | 家人提出设置、长辈确认；时间窗、免打扰、每日 0—3 次上限与“今天少打扰我”；仅向活跃本人会话发文字邀请，不后台唤醒或播音 |
| 关注线索与风险规则 | 候选/规则子路径已实现 | 六类暂态 Mock 候选、版本化规则及固定安全提示，明确求助优先；不输出诊断或确定诈骗结论，尚未形成持久 SignalEvent、家属通知或实际呼叫 |
| 家属通知、周报与紧急联系闭环 | 按后续周计划推进 | Mock 适配器和设计合同不代表业务闭环、通知送达或电话接通已经实现 |
| 实际语音与设备化能力 | 待门禁与指定设备验收 | 录音→ASR→编排→TTS→口型、离线唤醒、BLE、存在检测、kiosk、开机恢复及电话能力分别验证 |

离线副本仅限长辈已缓存的提醒与待同步反馈。完全断网时，远端撤权在重新联网或缓存到期后生效；系统/OEM 也可能延迟后台提醒与清理。摘要、家属敏感内容和 RAG 不提供离线读取。

部分照片场景已在一台小米 12（Android 12 / API 31）上复验：双端分别运行 Demo App，实际完成有效图片上传与查看，以及取消、超限/格式拒绝和损坏图片隔离。该结果不扩展为两台设备同步、全部界面、Keystore 或整套硬件验收。见 [照片真机复验](https://github.com/Leisurua/niannian/blob/198eff8c348410900b317d843089beede8562cca/docs/evidence/photo-retest-20261014.md)。第六周新增界面、离线/后台表现及完整语音仍待指定设备验收。

## 产品原则

- **身份透明**：始终说明自己是 AI，不冒充子女或亲友；不了解的家庭事实明确说不确定。
- **老人掌握授权**：家庭、角色、数据归属和当前授权由服务端检查，敏感信息按范围使用，支持撤回。
- **候选与事实分离**：AI 只能提出候选，`PENDING` 记忆不能当作家庭事实，也不能进入 RAG 上下文。
- **隐私最小化**：默认不保存原始音频；私有照片按当前登录与授权读取，日志避免记录凭证和敏感全文。
- **建议而非诊断**：不输出疾病诊断，不把情绪或交流观察解释为医疗结论；通知与紧急动作由确定性业务策略决定。
- **如实展示能力**：界面标明 Demo/Mock、离线、不可用及未验证状态，不把模拟输出描述为真实送达、接通或播音。

## 技术架构

| 层次 | 技术与职责 |
| --- | --- |
| Android 双端 | Kotlin、Jetpack Compose、ViewModel/StateFlow；长辈端与家属端共享认证和业务模块，长辈提醒缓存使用 Room 与 Keystore 支持的加密存储 |
| 后端 | Python 3.12、FastAPI、Pydantic v2、异步 SQLAlchemy 2、psycopg 与 Alembic；模块化单体，权限在服务/查询层执行 |
| 数据与文件 | PostgreSQL 为事实源；pgvector 在同一家庭/授权边界内保存并查询记忆向量；私有 S3 兼容对象存储/MinIO 保存照片 |
| 实时会话与 AI | REST + WebSocket；通过 provider-neutral DTO/Adapter 接入能力，当前会话使用确定性 Mock 与版本化 prompt |
| 后台任务 | 独立 APScheduler worker + PostgreSQL task/outbox；处理提醒、记忆索引/清理、摘要生成/清理和主动邀请，具备幂等键、租约、有限重试与死信状态 |

## 已验证交付

以下为已运行的交付快照，不代表真实语音、硬件或生产服务已验收：

| 检查 | 已记录结果 | 证据 |
| --- | --- | --- |
| 第六周开发阶段完整回归 | 453 项，0 failure/error/skip，含实际 PostgreSQL/pgvector、WSS 与 MinIO | [第六周交付](docs/evidence/week6-completion.md) |
| 发布分支 PostgreSQL 回归 | 第二周独立门禁 384 项；第三周双数据库门禁 456 项；均为 0 failure/error/skip，后者不含独立 MinIO 用例 | [第二周 CI](https://github.com/Leisurua/niannian/actions/runs/39139786518)、[第三周 CI](https://github.com/Leisurua/niannian/actions/runs/39139786522) |
| 发布分支 Android | 双端完整构建、150 次 JVM 测试、lint 及 12 APK 隐私扫描通过；真机另行验收 | [发布验证说明](https://github.com/Leisurua/niannian/pull/11) |
| GitHub CI | 2026-10-18，PR #11 的 `4355b59` 提交对应 12 项检查全部通过 | [PR 检查](https://github.com/Leisurua/niannian/pull/11/checks) |

各阶段数字是不同范围的快照，不累计计算完成度。第五周 RAG/离线提醒见 [交付记录](docs/evidence/week5.md)，第六周摘要/主动陪伴见 [交付记录](docs/evidence/week6-completion.md)。GitHub 检查以对应提交的实际运行结果为准；软件测试和 CI 不替代真机或真实 Provider 验收。

## 仓库结构

- `backend/`：Python 3.12、FastAPI、SQLAlchemy 2、Alembic 后端
- `android/`：`app-elder`、`app-family`、共享 `core-*` 与 `feature-*` Kotlin 模块
- `infra/`：PostgreSQL + pgvector 与 MinIO 开发环境
- `tests/`：跨模块工具、隐私、Demo 与设备检查；后端单元/集成/契约测试还位于 `backend/tests/`
- `docs/`：架构、冻结合同、开发计划与实际验收证据
- `scripts/`：分周验证、虚构数据和设备证据工具

## 本地运行

需要原生 **CPython 3.12**；Android 构建还需要 **JDK 17、Android SDK 35 / Build Tools 35.0.0**。创建并激活 Python 虚拟环境后，从仓库根目录安装依赖：

```powershell
python -m pip install -r backend/requirements.lock -r requirements-ci.txt
```

1. 在进程环境中选择 `APP_ENV=dev`、`test` 或 `demo`，应用会加载 `backend/config/<environment>.env`。将 `.env.example` 复制为忽略提交的 `.env`，配置指向自己授权的本地库的 `DATABASE_URL`，以及本地随机生成、至少 32 字符的 `AUTH_SIGNING_KEY`。
2. 从仓库根目录执行 `docker compose -f infra/docker-compose.yml up -d` 启动开发基础设施；将 `DATABASE_URL` 的账号、密码、主机和数据库名与该实例对应。Compose 默认账户仅用于本机开发。
3. 从 `backend/` 执行 `python -m alembic upgrade head` 应用迁移。第六周迁移头为 `20261017_week6_conversation`，共 18 个已实现模型；先完成第三周基础表和第五周索引/outbox，再升级第六周摘要版本与主动设置/计数。部署前备份，回滚演练只在空的隔离库执行，已有业务数据优先前向修复。合同修订见 [W3-01..05](docs/plan/week3-contract-review.md)、[W5-01..04](docs/plan/week5-contract-review.md)、[W6-01..04](docs/plan/week6-contract-review.md)。
4. 仍在 `backend/` 执行 `python -m app --reload` 启动 API。该入口会在 Windows 上配置异步 psycopg 所需的事件循环。`GET /health` 不要求数据库连接，因此通过该端点不能替代数据库或业务链路检查。
5. 另开终端，在同一环境、同样配置下，从 `backend/` 执行 `python -m app.worker.main --serve`。默认每 15 秒触发一次周期，执行提醒、索引/清理、摘要任务及在线主动邀请；`--once` 运行一次周期，无参数仅检查 worker 启动。受控摘要和记忆索引需要 worker 实际运行。
6. 从 `android/` 执行 `.\gradlew.bat clean build`，安装所需变体并配置 API 地址。Gradle flavor 为 `dev`、`qa`、`demo`，其中 `qa` 对应 `test` 环境。Windows 构建使用英文路径；副本构建需核对源码哈希。见 [Android 说明](android/README.md)。

照片还需要私有存储配置 `S3_ENDPOINT`、`S3_BUCKET`、`S3_ACCESS_KEY`、`S3_SECRET_KEY`。`PUBLIC_BASE_URL` 应为客户端可访问的 API 地址；照片上传地址的存储主机也必须能被设备访问。默认照片上限 5 MiB、1200 万像素，下载每次重查登录与授权。部署环境需配置独立凭证和 HTTPS。

所有已提交配置使用 Mock 模式。DEMO 登录仅接受虚构身份 `demo-child`、`demo-elder`、`demo-caregiver`、`demo-other`；真实短信/OAuth 登录尚未接入。完整 seed 仍涉及未实现的后续业务表，不能将 `python scripts/seed_demo_data.py --check` 的 fixture 检查当作完整数据库重放通过。见 [虚构数据说明](scripts/README.md)。

## 验证入口

安装 `backend/requirements.lock` 和 `requirements-ci.txt`，仅提供显式的一次性测试数据库后运行：

```powershell
python scripts/verify_week2.py
python scripts/verify_week3.py --postgres-only
python scripts/verify_week4.py
python scripts/verify_week5.py --source C:/nian-nian-checks/week5-source
python scripts/verify_week6.py --integration --source C:/nian-nian-checks/week6-source
```

`WEEK2_TEST_DATABASE_URL`、`WEEK3_TEST_DATABASE_URL` 的数据库名分别必须以 `_week2_test`、`_week3_test` 结尾。第二周入口只需要前者；第三周 PostgreSQL 及第四至第六周完整后端入口需要两者。第五、六周完整验证还需要 `WEEK3_STORAGE_CONFIG` 指向隔离 MinIO 设置；第六周入口运行前先在两个测试库完成 `alembic upgrade head`。`--postgres-only` 明确不验收真实 MinIO。

示例 `--source` 路径必须位于仓库之外并使用 ASCII 字符；第六周要求新的空目录，复验时换用新目录。缺少依赖、报告无效、跳过或未运行均不能视为 `PASS`，以具体报告和退出状态为准。

其他开发命令：

- 后端测试：先将 `backend/` 的绝对路径加入 `PYTHONPATH`，再从仓库根目录执行 `python -m pytest backend/tests tests`；结果中的跳过项不能当作集成验收通过。分周入口会自行设置导入路径。
- 隐私检查：`python -m unittest discover -s tests/security -p "test_*.py" -v`；先构建 APK 才能覆盖包扫描。该入口检查工作目录，建议在干净源码检出中运行，避免忽略目录里的本地工具/产物被误扫。
- 基础设施状态：`docker compose -f infra/docker-compose.yml ps`。
- 第一周工程环境：`python scripts/verify_week1.py`；说明见 [验证工具记录](docs/evidence/week1-tooling.md)。

Gradle Wrapper 8.11.1、AGP 8.7.3、Kotlin 2.0.21、Compose BOM 2024.12.01 及各模块依赖已锁定；构建通过不代替真机验收。

## 文档导航与后续计划

- [产品需求与设计](nian-nian-requirements-design.md)：产品目标、角色、场景与 12 周范围。
- [开发计划](docs/development-plan.md#20-12-week-mapping)、[验收清单](docs/development-checklist.md)：后续排期与各门禁状态。
- [系统设计](docs/system-design.md)、[API 合同](docs/api-spec.md)、[数据库设计](docs/database-design.md)：实现依据。
- [AI 合同](docs/ai-contracts.md)、[隐私与安全](docs/privacy-security.md)、[未决事项](docs/open-decisions.md)：模型能力、数据和设备接入边界。

后续按第七至第十二周计划推进 SignalEvent 持久化与通知、家属动态/响应、紧急联系、周报、跨设备与删除验收，以及通过数据策略和指定设备门禁后的实际语音与设备化集成。授权 RAG、离线提醒和受控摘要已有软件实现，其真实 Provider 质量与设备表现仍需分别验收。具体顺序以开发计划为准；本 README 不新增需求或改变冻结合同。真实 Provider 密钥、个人数据和敏感原文不得写入仓库。
