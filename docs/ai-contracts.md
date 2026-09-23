# 念念 AI Contracts

| 项目 | 内容 |
| --- | --- |
| 状态 | Baseline / v1.0 |
| 范围 | AI adapter、编排输入输出、候选对象与 provider-neutral contract |
| 依赖 | `docs/system-design.md`、`docs/database-design.md`、`docs/data-dictionary.md`、`docs/api-spec.md`、`docs/api-permission-matrix.md`、ADR-005 |
| 明确不包含 | 真实 provider SDK、数据库 ORM、业务 Controller、生产 Prompt 内容 |

本文是后续 Python 3.12 / Pydantic v2 实现的接口基线。示例使用 JSON Schema 风格和 Python Protocol 伪代码；字段名、枚举和边界优先于具体库语法。公共 API DTO 与内部 AI DTO 分离，不能把 ORM、token、embedding 或原始对话直接传给模型。

## 1. Contract Rules

1. `LLM proposes. Application decides.` LLM 只能生成回答和候选对象，授权、事实、通知、紧急联系和敏感动作由应用策略决定。
2. 所有请求带 `request_id`；会话内调用另外带 `conversation_id`。provider、model、prompt_id、prompt_version、latency 和结果状态进入脱敏结构化日志。
3. 所有字符串、数组和对象都有上限；解析失败按失败契约处理，禁止把原始文本当作已验证结果。
4. `family_id`、`elder_id`、consent 和删除状态由服务端上下文派生，不能由模型或客户端覆盖。
5. `confidence` 是候选分类信号，不是医疗概率，也不能独立触发通知或紧急动作。

## 2. Shared Types

```python
from datetime import datetime
from enum import StrEnum
from typing import Mapping, Protocol, Sequence
from uuid import UUID

class InputMode(StrEnum):
    VOICE = "VOICE"
    TEXT = "TEXT"

class SignalType(StrEnum):
    PHYSICAL_DISCOMFORT = "PHYSICAL_DISCOMFORT"
    EMOTION_EXPRESSION = "EMOTION_EXPRESSION"
    IMPORTANT_MEMORY = "IMPORTANT_MEMORY"
    MISS_FAMILY = "MISS_FAMILY"
    SCAM_RISK = "SCAM_RISK"
    EMERGENCY = "EMERGENCY"

class MemoryType(StrEnum):
    PERSON = "PERSON"
    RELATIONSHIP = "RELATIONSHIP"
    EVENT = "EVENT"
    PLACE = "PLACE"
    PREFERENCE = "PREFERENCE"
    TABOO = "TABOO"
    PHOTO = "PHOTO"

class MemoryVerification(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    DELETED = "DELETED"

class SignalSeverity(StrEnum):
    L0 = "L0"  # informational
    L1 = "L1"  # attention
    L2 = "L2"  # high attention
    L3 = "L3"  # urgent
    L4 = "L4"  # reserved for policy-defined critical emergency

class ProviderStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
```

`SignalSeverity` intentionally follows `signal_event.severity` (`L0`-`L4`) in the database. User-facing copy uses plain language and never displays the enum or a probability.

## 3. ProviderCapabilities

```json
{
  "provider": "mock",
  "model": "mock-conversation-v1",
  "version": "2026-09-22",
  "streaming": false,
  "structured_output": true,
  "function_calling": false,
  "audio_input": false,
  "audio_output": false,
  "embedding": false,
  "languages": ["zh-CN"],
  "max_context_tokens": 8192,
  "supports_emotion_hint": false,
  "offline": true
}
```

Unknown capabilities are `false` or `null`, never inferred. The orchestrator selects a provider only when the required capability is true and the configured data policy permits the call.

## 4. Common Errors, Timeouts and Fallback

```json
{
  "code": "TIMEOUT",
  "provider": "mock",
  "operation": "generate",
  "retryable": true,
  "safe_to_retry": true,
  "attempt": 1,
  "user_message_key": "ai.temporarily_unavailable",
  "detail_redacted": "provider deadline exceeded"
}
```

