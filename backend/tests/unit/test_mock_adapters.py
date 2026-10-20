"""Typed inputs, reproducible Mock outputs and explicit provider labels."""
import asyncio

import pytest
from app.integrations.contracts import (
    ASRRequest,
    AvatarState,
    AvatarStateRequest,
    EmbeddingRequest,
    LLMRequest,
    ProviderError,
    ProviderStatus,
    PushRequest,
    TTSRequest,
)
from app.integrations.mock import (
    MockAvatar,
    MockEmbedding,
    MockLLM,
    MockPush,
    MockTTS,
)
from pydantic import ValidationError


def run(awaitable):
    return asyncio.run(awaitable)


def conversation_request(**overrides):
    fields = {
        "request_id": "req-mock-1",
        "task": "conversation",
        "system_policy": "mock-policy-v1",
        "conversation_context": {},
        "authorized_memory": [],
        "user_input": "fixture utterance",
        "safety_context": {},
        "output_schema": {
            "type": "object",
            "required": [
                "reply", "intent", "needs_clarification", "memory_candidates",
                "signal_candidates", "memory_refs", "blocked_action",
                "uncertainty_reason",
            ],
            "properties": {
                "reply": {"type": "string", "maxLength": 2000},
                "memory_refs": {"type": "array", "maxItems": 5},
                "memory_candidates": {"type": "array", "maxItems": 5},
                "signal_candidates": {"type": "array", "maxItems": 3},
            },
        },
        "prompt_id": "conversation",
        "prompt_version": "1.0.0",
    }
    fields.update(overrides)
    return LLMRequest(**fields)


def test_all_mock_adapters_expose_explicit_capabilities():
    adapters = [
        MockLLM(), MockEmbedding(), MockTTS(), MockAvatar(), MockPush(),
    ]
    for adapter in adapters:
        capability = adapter.capabilities()
        assert capability.provider == "mock"
        assert capability.model.startswith("mock-")
        assert capability.version
        assert capability.offline is True

    assert MockLLM().capabilities().structured_output is True
    assert MockEmbedding().capabilities().embedding is True
    assert MockTTS().capabilities().audio_output is False
    assert MockAvatar().capabilities().supports_emotion_hint is False


def test_mock_llm_is_reproducible_and_never_promotes_input_to_a_family_fact():
    request = conversation_request(user_input="untrusted family assertion")
    first = run(MockLLM().generate(request))
    assert first == run(MockLLM().generate(request))
    assert first.provider == "mock"
    assert first.status is ProviderStatus.SUCCEEDED
    assert first.prompt_id == "conversation"
    assert first.prompt_version == "1.0.0"
    assert first.structured_output["memory_refs"] == []
    assert first.structured_output["memory_candidates"] == []
    assert first.structured_output["signal_candidates"] == []
    assert first.structured_output["blocked_action"] is None
    assert "untrusted family assertion" not in first.structured_output["reply"]


def test_mock_llm_rejects_output_schema_mismatch_without_leaking_input():
    request = conversation_request(
        user_input="fixture private text",
        output_schema={"type": "object", "required": ["not_produced"]},
    )
    with pytest.raises(ProviderError) as caught:
        run(MockLLM().generate(request))
    error = caught.value
    assert error.code == "INVALID_OUTPUT"
    assert error.provider == "mock"
    assert error.retryable is False
    assert "fixture private text" not in str(error)
    assert "fixture private text" not in (error.detail_redacted or "")


def test_mock_embedding_is_stable_and_respects_batch_shape():
    request = EmbeddingRequest(request_id="req-1", texts=["fixture one", "fixture two"])
    first = run(MockEmbedding().embed(request))
    assert first == run(MockEmbedding().embed(request))
    assert first.provider == "mock"
    assert first.dimension == 8
    assert len(first.vectors) == 2
    assert all(len(vector) == first.dimension for vector in first.vectors)
    assert first.vectors[0] != first.vectors[1]
    assert run(MockEmbedding().embed(EmbeddingRequest(request_id="req-2", texts=[]))).vectors == []


def test_mock_tts_and_avatar_report_honest_fallbacks():
    speech = run(MockTTS().synthesize(TTSRequest(request_id="req-1", text="模拟文本", emotion_hint="happy")))
    assert speech.provider == "mock"
    assert speech.audio is None
    assert speech.duration_ms is None
    assert speech.supports_emotion_hint is False

    avatar = MockAvatar()
    run(avatar.set_state(AvatarStateRequest(request_id="req-1", state=AvatarState.SPEAKING)))
    assert avatar.state is AvatarState.SPEAKING


def test_mock_push_never_claims_delivery():
    push = run(MockPush().send(PushRequest(
        request_id="req-1", event_id="fixture-event", summary_key="signal.attention",
    )))
    assert push.provider == "mock"
    assert push.simulated is True
    assert push.delivery_observed is False


@pytest.mark.parametrize(
    "dto,fields",
    [
        (ASRRequest, {"request_id": "req-1", "audio": b"x" * (1_048_576 + 1)}),
        (EmbeddingRequest, {"request_id": "req-1", "texts": ["x"] * 65}),
        (EmbeddingRequest, {"request_id": "req-1", "texts": ["x" * 4001]}),
        (TTSRequest, {"request_id": "req-1", "text": "x" * 2001}),
        (AvatarStateRequest, {"request_id": "req-1", "state": "UNKNOWN"}),
    ],
)
def test_request_and_result_bounds_fail_validation(dto, fields):
    with pytest.raises(ValidationError):
        dto(**fields)


def test_mock_llm_result_mutation_cannot_change_later_outputs():
    adapter = MockLLM()
    request = conversation_request()
    first = run(adapter.generate(request))
    first.structured_output["memory_refs"].append("untrusted-fixture-id")
    second = run(adapter.generate(request))
    assert second.structured_output["memory_refs"] == []


def test_mock_extraction_has_empty_reply_and_no_candidates():
    request = conversation_request(
        task="memory_extraction",
        output_schema={
            "type": "object",
            "required": ["reply", "memory_candidates"],
            "properties": {
                "reply": {"type": "string", "maxLength": 0},
                "memory_candidates": {"type": "array", "maxItems": 5},
            },
            "additionalProperties": False,
        },
    )
    result = run(MockLLM().generate(request))
    assert result.structured_output == {"reply": "", "memory_candidates": []}
