# 念念（NianNian）AI 陪伴系统

当前仓库是 NianNian 的工程骨架，按 `docs/development-plan.md` 逐步实现。E0-T01~T03 提供可启动的 FastAPI health endpoint、数据库/迁移基础、两个 Android Compose App 占位入口、环境配置与脱敏日志。

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
4. Start the API with `uvicorn app.main:app --app-dir backend --reload`.

The API exposes `GET /health` and does not require a database connection for that endpoint.

All checked-in profiles use Mock providers. The demo profile requires fictional data and Mock providers; its seed data is a later task. Android `dev`, `test`, and `demo` variants display their environment and provider source in the placeholder screen.

## Verification commands

- Backend tests: `python -m pytest backend/tests tests`
- Dependency-free privacy scan: `python -m unittest discover -s tests/security -p "test_*.py" -v`. Build Android APKs first to include the APK scan.
- Compose services: `docker compose -f infra/docker-compose.yml ps`
- Android (JDK 17 and Android SDK 35): from `android/`, run `.\gradlew.bat clean build`. The Gradle wrapper pins 8.11.1; Android Gradle Plugin pins 8.7.3, Kotlin pins 2.0.21, and Compose BOM pins 2024.12.01. Each Android module has a `gradle.lockfile` for resolved dependencies. `qa` is the internal Android flavor for the `test` environment.

No real provider keys or personal data belong in this repository. See the design documents for the frozen contracts and later task boundaries.
