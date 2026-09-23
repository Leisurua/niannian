# 念念（NianNian）设备测试矩阵

| 字段 | 说明 |
| --- | --- |
| 范围 | 指定 Android 平板、BLE 实体按钮、老人端 App 及其离线/权限/系统集成 |
| 状态 | Test plan only；未执行项不得填写 Pass |
| 记录原则 | 每次测试记录设备型号、Android API、App 版本、配置、日志时间、实际观察和证据路径 |
| 结果值 | `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN` |

`Offline?` 使用 `Y`、`N` 或 `Transition`。`Permission State` 使用 `Granted`、`Denied`、`Permanently denied`、`System/Admin` 或 `N/A`。

## 1. Entry and Evidence

| Test ID | Capability | Precondition | Action | Expected Result | Offline? | Permission State | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ENV-001 | Device baseline | Named tablet in hand | Record model/API/patch/SKU/GMS/ADB | Evidence captured; unknown fields explicitly marked | N | N/A | NOT_RUN | |
| ENV-002 | Build | Signed build available | Install and open app version page | Version/build hash matches release record | N | N/A | NOT_RUN | |
| ENV-003 | Demo mode | Demo config enabled | Open settings/device status | Mock status visibly labelled; no real-success wording | N | N/A | NOT_RUN | |
| ENV-004 | Logs/privacy | Debug logging enabled | Run one conversation/reminder/emergency flow | No raw audio/frame/full phone/full conversation/token in logs | Both | Granted | NOT_RUN | |

## 2. Kiosk, Device Owner and Boot

| Test ID | Capability | Precondition | Action | Expected Result | Offline? | Permission State | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| KIO-001 | Device Owner | Clean disposable tablet | Provision documented Device Owner path | Owner is observable; package/admin evidence saved | N | System/Admin | NOT_RUN | |
| KIO-002 | Lock Task | Device Owner provisioned | Apply allowlist and enter lock task | Elder app locked; exit to launcher blocked by policy | N | System/Admin | NOT_RUN | |
| KIO-003 | Kiosk status | Kiosk active | Read app/device status and heartbeat | `kiosk=ACTIVE` only after observed lock | N | System/Admin | NOT_RUN | |
| KIO-004 | Config failure | Device Owner absent | Start app | `KIOSK_CONFIG_ERROR`/clear next step; no false ACTIVE | N | System/Admin | NOT_RUN | |
| KIO-005 | Reboot recovery | Kiosk active | Reboot; observe 10 cycles | App/kiosk/essential state recovers on every cycle or failure is documented | N | System/Admin | NOT_RUN | |
| KIO-006 | Development exit | Test-only exit procedure available | Exit using documented admin/factory path | Exit works without hidden elder gesture; evidence retained | N | System/Admin | NOT_RUN | |
| KIO-007 | Crash recovery | Kiosk active | Force-stop/crash app, wait for OEM/system recovery | Recovery behavior is observed and reported; no claim if launcher remains | N | System/Admin | NOT_RUN | |
| KIO-008 | Boot restrictions | App force-stopped once | Reboot after force-stop | Boot delivery behavior recorded; fallback status is honest | N | System/Admin | NOT_RUN | |
| KIO-009 | Locked boot | Device-protected path implemented | Reboot before user unlock | Only safe initialization occurs; credential data is not accessed early | N | System/Admin | NOT_RUN | |

## 3. Permissions and Settings

