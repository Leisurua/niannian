import json
from uuid import UUID

import pytest

from app.modules.conversation.protocol import InputLimits, MessageBudget, ProtocolError, parse_client_frame

CONVERSATION = UUID('0192f1e4-6ed8-7c21-a4c1-5d58db7c3001')
OTHER = UUID('0192f1e4-6ed8-7c21-a4c1-5d58db7c3002')
LIMITS = InputLimits(max_frame_bytes=1024, max_text_chars=100, messages_per_window=3, window_seconds=1.0)


def frame(**changes):
    return json.dumps(dict(type='ping', conversation_id=str(CONVERSATION), sequence=1,
                          occurred_at='2026-10-09T00:00:00Z', payload={}) | changes, ensure_ascii=False)


def parse(raw, last=0):
    return parse_client_frame(raw, conversation_id=CONVERSATION, last_sequence=last, limits=LIMITS)


@pytest.mark.parametrize('kind,payload', [
    ('session.start', {'client_session_id': 'fictional-session', 'input_mode': 'TEXT'}),
    ('text.input', {'text': '虚构的测试输入'}), ('interrupt', {}), ('repeat', {}),
    ('slow_down', {}), ('session.end', {'reason': 'USER'}), ('ping', {}),
])
def test_text_state_client_messages(kind, payload):
    result = parse(frame(type=kind, payload=payload))
    assert result.type == kind
    assert result.payload == payload


@pytest.mark.parametrize('raw', [
    '{', 'null', '[]', '{}', '{"sequence":1,"sequence":2}',
    frame(sequence=True), frame(sequence='1'), frame(sequence=1.5), frame(sequence=0),
    frame(occurred_at='2026-10-09T00:00:00'), frame(type='provider.execute'),
    frame(payload={'value': float('nan')}), frame(extra='not-in-envelope'),
    frame(conversation_id='not-a-uuid'), '[' * 1000,
])
def test_malformed_envelope_never_echoes_input(raw):
    with pytest.raises(ProtocolError) as error:
        parse(raw)
    assert str(error.value) == 'WS_INVALID_MESSAGE'


@pytest.mark.parametrize('changes,code', [
    ({'conversation_id': str(OTHER)}, 'WS_CONVERSATION_MISMATCH'),
    ({'type': 'text.input', 'payload': {'text': '  '}}, 'WS_INVALID_PAYLOAD'),
    ({'type': 'text.input', 'payload': {'text': 'a' * 101}}, 'WS_TEXT_TOO_LARGE'),
    ({'type': 'text.input', 'payload': {'text': 'fictional', 'prompt': 'untrusted'}}, 'WS_INVALID_PAYLOAD'),
    ({'type': 'session.start', 'payload': {'client_session_id': 'test', 'input_mode': 'VOICE'}}, 'WS_AUDIO_DISABLED'),
    ({'type': 'session.start', 'payload': {'client_session_id': 'test', 'input_mode': 'LOCAL_WAKEWORD'}}, 'WS_AUDIO_DISABLED'),
    ({'type': 'audio.chunk', 'payload': {'base64_data': 'fictional'}}, 'WS_AUDIO_DISABLED'),
    ({'type': 'audio.end'}, 'WS_AUDIO_DISABLED'),
    ({'type': 'session.end', 'payload': {'reason': 'ADMIN_OVERRIDE'}}, 'WS_INVALID_PAYLOAD'),
    ({'payload': {'access_token': 'fictional-placeholder'}}, 'WS_INVALID_PAYLOAD'),
])
def test_wrong_resource_audio_and_unexpected_payloads_are_rejected(changes, code):
    with pytest.raises(ProtocolError, match=code):
        parse(frame(**changes))


def test_replay_is_checked_against_caller_supplied_checkpoint():
    for sequence in (1, 2, 3):
        with pytest.raises(ProtocolError, match='WS_SEQUENCE_REPLAY'):
            parse(frame(sequence=sequence), last=3)
    assert parse(frame(sequence=4), last=3).sequence == 4


def test_utf8_size_binary_surrogate_and_duplicate_payload_keys():
    with pytest.raises(ProtocolError, match='WS_FRAME_TOO_LARGE'):
        parse(frame(type='text.input', payload={'text': '念' * 400}))
    with pytest.raises(ProtocolError, match='WS_BINARY_NOT_ALLOWED'):
        parse(b'fictional audio bytes')
    with pytest.raises(ProtocolError, match='WS_INVALID_MESSAGE'):
        parse('\ud800')
    duplicate = frame(type='text.input').replace('"payload": {}', '"payload": {"text":"a","text":"b"}')
    with pytest.raises(ProtocolError, match='WS_INVALID_MESSAGE'):
        parse(duplicate)


def test_flood_budget_stays_bounded_and_recovers_at_window_boundary():
    budget = MessageBudget(LIMITS)
    for stamp in (0.0, 0.1, 0.2):
        budget.take(stamp)
    for _ in range(100):
        with pytest.raises(ProtocolError, match='WS_RATE_LIMITED'):
            budget.take(0.9)
    budget.take(1.0)
    with pytest.raises(ProtocolError, match='WS_RATE_LIMITED'):
        budget.take(1.0)
    budget.take(1.1)
    with pytest.raises(ValueError, match='monotonic'):
        budget.take(0.5)
    with pytest.raises(ValueError, match='monotonic'):
        budget.take(float('nan'))
