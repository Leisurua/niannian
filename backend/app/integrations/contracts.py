"""Provider-neutral adapter DTOs and protocols (AI Contracts v1.0)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdapterDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProviderStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"


class ProviderCapabilities(AdapterDTO):
    provider: str
    model: str | None = None
    version: str
    streaming: bool = False
    structured_output: bool = False
    function_calling: bool = False
    audio_input: bool = False
    audio_output: bool = False
    embedding: bool = False
    languages: tuple[str, ...] = ()
    max_context_tokens: int | None = None
    supports_emotion_hint: bool = False
    offline: bool = False


class ProviderError(Exception):
    """A redacted provider failure; never include request content in detail."""

    def __init__(
        self,
        *,
        code: str,
        provider: str,
        operation: str,
        retryable: bool,
        safe_to_retry: bool,
        attempt: int,
        user_message_key: str,
        detail_redacted: str | None = None,
    ) -> None:
        self.code = code
        self.provider = provider
        self.operation = operation
        self.retryable = retryable
        self.safe_to_retry = safe_to_retry
        self.attempt = attempt
        self.user_message_key = user_message_key
        self.detail_redacted = detail_redacted
        super().__init__(f"{provider}:{operation}:{code}")


class ASRRequest(AdapterDTO):
    request_id: str = Field(min_length=1)
    audio: bytes | None = Field(default=None, max_length=1_048_576)
    language_hint: str = "zh-CN"
    is_final: bool = False


class ASRResult(AdapterDTO):
    transcript: str = Field(max_length=2_000)
    confidence: float = Field(ge=0, le=1)
    confidence_band: str
    language: str
    is_final: bool
    provider: str
    model: str | None

    @field_validator("confidence_band")
    @classmethod
    def validate_band(cls, value: str) -> str:
        if value not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValueError("invalid confidence band")
        return value


class LLMRequest(AdapterDTO):
    request_id: str = Field(min_length=1)
    task: str
    system_policy: str
    conversation_context: dict[str, Any]
    authorized_memory: list[dict[str, Any]]
    user_input: str
    intent: str | None = None
    safety_context: dict[str, Any]
    output_schema: dict[str, Any]
    locale: str = "zh-CN"
    prompt_id: str
    prompt_version: str

    @field_validator("task")
    @classmethod
    def validate_task(cls, value: str) -> str:
        if value not in {
            "conversation", "memory_extraction", "signal_extraction",
            "summary", "weekly_narrative", "scam_semantic",
        }:
            raise ValueError("unsupported LLM task")
        return value


class LLMResponse(AdapterDTO):
    status: ProviderStatus
    structured_output: dict[str, Any] | None
    raw_text_for_fallback: str | None
    provider: str
    model: str
    prompt_id: str
    prompt_version: str
    latency_ms: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class EmbeddingRequest(AdapterDTO):
    request_id: str = Field(min_length=1)
    texts: list[str] = Field(max_length=64)
    language: str = "zh-CN"

    @field_validator("texts")
    @classmethod
    def validate_texts(cls, value: list[str]) -> list[str]:
        if any(len(text) > 4_000 for text in value):
            raise ValueError("embedding text exceeds 4000 characters")
        return value


class EmbeddingResult(AdapterDTO):
    vectors: list[list[float]]
    dimension: int = Field(gt=0)
    provider: str
    model: str
    model_version: str


class TTSRequest(AdapterDTO):
    request_id: str = Field(min_length=1)
    text: str = Field(max_length=2_000)
    locale: str = "zh-CN"
    voice: str | None = None
    speed: float = Field(default=1.0, gt=0)
    volume: float = Field(default=1.0, ge=0)
    emotion_hint: str | None = None


class TTSResult(AdapterDTO):
    audio: bytes | None
    duration_ms: int | None = Field(default=None, ge=0)
    provider: str
    model: str | None
    supports_emotion_hint: bool


class AvatarState(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    WARNING = "WARNING"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class AvatarStateRequest(AdapterDTO):
    request_id: str = Field(min_length=1)
    state: AvatarState
    expression_hint: str | None = None
    mouth_amplitude: float | None = Field(default=None, ge=0, le=1)
    duration_ms: int | None = Field(default=None, ge=0)


class WakeWordDetected(AdapterDTO):
    request_id: str
    timestamp: datetime
    confidence: float = Field(ge=0, le=1)
    source: str

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        if value not in {"LOCAL_SDK", "BUTTON", "SYSTEM"}:
            raise ValueError("invalid wake-word source")
        return value


class PushRequest(AdapterDTO):
    request_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    summary_key: str = Field(min_length=1, max_length=120)


class PushResult(AdapterDTO):
    provider: str
    simulated: bool
    delivery_observed: bool


class WeatherRequest(AdapterDTO):
    request_id: str = Field(min_length=1)
    location_key: str = Field(min_length=1, max_length=120)


class WeatherResult(AdapterDTO):
    provider: str
    available: bool
    observed_at: datetime | None = None
    condition: str | None = None
    temperature_c: float | None = None
    simulated: bool


class ASRAdapter(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    async def transcribe(self, request: ASRRequest) -> ASRResult: ...


class LLMAdapter(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    async def generate(self, request: LLMRequest) -> LLMResponse: ...


class EmbeddingAdapter(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...


class TTSAdapter(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    async def synthesize(self, request: TTSRequest) -> TTSResult: ...


class AvatarAdapter(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    async def set_state(self, request: AvatarStateRequest) -> None: ...


class WakeWordAdapter(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    async def listen(self) -> WakeWordDetected | None: ...


class PushProvider(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    async def send(self, request: PushRequest) -> PushResult: ...


class WeatherAdapter(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    async def current(self, request: WeatherRequest) -> WeatherResult: ...
