# 念念 Scam and Signal Policy

| 项目 | 内容 |
| --- | --- |
| 状态 | Baseline / v1.0 |
| 目的 | 定义 SignalCandidate、诈骗规则、敏感事件策略、通知和解释边界 |
| 持久化约束 | 使用现有 `signal_event` 枚举与字段；12 周版本不增加 RiskRule 表 |
| 规则来源 | 版本化 YAML/JSON 配置包，发布版本写入 `rule_id`/`rule_version` |

## 1. Signal Types

数据库稳定类型只有：

`PHYSICAL_DISCOMFORT`, `EMOTION_EXPRESSION`, `IMPORTANT_MEMORY`, `MISS_FAMILY`, `SCAM_RISK`, `EMERGENCY`。

这些是交流/安全线索，不是医疗诊断。`SignalCandidate` 是模型/规则产生的暂态候选；通过应用验证、授权和去重后才创建 `SignalEvent`。

## 2. Signal Candidate Contract

```json
{
  "type": "PHYSICAL_DISCOMFORT",
  "confidence": 0.86,
  "confidence_band": "HIGH",
  "evidence_summary": "老人主动说今天胸口不舒服",
  "trigger_category": "SELF_REPORTED_DISCOMFORT",
  "recommended_action": "CHECK_IN_AND_OFFER_CONTACT",
  "source_conversation_id": "uuid",
  "source_message_id": "uuid",
  "attributes": {}
}
```

Limits: one of six types, max three candidates per turn, evidence <=240 chars, no full transcript, no diagnosis, no raw audio. `confidence` may be recorded internally as 0..1 for evaluation, while `confidence_band` is `LOW/MEDIUM/HIGH` for policy routing. Neither is a medical or fraud probability; neither can bypass deterministic policy.

## 3. Deterministic Rules

Rules run before and after LLM semantic analysis. A rule record is reviewable and testable:

```yaml
rule_id: SCAM_TRANSFER_SECRECY
version: "1.0.0"
kind: COMBINATION
keywords: [转账, 汇款, 打钱, 验证码, 不要告诉别人, 保密]
semantic_categories: [TRANSFER, SECRECY]
combination:
  all_of: [TRANSFER, SECRECY]
severity: L2
action: PAUSE_AND_VERIFY_WITH_FAMILY
message_template: scam.transfer_secrecy
dedup_window: 30m
```

Rules may produce indicators and a recommended policy action. They do not assert that a person is a criminal. A deterministic emergency rule has priority over ordinary conversation and is evaluated even if an LLM is unavailable.

## 4. Scam Categories

| Category | Examples | Alone sufficient? |
| --- | --- | --- |
| `TRANSFER` | 转账、汇款、打钱、银行卡转入 | usually no |
| `VERIFICATION_CODE` | 验证码、短信码、动态码 | no; block sharing if an action is requested |
| `IMPERSONATION` | 冒充孩子、客服、警察、熟人 | no |
| `SECRECY` | 不要告诉家人、保密、别让别人知道 | no |
| `UNKNOWN_LINK` | 陌生链接、点击网址、扫码 | no |
| `BANK_ACCOUNT` | 卡号、账户、开户、收款账号 | no |
| `CREDENTIAL` | 密码、登录口令、身份证号 | no |
| `URGENT_PAYMENT` | 马上、立刻、现在付款、逾期威胁 | no |

Semantic analysis can add categories such as `IMPERSONATION` or `SECRECY`; it can never directly set `SCAM_RISK` as a final event.

## 5. Rule Combination and Risk Levels

The engine uses explainable combination rules, not medical-style probabilities:

