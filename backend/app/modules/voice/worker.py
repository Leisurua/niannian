import asyncio
from io import BytesIO
from types import SimpleNamespace
import wave
from datetime import timedelta
from sqlalchemy import select
from app.modules.voice import service
from app.modules.voice.models import VoiceProfile
from app.modules.account.service import note_provider_resource, note_possible_copy, send_gate
from app.platform import tasks
from app.platform.identifiers import utcnow


async def current(db, profile_id, task_id, token):
    row = await db.get(VoiceProfile, profile_id)
    if not row or row.status not in ('QUEUED', 'GENERATING'):
        raise RuntimeError('Voice no longer approved')
    await service.access(db, SimpleNamespace(user_id=row.owner_user_id), row.id, owner=True)
    if not row.approved_at or not row.sample_key or row.expires_at <= utcnow():
        raise RuntimeError('Voice authorization expired')
    lease = await tasks.leased(db, task_id, token)
    if not lease or row.version != lease.resource_version:
        raise RuntimeError('Voice lease expired')
    lease.lease_until = utcnow() + timedelta(seconds=180)
    row.status = 'GENERATING'
    return row


async def generate(factory, storage, settings, task_id, token, profile_id, provider):
    async with factory() as db:
        row = await current(db, profile_id, task_id, token)
        if row.provider_workspace != settings.family_voice_workspace_id:
            raise RuntimeError('Provider workspace changed')
        owner, key = row.owner_user_id, row.sample_key
        await note_possible_copy(db, owner, 'COSYVOICE:' + row.provider_workspace)
        await db.commit()
    sample = await storage.read(key, service.MAX_SAMPLE)
    service.validate_sample(sample)
    async with factory() as gate:
        await send_gate(gate, owner, shared=True)
        async with factory() as db:
            row = await current(db, profile_id, task_id, token)
            voice_id = row.provider_voice_id
            await db.commit()
        if not voice_id:
            voice_id = await provider.create(sample, 'nn' + profile_id.hex[:8])
            # Preserve the remote handle even if consent changed during the call.
            async with factory() as db:
                row = await db.get(VoiceProfile, profile_id)
                row.provider_voice_id = voice_id
                await note_provider_resource(db, owner, 'COSYVOICE:' + row.provider_workspace,
                    {'voice_id': voice_id, 'workspace': row.provider_workspace})
                await db.commit()
        for _ in range(30):
            async with factory() as db:
                await current(db, profile_id, task_id, token)
                await db.commit()
            state = await provider.query(voice_id)
            if state == 'OK':
                break
            if state != 'DEPLOYING':
                raise RuntimeError('Voice failed')
            await asyncio.sleep(1)
        else:
            raise RuntimeError('Voice not ready')
        audio = bytearray()
        async for chunk in provider.stream(service.PREVIEW_TEXT, voice_id):
            audio.extend(chunk)
            if len(audio) > 2_880_000:
                raise RuntimeError('Preview too large')
        output = BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(audio)
        async with factory() as db:
            row = await current(db, profile_id, task_id, token)
            preview = f'voices/{row.id}/preview.wav'
            await storage.write(preview, output.getvalue(), 'audio/wav')
            row.preview_key = preview
            await getattr(storage, 'delete_all_versions', storage.delete)(row.sample_key)
            row.sample_key, row.status, row.error_code = None, 'READY', None
            await tasks.finish(db, task_id, token)
            await db.commit()


async def cleanup(factory, storage, settings, task_id, token, profile_id, provider):
    async with factory() as db:
        row = await db.get(VoiceProfile, profile_id)
        if not row or row.status == 'DELETED':
            await tasks.finish(db, task_id, token)
            await db.commit()
            return
        owner = row.owner_user_id
    # Wait for a previously authorized create call to settle before deletion.
    async with factory() as gate:
        await send_gate(gate, owner)
        async with factory() as db:
            row = await db.get(VoiceProfile, profile_id)
            if row.status != 'REVOKED':
                raise RuntimeError('Unexpected cleanup state')
            if row.provider_voice_id:
                if row.provider_workspace != settings.family_voice_workspace_id:
                    raise RuntimeError('Provider workspace changed')
                if provider is None:
                    from app.integrations.family_voice import CosyVoice
                    provider = CosyVoice(settings)
                await provider.delete(row.provider_voice_id)
                row.provider_voice_id = None
            for key in (row.sample_key, row.preview_key):
                if key:
                    await getattr(storage, 'delete_all_versions', storage.delete)(key)
            row.sample_key, row.preview_key, row.status, row.error_code = None, None, 'DELETED', None
            row.display_name, row.sample_hash = '已删除声音', None
            await tasks.finish(db, task_id, token)
            await db.commit()


async def run_one(factory, storage, settings, *, provider=None):
    async with factory() as db:
        task = await tasks.claim(db, kinds=('VOICE_GENERATE', 'VOICE_CLEANUP'))
        if task is None:
            return False
        task_id, token, profile_id, kind = task.id, task.lease_token, task.resource_id, task.kind
        task.lease_until = utcnow() + timedelta(seconds=180)
        await db.commit()
    try:
        from app.integrations.family_voice import CosyVoice
        if kind == 'VOICE_GENERATE':
            provider = provider or CosyVoice(settings)
        async with asyncio.timeout(150):
            await (generate if kind == 'VOICE_GENERATE' else cleanup)(factory, storage, settings, task_id, token, profile_id, provider)
    except asyncio.CancelledError:
        raise
    except Exception:
        async with factory() as db:
            row = await db.get(VoiceProfile, profile_id)
            if row and row.status in ('QUEUED', 'GENERATING'):
                row.status, row.error_code = 'FAILED', 'VOICE_GENERATION_FAILED'
            elif row and row.status == 'REVOKED':
                row.error_code = 'VOICE_CLEANUP_PENDING'
            await tasks.finish(db, task_id, token, error=True)
            await db.commit()
    return True
