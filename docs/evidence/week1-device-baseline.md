# Week 1 — device baseline kickoff

Date: 2026-09-29. Scope: ENV-001/002 record and E9-T01..05 kickoff only.

The project owner confirmed that no test device is currently available. No device,
emulator, BLE button or hardware observation is represented by this record.
No proposed ADR-010..014 is promoted to Accepted.

## Baseline

| Field | Observation | Evidence/status |
| --- | --- | --- |
| Manufacturer / model / SKU | UNKNOWN | Device not supplied |
| Android version / API / security patch | UNKNOWN | ENV-001 NOT_RUN |
| GMS / USB debugging / ADB connection | UNKNOWN | ADB unavailable on this host |
| Elder app version / installed build hash | UNKNOWN | ENV-002 NOT_RUN; source version alone is insufficient |
| Family app version / installed build hash | UNKNOWN | ENV-002 NOT_RUN |
| Device Owner / Lock Task / OEM startup | UNKNOWN | KIO-001..009 NOT_RUN |
| Wi-Fi / captive portal / offline recovery | UNKNOWN | Device not supplied |
| SIM / Telecom / call permission / observed call state | UNKNOWN | No call initiated |
| BLE version / button model / GATT / battery / press semantics | UNKNOWN | BLE-001..014 NOT_RUN |
| Camera / low light / power / privacy | UNKNOWN | CAM-001..011 NOT_RUN |
| Microphone / speaker / echo / audio ownership | UNKNOWN | AUD-001..010 NOT_RUN |
| Battery / charger / temperature / system settings control | UNKNOWN | Device not supplied |

Evidence generation: `python scripts/collect_device_baseline.py` produces
`artifacts/week1/device-baseline.json`. Current result: `NOT_RUN: ADB_UNAVAILABLE`.
Exit 2 means not verified, never success. The collector saves only allowlisted
model/version properties; it does not save the device serial, accounts, logcat,
media, microphone input or phone numbers. Multiple devices require `--serial`;
this selector stays local and is omitted from the report.

An inventory PASS means only that required model/version fields were read.
`hardware_gate` stays `NOT VERIFIED`, and capability fields remain `UNKNOWN`.
SKU, GMS, app build and all capability observations must still be completed manually.

## Spike owners, dependencies and evidence

Codex owns this week's scripts, fixture checks and kickoff documentation.
The project owner supplies/selects hardware and assigns the on-device operator
once equipment is available; that operator is currently **unassigned**.

| Task | Week 1 work | Dependency for actual execution | Evidence destination | Actual result / fallback to validate |
| --- | --- | --- | --- | --- |
| E9-T01 / D-006 | Baseline and kiosk checklist prepared | Named test tablet, reviewed provisioning procedure | `artifacts/device/E9-T01/` | NOT_RUN; ordinary App with visible configuration warning |
| E9-T02 / D-007 | Protocol/duplicate/reconnect evidence checklist prepared | E8-T01 and named BLE button/protocol | `artifacts/device/E9-T02/` | NOT_RUN; large on-screen contact entry |
| E9-T03 / D-008 | Presence/power/privacy checklist prepared | Named tablet, permission and Consent | `artifacts/device/E9-T03/` | NOT_RUN; camera disabled, core interaction remains available |
| E9-T04 / D-009 | Audio-ownership/offline checklist prepared | E4-T01, candidate SDK/license and named tablet | `artifacts/device/E9-T04/` | NOT_RUN; tap/button; no fake offline AI answer |
| E9-T05 / D-010 | SIM/no-SIM/permission/call-state checklist prepared | E8-T01 and named tablet | `artifacts/device/E9-T05/` | NOT_RUN; only observed outcomes, never infer CONNECTED from intent launch |

These are planned fallbacks, not implemented device features. No hardware SDK,
permission, provisioning, factory reset, phone call or device-state mutation is
introduced by the Week 1 collector.

## Operator procedure when equipment is available

1. Record an operator and equipment alias. Install Android platform-tools and
   connect one authorized test device; run the collector with `--adb` if needed.
2. Confirm manufacturer/model/SKU/API/patch against Settings. Record GMS and the
   installed build version/hash manually, using synthetic demo data only.
3. Execute ENV-001..004 and the task's cases from `docs/device-test-matrix.md`.
   Store a timestamp, permission/network state, observed result and sanitized
   evidence path for each case. UNKNOWN is not supported.
4. Kiosk provisioning requires a disposable named device and the reviewed device
   procedure. Collect Device Owner/allowlist/Lock Task observations, exit and
   crash recovery. Do not use this collector as provisioning authorization.
5. For BLE capture only the approved protocol fields; for camera verify frame
   disposal without recording frames; for audio record state transitions, not
   audio. Telephony outcomes must be observed independently from launch intents.
6. Complete the ten-cycle gate below or document the approved fallback and its
   failed gate. Do not mark E9 complete on an emulator or fixture result.

| Reboot/exit cycle | Observed recovery / exit / evidence | Status |
| --- | --- | --- |
| 1 | No device | NOT_RUN |
| 2 | No device | NOT_RUN |
| 3 | No device | NOT_RUN |
| 4 | No device | NOT_RUN |
| 5 | No device | NOT_RUN |
| 6 | No device | NOT_RUN |
| 7 | No device | NOT_RUN |
| 8 | No device | NOT_RUN |
| 9 | No device | NOT_RUN |
| 10 | No device | NOT_RUN |
