# Week 2 device Spike execution record

Date: 2026-10-09. Scope: E9-T01..05 evidence and dependency review.

Platform-tools/ADB is now available in a workspace-local test runtime. A fresh
`collect_device_baseline.py --adb <local-adb> --output artifacts/week2/device-baseline.json`
returned **NOT_RUN: NO_AUTHORIZED_DEVICE**, exit 2. No model/API/SKU, installed build,
physical button, camera, microphone or SIM observation is available. The previous
owner record states no device was supplied; no operator is assigned yet.

| Task | Actual gate | Dependency / evidence still needed | Visible current behavior |
| --- | --- | --- | --- |
| E9-T01 kiosk/boot | NOT VERIFIED | Named disposable tablet; Device Owner/Lock Task evidence; 10 reboot/exit observations | Ordinary app; screen explicitly says kiosk is not enabled |
| E9-T02 BLE | NOT VERIFIED | E8-T01; named button; GATT allowlist, packet/press semantics, battery/reconnect/dedup observations | No BLE permission, adapter or connection claim |
| E9-T03 camera | NOT VERIFIED | Named tablet; permission/Consent; power/false-trigger and no-frame-storage observations | No camera permission or capture |
| E9-T04 wake/audio | NOT VERIFIED | E4-T01; candidate SDK/licence; named tablet; one audio owner/offline measurements | No microphone/wake SDK; no offline AI answer |
| E9-T05 telephony | NOT VERIFIED | E8-T01; named tablet/SIM; permission/no-SIM/no-answer/call-state observations | No phone permission, call or CONNECTED claim |

The backend task dependencies E4-T01 and E8-T01 belong to later weeks. They were
not started to manufacture Spike completion. ADR-010..014 remain Proposed.
Android compilation/unit/lint checks are software checks and cannot pass these
physical-device gates. The exact on-device cases and evidence fields remain in
`docs/device-test-matrix.md` and `docs/evidence/week1-device-baseline.md`.

When equipment is supplied, record the operator and named-device baseline, install
the verified APK, and execute each gate with fictional data. Record permission,
network, timestamp, observed result and sanitized evidence path; capture no raw
audio, camera frames, device serial, phone number or account/token content.
