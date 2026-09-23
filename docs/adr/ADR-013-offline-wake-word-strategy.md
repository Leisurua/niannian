# ADR-013 Offline Wake Word Strategy

- Status: Proposed
- Date: 2026-09-22
- Scope: Local wake word and microphone ownership

## Context

FR-061 requires offline wake behavior, while online ASR, system calls and wake word all compete for microphone ownership. Provider, SDK license, model footprint and target-device latency are unknown.

## Decision

Use a mature offline Wake Word SDK behind `WakeWordManager`, with `AudioSessionCoordinator` enforcing one owner: `WAKEWORD`, `LISTENING`, `CALL` or `IDLE`. Pause/release wake word before ASR or calls. Offline detection may wake local UI and cached reminders but cannot fabricate online AI output. Do not train a model in this scope.

## Consequences

The wake word is not identity authentication. Microphone denial and SDK failure degrade to button/tap entry. Provider selection and latency remain Proposed until a disconnected-network spike passes on the named tablet.
