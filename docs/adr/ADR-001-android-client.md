# ADR-001 Android 客户端技术选择

- Status: Accepted
- Date: 2026-09-22

## Context

需求包含 Android 平板 kiosk、开机自启、BLE 呼叫按钮、CameraX 人员存在检测、离线唤醒、Foreground Service 和系统电话能力。老人端与子女端 UI、权限和发布方式差异很大，项目周期为 12 周。

## Options

1. 一个按角色切换的 Android App。
2. 两个原生 Kotlin App，共享 Gradle 多 Module。
3. Flutter/React Native，并为设备能力增加原生桥接。

## Decision

选择 Kotlin + Jetpack Compose + Android Jetpack，并采用 `app-elder` 与 `app-family` 两个 App，共享 `core-*`、`feature-*` 模块。老人端独占 device modules。采用 ViewModel + StateFlow + Repository，按业务需要使用小型 UseCase。

## Consequences

权限、设备集成、发布和并行开发边界清晰，子女端不会携带老人端硬件权限。Gradle 初始配置比单 App 多，需要在第 1 周建立共享模块和 CI。若课程强制跨平台栈，必须另行评估原生插件风险，不能默默改动本决策。

