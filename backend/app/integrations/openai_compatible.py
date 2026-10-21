"""JSON-mode Chat Completions adapter. No credentials or raw provider errors in logs."""

import json
import time

import httpx

from app.integrations.contracts import LLMResponse, ProviderCapabilities, ProviderError, ProviderStatus


class OpenAICompatibleLLM:
    provider = "openai_compatible"

    def __init__(self, *, base_url, api_key, model, timeout=20, thinking=None, transport=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.thinking = thinking
        self.transport = transport

    def capabilities(self):
        return ProviderCapabilities(provider=self.provider, model=self.model, version="1.0.0",
                                    structured_output=True, languages=("zh-CN",))

    async def generate(self, request):
        started = time.monotonic()
        messages = [
            {"role": "system", "content": request.system_policy + "\n只输出 JSON，符合以下 schema：\n"
             + json.dumps(request.output_schema, ensure_ascii=False)},
            {"role": "user", "content": json.dumps({
                "authorized_memory": request.authorized_memory,
                "recent_turns": request.conversation_context.get("recent_turns", []),
                "user_input": request.user_input,
            }, ensure_ascii=False)},
        ]
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "response_format": {"type": "json_object"}, "max_tokens": 1200}
        if self.thinking is not None:
            payload["thinking"] = {"type": self.thinking}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False,
                                         transport=self.transport) as client:
                async with client.stream("POST", self.base_url + "/chat/completions",
                        headers={"Authorization": "Bearer " + self.api_key},
                        json=payload) as response:
                    response.raise_for_status()
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 65536:
                            raise ValueError("Oversized response")
            body = json.loads(content)
            choice = body["choices"][0]
            if choice.get("finish_reason") != "stop" or choice["message"].get("tool_calls"):
                raise ValueError("Incomplete or unsupported response")
            output = json.loads(choice["message"]["content"])
            if not isinstance(output, dict):
                raise ValueError("Invalid JSON object")
        except httpx.TimeoutException:
            raise TimeoutError("LLM deadline exceeded") from None
        except Exception:
            raise ProviderError(code="UNAVAILABLE", provider="openai_compatible", operation="generate",
                retryable=False, safe_to_retry=False, attempt=1,
                user_message_key="ai.temporarily_unavailable") from None
        return LLMResponse(status=ProviderStatus.SUCCEEDED, structured_output=output,
            raw_text_for_fallback=None, provider="openai_compatible", model=self.model,
            prompt_id=request.prompt_id, prompt_version=request.prompt_version,
            latency_ms=int((time.monotonic() - started) * 1000))
