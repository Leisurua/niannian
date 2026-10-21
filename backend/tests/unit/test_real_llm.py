import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.ai.conversation import AIOrchestrator, UNAVAILABLE, configured_orchestrator
from app.integrations.openai_compatible import OpenAICompatibleLLM
from app.modules.conversation import api
from app.platform.config import Settings
from app.platform.errors import AppError


def output(**changes):
    return dict(reply="听起来您很喜欢种花。最近在种什么花呢？", memory_refs=[], intent="GENERAL_CHAT",
                needs_clarification=False, memory_candidates=[], signal_candidates=[],
                blocked_action=None, uncertainty_reason=None) | changes


def adapter(handler):
    return OpenAICompatibleLLM(base_url="https://llm.example/v1", api_key="fictional-key",
        model="fictional-model", transport=httpx.MockTransport(handler))


def response(value=None, finish="stop"):
    return httpx.Response(200, json={"choices": [{"finish_reason": finish,
        "message": {"content": json.dumps(output() if value is None else value)}}]})


def turn(llm, **kwargs):
    return asyncio.run(AIOrchestrator(llm=llm).handle(
        request_id="fictional-request", conversation_id=uuid4(), text="我喜欢种花", **kwargs))


def test_real_json_roundtrip_and_short_context():
    seen = []
    def handle(request):
        seen.append(request)
        return response()
    result = turn(adapter(handle), recent_turns=[{"user": "你好", "assistant": "您好"}])
    assert result.assistant_text == output()["reply"]
    assert result.fallback_code is None
    assert result.trace["provider"] == "openai_compatible"
    request = seen[0]
    assert str(request.url) == "https://llm.example/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer fictional-key"
    body = json.loads(request.content)
    assert body["model"] == "fictional-model"
    assert "thinking" not in body
    assert body["response_format"] == {"type": "json_object"}
    payload = json.loads(body["messages"][1]["content"])
    assert payload["recent_turns"] == [{"user": "你好", "assistant": "您好"}]
    assert "我喜欢种花" not in str(result.trace)


@pytest.mark.parametrize("value", [
    output(reply=" "), output(reply="x" * 2001), output(memory_refs=[str(uuid4())]),
    output(needs_clarification="false"), output(signal_candidates=[{"type": "EMERGENCY"}]),
    output(memory_candidates=[{"content": "invented"}]), output(execute="CALL"),
    output(blocked_action="CALL"), output(intent="CALL_NOW"),
])
def test_real_untrusted_schema_or_authority_fails_closed(value):
    result = turn(adapter(lambda _: response(value)))
    assert result.assistant_text == UNAVAILABLE
    assert result.fallback_code == "INVALID_OR_UNAVAILABLE_OUTPUT"


@pytest.mark.parametrize("status", [401, 429, 500, 302])
def test_provider_error_is_redacted_without_retry(status):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, text="fictional-private-provider-body",
                              headers={"Location": "https://other.example/"})
    result = turn(adapter(handle))
    assert len(calls) == 1
    assert result.assistant_text == UNAVAILABLE
    assert "fictional-private-provider-body" not in str(result)
    assert "fictional-key" not in str(result)


@pytest.mark.parametrize("reply", [
    httpx.Response(200, content=b"not-json"), response(finish="length"),
    httpx.Response(200, content=b"x" * 65537),
])
def test_incomplete_invalid_and_oversized_responses(reply):
    assert turn(adapter(lambda _: reply)).assistant_text == UNAVAILABLE