| Test ID | Capability | Precondition | Action | Expected Result | Offline? | Permission State | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PER-001 | Microphone | Fresh install | Grant `RECORD_AUDIO` | Capability becomes usable and heartbeat reflects state | N | Granted | NOT_RUN | |
| PER-002 | Microphone denial | Fresh install | Deny microphone | Voice unavailable; button/reminder/contact still work | N | Denied | NOT_RUN | |
| PER-003 | Permanent microphone denial | Denied twice/settings blocked | Trigger voice entry | One explanation + Settings path; no prompt loop | N | Permanently denied | NOT_RUN | |
| PER-004 | Camera | Fresh install and consent | Grant `CAMERA` and `CAMERA_PROXIMITY` | Presence can be enabled | N | Granted | NOT_RUN | |
| PER-005 | Camera denial | Camera requested | Deny camera | Presence disabled; no frame access; conversation/reminder continue | N | Denied | NOT_RUN | |
| PER-006 | Bluetooth scan/connect | Fresh install | Grant applicable BLE permissions and enable adapter | Scan/connect path available | N | Granted | NOT_RUN | |
| PER-007 | Bluetooth denial/off | BLE configured | Deny permission or turn adapter off | `DISABLED`/`PERMISSION_REQUIRED`; no scan loop; screen Emergency works | N | Denied | NOT_RUN | |
| PER-008 | Notifications | Applicable API | Deny `POST_NOTIFICATIONS` | In-app device state remains; FGS behavior follows API policy | N | Denied | NOT_RUN | |
| PER-009 | Call | SIM/Telecom candidate | Grant/deny `CALL_PHONE` | Local path only shown when observable; fallback on denial | N | Denied/Granted | NOT_RUN | |
| PER-010 | Battery/OEM | Device settings accessible | Inspect Doze, auto-start and battery policy | Configuration recorded; no assumption that plugged-in means exempt | N | System/Admin | NOT_RUN | |

## 4. BLE Button

| Test ID | Capability | Precondition | Action | Expected Result | Offline? | Permission State | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BLE-001 | Protocol discovery | Button model available | Capture advertisement/GATT services/chars/payload | Protocol record created; unknown fields remain TBD | N | Granted | NOT_RUN | |
| BLE-002 | Scan | Button off/on | Start bounded scan | Candidate found without continuous high-rate scan | N | Granted | NOT_RUN | |
| BLE-003 | Pair/bond | Protocol requires/does not require bond | Complete expected pairing path | Result and requirement recorded; no assumed bond | N | Granted | NOT_RUN | |
| BLE-004 | Connect/subscribe | Button paired | Connect and subscribe | `CONNECTED` only after service/characteristic verified | N | Granted | NOT_RUN | |
| BLE-005 | Button event | Connected | Press once according to vendor protocol | One `PhysicalButtonPressed`; local Emergency progress appears | Y | Granted | NOT_RUN | |
| BLE-006 | Duplicate packet | Connected | Replay same packet rapidly | One event/case within dedupe window | Y | Granted | NOT_RUN | |
| BLE-007 | Long/double press | Protocol semantics unresolved | Exercise all press patterns | Results recorded; no semantic chosen without evidence | Y | Granted | NOT_RUN | |
| BLE-008 | Button off | Connected then power off button | Observe state | `DISCONNECTED`; bounded reconnect; no crash | Y | Granted | NOT_RUN | |
| BLE-009 | Bluetooth off | Connected then turn adapter off | Observe state and UI | `DISABLED`; scanning stops; fallback contact visible | Y | Granted | NOT_RUN | |
| BLE-010 | Reconnect | Button and app restart | Restart app/tablet/button separately | Reconnect/subscription restore with backoff; no replay | Y | Granted | NOT_RUN | |
| BLE-011 | Screen off | Connected | Turn screen off for configured interval, press button | Behavior recorded; event reliability meets gate or is degraded honestly | Y | Granted | NOT_RUN | |
| BLE-012 | Low battery | Button battery below vendor threshold | Observe battery characteristic/event | `LOW_BATTERY`; event behavior documented | Y | Granted | NOT_RUN | |
| BLE-013 | Unknown device | Another BLE peripheral nearby | Scan/connect | Not connected unless allowlisted/protocol matches | Y | Granted | NOT_RUN | |
| BLE-014 | Backend offline | Connected, network disabled | Press button | Local case/progress works; sync queued; no fake server success | Y | Granted | NOT_RUN | |

## 5. CameraX Presence

