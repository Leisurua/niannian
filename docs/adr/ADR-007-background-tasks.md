# ADR-007 后台任务方案

- Status: Accepted
- Date: 2026-09-22

## Context

系统需要提醒、主动陪伴、周报、删除、embedding、推送和事件通知，任务必须可重试、幂等和可观察。12 周版本不适合引入 Redis/Celery 运维栈。

## Options

1. FastAPI BackgroundTasks。
2. API 进程内 APScheduler。
3. 独立 worker + APScheduler + PostgreSQL task/outbox。
4. Celery + Redis。

## Decision

采用独立 `worker` 进程运行 APScheduler。API 事务写入任务/事件表；worker 使用租约、唯一业务键、最大重试、指数退避、超时和死信状态领取任务。单实例演示可共用代码，但部署仍保留 worker 边界。

## Consequences

比 BackgroundTasks 可靠且比 Celery 成本低。需要实现任务幂等和 worker 健康检查。未来吞吐不足时，可在不改变任务契约的前提下迁移 Celery/Redis。

