# 念念（NianNian）AI 陪伴系统

当前仓库按 `docs/development-plan.md` 推进到第二周。后端已实现虚构 DEMO 登录、刷新轮换与重用检测、退出、家庭邀请与本人确认、分项授权及不可变撤回历史；两个 Android Compose App 提供对应流程。现有迁移覆盖 Auth/Family/Consent 及审计、设备关联的 8 张基础表。聊天、记忆、提醒等后续业务及真实设备能力尚未实现。

第二周验证与双端演示步骤见 [第二周交付记录](docs/evidence/week2.md)。使用显式的一次性 PostgreSQL 测试库运行 `python scripts/verify_week2.py`；未配置数据库会报告 `NOT VERIFIED`，不以跳过集成测试作为通过。硬件与 Android UI 真机验收独立记录。

第一周统一检查：安装 `backend/requirements.lock` 和 `requirements-ci.txt` 后运行 `python scripts/verify_week1.py`。缺少 Android 或 Docker 环境时会输出 `NOT VERIFIED`，不会伪装为通过。CI、运行方法与边界见 [验证工具说明](docs/evidence/week1-tooling.md)，设备记录见 [设备基线启动记录](docs/evidence/week1-device-baseline.md)。

## Repository structure

- `backend/`：Python 3.12、FastAPI、SQLAlchemy 2、Alembic 后端
- `android/`：`app-elder`、`app-family` 与共享 Kotlin 模块
- `infra/`：PostgreSQL + pgvector 与 MinIO 开发环境
- `tests/`：跨模块 contract 测试占位
- `docs/`：需求、架构和冻结 contract（不在本任务修改）

## Local setup

1. Set `APP_ENV` to `dev`, `test`, or `demo` in the process environment. The backend loads `backend/config/<environment>.env`. Copy `.env.example` to `.env` only for local overrides or secrets; `.env` is ignored by Git.
2. Create a native CPython 3.12 environment and install `backend/requirements.lock` for the verified dependency set. `backend/requirements.txt` lists the direct dependencies.
3. Start services with `docker compose -f infra/docker-compose.yml up -d` when testing infrastructure tasks.
4. Configure `AUTH_SIGNING_KEY` with a locally generated random value of at least 32 characters; keep it in the ignored `.env` or process environment. From `backend/`, start the API with `python -m app --reload`. This entry point sets the selector event loop needed for async psycopg on Windows before starting Uvicorn.

The API exposes `GET /health` and does not require a database connection for that endpoint.

All checked-in profiles use Mock providers. Only fictional `demo-child`, `demo-elder`, `demo-caregiver` and `demo-other` identifiers are accepted by DEMO login. SMS/OAuth and real-provider login are unavailable. Android `dev`, `test`, and `demo` variants display their environment and provider source throughout the auth/family/consent screens.

## Verification commands

- Backend tests: `python -m pytest backend/tests tests`
- Dependency-free privacy scan: `python -m unittest discover -s tests/security -p "test_*.py" -v`. Build Android APKs first to include the APK scan.
- Compose services: `docker compose -f infra/docker-compose.yml ps`
- Android (JDK 17 and Android SDK 35): from `android/`, run `.\gradlew.bat clean build`. The Gradle wrapper pins 8.11.1; Android Gradle Plugin pins 8.7.3, Kotlin pins 2.0.21, and Compose BOM pins 2024.12.01. Each Android module has a `gradle.lockfile` for resolved dependencies. `qa` is the internal Android flavor for the `test` environment.

No real provider keys or personal data belong in this repository. See the design documents for the frozen contracts and later task boundaries.
