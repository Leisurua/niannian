# ADR-008 推送方案

- Status: Proposed
- Date: 2026-09-22

## Context

子女端需要接收 SignalEvent、诈骗、高优先级提醒和紧急事件。FCM 的中国大陆可达性、比赛网络、设备环境、短信/电话费用和合规尚未确认，Demo 不能依赖外部推送。

## Options

1. FCM 作为唯一通道。
2. 国内供应商作为唯一通道。
3. `PushProvider` 抽象，Mock/应用内轮询为基线，FCM/短信/电话为可选实现。

## Decision

暂定采用选项 3。`PushProvider` 只发送 event id 和最小摘要，客户端通过 REST 拉取授权详情；MockPush 和应用内轮询保证演示。真实供应商在确认网络、费用、数据留存、Android 设备和竞赛规则后再定。

## Consequences

核心业务不被 FCM 阻塞，新增 provider 只影响 integrations。应用内轮询不具备生产级实时性，必须在 UI 显示同步状态；决策仍需人工确认。

