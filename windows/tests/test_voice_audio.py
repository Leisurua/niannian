from contextlib import nullcontext
from functools import partial
import io
import json
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock
import wave

import pytest
from niannian_desktop.audio import Audio, wav_bytes
from niannian_desktop.conversation import ConversationPanel, ConversationSocket
from niannian_desktop.voice_api import VoiceApi


def test_recording_wire_format_and_pcm_limits():
    pcm = b'\0\1' * 2400
    with wave.open(io.BytesIO(wav_bytes(pcm))) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 24000)
        assert wav.readframes(2400) == pcm
    audio = Audio()
    for invalid in (b'1', b'00' * 4097):
        with pytest.raises(ValueError):
            audio.feed(invalid)
    audio.feed(b'00')
    audio.stop()
    assert audio.queue.empty()


def test_voice_socket_rejects_old_sequence_and_other_conversation():
    socket = ConversationSocket.__new__(ConversationSocket)
    socket.id, socket.server_sequence = 'conversation', None
    def frame(sequence, conversation='conversation'):
        return json.dumps(dict(conversation_id=conversation, sequence=sequence, payload={}, type='pong'))
    socket.validate(frame(4))
    for invalid in (frame(4), frame(6), frame(5, 'other')):
        with pytest.raises(ValueError):
            socket.validate(invalid)
    assert socket.validate(frame(5))['sequence'] == 5


def test_normal_server_close_reports_disconnect(monkeypatch):
    from websockets.sync import client as websocket_client

    socket = ConversationSocket.__new__(ConversationSocket)
    socket.client = SimpleNamespace(base_url='https://review.example.test', access_token='test-token')
    socket.family, socket.voice = 'test-family', None
    socket.closed, socket.lock = Event(), Lock()
    socket.sequence, socket.server_sequence, socket.floor = 0, None, 0
    socket.callback, socket.failed = Mock(), Mock()
    ready = dict(conversation_id='session', sequence=1, payload={}, type='session.ready')

    class Transport:
        send = Mock()

        def __iter__(self):
            return iter([json.dumps(ready)])

    monkeypatch.setattr(VoiceApi, 'request', lambda *args: {'id': 'session'})
    monkeypatch.setattr(websocket_client, 'connect', lambda *args, **kwargs: nullcontext(Transport()))
    socket.connect()
    socket.callback.assert_called_once_with(ready)
    socket.failed.assert_called_once()
    assert socket.socket is None


def test_send_failure_retains_draft_and_explicit_end_notifies_server():
    panel = SimpleNamespace(connection=SimpleNamespace(send=Mock(side_effect=OSError)),
        input=SimpleNamespace(get=lambda: '未发送的测试输入', set=Mock()), status=SimpleNamespace(set=Mock()),
        audio=SimpleNamespace(stop=Mock()), playback=None, slow=False, append=Mock(),
        clear_invitation=Mock(), reset=Mock())
    panel.command = partial(ConversationPanel.command, panel)
    ConversationPanel.submit(panel)
    panel.input.set.assert_not_called()
    panel.append.assert_not_called()
    panel.clear_invitation.assert_not_called()
    ConversationPanel.failed_connection(panel, '对话已断开')
    panel.reset.assert_called_once_with(keep_draft=True)

    panel.command = Mock(return_value=True)
    panel.reset.reset_mock()
    ConversationPanel.end(panel)
    panel.command.assert_called_once_with('session.end', {'reason': 'USER'})
    panel.reset.assert_called_once_with()


@pytest.mark.parametrize('action,reply,speech_mode', [
    ('ACCEPT', '今天想做什么？', 'device'),
    ('DECLINE', '好的，暂时不聊。', 'none'),
    ('PAUSE_TODAY', '今天已减少主动互动。', 'device'),
])
def test_proactive_invitation_never_plays_audio_before_explicit_response(action, reply, speech_mode):
    from datetime import datetime, timedelta, timezone
    spoken, displayed, sent, statuses = [], [], [], []
    def command(*args):
        sent.append(args)
        return True
    panel = SimpleNamespace(connection=SimpleNamespace(floor=0, sequence=5),
        voice_allowed=True, slow=False, invitation=None, playback=None,
        status=SimpleNamespace(set=statuses.append),
        audio=SimpleNamespace(speak=lambda *args: spoken.append(args), stop=lambda: None),
        clear_invitation=lambda: None, append=displayed.append,
        invitation_row=SimpleNamespace(pack=lambda **kw: None), after=lambda *args: 'timer',
        command=command)
    ConversationPanel.receive(panel, dict(type='session.ready', payload={'llm_mode': 'mock', 'voice_allowed': True}))
    assert 'Mock 演示' in statuses[-1]
    invitation = '0192f1e4-6ed8-7c21-a4c1-5d58db7c3002'
    ConversationPanel.receive(panel, dict(type='assistant.text', in_reply_to=1, payload=dict(text='聊一会儿？',
        proactive_invitation_id=invitation, expires_at=(datetime.now(timezone.utc) + timedelta(minutes=4)).isoformat())))
    assert not spoken and panel.invitation == invitation
    ConversationPanel.respond_invitation(panel, action)
    assert sent[0][1]['proactive_invitation_id'] == invitation
    assert sent[0][1]['proactive_response'] == action and not spoken
    ConversationPanel.receive(panel, dict(type='assistant.text', in_reply_to=2, payload={
        'text': reply, 'speech_mode': speech_mode, 'source_labels': ['主动陪伴设置']}))
    assert displayed[-1].endswith('来源：主动陪伴设置')
    assert spoken == ([(reply, False)] if speech_mode == 'device' else [])
