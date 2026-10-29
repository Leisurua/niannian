"""Text/state WSS input contract; the transport authenticates every operation."""

from collections import deque
from dataclasses import dataclass
import json
import math
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator

ClientType = Literal['session.start', 'audio.chunk', 'audio.end', 'text.input',
                     'interrupt', 'repeat', 'slow_down', 'session.end', 'ping']
ServerType = Literal['session.ready', 'asr.partial', 'asr.final', 'assistant.state',
                     'assistant.text', 'tts.start', 'tts.end', 'signal.created',
                     'warning', 'error', 'pong', 'voice.permission']
BackendState = Literal['IDLE', 'LISTENING', 'THINKING', 'SPEAKING', 'WARNING', 'OFFLINE', 'ERROR']


class ProtocolError(ValueError):
    """Only a constant error code escapes; invalid content must not enter logs."""


class _Payload(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class StartPayload(_Payload):
    client_session_id: str = Field(min_length=1, max_length=128)
    input_mode: Literal['VOICE', 'TEXT', 'LOCAL_WAKEWORD']


class TextPayload(_Payload):
    text: str = Field(min_length=1)
    timezone: str = 'Asia/Shanghai'
    weather_city_id: int | None = Field(default=None, gt=0, le=2147483647, strict=True)

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        from app.modules.reminder.schedule import iana_zone
        iana_zone(value)
        return value

    @field_validator('text')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Empty input')
        return value


class EndPayload(_Payload):
    reason: Literal['USER', 'TIMEOUT', 'ERROR'] | None = None


class ClientEnvelope(_Payload):
    type: ClientType
    conversation_id: UUID
    sequence: int = Field(ge=1, strict=True)
    occurred_at: AwareDatetime
    payload: dict


@dataclass(frozen=True)
class InputLimits:
    max_frame_bytes: int
    max_text_chars: int
    messages_per_window: int
    window_seconds: float

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in (
            self.max_frame_bytes, self.max_text_chars, self.messages_per_window,
        )) or not math.isfinite(self.window_seconds) or self.window_seconds <= 0:
            raise ValueError('Positive input limits required')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError('WS_INVALID_MESSAGE')
        result[key] = value
    return result


def _reject_constant(value):
    raise ProtocolError('WS_INVALID_MESSAGE')


def parse_client_frame(
    frame: str, *, conversation_id: UUID, last_sequence: int, limits: InputLimits,
) -> ClientEnvelope:
    if not isinstance(frame, str):
        raise ProtocolError('WS_BINARY_NOT_ALLOWED')
    if len(frame) > limits.max_frame_bytes:
        raise ProtocolError('WS_FRAME_TOO_LARGE')
    try:
        size = len(frame.encode('utf-8'))
    except UnicodeError:
        raise ProtocolError('WS_INVALID_MESSAGE') from None
    if size > limits.max_frame_bytes:
        raise ProtocolError('WS_FRAME_TOO_LARGE')
    try:
        value = json.loads(frame, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        envelope = ClientEnvelope.model_validate(value)
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise ProtocolError('WS_INVALID_MESSAGE') from None
    if envelope.conversation_id != conversation_id:
        raise ProtocolError('WS_CONVERSATION_MISMATCH')
    if envelope.sequence <= last_sequence:
        raise ProtocolError('WS_SEQUENCE_REPLAY')
    if envelope.type in ('audio.chunk', 'audio.end'):
        raise ProtocolError('WS_AUDIO_DISABLED')
    try:
        if envelope.type == 'session.start':
            start = StartPayload.model_validate(envelope.payload)
            if start.input_mode != 'TEXT':
                raise ProtocolError('WS_AUDIO_DISABLED')
        elif envelope.type == 'text.input':
            text = TextPayload.model_validate(envelope.payload)
            if len(text.text) > limits.max_text_chars:
                raise ProtocolError('WS_TEXT_TOO_LARGE')
        elif envelope.type == 'session.end':
            EndPayload.model_validate(envelope.payload)
        else:
            _Payload.model_validate(envelope.payload)
    except ValidationError:
        raise ProtocolError('WS_INVALID_PAYLOAD') from None
    return envelope


class MessageBudget:
    """Bounded sliding window; use a monotonic clock supplied by the transport.

    A transport must scope this to user/session and bound connections separately.
    This helper alone is not the WS-007 acceptance gate.
    """

    def __init__(self, limits: InputLimits):
        self.limits = limits
        self._arrivals: deque[float] = deque()
        self._last_time: float | None = None

    def take(self, now: float) -> None:
        if not math.isfinite(now) or self._last_time is not None and now < self._last_time:
            raise ValueError('A nondecreasing monotonic clock is required')
        self._last_time = now
        while self._arrivals and self._arrivals[0] <= now - self.limits.window_seconds:
            self._arrivals.popleft()
        if len(self._arrivals) >= self.limits.messages_per_window:
            raise ProtocolError('WS_RATE_LIMITED')
        self._arrivals.append(now)
