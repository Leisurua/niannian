# ADR-009 数字人方案

- Status: Proposed
- Date: 2026-09-22

## Context

需求只要求 idle、listening、thinking、speaking、warning 等基础状态和基础口型，不要求自研生成模型。具体 SDK 的授权、离线能力、设备性能和数据政策尚未确定。

## Options

1. Live2D 或其他成熟 SDK。
2. 第三方 Avatar SDK。
3. 简化 2D/3D Avatar + TTS 音频时长驱动口型。
4. 自研复杂 3D/生成式数字人。

## Decision

暂定优先选择成熟 SDK 或简化 Avatar，统一业务无关的 `AvatarState` 和 `AvatarAdapter`；演示默认使用 MockAvatar/简化资源，真实 SDK 作为可替换 provider。禁止自研复杂数字人、音素级模型和冒充具体家人的脸/声音。

## Consequences

可以先交付对话和安全闭环，SDK 失效时仍能显示语音/文字。需要在指定平板上验证帧率、包体、授权和离线行为后才能把具体供应商标为 Accepted。

