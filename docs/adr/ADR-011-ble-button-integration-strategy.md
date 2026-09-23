# ADR-011 BLE Button Integration Strategy

- Status: Proposed
- Date: 2026-09-22
- Scope: Elder tablet physical emergency button

## Context

The BLE button is P0, but no button model, GATT service, payload, press semantics, bonding requirement or battery characteristic is recorded. Guessing a protocol would create an unsafe Emergency integration.

## Decision

Isolate BLE behind `BLEButtonManager`. It owns discovery, connection, subscription, reconnect, battery observation and validation, then emits `PhysicalButtonPressed`. EmergencyCoordinator owns policy, idempotency and contact. Protocol and single/long/double-press semantics remain `BLE Protocol TBD` until packet captures and real-device tests are complete.

## Consequences

The first spike must capture the protocol and duplicate behavior. Software dedupe is required even if the device claims reliable notifications. BLE failure degrades to screen/voice Emergency and is visible in capability state.
