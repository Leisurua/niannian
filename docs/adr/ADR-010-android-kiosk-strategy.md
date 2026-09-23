# ADR-010 Android Kiosk Strategy

- Status: Proposed
- Date: 2026-09-22
- Scope: `app-elder` dedicated Android tablet

## Context

FR-060 requires an elderly-facing kiosk after reboot. A normal application calling `startLockTask()` is not equivalent to a Device Owner/COSU deployment and may not survive reboot or prevent system escape. The target tablet model, API level and OEM policy are not yet verified.

## Decision

Use Device Owner plus an Android-supported dedicated-device/Lock Task configuration as the target strategy. Keep a normal-App/config-error mode when Device Owner, allowlist or OEM policy cannot be established. Do not write a universal provisioning command until the real tablet passes clean-device provisioning and 10 reboot/exit tests.

## Consequences

The device must be provisioned before demo use and development exit requires an admin/factory-reset path. The app reports `ACTIVE`, `CONFIG_ERROR`, `DISABLED` or `UNKNOWN`; it never infers kiosk success from an API call alone. A failed gate requires a visible fallback and a decision record.
