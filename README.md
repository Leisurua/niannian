# 念念（NianNian）AI 陪伴系统

当前软件基线已覆盖登录、家庭、授权、家庭记忆、提醒、会话、设备绑定、消息投递，以及主动陪伴的 PC-B 策略核心与 PC-C worker/单设备投递；后端现有 17 个 SQLAlchemy 业务模型。主动陪伴已具备确定性门控、并发保护、HOME_HUB 优先/ELDER_MOBILE 回退和短 TTL 系统消息，但公共策略 API、PC-D Android 体验及 PC-E 端到端验收仍未完成。

第三周历史验证与演示步骤见 [交付记录](docs/evidence/week3.md)。当时的本地后端 243 项测试、双端离线构建和 68 次 JVM 测试、真实 MinIO 文件链路均已通过；主动陪伴验证见 [PC-B 证据](docs/evidence/proactive-companion-pc-b.md)和 [PC-C 证据](docs/evidence/proactive-companion-pc-c.md)。**真机 UI/照片选择器/Keystore 和硬件验收仍未完成**；AI 回复、语音、摘要、完整 RAG 与 Android 离线提醒按后续计划推进。

当前 Alembic 唯一 head 为 `20261017_proactive_core`；部署前备份，在 `backend/` 执行 `python -m alembic upgrade head`。回滚只允许空的隔离库，已有业务数据应使用前向修复。2026-10-18，Kali 主演示库及匹配的 API/worker 已安全升级到该 head，记录见 [数据库升级证据](docs/evidence/database-upgrade-20261018.md)。第三周合同修订历史见 [W3-01..05](docs/plan/week3-contract-review.md)。

照片需要私有 S3/MinIO 配置 `S3_ENDPOINT/S3_BUCKET/S3_ACCESS_KEY/S3_SECRET_KEY`。`PUBLIC_BASE_URL` 是客户端可访问的 API 地址；上传地址的存储主机也必须能被设备访问。默认照片上限 5 MiB、1200 万像素；下载每次重新校验登录与授权，不使用永久公开 URL。生产使用 HTTPS。另开终端在 `backend/` 执行 `python -m app.worker.main --serve`，每 15 秒生成提醒执行并清理文件；`--once` 用于单次运行。无参数只检查 worker 启动。

第二周验证与双端演示步骤见 [第二周交付记录](docs/evidence/week2.md)。使用显式的一次性 PostgreSQL 测试库运行 `python scripts/verify_week2.py`；未配置数据库会报告 `NOT VERIFIED`，不以跳过集成测试作为通过。硬件与 Android UI 真机验收独立记录。

第一周统一检查：安装 `backend/requirements.lock` 和 `requirements-ci.txt` 后运行 `python scripts/verify_week1.py`。缺少 Android 或 Docker 环境时会输出 `NOT VERIFIED`，不会伪装为通过。CI、运行方法与边界见 [验证工具说明](docs/evidence/week1-tooling.md)，设备记录见 [设备基线启动记录](docs/evidence/week1-device-baseline.md)。

## Repository structure

- `backend/`：Python 3.12、FastAPI、SQLAlchemy 2、Alembic 后端
- `android/`：`app-elder`、`app-family` 与共享 Kotlin 模块
- `windows/family-client/`：可打包为单文件 EXE 的 Windows 子女端与联机自检
- `windows/elder-demo/`：大字号 Windows 老人演示端，用于课堂双端消息闭环
- `infra/`：PostgreSQL + pgvector 与 MinIO 开发环境
- `tests/`：跨模块 contract 测试占位
- `docs/`：需求、架构和冻结 contract（不在本任务修改）

## Local setup

1. Set `APP_ENV` to `dev`, `test`, or `demo` in the process environment. The backend loads `backend/config/<environment>.env`. Copy `.env.example` to `.env` only for local overrides or secrets; `.env` is ignored by Git.
2. Create a native CPython 3.12 environment and install `backend/requirements.lock` for the verified dependency set. `backend/requirements.txt` lists the direct dependencies.
3. Start services with `docker compose -f infra/docker-compose.yml up -d` when testing infrastructure tasks.
4. Configure `AUTH_SIGNING_KEY` with a locally generated random value of at least 32 characters; keep it in the ignored `.env` or process environment. From `backend/`, start the API with `python -m app --reload`. This entry point sets the selector event loop needed for async psycopg on Windows before starting Uvicorn.

The API exposes `GET /health` and does not require a database connection for that endpoint.

Kali/Linux 可用 Docker Compose 一次启动 API、worker、数据库、迁移和私有对象存储；详见 [Kali Linux 服务端部署](infra/linux/README.md)。该方式与 Windows 本地启动方式共用同一套业务代码。

All checked-in profiles use Mock providers. Only fictional `demo-child`, `demo-elder`, `demo-caregiver` and `demo-other` identifiers are accepted by DEMO login. SMS/OAuth and real-provider login are unavailable. Android `dev`, `test`, and `demo` variants display their environment and provider source throughout the auth/family/consent screens.

The demo profile requires fictional data and Mock providers. E0-T08 supplies [fictional seed fixtures](scripts/README.md); run `python scripts/seed_demo_data.py --check` without a database. Applying the complete seed requires its reviewed business schema; the current migration chain covers 17 implemented SQLAlchemy models but still does not cover later Signal/Notification/Report entities. Android creates and reads authorized Memory records through the API; complete seed replay remains a later vertical-slice gate.

## Verification commands

- Backend tests: `python -m pytest backend/tests tests`
- Dependency-free privacy scan: `python -m unittest discover -s tests/security -p "test_*.py" -v`. Build Android APKs first to include the APK scan.
- Compose services: `docker compose -f infra/docker-compose.yml ps`
- Android (JDK 17 and Android SDK 35): from `android/`, run `.\gradlew.bat clean build`. The Gradle wrapper pins 8.11.1; Android Gradle Plugin pins 8.7.3, Kotlin pins 2.0.21, and Compose BOM pins 2024.12.01. Each Android module has a `gradle.lockfile` for resolved dependencies. `qa` is the internal Android flavor for the `test` environment.

No real provider keys or personal data belong in this repository. See the design documents for the frozen contracts and later task boundaries.