| Test ID | Capability | Precondition | Action | Expected Result | Offline? | Permission State | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CAM-001 | Camera start | Permission and consent granted | Enter Home/idle | Camera binds only in configured active window | Y | Granted | NOT_RUN | |
| CAM-002 | No person | Idle window | Leave scene empty | `ABSENT`; no wake | Y | Granted | NOT_RUN | |
| CAM-003 | One person | Idle window | Person enters and remains threshold | `PRESENT`; one Wake UI event after threshold | Y | Granted | NOT_RUN | |
| CAM-004 | Multiple people | Detector active | Two or more people present | Presence only; no identity/person count dependency | Y | Granted | NOT_RUN | |
| CAM-005 | Photo/background | Detector active | Show a face/photo/background image | Must not be treated as identity; false-trigger result recorded | Y | Granted | NOT_RUN | |
| CAM-006 | Low light | Detector active | Repeat no-person/person in low light | Result and false-trigger rate recorded; no invented certainty | Y | Granted | NOT_RUN | |
| CAM-007 | Cooldown | Person remains | Keep present after wake | No repeated wake storm during cooldown | Y | Granted | NOT_RUN | |
| CAM-008 | Screen off | Device screen off | Observe sampling/stop policy | Camera behavior follows power policy; no unexpected 24h full rate | Y | Granted | NOT_RUN | |
| CAM-009 | Permission revoke | Active camera | Revoke permission in Settings | Analyzer unbinds; no frame access; state updates | Y | Denied | NOT_RUN | |
| CAM-010 | Privacy | Test run | Inspect files/logs/network | No saved/uploaded frame, face template or identity field | Both | Granted | NOT_RUN | |
| CAM-011 | Long run | Camera active profile | Run benchmark window | Battery, CPU, temperature, memory and false triggers recorded | Y | Granted | NOT_RUN | |

## 6. Audio and Wake Word

| Test ID | Capability | Precondition | Action | Expected Result | Offline? | Permission State | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUD-001 | Wake word online | SDK/model and mic ready | Say wake word in quiet room | Local UI wakes; audio owner changes to ASR before capture | N | Granted | NOT_RUN | |
| AUD-002 | Wake word offline | Disable network | Say wake word | Local prompt/UI works; no fabricated AI answer | Y | Granted | NOT_RUN | |
| AUD-003 | ASR ownership | Wake word ready | Trigger then speak | Wake stream pauses; ASR is sole mic owner | Both | Granted | NOT_RUN | |
| AUD-004 | Audio focus loss | Conversation active | Start another audio/call source | Current owner pauses/fails clearly; no two captures | Both | Granted | NOT_RUN | |
| AUD-005 | Mic denied | Permission removed | Trigger wake/button conversation | Voice path degrades; reminder/contact remain | Both | Denied | NOT_RUN | |
| AUD-006 | TV/background | Wake SDK ready | Repeat at distance/noise levels | Latency/false-trigger/repeat rate recorded, not assumed | Both | Granted | NOT_RUN | |
| AUD-007 | Elder speech | Audio profile ready | Test slow speech and repeats | ASR low confidence asks repeat; no high-risk action on uncertainty | Both | Granted | NOT_RUN | |
| AUD-008 | TTS route | Speaker available | Play reminder and fallback copy | Intelligible output at safe volume; route recorded | Both | N/A | NOT_RUN | |
| AUD-009 | Call audio | Telephony path available | Start call while wake word enabled | `CALL` owns audio; wake word/ASR paused | N | Granted | NOT_RUN | |
| AUD-010 | Long run | Wake profile enabled | Run configured duration | Battery, memory, temperature and restart behavior recorded | Both | Granted | NOT_RUN | |

## 7. Reminder and Offline Scheduler

