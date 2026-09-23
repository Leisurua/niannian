# ADR-003 PostgreSQL + pgvector

- Status: Accepted
- Date: 2026-09-22

## Context

系统需要事务性业务数据、家庭/授权过滤、审计和家庭记忆相似检索。12 周版本不应维护多个数据系统。

## Options

1. PostgreSQL + pgvector。
2. PostgreSQL 加独立向量库（Milvus/Pinecone/Weaviate）。
3. 关系库加 Elasticsearch。

## Decision

PostgreSQL 负责 User、Family、Consent、Memory 元数据、Reminder、Conversation、InteractionMetric、SignalEvent、Notification、EmergencyContact、DeviceBinding、WeeklyReport 和 AuditLog；pgvector 负责已授权记忆和必要主题 embedding。

## Consequences

事务和权限过滤在同一边界内，部署和删除流程简单。大规模向量吞吐不是本项目目标；未来若需要独立向量服务，应保持 Memory/permission contract 不变并通过 Adapter 迁移。检索硬条件必须是 `CONFIRMED + AUTHORIZED + NOT_DELETED`。

