import io
import json
import wave

import pytest
from niannian_desktop.audio import Audio, wav_bytes
from niannian_desktop.conversation import ConversationSocket


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


def test_proactive_invitation_never_plays_audio_before_explicit_response():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from niannian_desktop.conversation import ConversationPanel
    spoken, displayed, sent = [], [], []
    panel = SimpleNamespace(connection=SimpleNamespace(floor=0, sequence=5),
        voice_allowed=True, slow=False, invitation=None, playback=None,
        audio=SimpleNamespace(speak=lambda *args: spoken.append(args), stop=lambda: None),
        clear_invitation=lambda: None, append=displayed.append,
        invitation_row=SimpleNamespace(pack=lambda **kw: None), after=lambda *args: 'timer',
        command=lambda *args: sent.append(args))
    invitation = '0192f1e4-6ed8-7c21-a4c1-5d58db7c3002'
    ConversationPanel.receive(panel, dict(type='assistant.text', in_reply_to=1, payload=dict(text='聊一会儿？',
        proactive_invitation_id=invitation, expires_at=(datetime.now(timezone.utc) + timedelta(minutes=4)).isoformat())))
    assert not spoken and panel.invitation == invitation
    ConversationPanel.respond_invitation(panel, 'ACCEPT')
    assert sent[0][1]['proactive_invitation_id'] == invitation
    assert sent[0][1]['proactive_response'] == 'ACCEPT' and not spoken
    ConversationPanel.receive(panel, dict(type='assistant.text', in_reply_to=2, payload={'text': '今天想做什么？'}))
    assert spoken == [('今天想做什么？', False)]