| Test ID | Capability | Precondition | Action | Expected Result | Offline? | Permission State | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REM-001 | Online cache | Reminder exists online | Sync to tablet | Local rule has version/timezone/occurrence data | N | N/A | NOT_RUN | |
| REM-002 | Offline due | Cache fresh, network off | Wait for due occurrence | Reminder presents locally with `source=OFFLINE` | Y | N/A | NOT_RUN | |
| REM-003 | Offline feedback | Due reminder offline | Submit DONE/LATER/SKIPPED | Local feedback persisted and marked pending | Y | N/A | NOT_RUN | |
| REM-004 | Restore sync | Pending feedback | Restore validated network | One idempotent ACK; queue removed only after ACK | Transition | N/A | NOT_RUN | |
| REM-005 | No response | No feedback window | Let window expire | Worker semantics remain `NO_RESPONSE`, never “未服药” | Both | N/A | NOT_RUN | |
| REM-006 | Reboot | Future reminder cached | Reboot before due | Occurrence rescheduled once, no duplicate prompt | Both | N/A | NOT_RUN | |
| REM-007 | Timezone | Reminder with IANA timezone | Change timezone and recalculate | Future occurrence follows documented local-time policy | Both | N/A | NOT_RUN | |
| REM-008 | Clock change | Reminder scheduled | Move clock forward/back in test profile | Duplicate/missed behavior recorded; safety policy applied | Both | N/A | NOT_RUN | |
| REM-009 | DST | DST timezone fixture | Cross transition | Local schedule remains correct or limitation documented | Both | N/A | NOT_RUN | |
| REM-010 | Exact access absent | Exact alarm not granted | Schedule high-accuracy reminder | Falls back/blocks with clear timing limitation; no false exactness | Both | System/Admin | NOT_RUN | |
| REM-011 | Scheduler recovery | Kill process | Wait/reopen | Scheduler rebuilds from Room; no lost acknowledged result | Both | N/A | NOT_RUN | |
| REM-012 | Stale cache | Cache beyond configured freshness | Go offline | Stale label and safe behavior; no current weather/medication rewrite | Y | N/A | NOT_RUN | |

## 8. Connectivity and Sync

| Test ID | Capability | Precondition | Action | Expected Result | Offline? | Permission State | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NET-001 | Wi-Fi online | Valid Wi-Fi | Connect and probe backend | `ONLINE` only after validated route/backend | N | N/A | NOT_RUN | |
| NET-002 | Wi-Fi disconnected | Online session | Disable Wi-Fi | `OFFLINE`; cached functions remain | Y | N/A | NOT_RUN | |
| NET-003 | Captive portal | Portal network | Connect without sign-in | `CAPTIVE_PORTAL`, not `ONLINE`; show network action | Y | N/A | NOT_RUN | |
| NET-004 | Backend down | Network route valid | Stop/mock backend | `LIMITED`; no fake AI/notification success | Y | N/A | NOT_RUN | |
| NET-005 | Provider down | Backend online | Make AI/push provider unavailable | Conversation/notification fallback follows contract; Emergency/reminder continue | N | N/A | NOT_RUN | |
| NET-006 | Queue ordering | Multiple pending actions | Restore network | Actions ordered/deduped; retry/backoff visible in logs | Transition | N/A | NOT_RUN | |
| NET-007 | Retry duplicate | Same request retried | Replay same Idempotency-Key | Server returns same logical result; no duplicate event/call | Transition | N/A | NOT_RUN | |
| NET-008 | Repeated offline/online | Toggle network repeatedly | Observe state changes | Coalesced heartbeat/sync; no storm | Transition | N/A | NOT_RUN | |

## 9. Emergency and Telephony