`ProviderError` fields are `code`, `provider`, `operation`, `retryable`, `safe_to_retry`, `attempt`, `user_message_key` and optional redacted detail. Never include prompt, API key, raw transcript or provider response.

| Operation | Recommended initial timeout (tunable) | Retry | Safe fallback |
| --- | ---: | --- | --- |
| ASR final | 4 s | one retry only before a user re-prompt; low-confidence result is not retried as a high-risk action | ask the elder to repeat or use text/button |
| LLM response | 8 s to first usable response, 20 s total | one retry only for transport/429 with idempotency key; never duplicate a completed answer | fixed honest unavailable message |
| TTS | 5 s to start, 12 s total | one retry for transport; no retry after interrupt | render text and allow repeat |
| Embedding | 10 s per batch | worker retry with bounded backoff | keep Memory `PENDING`/not RAG available |
| Avatar | 2 s state acknowledgement | no business retry | keep text/audio and use `IDLE`/`SPEAKING` simplified state |
| Wake word | device-specific, tune on target tablet | local SDK policy | button/tap entry |

These values are starting budgets for a 12-week demo, not performance claims. The total conversation budget is 20 seconds for a complete non-streaming turn; a client may show `THINKING` while the server is within this budget.

## 5. Adapter Protocols

All adapters expose `capabilities()`, accept a request DTO, return a result DTO, and raise only `ProviderError` or a typed validation error. Provider classes live under `integrations/providers`; Mock classes live under `integrations/mock`.

### 5.1 ASRAdapter

```python
class ASRRequest:
    request_id: str
    audio: bytes | None       # bounded chunk; not persisted by this contract
    language_hint: str = "zh-CN"
    is_final: bool = False

class ASRResult:
    transcript: str           # max 2,000 chars, redacted before logs
    confidence: float         # 0..1; internal only
    confidence_band: str      # LOW | MEDIUM | HIGH for WSS/UI
    language: str
    is_final: bool
    provider: str
    model: str | None

class ASRAdapter(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    async def transcribe(self, request: ASRRequest) -> ASRResult: ...
```

If `confidence_band=LOW`, ordinary intent/signal processing waits for a repeat. Explicit emergency words from deterministic rules may enter the emergency confirmation path, but an unclear utterance never alone sends a family notification.

### 5.2 LLMAdapter

```python
class LLMRequest:
    request_id: str
    task: str  # conversation, memory_extraction, signal_extraction, summary,
              # weekly_narrative, scam_semantic
    system_policy: str       # versioned policy reference/content, not ORM
    conversation_context: dict
    authorized_memory: list[dict]
    user_input: str
    intent: str | None
    safety_context: dict
    output_schema: dict
    locale: str = "zh-CN"
    prompt_id: str
    prompt_version: str

class LLMResponse:
    status: ProviderStatus
    structured_output: dict | None
    raw_text_for_fallback: str | None  # never used for sensitive actions
    provider: str
    model: str
    prompt_id: str
    prompt_version: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
```

`raw_text_for_fallback` can be used only after plain-language safety validation for a non-factual conversational fallback. It can never create a Memory, SignalEvent, notification, phone call or authorization decision.

### 5.3 EmbeddingAdapter

```python
class EmbeddingRequest:
    request_id: str
    texts: list[str]       # max 64 items; each max 4,000 chars
    language: str = "zh-CN"

class EmbeddingResult:
    vectors: list[list[float]]
    dimension: int
    provider: str
    model: str
    model_version: str
```

Embedding is called only after a Memory is `CONFIRMED` and authorized for indexing. Failed or stale embeddings do not make a Memory retrievable.

### 5.4 TTSAdapter

```python
class TTSRequest:
    request_id: str
    text: str               # max 2,000 chars; already safety-validated
    locale: str = "zh-CN"
    voice: str | None = None
    speed: float = 1.0      # provider bounded; client may request slower/louder
    volume: float = 1.0
    emotion_hint: str | None = None

class TTSResult:
    audio: bytes | None
    duration_ms: int | None
    provider: str
    model: str | None
    supports_emotion_hint: bool
```

Unsupported `emotion_hint` is ignored and logged as a capability mismatch; it is not an error.

