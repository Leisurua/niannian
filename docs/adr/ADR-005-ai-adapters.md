# ADR-005 AI Adapter

- Status: Accepted
- Date: 2026-09-22

## Context

ASR、LLM、Embedding、TTS、Avatar 和 Wake Word 的供应商、网络和配额可能变化，且比赛 Demo 不能完全依赖公网。业务代码也不能把 LLM 当作安全决策器。

## Options

1. 业务模块直接调用供应商 SDK。
2. 统一 Adapter + provider 实现 + Mock。
3. 只使用单一厂商并延后抽象。

## Decision

统一定义 `ASRAdapter`、`LLMAdapter`、`EmbeddingAdapter`、`TTSAdapter`、`AvatarAdapter`、`WakeWordAdapter`（以及 Weather、Push）。业务只依赖 DTO、能力和错误码；供应商实现位于 `integrations/providers`，Mock 位于 `integrations/mock`。所有调用有 timeout、有限重试、fallback、脱敏、provider/version 和 prompt version 记录。

## Consequences

可切换供应商、离线演示和故障测试；需要维护 contract 和 Mock 行为。LLM 只能生成候选语义和话术，安全规则、授权和通知策略必须在业务代码中复核。