| Combination | Category | Severity | Policy |
| --- | --- | --- | --- |
| `TRANSFER + SECRECY` | `TRANSFER_AND_SECRECY` | L2 | pause sensitive action, family verification |
| `IMPERSONATION + URGENT_PAYMENT` | `IMPERSONATION_URGENT_PAYMENT` | L2 | pause, family notification if authorized |
| `VERIFICATION_CODE + CREDENTIAL` | `CREDENTIAL_REQUEST` | L2 | never relay code/credential; offer family contact |
| `VERIFICATION_CODE + SECRECY` | `VERIFICATION_CODE_AND_SECRECY` | L2 | W6-03 / SCAM_CODE_SECRECY v1.1.0; never relay code; verify with family |
| `UNKNOWN_LINK + URGENT_PAYMENT` | `UNKNOWN_LINK_PAYMENT` | L2 | do not open/click; verify with family |
| `TRANSFER + BANK_ACCOUNT + URGENT_PAYMENT` | `URGENT_TRANSFER_REQUEST` | L3 | pause, high-priority notification if consented |
| one low-specificity indicator | `SINGLE_INDICATOR` | L0/L1 | explain and ask a clarifying question; no family push by default |

`“我今天去银行给自己的账户转钱”` is not automatically scam: the engine asks context and does not notify solely on `TRANSFER`. A high-severity event still never claims certainty about the other party.

## 6. LLM Semantic Analysis

The `scam_semantic` prompt receives a redacted current utterance and returns only:

```json
{
  "semantic_indicators": ["IMPERSONATION", "SECRECY"],
  "requested_action": "SHARE_CODE",
  "evidence_summary": "疑似冒充亲属并要求保密",
  "needs_clarification": false
}
```

It must not return a verdict, notification command, severity, contact success or policy override. Invalid/timeout output contributes no semantic indicator; deterministic rules continue.

## 7. Severity

The database uses `L0` informational, `L1` attention, `L2` high attention, `L3` urgent and `L4` policy-reserved critical. Severity is based on rule combinations, action blocked and emergency policy, not on a disease or fraud probability. UI translates it to plain copy and never exposes `L*` or confidence numbers.

## 8. Deduplication

Configuration key `signal_dedup_window` is versioned and tunable. Initial recommendations: same elder + same family + same type + same trigger category within 30 minutes maps to one active event; emergency button presses use a shorter 5-minute idempotency window but each actual contact attempt remains auditable. The dedupe key is a stable hash of family, owner, type, category and window bucket.

Duplicates reference `duplicate_of_id` and never delete the original. A changed category or a new policy-relevant severity creates a new event. Notification dedupe is separate from event dedupe.

## 9. Consent

Before family notification, the policy checks active membership, event owner, relevant scope (`NOTIFICATION_TO_FAMILY`; `HEALTH_MEDICATION` for health-related signal), same family and current Consent. A denial creates a `WITHHELD` event or local-only safety response; it does not imply consent. Consent revocation takes effect immediately for retrieval and notification decisions.

Emergency local contact may remain available to the elder under the existing emergency policy, but family event details still follow authorization and are audited.

## 10. Notification Policy

```text
SignalEvent -> consent -> quiet hours / recipient -> dedupe -> Notification -> provider attempts
```

| Event | Default | Quiet hours | Fallback |
| --- | --- | --- | --- |
| `EMOTION_EXPRESSION` | in-app aggregate, no push per utterance | respect quiet hours | weekly metric |
| `MISS_FAMILY` | in-app suggestion; push only if user opted in or repeated threshold met | respect quiet hours | elder can call family |
| `IMPORTANT_MEMORY` | pending family review/in-app | respect quiet hours | no notification if scope absent |
| `PHYSICAL_DISCOMFORT` | authorized family in-app/push based on policy | high severity may override; never diagnose | offer contact/urgent path |
| `SCAM_RISK` L2/L3 | warning immediately; family notification when consented | L2 follows quiet hours; L3 policy may escalate | local warning and contact option |
| `EMERGENCY` | emergency flow and configured contact | emergency override | show actual failure reason |

SignalEvent truth and provider delivery status are separate. `FAILED` or `NO_ANSWER` never becomes `CONNECTED` by inference.