### 5.5 AvatarAdapter

```python
class AvatarState(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    WARNING = "WARNING"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"

class AvatarStateRequest:
    request_id: str
    state: AvatarState
    expression_hint: str | None = None
    mouth_amplitude: float | None = None  # 0..1, optional
    duration_ms: int | None = None

class AvatarAdapter(Protocol):
    async def set_state(self, request: AvatarStateRequest) -> None: ...
```

The adapter does not receive conversation text, Memory, provider prompts or Live2D-specific parameters. The client maps the existing UI states to provider details.

### 5.6 WakeWordAdapter

```python
class WakeWordDetected:
    request_id: str
    timestamp: datetime
    confidence: float
    source: str  # LOCAL_SDK | BUTTON | SYSTEM

class WakeWordAdapter(Protocol):
    async def listen(self) -> WakeWordDetected | None: ...
```

Wake word detection is not identity verification or biometric authentication. Any speaker may wake the device; authorization is checked when accessing a resource or starting a protected action.

## 6. ConversationContext

```json
{
  "conversation_id": "uuid",
  "elder_id": "uuid",
  "family_id": "uuid",
  "locale": "zh-CN",
  "session_state": "LISTENING",
  "recent_turns": [
    {"role":"USER","text":"...","age_seconds":12}
  ],
  "summary": "可选的受控会话摘要",
  "authorized_memory": [],
  "reminder_context": {"due": [], "recent_feedback": []},
  "safety_context": {"deterministic_flags": [], "quiet_hours": false},
  "input_mode": "VOICE",
  "created_at": "2026-09-22T06:00:00Z"
}
```

The context builder uses a bounded recent window (recommended 8 turns / 4,000 characters, tunable), one bounded summary (recommended 1,000 characters) and separately retrieved Memory. It drops expired, revoked, deleted, cross-family and unauthorized content before building the request. Current user statements are marked `CURRENT_UTTERANCE`, not `FAMILY_FACT`.

## 7. MemoryCandidate

```json
{
  "candidate_id": "uuid",
  "type": "EVENT",
  "subject_user_id": "uuid",
  "content": "老人说年轻时在杭州工作。",
  "suggested_title": "年轻时在杭州工作",
  "evidence_summary": "本轮对话中老人主动讲述一段工作经历",
  "source_conversation_id": "uuid",
  "source_message_id": "uuid",
  "confidence": 0.78,
  "confidence_band": "MEDIUM",
  "required_consent_scope": "FAMILY_MEMORY",
  "candidate_status": "NEW",
  "contains_health_content": false
}
```

Limits: max 5 candidates per turn; title 120 chars; content 1,000 chars; evidence 240 chars; `confidence` is optional internally but, when present, must be 0..1. It is not a medical probability and is never shown as a user-facing score. The application normalizes and deduplicates candidates, then persists them as database `memory.verification_status=PENDING`. Only an authorized human/application confirmation can create `CONFIRMED`.

`candidate_status` is an internal extraction result: `NEW`, `POSSIBLE_DUPLICATE` or `UPDATE_CANDIDATE`. It is not a database Memory status.

## 8. SignalCandidate

```json
{
  "candidate_id": "uuid",
  "type": "SCAM_RISK",
  "confidence": 0.91,
  "confidence_band": "HIGH",
  "evidence_summary": "出现转账与要求保密的表达",
  "trigger_category": "TRANSFER_AND_SECRECY",
  "recommended_action": "PAUSE_AND_VERIFY_WITH_FAMILY",
  "source_conversation_id": "uuid",
  "source_message_id": "uuid",
  "attributes": {"semantic_indicators": ["TRANSFER", "SECRECY"]}
}
```

Limits: max 3 candidates per turn; evidence 240 chars; `confidence` is optional internally and, when present, must be 0..1; category and action are enums. The value is not a fraud probability and cannot independently trigger a notification or block. LLM output is merged with deterministic rules, then validated by policy. Only the application creates a database `SignalEvent` with `rule_id`, `rule_version`, `policy_version`, consent result and dedupe key.

## 9. RetrievedMemory

