# ADR-012 Presence Detection Strategy

- Status: Proposed
- Date: 2026-09-22
- Scope: CameraX presence wake on the elder tablet

## Context

The product needs “有人在设备前” wake behavior, not identity. Camera power, low-light accuracy, photo false positives and OEM CameraX behavior are unknown.

## Decision

Use CameraX ImageAnalysis with a mature lightweight presence-capable detector candidate (ML Kit Face Detection is the initial spike target). Emit only `PRESENT`, `ABSENT` or `UNKNOWN` after a duration threshold and cooldown. Discard frames, do not identify people, create biometric templates or upload images. Acceptance requires a target-device power/temperature/false-trigger benchmark.

## Consequences

Camera permission or consent denial disables the feature without blocking conversation, reminders or Emergency. The detector/provider cannot be marked Accepted until the benchmark and privacy inspection pass.
