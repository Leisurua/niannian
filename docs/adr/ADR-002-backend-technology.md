# ADR-002 Backend 技术选择

- Status: Accepted
- Date: 2026-09-22

## Context

后端要覆盖家庭、授权、记忆/RAG、SignalEvent、提醒、通知、周报、设备和 AI provider 集成，并需要可测试的 HTTP API 与后台任务。

## Options

1. Python FastAPI + Pydantic + SQLAlchemy 2 + Alembic。
2. Node.js/NestJS。
3. Java/Spring Boot。

## Decision

采用 Python 3.12（以项目环境可用稳定版本为准）、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic。以模块化单体运行，API 与 worker 可拆成两个进程但共享领域模块。

## Consequences

AI SDK、数据处理和快速原型成本低，团队容易测试和演示。需要统一 async 数据库访问、类型检查、迁移和日志规范，避免 FastAPI 路由直接包含业务规则。

