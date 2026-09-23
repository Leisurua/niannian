# ADR-004 模块化单体

- Status: Accepted
- Date: 2026-09-22

## Context

项目有多个业务领域，但团队规模和交付周期有限。微服务会带来部署、联调、鉴权、消息和可观测性成本。

## Options

1. 模块化单体，API 与 worker 进程分离。
2. 从第一天拆分多个微服务。
3. 单一无边界应用目录。

## Decision

采用一个 FastAPI 模块化单体，模块拥有自己的数据访问和公开 service/event 契约；`backend` 与 `worker` 是部署进程边界，不是微服务边界。禁止跨模块访问私有 repository/model。

## Consequences

本地 Docker Compose 和测试简单，12 周内可完成；模块边界为未来拆分留下路径。需要 code review 检查跨模块依赖和事务边界，不能以“同一进程”为由绕过封装。