## 11. Explainability

Every validated event records `rule_id`, `rule_version`, `policy_version`, category, minimal `evidence_summary`, source conversation/message references, consent result, dedupe result and outcome. User-facing explanation is human language, for example: “这段交流中出现了转账和要求保密的信息，建议先联系家人核实。” No raw transcript, chain of thought, provider metadata or family internal note is shown.

## 12. False Positive Handling

Family can mark an event `FALSE_POSITIVE` with a short reason. The system keeps the event and audit record, suppresses duplicate notifications for the configured period and includes the labelled case in evaluation. False-positive feedback does not silently weaken a safety rule; rule changes require a new version and regression run.

## 13. Emergency Policy

Deterministic high-priority triggers include `救命`, `帮我叫人`, `我要联系急救` and a BLE emergency button event. The engine enters `WARNING`/emergency contact flow even if LLM or TTS is down. A short ambiguous phrase asks for confirmation where safe; explicit trigger does not wait for a model verdict. The application reports `INITIATED`, `CONNECTING`, `CONNECTED`, `NO_ANSWER`, `FAILED` or `CANCELLED` exactly as observed.

## 14. Physical Discomfort Policy

Accept direct self-reports such as “胸口不舒服”“头晕”“疼”. The event says “老人提到身体不舒服”, offers family/emergency contact and uses `HEALTH_MEDICATION`/notification consent as required. It must not say heart disease, severity diagnosis, medication change or predicted outcome. A request for medical advice receives a disclaimer and contact guidance.

## 15. Emotion Expression Policy

Allowed labels are expressive categories such as `SAD_EXPRESSION`, `LONELY_EXPRESSION`, `HAPPY_EXPRESSION` and `WORRIED_EXPRESSION`. They describe this conversation only and feed aggregate “交流观察线索”. Forbidden labels include depression, anxiety disorder, mental illness, cognitive decline and sleep diagnosis. A single ordinary sad word is not automatically a family push.

## 16. Miss Family Policy

Create `MISS_FAMILY` when the elder expresses missing a family member, asks to contact them, says it has been a long time, or explicitly wants a conversation. Merely mentioning a child, asking a factual question or discussing a family event is insufficient. Recommended action is a real call/video suggestion, never a fabricated message from the family member.

## 17. Important Memory Policy

Use `IMPORTANT_MEMORY` for a potentially useful family story, life experience, important person, photo background, preference or taboo. It may accompany a `MemoryCandidate`, but the two objects remain separate. The candidate is `PENDING` until family confirmation; the SignalEvent can be acknowledged independently.

## 18. Rule Versioning

Rules are reviewed YAML/JSON in source control. Each release has `rule_id`, semantic version, change note, test cases and deployment commit. `SignalEvent.rule_id/rule_version` is immutable. There is no runtime rule editor or RiskRule table in the 12-week scope.

## 19. Test Cases

| ID | Input | Expected | Must not |
| --- | --- | --- | --- |
| SC-001 | “有人让我把验证码告诉他，还说别告诉孩子。” | `SCAM_RISK`, `VERIFICATION_CODE+SECRECY`, block sharing | claim certain criminality |
| SC-002 | “我今天给自己的另一个账户转钱。” | no scam event; clarify if needed | notify solely on TRANSFER |
| SC-003 | “你是我儿子吗？马上给我转钱。” | impersonation/urgent payment, L2/L3 policy | impersonate son |
| SC-004 | “验证码是什么东西？” | no event, general explanation | notify family |
| SC-005 | “点这个陌生链接就能领奖，马上付款。” | unknown-link-payment, block click/payment | open link |
| SC-006 | “我想女儿了。” | `MISS_FAMILY`, suggest contact | diagnose loneliness |
| SC-007 | “我年轻时在杭州工作。” | `IMPORTANT_MEMORY` optional + `MemoryCandidate(PENDING)` | auto-confirm Memory |
| SC-008 | “我胸口有点不舒服。” | `PHYSICAL_DISCOMFORT`, offer contact | diagnose heart disease |
| SC-009 | “救命，帮我叫人。” | deterministic emergency flow | wait only for LLM |
| SC-010 | repeated same safe utterance | one event in dedup window | send ten pushes |

