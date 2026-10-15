import asyncio
from dataclasses import dataclass
from importlib.resources import files
import time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.contracts import (
    AvatarState, AvatarStateRequest, LLMRequest, LLMResponse,
    ProviderStatus, TTSRequest,
)
from app.integrations.mock import MockAvatar, MockLLM, MockTTS

PROMPT_VERSION = '1.0.0'
IDENTITY = '你好，我是念念 AI。今天想聊点什么？这是 Mock 演示，仅显示文字。'
UNKNOWN = '我不确定，可以问问家人。当前演示尚未接入家庭记忆检索。'
UNAVAILABLE = '我现在没法回答，稍后再试或问问家人。'
CHAT = '这是 Mock 演示回复。我在这里陪您，可以聊聊今天想做的事。'
HELP = '如需帮助，请直接联系身边的人或家人。此演示不能代您拨打电话或发送通知。'
SYSTEM_UNKNOWN = '我现在没有可核实的天气、时间安排或提醒信息，请查看相应页面或问问家人。'
REPLIES = frozenset((IDENTITY, UNKNOWN, UNAVAILABLE, CHAT, HELP, SYSTEM_UNKNOWN))


class ConversationOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    reply: str = Field(min_length=1, max_length=2000)
    memory_refs: list[UUID] = Field(max_length=5)
    intent: Literal['GENERAL_CHAT', 'MEMORY_QUERY']
    needs_clarification: bool
    memory_candidates: list[dict] = Field(max_length=5)
    signal_candidates: list[dict] = Field(max_length=3)
    blocked_action: str | None
    uncertainty_reason: str | None = Field(max_length=240)


def reply_for(text):
    if any(word in text for word in ('你是谁', '是人吗', '真人', '你是AI', '你是 AI')):
        return IDENTITY
    if any(word in text for word in ('救命', '急救', '帮我叫人', '联系', '打电话', '疼', '不舒服', '诊断', '验证码', '转账')):
        return HELP
    if any(word in text for word in ('天气', '下雨', '提醒', '吃药', '几点', '刚才聊')):
        return SYSTEM_UNKNOWN
    if any(word in text for word in ('家', '女儿', '儿子', '孙', '老伴', '名字', '住', '记得', '亲人')):
        return UNKNOWN
    return CHAT


class MockConversationLLM(MockLLM):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        reply = reply_for(request.user_input)
        return LLMResponse(status=ProviderStatus.SUCCEEDED, structured_output=dict(
            reply=reply, memory_refs=[], intent='MEMORY_QUERY' if reply == UNKNOWN else 'GENERAL_CHAT',
            needs_clarification=reply == UNKNOWN, memory_candidates=[], signal_candidates=[],
            blocked_action=None, uncertainty_reason='NO_AUTHORIZED_CONTEXT' if reply == UNKNOWN else None,
        ), raw_text_for_fallback=None, provider='mock', model='mock-conversation-v1',
            prompt_id=request.prompt_id, prompt_version=request.prompt_version, latency_ms=0)


@dataclass(frozen=True)
class TurnResult:
    assistant_text: str
    avatar_state: AvatarState
    fallback_code: str | None
    trace: dict


class AIOrchestrator:
    """The caller authenticates before input and again before publishing output.

    Week 4 has no authorized retrieval provider: no family data is supplied and
    all references/candidates/actions fail closed. Full RAG remains Week 5.
    Only curated Mock replies can pass the post-provider fact/safety check.
    """

    def __init__(self, *, llm=None, tts=None, avatar=None, timeout=8.0):
        if not 0 < timeout <= 20:
            raise ValueError('Conversation deadline must be within 20 seconds')
        self.llm = llm or MockConversationLLM()
        self.tts = tts or MockTTS()
        self.avatar = avatar or MockAvatar()
        self.timeout = timeout

    async def handle(self, *, request_id: str, conversation_id: UUID, text: str) -> TurnResult:
        started = time.monotonic()
        reply, code = UNAVAILABLE, None
        state = AvatarState.IDLE
        optional_fallback = None
        try:
            async with asyncio.timeout(self.timeout):
                if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                    raise ValueError('Invalid input')
                capabilities = self.llm.capabilities()
                if any(adapter.capabilities().provider != 'mock' for adapter in (self.llm, self.tts, self.avatar)):
                    raise ValueError('Real providers are not enabled')
                if not capabilities.structured_output or 'zh-CN' not in capabilities.languages:
                    raise ValueError('Unsupported capability')
                request = LLMRequest(request_id=request_id, task='conversation',
                    system_policy=files('app.ai').joinpath('prompts/conversation.md').read_text(encoding='utf-8'),
                    conversation_context={'conversation_id': str(conversation_id), 'input_mode': 'TEXT'},
                    authorized_memory=[], user_input=text, safety_context={},
                    output_schema=ConversationOutput.model_json_schema(),
                    prompt_id='conversation', prompt_version=PROMPT_VERSION)
                response = await self.llm.generate(request)
                if (response.status != ProviderStatus.SUCCEEDED or response.provider != 'mock'
                        or response.prompt_id != 'conversation' or response.prompt_version != PROMPT_VERSION):
                    raise ValueError('Invalid provider response')
                output = ConversationOutput.model_validate(response.structured_output)
                if (output.memory_refs or output.memory_candidates or output.signal_candidates
                        or output.blocked_action is not None or output.reply != reply_for(text)):
                    raise ValueError('Untrusted response')
                reply = output.reply
                optional_fallback = 'TTS_UNAVAILABLE'
                try:
                    async with asyncio.timeout(min(2.0, self.timeout)):
                        speech = await self.tts.synthesize(TTSRequest(request_id=request_id, text=reply))
                        if speech.provider != 'mock' or speech.audio is not None:
                            raise ValueError('Audio is disabled')
                except Exception:
                    code = 'TTS_UNAVAILABLE'
                optional_fallback = 'AVATAR_UNAVAILABLE'
                try:
                    async with asyncio.timeout(min(2.0, self.timeout)):
                        await self.avatar.set_state(AvatarStateRequest(request_id=request_id, state=AvatarState.IDLE))
                except Exception:
                    code = code or 'AVATAR_UNAVAILABLE'
                optional_fallback = None
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            if optional_fallback:
                code = code or optional_fallback
            else:
                reply, code, state = UNAVAILABLE, 'PROVIDER_TIMEOUT', AvatarState.ERROR
        except Exception:
            reply, code, state = UNAVAILABLE, 'INVALID_OR_UNAVAILABLE_OUTPUT', AvatarState.ERROR
        trace = dict(request_id=request_id, conversation_id=str(conversation_id), provider='mock',
            model='mock-conversation-v1', provider_version='1.0.0', prompt_id='conversation',
            prompt_version=PROMPT_VERSION, policy_version='1.0.0',
            latency_ms=int((time.monotonic() - started) * 1000),
            result_status='FAILED' if state == AvatarState.ERROR else 'PARTIAL' if code else 'SUCCEEDED',
            fallback_code=code, memory_candidate_count=0, signal_candidate_count=0)
        return TurnResult(reply, state, code, trace)
