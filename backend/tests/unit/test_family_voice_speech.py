import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.modules.conversation.speech import Speech
from app.modules.conversation import speech as module


@pytest.mark.parametrize('voice,memory,cloud,fallback', [
    (False, True, True, ''), (True, False, True, ''),
    (True, True, False, 'authorized reply'),
])
def test_revocation_cancels_pending_audio_without_leaking_text(monkeypatch, voice, memory, cloud, fallback):
    monkeypatch.setattr(module.service, 'voice_allowed', AsyncMock(return_value=voice))
    monkeypatch.setattr(module.rag, 'revalidate', AsyncMock(return_value=memory))
    monkeypatch.setattr(module.voices, 'selected', AsyncMock(return_value=(SimpleNamespace(id='profile', version=1), cloud)))
    async def run():
        state = Speech(None, '', None, 'conversation')
        state.playback_id, state.profile, state.reply = 'playback', ('profile', 1), 3
        state.text = 'authorized reply'
        state.task = asyncio.create_task(asyncio.sleep(30))
        task = state.task
        await state.queue.put(('tts.chunk', {'audio': 'old'}))
        row = SimpleNamespace(id='conversation', family_id='family', server_sequence=5)
        events = await state.validate(None, None, row)
        assert events[0]['payload']['fallback_text'] == fallback
        assert events[0]['payload']['playback_id'] == 'playback'
        assert events[0]['in_reply_to'] == 3
        assert task.cancelled() and state.queue.empty() and state.playback_id is None
    asyncio.run(run())


def test_finished_stream_remains_revocable_while_client_is_playing(monkeypatch):
    monkeypatch.setattr(module.service, 'voice_allowed', AsyncMock(return_value=True))
    monkeypatch.setattr(module.rag, 'revalidate', AsyncMock(return_value=True))
    selected = AsyncMock(return_value=(SimpleNamespace(id='profile', version=1), True))
    monkeypatch.setattr(module.voices, 'selected', selected)
    async def run():
        state = Speech(None, '', None, 'conversation')
        state.playback_id, state.profile, state.reply = 'playback', ('profile', 1), 3
        state.next_task = asyncio.create_task(asyncio.sleep(0, result=('tts.end', {})))
        await state.next_task
        row = SimpleNamespace(id='conversation', family_id='family', server_sequence=5)
        assert (await state.drain(None, None, row))[0]['type'] == 'tts.end'
        assert state.waiting() == set()
        selected.return_value = (None, True)
        assert (await state.validate(None, None, row))[0]['type'] == 'tts.error'
    asyncio.run(run())
