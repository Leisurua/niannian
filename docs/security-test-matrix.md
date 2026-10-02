# 念念（NianNian）安全测试矩阵

| ID | Area | Preconditions | Attack / Action | Expected Result | Evidence | Priority |
| --- | --- | --- | --- | --- | --- | --- |
| AUTH-001 | Authorization | Family A/B fixtures | A token requests B Memory list | Denied/hidden; no item/count leak | response + audit + query trace | P0 |
| AUTH-002 | Authorization | Family A/B | Request B Reminder/detail/executions | Denied/hidden; no medication data | response + audit | P0 |
| AUTH-003 | Authorization | Family A/B | Request B SignalEvent/Notification | Denied/hidden; no event status leak | response + notification trace | P0 |
| AUTH-004 | Authorization | Family A/B | Request B WeeklyReport | Denied/hidden; no metric leak | response + SQL scope | P0 |
| AUTH-005 | Authorization | Family A/B | Request B File/download URL | Denied; no URL/object access | response + object GET denied | P0 |
| AUTH-006 | Authorization | Family A/B | Request B Device/heartbeat/settings | Denied; no state mutation | response + audit | P0 |
| AUTH-007 | Authorization | Family A/B | Request B AuditLog/export/delete job | Denied/hidden; no job metadata | response + audit | P0 |
| AUTH-008 | Token | valid session | Expired access token | 401; no resource action | response + server log code | P0 |
| AUTH-009 | Token | rotated refresh token | Reuse old refresh token | 401; token family/session revoked and audited | session state + audit | P0 |
| AUTH-010 | Token | logged-in device | Logout then use access/refresh | Denied after defined residual window; no new refresh | response + session row | P0 |
| AUTH-011 | Token | multiple sessions | Logout-all then use every refresh token | All sessions denied | session inventory + audit | P0 |
| AUTH-012 | Token | lost/shared device | Unbind/lost then attempt access | Local token wiped; server session denied | device/session + wipe evidence | P1 |
| AUTH-013 | Token | malformed/wrong signature | Send modified JWT/bearer | Uniform 401; no claims/stack leak | response + log scan | P1 |
| AUTH-014 | Enumeration | users/invites/resources | Probe phone, invite, Memory UUID | Equivalent errors; no existence claim | response/timing comparison | P1 |
| AUTH-015 | Mass assignment | family/member DTO | Send role=SYSTEM/status=CONFIRMED/owner=B | Rejected/ignored; server retains authority | response + DB diff | P0 |
| AUTH-016 | Permission | CHILD/CAREGIVER/CONTACT | Same family but missing permission/Consent | Denied/redacted; no implicit grant | matrix result + audit | P0 |
| AUTH-017 | Token | User A and User B sessions | Present User A token with User B device/resource identifiers | Token identity wins; wrong-user action denied and audited | response + session/resource trace | P0 |
| CONS-001 | Consent | granted Memory scope | Grant then read via API/RAG | Access only for subject/grantee/scope | API + RAG trace | P0 |
| CONS-002 | Consent | granted scope | Revoke then request Memory/summary | Immediate deny/redact | API response + audit | P0 |
| CONS-003 | Consent | revoked Memory | RAG query with cached embedding | No result/context/citation | retrieval + vector trace | P0 |
| CONS-004 | Consent | revoked Photo | New URL/use old URL | New URL denied; old URL only documented TTL | response + TTL/object evidence | P0 |
| CONS-005 | Consent | pending notification | Revoke before delivery | Withheld/cancelled/re-evaluated | queue + provider mock | P0 |
| CONS-006 | Consent | pending export | Revoke before packaging/download | Revoked resource excluded/job invalidated | manifest + audit | P0 |
| CONS-007 | Consent | Family App offline cache | Revoke while offline then sync | Cache invalidated/hidden; stale label | screen + cache inspection | P0 |
| CONS-008 | Consent | AI context pending | Revoke during context build | Context filtered/cancelled; no provider send | adapter fixture | P0 |
| RAG-001 | RAG | A/B confirmed Memory | Query A with B similar text | B never retrieved | retrieval IDs + SQL predicate | P0 |
| RAG-002 | RAG | PENDING Memory | Query matching pending fact | Not used as fact/context | retrieval + reply | P0 |
| RAG-003 | RAG | REVOKED Memory | Query matching revoked fact | Excluded | vector/response evidence | P0 |
| RAG-004 | RAG | DELETED Memory | Query before worker cleanup | Excluded immediately | list/RAG negative + task state | P0 |
| RAG-005 | RAG | consent revoked | Query old cache | Cache miss/invalidation | cache version evidence | P0 |
| RAG-006 | RAG | malicious Memory | Text says ignore rules/reveal B | Untrusted data; no override | prompt fixture + output | P0 |
| RAG-007 | RAG | invalid memory_ref | LLM returns ref outside retrieval set | Factual fallback; no leak | validator trace | P0 |
| FILE-001 | File | private bucket | Guess key/direct public URL | Access denied; bucket not public | bucket policy + GET result | P0 |
| FILE-002 | Upload | upload request | Fake MIME/extension/path filename | Rejected/quarantined; safe key | metadata + key | P1 |
| FILE-003 | Upload | limits configured | Oversized/compressed bomb/zero checksum | Rejected before availability | response + quarantine | P1 |
| FILE-004 | Integrity | pending asset | Wrong checksum at confirm | Confirm denied; no RAG/download | response + status | P1 |
| FILE-005 | Privacy | photo with GPS EXIF | Upload/download/export | EXIF removed or explicit decision/evidence | metadata inspection | P1 |
| FILE-006 | Lifecycle | orphan upload | Abandon request then cleanup | Removed/failed; never readable | worker + object list | P1 |
| FILE-007 | Access | deleted/revoked Memory photo | Download after revoke/delete | Denied; cleanup queued | response + object state | P0 |
| FILE-008 | Enumeration | A/B asset IDs | Request B metadata | Hidden/denied without existence leak | response comparison | P0 |
| WS-001 | WebSocket | valid A conversation | Invalid/expired token connect | Rejected/closed; no events | close code + log | P0 |
| WS-002 | WebSocket | A token | Connect to B conversation id | Rejected; no state/message | close code + audit | P0 |
| WS-003 | WebSocket | live session | Malformed JSON/unexpected type | Error/close; no crash/action | response + stability log | P1 |
| WS-004 | WebSocket | live session | Oversized frame/audio chunk | Rejected/limited | limit evidence | P1 |
| WS-005 | WebSocket | sequence protocol | Replay/duplicate old message | Ignored/rejected; no duplicate action | sequence log | P1 |
| WS-006 | WebSocket | live session | Expire/revoke token during connection | Close/reauthorize; no further content | close + session state | P0 |
| WS-007 | WebSocket | live session | Flood messages/connections | Per-user/session limits; Emergency unaffected | metrics + response | P1 |
| WS-008 | WebSocket | reconnect | Reconnect stale conversation | Only owner/current Consent; no stale transcript | response + trace | P0 |
| WS-009 | WebSocket | ASR/TTS | Inspect outbound events | No token/provider metadata/full sensitive transcript | capture + log scan | P0 |
| AI-001 | AI | malicious Elder input | Ask for other family facts | Uncertainty/deny; no unauthorized context | provider request + output | P0 |
| AI-002 | AI | malicious Memory/upload | Instruction-like content | Marked untrusted; cannot change policy | prompt fixture + output | P0 |
| AI-003 | AI | candidate output | Propose Consent/delete/notify/emergency | Application rejects direct action | DTO + action audit | P0 |
| AI-004 | AI | provider timeout | Timeout/invalid schema | Safe fallback; no sensitive action | adapter mock + state | P1 |
| AI-005 | AI | fabricated ref/fact | Unsupported name/date/relationship | Removed or uncertainty fallback | validation trace | P1 |
| AI-006 | AI | redaction policy | Ordinary query vs Medication/Photo/Phone | Only allowlisted fields sent | request capture fixture | P0 |
| AI-007 | Provider | provider config | Inspect training/retention/region/log policy | Real S2/S3 blocked until decision | provider approval record | P0 |
| PRIV-001 | Notification | locked screen | Receive signal/health/emergency push | Generic/minimal; no full conversation/health/secret | screenshot + payload | P0 |
| PRIV-002 | Logging | full app flow; Android app-owned execution per approved E0-T03 option A | Inspect normal/crash logs; main/worker, nested/suppressed errors, hostile formatting and failed sink | No token/key/audio/transcript/phone/health/memory/URL through app-owned boundaries; content-free fatal termination; unmanaged/framework/native/OEM residual separately reported, never counted PASS | redaction scan + [approved boundary](evidence/E0-T03-repair-proposal.md); retain original unmanaged-thread FAIL | P0 |
| PRIV-003 | Demo | demo build | Run conversation/emergency/report | Fictional fixture; no production secret/content | artifact scan | P0 |
| PRIV-004 | Signal | PHYSICAL/EMOTION/MISS/SCAM | Read family detail | Minimum evidence; no raw conversation/diagnosis | response + audit | P1 |
| PRIV-005 | Conversation | audio policy unset | Run voice flow | No raw audio persisted without approved policy | object/DB inspection | P0 |
| PRIV-006 | WeeklyReport | contact/denied metric | Request report/export/push | Missing/redacted; Emergency Contact no full report | response + manifest | P1 |
| PRIV-007 | Audit | sensitive read/delete | Inspect AuditLog | actor/time/resource/action/result; no content/token/phone | row inspection | P0 |
| PRIV-008 | Secrets | repository/CI fixture | Search Git/.env/log/APK | No real secrets; example keys only | secret scan report | P0 |
| PRIV-009 | Export | own/family export | Request then revoke/delete | auth/re-auth, short URL/expiry/audit, no revoked/B data | manifest + URL status | P0 |
| PRIV-010 | Privacy | demo/test recording flow | Capture screenshot/screen recording of Elder/Family UI | Only fictional data; no token/phone/health/full conversation visible | screenshot review + artifact scan | P1 |
| EMG-001 | Emergency | configured contact | Screen trigger | Coordinator + visible progress | screen + case row | P1 |
| EMG-002 | Emergency | wake enabled | Explicit emergency phrase | Deterministic path, no LLM dependency | event trace | P0 |
| EMG-003 | Emergency | BLE connected | Press once | One case/attempt, idempotent | case/attempt IDs | P0 |
| EMG-004 | Emergency | BLE/voice | Duplicate packet/repeated phrase | One logical case in dedupe window | dedupe evidence | P0 |
| EMG-005 | Emergency | provider/SIM unavailable | Trigger call | FAILED/NO_ANSWER/pending; never fake CONNECTED | provider mock + UI | P0 |
| EMG-006 | Emergency | no SIM/call permission | Trigger | Fallback/clear failure; Quiet Hours only bypassed for flow | device log + UI | P1 |
| EMG-007 | Emergency | backend offline | Trigger BLE/screen | Local progress/fallback; no server success claim | offline capture | P1 |
| EMG-008 | Emergency | repeated abuse | Flood emergency endpoint | Independent abuse control + local safe alternative | rate response + case count | P1 |
| EMG-009 | Emergency | case in progress | Replay idempotency/reconnect | No duplicate call; status reconciles | case timeline | P1 |
| EMG-010 | Emergency | emergency override | Attempt full Conversation/Memory read | Override cannot expand consent | response + audit | P0 |
| BLE-001 | BLE | named hardware | Inspect GATT/service allowlist | Unknown device not trusted; TBD remains blocked | protocol capture | P0 |
| BLE-002 | BLE | paired device | Replay packet/duplicate notification | Rejected/deduped; no repeated case | packet + case | P0 |
| BLE-003 | BLE | reconnect | Connect to wrong nearby device | No subscription/action | device identity log | P1 |
| BLE-004 | BLE | low battery/off/denied | Trigger button | Visible state; screen/voice fallback | UI + heartbeat | P1 |
| DEV-001 | Android local | token stored | Inspect SharedPreferences/DataStore/Room | No plaintext token; Keystore-backed | device inspection | P0 |
| DEV-002 | Android local | S2/S3 cached | Revoke/delete offline then sync | Cache hidden/wiped; stale label | DB/cache evidence | P0 |
| DEV-003 | Camera | permission denied | Start presence | No frame access/upload; other features work | permission log + network | P0 |
| DEV-004 | Camera | presence active | Inspect files/network/template | No frame, identity, biometric template or remote view | file/network scan | P0 |
| DEV-005 | Microphone | wakeword SDK | Wake → ASR → call | Single audio owner; no continuous cloud stream | audio focus trace | P0 |
| DEV-006 | Kiosk | clean tablet | Provision Device Owner/LockTask | ACTIVE only after observed lock; honest config error | provisioning evidence | P1 |
| DEV-007 | Kiosk | active kiosk | Settings/ADB/USB/debug/lost device | Exit controlled; session/token invalidated | device record | P1 |
| DEV-008 | Device | uninstall/force stop/reboot | Observe boot/local data | No unsafe credential access; honest recovery | device logs | P1 |
| DEL-001 | Delete | Memory + chunk/vector/cache/object | Delete Memory | API/list/RAG/cache/object unavailable before worker finish | timestamps + negatives | P0 |
| DEL-002 | Delete | Conversation + summary | Delete account/session data | Summary/transcript/export/local/provider action per policy | job manifest | P0 |
| DEL-003 | Delete | queued notification/export | Revoke/delete before delivery/package | Re-evaluate/withhold/exclude | queue/manifest | P0 |
| DEL-004 | Delete | forced worker failure | Fail object/vector cleanup | PARTIAL_FAILURE, no false complete, retry visible | job state + alert | P1 |
| DEL-005 | Delete | audit | Inspect audit after delete | Minimal fact per policy; no content resurrected | audit row + policy | P1 |
| DEL-006 | Backup | synthetic backup | Delete then inspect restore | Backup exception disclosed and follows decision | backup inventory | P1 |

## 1. Test Execution Rules

- 记录版本、设备型号/API、配置、fixture、时间和证据路径；结果只允许 `PASS/FAIL/BLOCKED/NOT_RUN`。
- 负向测试使用两个家庭、两个老人、不同角色和交叉 Consent；不能只测 UI 隐藏，必须验证服务端响应、查询条件和数据平面。
- P0 测试未通过、`BLOCKED` 或没有证据时，不得把课程 Demo 描述为通过安全验收。
- 后续工具建议：pip-audit、Android dependency inspection、secret scanning、静态分析和依赖更新审查；本矩阵不等于已经执行这些工具。