## 20. API / Database Proposals

API Change Proposals: **None.** Existing warning/signal/event/contact endpoints express the policy.

Database Change Proposals: **None.** Rule bodies remain versioned config; existing `signal_event` fields store the audit-relevant result.


## Week 6 approved implementation (W6-01..04, 2026-10-18)

Approval: [W6-01..04](plan/week6-contract-review.md), project owner replied “是” in this chat.
This section supersedes earlier Week 3/4 “summary unavailable” implementation notes for the reviewed Mock path only.

- Conversation adds summary_version > 0; outbox permits CONVERSATION_SUMMARY and CONVERSATION_SUMMARY_CLEANUP.
  Store curated Mock themes only, at most 1000 characters; PENDING is unreadable. First input starts a non-renewable
  maximum 24h lifetime, shortened by known self-grant expiry. No transcript/audio/summary export or local disk cache.
- Explicit self CONVERSATION_SUMMARY grant enables generation; named family grant enables authorized reads separately.
  Every read requires current family/member/role/SUMMARY_READ/grantee/scope/resource checks. Self revoke hides and
  schedules cleanup; revoking one reader does not revoke other readers. Summary grants never enable notifications.
- GET conversation and POST summary require X-Access-Reason FAMILY_CHECK_IN/FOLLOW_UP for non-owners (422 when
  absent/invalid after access check), persisted as AuditLog.reason without content. Responses use no-store.
  The known-id view exposes no history list, transcript or discovery API. Failure/empty/expired never falls back to raw input.
- Four proactive operations: GET/PUT /families/{family_id}/proactive-preferences/{owner_user_id}, POST same path
  /confirm and /pause-today. PUT requires If-Match; POST commands require Idempotency-Key. CHILD/CAREGIVER with
  REMINDER_WRITE proposes; only ELDER owner confirms current version or pauses. GET needs owner/REMINDER_READ.
  Default disabled, cap 0..3, IANA timezone, local minute times, paired quiet hours. No new permission codes.
- ProactivePreference and ProactiveDailyCounter are the approved tables. Counter reservation is transactional and
  survives failure/restart; retains no text, expires after 48h. Timezone changes carry recent usage and today's pause.
  Worker sends only transient id/version/time hints through PostgreSQL NOTIFY to a currently connected owner WSS;
  API rechecks current authorization/settings before a fixed Mock invitation. No offline/background wake or push.
  Reconnect does not replay notifications. Failed/lost invitation can consume a slot and is never labelled delivered.
  Necessary reminders and emergency access are independent of proactive pause. No new WSS message type/state.
- Full candidate category/action vocabulary and SCAM_CODE_SECRECY are frozen in W6-03. Six types remain temporary
  Mock candidates, not facts/events/notifications. Deterministic emergency/scam copy survives LLM/TTS failure.
  SignalEvent persistence and notification delivery remain Week 7. Real voice/provider gates remain unapproved.


## Week 7 approved contract — 2026-10-19

[W7-01..04](plan/week7-contract-review.md) 已由项目负责人在本聊天回复“是”批准。

W7-03 消除 §8/§9 歧义：去重 hash 加入 severity，不同类别/严重度新事件，同桶重复只返回原有事实、不追加通知且不续期。SCAM 不需要健康 scope，不适需要健康 scope。无授权走本地警告路径，不持久化敏感 WITHHELD 证据。已批准触发类别落库；仅来源会话引用，Mock 来源消息 ID 为 null。所有非紧急通知（含 L3）遵守免打扰；情绪/思念/待核实记忆仅应用内。本轮 EMERGENCY 只保留本地提示，第八周处理。
