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
