"""Deterministic, explicitly simulated adapters for offline development."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from app.integrations.contracts import (
    ASRRequest, ASRResult, AvatarState, AvatarStateRequest, EmbeddingRequest,
    EmbeddingResult, LLMRequest, LLMResponse, ProviderCapabilities, ProviderError,
    ProviderStatus, PushRequest, PushResult, TTSRequest, TTSResult,
    WakeWordDetected, WeatherRequest, WeatherResult,
)

MOCK_VERSION = "1.0.0"


def _capabilities(model: str, **overrides: Any) -> ProviderCapabilities:
    return ProviderCapabilities(
        provider="mock", model=model, version=MOCK_VERSION,
        languages=("zh-CN",), offline=True, **overrides,
    )


class MockASR:
    def capabilities(self) -> ProviderCapabilities:
        return _capabilities("mock-asr-v1", audio_input=True)

    async def transcribe(self, request: ASRRequest) -> ASRResult:
        # No audio is decoded or retained; callers can exercise the text path.
        has_audio = bool(request.audio)
        return ASRResult(
            transcript="模拟语音输入" if has_audio else "",
            confidence=1.0 if has_audio else 0.0,
            confidence_band="HIGH" if has_audio else "LOW",
            language=request.language_hint,
            is_final=request.is_final,
            provider="mock", model="mock-asr-v1",
        )


_DEFAULT_LLM_OUTPUT: dict[str, dict[str, Any]] = {
    "conversation": {
        "reply": "这是模拟回复。没有可核实的家庭信息时，请向家人确认。",
        "memory_refs": [], "intent": "GENERAL_CHAT", "needs_clarification": False,
        "memory_candidates": [], "signal_candidates": [],
        "blocked_action": None, "uncertainty_reason": None,
    },
    "memory_extraction": {"reply": "", "memory_candidates": []},
    "signal_extraction": {"reply": "", "signal_candidates": []},
    "summary": {"summary": ""},
    "weekly_narrative": {"narrative": ""},
    "scam_semantic": {"reply": "", "signal_candidates": []},
}


def _schema_matches(value: Any, schema: dict[str, Any]) -> bool:
    """Check the simple object schema subset used by mock fixtures.

    The orchestrator remains responsible for complete task schema and policy
    validation before it can use any model output.
    """
    expected = schema.get("type")
    if expected == "object" and not isinstance(value, dict):
        return False
    if expected == "array" and not isinstance(value, list):
        return False
    if expected == "string" and not isinstance(value, str):
        return False
    if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        return False
    if expected == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        return False
    if expected == "boolean" and not isinstance(value, bool):
        return False
    if expected == "null" and value is not None:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if isinstance(value, str) and len(value) > schema.get("maxLength", float("inf")):
        return False
    if isinstance(value, list):
        if len(value) > schema.get("maxItems", float("inf")):
            return False
        item_schema = schema.get("items")
        if isinstance(item_schema, dict) and any(not _schema_matches(item, item_schema) for item in value):
            return False
    if isinstance(value, dict):
        if any(key not in value for key in schema.get("required", [])):
            return False
        properties = schema.get("properties", {})
        if any(key in properties and not _schema_matches(item, properties[key]) for key, item in value.items()):
            return False
        if schema.get("additionalProperties") is False and any(key not in properties for key in value):
            return False
    return True


class MockLLM:
    def __init__(self, *, output_by_task: dict[str, dict[str, Any]] | None = None) -> None:
        self._output_by_task = deepcopy(output_by_task if output_by_task is not None else _DEFAULT_LLM_OUTPUT)

    def capabilities(self) -> ProviderCapabilities:
        return _capabilities("mock-conversation-v1", structured_output=True, max_context_tokens=8192)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        output = self._output_by_task.get(request.task)
        if output is None or not _schema_matches(output, request.output_schema):
            raise ProviderError(
                code="INVALID_OUTPUT", provider="mock", operation="generate",
                retryable=False, safe_to_retry=False, attempt=1,
                user_message_key="ai.temporarily_unavailable",
                detail_redacted="mock output does not match requested schema",
            )
        return LLMResponse(
            status=ProviderStatus.SUCCEEDED,
            structured_output=deepcopy(output), raw_text_for_fallback=None,
            provider="mock", model="mock-conversation-v1",
            prompt_id=request.prompt_id, prompt_version=request.prompt_version,
            latency_ms=0, input_tokens=None, output_tokens=None,
        )


class MockEmbedding:
    DIMENSION = 8

    def capabilities(self) -> ProviderCapabilities:
        return _capabilities("mock-embedding-v1", embedding=True)

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        vectors = []
        for value in request.texts:
            digest = hashlib.sha256(value.encode("utf-8")).digest()
            vectors.append([
                (int.from_bytes(digest[index:index + 4], "big") / 0xFFFFFFFF) * 2 - 1
                for index in range(0, self.DIMENSION * 4, 4)
            ])
        return EmbeddingResult(
            vectors=vectors, dimension=self.DIMENSION, provider="mock",
            model="mock-embedding-v1", model_version=MOCK_VERSION,
        )


class MockTTS:
    def capabilities(self) -> ProviderCapabilities:
        return _capabilities("mock-tts-v1", audio_output=False)

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        # A text-only fallback avoids presenting generated silence as speech.
        return TTSResult(
            audio=None, duration_ms=None, provider="mock", model="mock-tts-v1",
            supports_emotion_hint=False,
        )


class MockAvatar:
    def __init__(self) -> None:
        self.state = AvatarState.IDLE

    def capabilities(self) -> ProviderCapabilities:
        return _capabilities("mock-avatar-v1")

    async def set_state(self, request: AvatarStateRequest) -> None:
        self.state = request.state


class MockWakeWord:
    def __init__(self, detection: WakeWordDetected | None = None) -> None:
        self._detection = detection

    def capabilities(self) -> ProviderCapabilities:
        return _capabilities("mock-wakeword-v1")

    async def listen(self) -> WakeWordDetected | None:
        # No synthetic wake event is emitted unless a test supplies one.
        return self._detection


class MockPush:
    def capabilities(self) -> ProviderCapabilities:
        return _capabilities("mock-push-v1")

    async def send(self, request: PushRequest) -> PushResult:
        return PushResult(provider="mock", simulated=True, delivery_observed=False)


class MockWeather:
    def capabilities(self) -> ProviderCapabilities:
        return _capabilities("mock-weather-v1")

    async def current(self, request: WeatherRequest) -> WeatherResult:
        # No live observation exists. UI can show an explicit unavailable state.
        return WeatherResult(provider="mock", available=False, simulated=True)