def test_provider_timeout_and_cancellation():
    def timeout(request):
        raise httpx.ReadTimeout("private detail", request=request)
    assert turn(adapter(timeout)).fallback_code == "PROVIDER_TIMEOUT"

    async def scenario():
        started = asyncio.Event()
        async def blocked(request):
            started.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(AIOrchestrator(llm=adapter(blocked)).handle(
            request_id="cancel", conversation_id=uuid4(), text="你好"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())


def test_authorized_uuid_strings_and_all_context_are_revalidated():
    record = SimpleNamespace(id=uuid4(), family_id=uuid4(), type="EVENT", content="虚构养花记录")
    result = turn(adapter(lambda _: response(output(memory_refs=[str(record.id)]))), memory_records=[record])
    assert result.fallback_code is None
    assert result.memory_records == (record,)
    # Context still affects a free-form answer when the model omits citations.
    assert turn(adapter(lambda _: response()), memory_records=[record]).memory_records == (record,)


def test_deterministic_safety_does_not_call_real_provider():
    def forbidden(_):
        pytest.fail("Safety decision must precede external requests")
    result = asyncio.run(AIOrchestrator(llm=adapter(forbidden)).handle(
        request_id="safety", conversation_id=uuid4(), text="救命"))
    assert result.avatar_state.value == "WARNING"


def test_explicit_configuration_keeps_demo_auth_independent():
    settings = Settings(app_env="dev", provider_mode="mock", llm_provider="openai_compatible",
        llm_base_url="https://llm.example/v1", llm_model="fictional-model", llm_api_key="fictional-key")
    assert configured_orchestrator(settings).llm.capabilities().provider == "openai_compatible"
    assert settings.provider_mode == "mock"


@pytest.mark.parametrize("thinking", [None, "disabled", "enabled"])
def test_deepseek_configuration_reaches_wire_and_discards_reasoning(thinking):
    settings = Settings(app_env="dev", provider_mode="mock", llm_provider="openai_compatible",
        llm_base_url="https://api.deepseek.com", llm_model="deepseek-flash",
        llm_api_key="fictional-key", llm_thinking=thinking)
    orchestrator = configured_orchestrator(settings)
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"model": "deepseek-flash", "choices": [{
            "finish_reason": "stop", "message": {
                "content": json.dumps(output()), "reasoning_content": "private reasoning fixture",
            },
        }]})
    orchestrator.llm.transport = httpx.MockTransport(handle)
    result = asyncio.run(orchestrator.handle(
        request_id="deepseek-test", conversation_id=uuid4(), text="你好，念念"))
    assert result.assistant_text == output()["reply"]
    assert result.fallback_code is None
    assert result.trace["model"] == "deepseek-flash"
    assert "private reasoning fixture" not in str(result)
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.deepseek.com/chat/completions"
    assert request.headers["authorization"] == "Bearer fictional-key"
    body = json.loads(request.content)
    assert body["model"] == "deepseek-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["stream"] is False
    if thinking is None:
        assert "thinking" not in body
    else:
        assert body["thinking"] == {"type": thinking}


@pytest.mark.parametrize("changes", [
    {"llm_api_key": None}, {"llm_model": ""}, {"llm_base_url": "http://llm.example"},
    {"llm_base_url": "https://user:password@llm.example"},
    {"llm_base_url": "https://llm.example?key=value"}, {"app_env": "demo", "demo_data": True},
    {"app_env": "test"},
    {"llm_thinking": "off"},
])
def test_invalid_real_configuration_fails_before_network(changes):
    with pytest.raises(ValueError) as failure:
        Settings(**(dict(app_env="dev", llm_provider="openai_compatible",
            llm_base_url="https://llm.example/v1", llm_model="model", llm_api_key="fictional-key") | changes))
    assert "fictional-key" not in str(failure.value)


def test_failed_authentication_never_sends_input_to_llm(monkeypatch):
    class DB:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    monkeypatch.setattr(api, "authenticate", AsyncMock(side_effect=AppError("AUTH", "denied", 401)))
    orchestrator = SimpleNamespace(handle=AsyncMock())
    with pytest.raises(AppError):
        asyncio.run(api.generate_turn(DB, "Bearer fictional", Settings(), orchestrator, uuid4(), "private", "req"))
    orchestrator.handle.assert_not_awaited()
