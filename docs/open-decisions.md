# 念念（NianNian）Open Decisions Register

本表合并 Requirements、API、Database、AI、Device、Privacy/Security 和 ADR 中的未决事项。重复问题只保留一个 ID。未决不等于工程停止；`Blocking?` 指它是否阻止整个项目的下一步，而不是是否阻止某个 Feature 的生产化。

## Decision Classes

| Class | Meaning |
| --- | --- |
| D0 | 搭建工程或冻结基础 Contract 前必须确定 |
| D1 | 工程可先搭建，但对应 Feature 开始前必须确定 |
| D2 | 通过真机/Provider/性能 Spike 决定 |
| D3 | 可用开发/测试默认值先实现，之后配置化确认 |

**当前 D0：None。** Mock login、Mock providers、no-raw-audio 默认和 capability fallback 使工程初始化可以开始。

## Consolidated Register

| ID | Class | Title | Source | Question | Options | Recommended Default | Blocking? / Blocking What? | Owner | Deadline | Validation Method | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D-001 | D1 | Authentication credential and token lifecycle | Requirements §13; API §5/34; privacy §7 | 比赛版最终用何种登录凭证？Access/Refresh TTL、reuse、lost-device、shared-device re-auth 如何定？ | Demo only；verification code；后续可替换 credential | Batch 0 用 `DEMO` contract；Auth feature 前冻结 verification discriminator、短 TTL、refresh reuse 全族撤销、Keystore/re-auth | No project-wide; blocks production Auth acceptance | Backend/Auth owner | Before E1 Auth implementation | AUTH-008..017 + contract review | OPEN / DEV DEFAULT |
| D-002 | D1 | Raw audio, transcript and summary retention | Requirements FR-015/005; DB §12/20; retention R-001..003; API conflict | raw audio 是否允许调试保存？transcript/summary 是否导出、保留多久？ | 默认不保存；批准的短期 debug；受控 summary only | 默认 no raw audio；本地/流式 ASR 后丢弃；仅保存受控 summary/status，期限由 privacy owner 决定 | No project-wide; blocks real Conversation retention/export gate | Privacy + AI owner | Before real conversation data | PRIV-005, DEL-002, provider deletion evidence | OPEN / PRIVACY GATE |
| D-003 | D1 | External AI/provider data policy | Privacy §12; threat T-019; ADR-005 | Provider 是否训练、留存、跨境、保留日志？删除 API 和 DPA 是否满足？ | Mock only；provider with no-train/retention controls；local provider | Batch 0 只用 Mock；真实 S2/S3 发送前必须完成 provider checklist 和合同/配置批准 | No project-wide; blocks real provider integration | Security + Integration owner | Before provider integration | AI-006/007, redaction capture, provider approval record | OPEN / MOCK ALLOWED |
| D-004 | D3 | Push/SMS/Phone provider | ADR-008; Requirements FR-041/053; API conflict | 比赛网络、费用、区域和 Android 权限是否支持真实渠道？ | FCM；国内 provider；MockPush + IN_APP polling；Telecom local | `MockPush` + IN_APP 为演示基线；channel/status 仍按公共 contract；真实 provider 可替换 | No; blocks real delivery claim only | Integration + Demo owner | Before E6/E8 real-channel task | provider smoke + failure/NO_ANSWER tests | OPEN / MOCK BASELINE |
| D-005 | D2 | Avatar implementation | ADR-009; FR-016 | 采用哪种具体 SDK/简化 Avatar？离线、包体、授权和帧率是否可接受？ | mature SDK；简化 2D/3D；MockAvatar | 先实现 `AvatarAdapter` + Mock/简化资源；具体 SDK 不影响 API/DB | No; blocks polished Avatar acceptance only | Android/Design owner | Before E4 demo polish | avatar contract + PERF device benchmark | WAITING SPIKE |
| D-006 | D2 | Named tablet and kiosk/boot baseline | ADR-010; device §3/5/6 | 型号、API、Device Owner、Lock Task、OEM boot policy 是否可用？ | Device Owner COSU；普通 App + visible fallback | 目标 Device Owner + Lock Task；失败显示 `CONFIG_ERROR`/普通 App，不伪造 ACTIVE | No; blocks FR-060 hardware acceptance | Device owner | Batch 0 / Week 1 | ENV-001, KIO-001..009, 10 reboot gate | WAITING SPIKE |
| D-007 | D2 | BLE protocol and press semantics | ADR-011; device §9 | 型号、GATT、payload、bonding、电量、单/长/双击语义是什么？ | vendor protocol；software-defined semantics after capture | 先 `BLEButtonManager` + software dedupe；协议和语义 Spike 后冻结 | No; blocks FR-063 device acceptance | Android/Device owner | Batch 0 / Week 1-2 | BLE-001..014, packet capture, duplicate evidence | WAITING SPIKE |
| D-008 | D2 | CameraX presence detector | ADR-012; FR-062 | 目标设备功耗、低光误触发、持续阈值和 detector 是否可接受？ | ML Kit candidate；其他 mature lightweight detector；关闭该能力 | Camera consent 默认关闭/可选；只输出 presence state；失败不影响对话/提醒 | No; blocks presence acceptance only | Android/Privacy owner | Before E9 device feature | CAM-001..011 + privacy file/network scan | WAITING SPIKE |
| D-009 | D2 | Offline wake-word SDK | ADR-013; FR-061 | SDK/license/model footprint、断网延迟和 microphone ownership 是否满足？ | mature offline SDK；button/tap fallback | 先 `WakeWordAdapter` + Mock；失败降级按钮/点击；wake word 不作身份认证 | No; blocks offline wake acceptance only | Android/AI owner | Before E9 device feature | AUD-001..010 + offline spike | WAITING SPIKE |
| D-010 | D2 | Telephony and emergency channel | ADR-014; FR-053 | 指定平板是否有 SIM、Telecom、CALL_PHONE、可观察 call state？ | local Telecom；Push/SMS/VoIP/backend；Mock/fallback | 只有观测到才标 `CONNECTED`；无 SIM/权限则 local case + MockPush/应用内 + `FAILED/NO_ANSWER` | No; blocks local-call claim only | Android/Emergency owner | Before E8/E9 acceptance | EMG-001..012, SIM/no-SIM/permission tests | WAITING SPIKE |
| D-011 | D3 | Retention durations, backups and AuditLog | privacy §4/15/21; retention R-004..020 | AuditLog、backup、report、metric、notification、local cache 的具体期限是什么？ | course demo short retention；policy by data class；legal hold exception | 开发默认 privacy-preserving、`retention_until` 可配置；不在代码中写任意 7/30/90 天；raw audio 永不默认保存 | No for foundation; blocks production-like data and final deletion claim | Privacy/Security owner | Before demo with non-fictional data | retention config review + DEL matrix + restore evidence | OPEN / CONFIG GATE |
| D-012 | D3 | Runtime RiskRule editor | DB §4/28; AI/Scam policy | 比赛现场是否需要在线编辑诈骗规则？ | Versioned YAML/JSON in Git；new RiskRule table/admin UI | 12 周使用版本化 config；`rule_id/version` 写入 event；不新增表 | No; blocks rule-admin feature only | Safety owner | Before E5 scope lock | rule fixture + release review | CLOSED BY DEFAULT |
| D-013 | D3 | Similarity, signal and dedupe thresholds | AI §15/19; Scam §8; retention | topic similarity、signal threshold、dedup window 如何校准？ | fixed initial values；evaluation-calibrated config；per-device | 作为 config；先用 conservative dev values；以 labelled evaluation 调整，不改变 enum/contract | No; blocks calibration, not foundation | AI/Safety owner | Before E5/E7 tuning | AI evaluation + regression report | OPEN / CONFIG |
| D-014 | D1 | Medication authorship and confirmation | Requirements §13; UI F-010; DB Reminder | 医嘱由谁录入、谁核对？系统能否标记医生确认？ | Family only；elder + family；external clinician integration | 仅授权 CHILD/CAREGIVER 录入；二次确认；系统不声称医生确认、不自动改剂量 | No; blocks medication feature policy only | Product + Safety owner | Before E3 Reminder | permission matrix + reminder acceptance | OPEN / DEFAULT PROPOSED |
| D-015 | D1 | Demo data and external-network policy | Requirements §13/12-week; DB seed; UI Demo | 演示是否允许真实家庭数据、短信/电话/外网？ | real data；fictional seed + Mock; mixed | 全部 fictional seed；Mock/Real provider 显著标记；不提交真实 secret/phone/photo | No; blocks release/demo sign-off only | Demo lead + Security | Batch 0 | PRIV-003/008, seed smoke, artifact scan | OPEN / DEV DEFAULT |
| D-016 | D1 | Device proof and re-binding | Privacy §21 change proposal; threat T-004/T-020 | `/devices/register` 如何证明设备，丢失设备如何解绑/重绑？ | signed device attestation；one-time pairing code；admin-only reset | Batch 0 使用 device proof interface + one-time demo pairing；实现前冻结 lost/unbind and session wipe | No; blocks production device trust, not skeleton | Auth + Device owner | Before E9 | AUTH-012/017, DEV-001/007 | OPEN / INTERFACE FIRST |
| D-017 | D1 | WSS audio location and message policy | API §20/34; privacy §11 | 音频由本地 ASR 还是服务端 ASR？最大帧、重放、flood、token revoke 如何处理？ | local ASR + text/state WSS；server ASR + bounded chunks | Batch 0 text/state + Mock WSS；默认 local/ephemeral audio；实现前冻结 limits/re-auth | No; blocks voice provider integration only | Conversation + Security owner | Before E4 voice implementation | WS-001..009, audio ownership tests | OPEN / MOCK SAFE |

## Classification Summary

| Class | Count | Immediate action |
| --- | ---: | --- |
| D0 | 0 | None |
| D1 | 8 | Define defaults before the related feature; foundation may proceed |
| D2 | 6 | Run hardware/provider Spike in parallel |
| D3 | 3 | Use configuration and Mock defaults; calibrate later |

## Decision Handling Rules

1. Coding Agent 不得在代码中静默选择上述未决项；使用表中 Recommended Default，并在任务中引用 Decision ID。
2. 影响 API、DB、Consent/security boundary、跨模块行为的选择必须转为 ADR/Review；纯阈值、文案、布局和重试上限是 Implementation Decision。
3. 未完成 D2 的 Feature 只能实现 adapter、Mock、状态和 fallback，不得把 emulator 结果写成真机支持。
4. 未完成 D3 不得阻止 Batch 0；但所有 demo/test 配置必须标注来源、版本和可替换性。
