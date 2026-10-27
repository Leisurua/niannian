import asyncio
from datetime import timedelta
import hashlib
from types import SimpleNamespace

from app.modules.account.service import send_gate
from app.modules.avatar import service
from app.modules.avatar.models import AvatarJob
from app.modules.avatar.pipeline import ImageEditor, PipelineError, Tha3Renderer, check_pack
from app.modules.memory.models import FileAsset
from app.platform import tasks
from app.platform.config import get_settings
from app.platform.errors import AppError
from app.platform.identifiers import utcnow


async def current(db, job_id, task_id, token, settings, phase=None):
    row = await db.get(AvatarJob, job_id)
    if row is None:
        raise PipelineError('AUTHORIZATION_CHANGED')
    row = await service.access(db, SimpleNamespace(user_id=row.owner_user_id), row.id)
    lease = await tasks.leased(db, task_id, token)
    if not lease or row.version != lease.resource_version or row.status not in service.RUNNING:
        raise PipelineError('WORKER_INTERRUPTED')
    caps = service.capabilities(settings)
    if not caps['available'] or row.provider_id != caps['provider_id']:
        raise PipelineError('IMAGE_SERVICE_CHANGED')
    lease.lease_until = utcnow() + timedelta(seconds=30)
    if phase:
        row.status, row.updated_at = phase, utcnow()
    return row


async def perform(factory, storage, settings, job_id, task_id, token, editor, renderer):
    async with factory() as db:
        row = await current(db, job_id, task_id, token, settings, 'STYLIZING')
        source = await db.get(FileAsset, row.source_id)
        if not source or source.status != 'AVAILABLE' or source.deleted_at:
            raise PipelineError('SOURCE_UNAVAILABLE')
        source_key, mime = source.object_key + '.safe', source.mime_type
        await db.commit()
    photo = await storage.read(source_key, 5242880)
    async with factory() as db:
        row = await current(db, job_id, task_id, token, settings)
        await service.note_image_send(db, row, settings)
        await db.commit()
    illustration = await editor.edit(photo, mime)
    photo = b''
    async with factory() as db:
        await current(db, job_id, task_id, token, settings, 'PREPARING')
        await db.commit()
    illustration = await renderer.prepare(illustration)
    async with factory() as db:
        await current(db, job_id, task_id, token, settings, 'RENDERING')
        await db.commit()
    pack, _ = await renderer.render(illustration)
    illustration = b''
    preview = await asyncio.to_thread(check_pack, pack)
    async with factory() as db:
        row = await current(db, job_id, task_id, token, settings)
        for asset_id, data in ((row.pack_id, pack), (row.preview_id, preview)):
            asset = await db.get(FileAsset, asset_id)
            if not asset or asset.deleted_at or asset.status != 'PENDING_UPLOAD':
                raise PipelineError('AUTHORIZATION_CHANGED')
            await service.settled(storage.write(asset.object_key + '.safe', data, asset.mime_type))
            asset.size_bytes, asset.checksum, asset.status = len(data), hashlib.sha256(data).hexdigest(), 'AVAILABLE'
            asset.retention_until = None
        row.status, row.updated_at, row.error_code = 'READY', utcnow(), None
        await service.cleanup_assets(db, row, source_only=True)
        await tasks.finish(db, task_id, token)
        await db.commit()


async def keep_authorized(factory, settings, job_id, task_id, token):
    while True:
        await asyncio.sleep(5)
        async with factory() as db:
            await current(db, job_id, task_id, token, settings)
            await db.commit()


async def run_one(factory, storage, settings=None, *, editor=None, renderer=None):
    settings = settings or get_settings()
    async with factory() as db:
        task = await tasks.claim(db, kinds=('AVATAR_GENERATE',))
        await db.commit()
        if task is None:
            return False
        job_id, task_id, token = task.resource_id, task.id, task.lease_token
        row = await db.get(AvatarJob, job_id)
        owner = row.owner_user_id if row else None
    if owner is None:
        return True
    work = watch = None
    try:
        async with factory() as gate:
            # Account erasure waits for provider I/O and any started storage writes to settle.
            await send_gate(gate, owner, shared=True)
            work = asyncio.create_task(perform(factory, storage, settings, job_id, task_id, token,
                editor or ImageEditor(settings), renderer or Tha3Renderer(settings)))
            watch = asyncio.create_task(keep_authorized(factory, settings, job_id, task_id, token))
            try:
                done, _ = await asyncio.wait({work, watch}, return_when=asyncio.FIRST_COMPLETED)
                if work in done:
                    await work
                else:
                    await watch
            finally:
                work.cancel(); watch.cancel()
                await asyncio.gather(work, watch, return_exceptions=True)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        code = error.code if isinstance(error, PipelineError) else 'AUTHORIZATION_CHANGED' if isinstance(error, AppError) else 'AVATAR_GENERATION_FAILED'
        async with factory() as db:
            row = await db.get(AvatarJob, job_id)
            if row:
                from app.modules.family.service import context
                try:
                    await context(db, owner, row.family_id)
                    await db.refresh(row)
                except AppError:
                    pass
                if not row.deleted_at and row.status in service.RUNNING:
                    row.status, row.error_code, row.updated_at = 'FAILED', code, utcnow()
                    await service.cleanup_assets(db, row)
            await tasks.finish(db, task_id, token, error=True)
            await db.commit()
    return True


async def serve(*, once=False):
    from app.platform.db import session_factory
    from app.platform.storage import S3Storage
    settings = get_settings()
    storage = S3Storage(settings)
    while True:
        async with session_factory() as db:
            await service.maintenance(db)
            await db.commit()
        did_work = await run_one(session_factory, storage, settings)
        if once:
            return
        if not did_work:
            await asyncio.sleep(3)