| Test ID | Capability | Precondition | Action | Expected Result | Offline? | Permission State | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EMG-001 | Screen trigger | Contact configured | Press screen Emergency | Enters shared coordinator and shows local progress | Both | N/A | NOT_RUN | |
| EMG-002 | Voice trigger | Mic/wake ready | Say explicit emergency phrase | Deterministic path enters coordinator without waiting for LLM | Both | Granted | NOT_RUN | |
| EMG-003 | BLE trigger | Connected button | Press physical button | Same coordinator/source=BLE; one case only | Both | Granted | NOT_RUN | |
| EMG-004 | Duplicate BLE | Connected button | Duplicate packet/repeated press inside window | One emergency event/request; each real attempt auditable | Both | Granted | NOT_RUN | |
| EMG-005 | SIM + Telecom | SIM and capability confirmed | Initiate configured local call | Actual observed state recorded; no claim human answered | N | Granted | NOT_RUN | |
| EMG-006 | No SIM | SIM absent | Initiate emergency | Local call unavailable; fallback/mock path or honest `FAILED` reason visible | Y/N | Granted | NOT_RUN | |
| EMG-007 | Call permission denied | Call path candidate | Deny `CALL_PHONE` and initiate | `TELEPHONY_PERMISSION_DENIED`; fallback offered | N | Denied | NOT_RUN | |
| EMG-008 | Provider down | Backend/provider unavailable | Initiate with network | Local attempt not erased; backend remains pending/failed honestly | Y/limited | Granted | NOT_RUN | |
| EMG-009 | Family unavailable | Contact disabled/unreachable | Initiate | Actual `NO_ANSWER`/`FAILED` and next action; no false CONNECTED | Both | N/A | NOT_RUN | |
| EMG-010 | Cancel | Contacting but not connected | Cancel | `CANCELLED` only when cancellation observed/allowed | N | N/A | NOT_RUN | |
| EMG-011 | Process death | Emergency initiated | Kill app/process and restore | Local case reconciles; no duplicate call | Both | N/A | NOT_RUN | |
| EMG-012 | Rate limit | Repeated test triggers | Exceed ordinary request rate | Local Emergency path not silently blocked; abuse response and audit recorded | Both | N/A | NOT_RUN | |

## 10. Process, Power and Performance

| Test ID | Capability | Precondition | Action | Expected Result | Offline? | Permission State | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PERF-001 | Startup | Cold boot | Measure power-on to Ready | Latency recorded; no target invented in this plan | Both | System/Admin | NOT_RUN | |
| PERF-002 | Wake latency | Wake profile ready | Measure keyword to local UI and ASR | p50/p95 recorded | Both | Granted | NOT_RUN | |
| PERF-003 | BLE latency | Connected button | Measure press to local progress | p50/p95 recorded | Both | Granted | NOT_RUN | |
| PERF-004 | Reminder latency | Cached occurrence | Measure due time to presentation | Distribution and misses recorded | Y | N/A | NOT_RUN | |
| PERF-005 | Battery | Full charge/profile | Run idle, wake, camera, BLE profiles | Battery drain per profile recorded | Both | Varies | NOT_RUN | |
| PERF-006 | Memory | Long run | Observe app/FGS memory | Growth/leak and recovery recorded | Both | Varies | NOT_RUN | |
| PERF-007 | Temperature | Long run | Measure surface/device temperature | Temperature and throttling recorded | Both | Varies | NOT_RUN | |
| PERF-008 | Screen | Brightness/timeout profiles | Run demo duration | Burn-in/brightness/timeout behavior recorded | Both | N/A | NOT_RUN | |
| PERF-009 | OEM kill | Battery policy default | Let device idle/doze | Process/FGS/reminder/BLE behavior recorded | Both | System/Admin | NOT_RUN | |

## 11. Acceptance and Sign-off

The device is ready for implementation/demo only when:

1. Kiosk and boot pass the 10-reboot gate or have an approved, visible fallback.
2. BLE protocol, event semantics, duplicate suppression and reconnect evidence exist.
3. Offline wake word, local reminder and Emergency behavior are demonstrated without public internet.
4. Camera privacy checks prove no frame/face data persistence or upload.
5. Microphone ownership tests prove Wake Word, ASR and Call do not capture simultaneously.
6. SIM/no-SIM, permission denial and provider failure outcomes are honest and actionable.
7. Performance measurements include startup, wake, BLE, reminder, battery, memory and temperature.
8. Every `BLOCKED` item has an owner, impact, fallback and decision date; it is not counted as pass.

Sign-off record:

```text
Device / model:
Android API / patch:
App version / build:
BLE button / protocol revision:
Test window:
Executed by:
Hardware Acceptance Gate: PASS / CONDITIONAL / FAIL
Open blockers:
Approved fallback decisions:
Evidence links:
```