```json
{
  "memory_id": "uuid",
  "type": "RELATIONSHIP",
  "content": "家人提供的信息：女儿小林住在杭州。",
  "relevance": 0.83,
  "source_type": "FAMILY_MEMORY",
  "verification": "CONFIRMED",
  "allowed_scope": "FAMILY_MEMORY",
  "family_id": "uuid"
}
```

`embedding`, internal metadata, deleted rows, pending rows and provider details are never sent to the LLM. The server verifies every `memory_ref` in a response against the current authorized retrieval set before accepting it.

## 10. LLMResponse Schema

Conversation output is the only task allowed to include a user-facing reply:

```json
{
  "reply": "根据家人提供的信息，小林住在杭州。如果你不确定，我们可以问问家人。",
  "memory_refs": ["uuid"],
  "intent": "MEMORY_QUERY",
  "needs_clarification": false,
  "memory_candidates": [],
  "signal_candidates": [],
  "blocked_action": null,
  "uncertainty_reason": null
}
```

Required fields are `reply`, `intent`, `needs_clarification`, `memory_candidates`, `signal_candidates`, `memory_refs`, `blocked_action` and `uncertainty_reason`. `reply` is 2,000 chars maximum; `memory_refs` max 5; enum values are task-specific and unknown values fail validation. For extraction tasks `reply` is empty and only the task schema is accepted.

Validation order: JSON parse -> schema/length/enum validation -> reference validation -> fact/safety policy -> application decision. A failure yields a fixed fallback and a structured error; it never executes a sensitive action.

## 11. AIOrchestrator Protocol

```python
class AIOrchestrator(Protocol):
    async def handle(self, context: ConversationContext) -> "OrchestrationResult": ...

class OrchestrationResult:
    assistant_text: str
    source_labels: list[str]        # e.g. FAMILY_MEMORY, SYSTEM_REMINDER
    avatar_state: AvatarState
    tts: TTSResult | None
    memory_candidates: list[MemoryCandidate]
    signal_candidates: list[SignalCandidate]
    blocked_action: str | None
    fallback_code: str | None
    trace: "AITraceSummary"
```

The orchestrator may call adapters, context builder, memory query, deterministic rules and policy services. It must not perform database CRUD, Push/SMS/Phone, Android UI, Consent persistence or AuditLog persistence. It emits domain commands/events to those services instead.

## 12. AITraceSummary and Logging Contract

```json
{
  "request_id": "req-...",
  "conversation_id": "uuid",
  "provider": "mock",
  "model": "mock-conversation-v1",
  "prompt_id": "conversation",
  "prompt_version": "1.0.0",
  "latency_ms": 920,
  "token_usage": {"input": 100, "output": 62},
  "result_status": "SUCCEEDED",
  "signal_candidate_count": 1,
  "memory_candidate_count": 0,
  "rule_ids": ["SCAM_TRANSFER_SECRECY"],
  "policy_version": "1.0.0",
  "fallback_code": null
}
```

This is a structured reason summary, not Chain of Thought. Raw audio, full transcript, sensitive Memory, API keys and hidden model reasoning are excluded. Cost tracking may add `audio_seconds`, `input_tokens`, `output_tokens` and `request_count` at aggregate level.

## 13. Redaction Contract

Before a third-party call, a `RedactionPolicy` removes or masks phone numbers, verification codes, account numbers, access tokens, unrelated family members and unrelated health details. Redaction is task-specific:

| Task | Family Memory allowed | Raw health detail | Phone/account/token |
| --- | --- | --- | --- |
| Conversation | only retrieved, authorized, relevant facts | only when required for a safety response | never |
| Memory extraction | no existing Memory by default | candidate text only if scope allows | never |
| Signal extraction | no Memory unless needed for classification | minimal candidate evidence | never |
| Summary | current authorized session data | minimum necessary | never |
| Weekly narrative | structured metrics and redacted event summaries | category only | never |
| Scam semantic | current utterance with redaction | no unrelated health data | mask all credentials |

Redaction produces a trace flag (`redacted_fields`) without retaining the original value in ordinary logs.
