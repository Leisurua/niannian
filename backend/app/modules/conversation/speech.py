"""Connection-scoped speech; a single socket writer owns all event sequences."""
import asyncio
import base64
from uuid import uuid4

from app.integrations.family_voice import CosyVoice
from app.modules.conversation import service
from app.modules.auth.service import authenticate
from app.modules.account.service import note_possible_copy, send_gate
from app.modules.memory import rag
from app.modules.voice import service as voices


class Speech:
    def __init__(self, factory, bearer, settings, conversation_id, provider=None):
        self.factory, self.bearer, self.settings = factory, bearer, settings
        self.conversation_id = conversation_id
        self.provider = provider
        self.enabled = False
        self.queue = asyncio.Queue(maxsize=4)
        self.task = self.next_task = None
        self.playback_id = None
        self.profile = None
        self.text = ''
        self.records = ()
        self.reply = None
        self.speed = 1.0
        self.terminal = False

    async def stop(self):
        pending = [t for t in (self.task, self.next_task) if t]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self.task = self.next_task = None
        while not self.queue.empty():
            self.queue.get_nowait()
        self.profile = None
        self.playback_id = None
        self.terminal = False

    def waiting(self):
        if self.playback_id and not self.terminal and self.next_task is None:
            self.next_task = asyncio.create_task(self.queue.get())
        return {self.next_task} if self.next_task else set()

    def event(self, row, kind, **payload):
        return {**service.event(row, kind, {'playback_id': self.playback_id, 'voice_profile_id': str(self.profile[0]) if self.profile else None, **payload}),
                'in_reply_to': self.reply}

    async def validate(self, db, actor, row):
        if not self.playback_id:
            return []
        voice_ok = await service.voice_allowed(db, row)
        memory_ok = await rag.revalidate(db, actor, self.records)
        selected, allowed = await voices.selected(db, actor, row.family_id)
        valid = selected is not None and (selected.id, selected.version) == self.profile
        if voice_ok and memory_ok and allowed and valid:
            return []
        event = self.event(row, 'tts.error', code='VOICE_PERMISSION_CHANGED',
            fallback_text=self.text if voice_ok and memory_ok and not self.terminal else '',
            message='声音权限已变更。')
        await self.stop()
        return [event]

    async def begin(self, db, actor, row, outgoing, records=(), *, identity=False):
        if not self.enabled:
            return
        outgoing['payload']['speech_mode'] = 'none'
        if not await service.voice_allowed(db, row) or 'in_reply_to' not in outgoing:
            return
        outgoing['payload']['speech_mode'] = 'device'
        selected, allowed = await voices.selected(db, actor, row.family_id)
        if not selected or not allowed:
            return
        await self.stop()
        self.playback_id = str(uuid4())
        self.profile = (selected.id, selected.version)
        if identity:
            outgoing['payload']['text'] += '当前使用的是家人授权合成的声音。'
        self.text, self.records = outgoing['payload']['text'], records
        self.reply = outgoing['in_reply_to']
        outgoing['payload']['speech_mode'] = 'cloud'
        outgoing['payload']['voice_name'] = selected.display_name
        await note_possible_copy(db, actor.user_id, 'COSYVOICE:' + self.settings.family_voice_workspace_id)
        self.task = asyncio.create_task(self.produce(selected.provider_voice_id))

    async def produce(self, provider_voice_id):
        try:
            # Account erasure waits on this gate; revocation never waits for network I/O.
            async with self.factory() as gate:
                actor = None
                async with self.factory() as db:
                    actor = await authenticate(db, self.bearer[7:], self.settings)
                    await db.commit()
                await send_gate(gate, actor.user_id, shared=True)
                async with self.factory() as db:
                    actor = await authenticate(db, self.bearer[7:], self.settings)
                    row = await service.access(db, actor, self.conversation_id, owner_only=True, active=True)
                    selected, allowed = await voices.selected(db, actor, row.family_id)
                    if not selected or not allowed or (selected.id, selected.version) != self.profile or not await service.voice_allowed(db, row) or not await rag.revalidate(db, actor, self.records):
                        raise ValueError('Permission changed')
                    await db.commit()
                if self.provider is None and (selected.provider_workspace != self.settings.family_voice_workspace_id or selected.provider_model != CosyVoice.model):
                    raise ValueError('Voice provider configuration changed')
                provider = self.provider or CosyVoice(self.settings)
                await self.queue.put(('tts.start', {'format': 'pcm_s16le', 'sample_rate': 24000, 'channels': 1}))
                async for pcm in provider.stream(self.text, provider_voice_id, self.speed):
                    for offset in range(0, len(pcm), 8192):
                        chunk = pcm[offset:offset + 8192]
                        await self.queue.put(('tts.chunk', {'audio': base64.b64encode(chunk).decode('ascii')}))
                        await asyncio.sleep(len(chunk) / 48000)
                await self.queue.put(('tts.end', {}))
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.queue.put(('tts.error', {'code': 'VOICE_PROVIDER_UNAVAILABLE',
                'message': '家人声音暂不可用，已改用普通声音。', 'fallback_text': self.text}))

    async def drain(self, db, actor, row):
        invalid = await self.validate(db, actor, row)
        if invalid:
            return invalid
        if not self.next_task or not self.next_task.done():
            return []
        kind, payload = self.next_task.result()
        self.next_task = None
        event = self.event(row, kind, **payload)
        if kind in ('tts.end', 'tts.error'):
            self.terminal = True
        return [event]
