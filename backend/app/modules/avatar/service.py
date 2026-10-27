import asyncio
from datetime import timedelta
import hashlib
from types import SimpleNamespace
from urllib.parse import urlsplit

from sqlalchemy import select

from app.modules.account.service import note_possible_copy
from app.modules.audit import service as audit
from app.modules.auth.service import active_user
from app.modules.avatar.models import AvatarJob
from app.modules.consent import service as consent
from app.modules.family import service as family
from app.modules.memory.file_validation import FilePreflightError, UploadDeclaration, verify_upload_bytes
from app.modules.memory.images import sanitize_photo
from app.modules.memory.models import FileAsset
from app.platform import tasks
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7, iso_utc

MAX_PACK = 24 * 1024 * 1024
RUNNING = ('UPLOADING', 'QUEUED', 'STYLIZING', 'PREPARING', 'RENDERING')


async def settled(operation):
    pending = asyncio.create_task(operation)
    try:
        return await asyncio.shield(pending)
    except asyncio.CancelledError:
        await pending
        raise


def capabilities(settings):
    brand = '千问' if settings.avatar_image_provider == 'qwen' else '豆包'
    label = f'{brand} · {urlsplit(settings.avatar_image_base_url or "").hostname or "未配置"} / {settings.avatar_image_model or "未配置"}'
    provider_id = hashlib.sha256(f'{settings.avatar_image_provider}:{settings.avatar_image_base_url}:{settings.avatar_image_model}:tha3-v2'.encode()).hexdigest()
    return dict(available=settings.avatar_generation_enabled and settings.app_env == 'dev', provider_id=provider_id,
        provider_label=label, max_photo_bytes=min(settings.file_max_size_bytes, 5242880),
        notice='照片将上传私有服务器，并发送至所列图像服务转为动漫立绘。生成后先预览，由您确认启用；念念仍是 AI。')


async def authorize(db, owner, fid):
    await active_user(db, owner, lock=False)
    _, member = await family.context(db, owner, fid)
    if member.role != 'ELDER':
        raise AppError('PERMISSION_DENIED', '仅由长辈本人制作自己的陪伴形象。', 403)
    return await consent.explicit_scope(db, fid, owner, owner, 'PORTRAIT')


async def access(db, actor, job_id, *, removal=False):
    row = await db.get(AvatarJob, job_id, populate_existing=True)
    if not row or row.owner_user_id != actor.user_id or row.deleted_at and not removal:
        raise AppError('AVATAR_NOT_FOUND', '制作任务不存在或不可访问。', 404)
    if removal:
        await family.context(db, actor.user_id, row.family_id)
    else:
        grant = await authorize(db, actor.user_id, row.family_id)
        await db.refresh(row)
        if row.deleted_at or grant != row.consent_id or row.expires_at and row.expires_at <= utcnow():
            raise AppError('AVATAR_NOT_FOUND', '形象授权或任务已失效。', 404)
    return row


async def view(db, row):
    pack = await db.get(FileAsset, row.pack_id) if row.pack_id else None
    return dict(id=str(row.id), family_id=str(row.family_id), owner_user_id=str(row.owner_user_id),
        consent_id=str(row.consent_id), status=row.status, version=row.version,
        error_code=row.error_code, created_at=iso_utc(row.created_at), expires_at=iso_utc(row.expires_at) if row.expires_at else None,
        confirmed_at=iso_utc(row.confirmed_at) if row.confirmed_at else None,
        pack_checksum=pack.checksum if pack and pack.status == 'AVAILABLE' else None)


def new_asset(owner, fid, job_id, suffix, mime, size=0, checksum='0' * 64):
    return FileAsset(id=uuid7(), owner_user_id=owner, family_id=fid,
        object_key=f'private/{fid}/avatars/{job_id}/{suffix}', media_type='PHOTO' if mime.startswith('image/') else 'OTHER',
        mime_type=mime, size_bytes=size, checksum=checksum, status='PENDING_UPLOAD',
        retention_until=utcnow() + timedelta(hours=24))


async def create(db, actor, body, key, storage, settings, request_id):
    caps = capabilities(settings)
    if not caps['available']:
        raise AppError('AVATAR_UNAVAILABLE', '照片制作服务尚未配置，请联系管理员。', 503)
    grant = await authorize(db, actor.user_id, body.family_id)
    if grant != body.consent_id or body.provider_id != caps['provider_id']:
        raise AppError('AVATAR_APPROVAL_CHANGED', '授权或照片处理服务已变化，请重新确认。', 409)
    idem = audit.Idempotency(key, 'avatar-create', body.model_dump(mode='json'))
    prior = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
    if prior:
        row = await access(db, actor, prior)
        return await upload_view(db, row, storage, settings)
    pending = await db.scalar(select(AvatarJob.id).where(AvatarJob.family_id == body.family_id,
        AvatarJob.owner_user_id == actor.user_id, AvatarJob.status.in_(RUNNING), AvatarJob.deleted_at.is_(None),
        AvatarJob.expires_at > utcnow()).limit(1))
    if pending:
        raise AppError('AVATAR_IN_PROGRESS', '已有制作任务，请查看进度或取消后重新选择。', 409)
    declaration = UploadDeclaration('PHOTO', body.mime_type, body.size_bytes, body.checksum)
    try:
        declaration.validate(max_size_bytes=min(settings.file_max_size_bytes, 5242880))
    except FilePreflightError:
        raise AppError('AVATAR_PHOTO_INVALID', '照片大小或格式不支持。', 422) from None
    job_id = uuid7()
    source = new_asset(actor.user_id, body.family_id, job_id, 'source', body.mime_type, body.size_bytes, body.checksum)
    pack = new_asset(actor.user_id, body.family_id, job_id, 'pack', 'application/zip')
    preview = new_asset(actor.user_id, body.family_id, job_id, 'preview', 'image/png')
    db.add_all([source, pack, preview]); await db.flush()
    row = AvatarJob(id=job_id, family_id=body.family_id, owner_user_id=actor.user_id, consent_id=grant,
        provider_id=body.provider_id, source_id=source.id, pack_id=pack.id, preview_id=preview.id,
        status='UPLOADING', version=1, expires_at=utcnow() + timedelta(hours=24))
    db.add(row)
    await audit.record(db, actor.user_id, 'AVATAR_PHOTO_AUTHORIZED', 'AVATAR', row.id, row.family_id,
        request_id, metadata=idem.metadata)
    return await upload_view(db, row, storage, settings)


async def upload_view(db, row, storage, settings):
    result = await view(db, row)
    if row.status == 'UPLOADING':
        source = await db.get(FileAsset, row.source_id)
        original_upload_deadline = row.created_at + timedelta(seconds=300)
        seconds = min(settings.file_url_seconds, int((original_upload_deadline - utcnow()).total_seconds()))
        if seconds <= 0:
            raise AppError('AVATAR_UPLOAD_EXPIRED', '照片上传已过期，请取消任务后重新选择。', 409)
        result.update(upload_url=await storage.upload_url(source.object_key, source.mime_type, source.size_bytes, seconds),
            required_headers={'Content-Type': source.mime_type, 'Content-Length': str(source.size_bytes)})
    return result


async def complete_upload(db, actor, job_id, key, storage, settings, request_id):
    row = await access(db, actor, job_id)
    idem = audit.Idempotency(key, 'avatar-upload:' + str(job_id), {})
    if await idem.previous(db, actor.user_id, settings.idempotency_seconds) or row.status != 'UPLOADING':
        return await view(db, row)
    source = await db.get(FileAsset, row.source_id)
    if source.status != 'PENDING_UPLOAD' or row.created_at + timedelta(seconds=360) <= utcnow():
        raise AppError('AVATAR_UPLOAD_EXPIRED', '上传已过期，请取消后重新选择。', 409)
    try:
        data = await storage.read(source.object_key, min(settings.file_max_size_bytes, 5242880))
        verify_upload_bytes(UploadDeclaration('PHOTO', source.mime_type, source.size_bytes, source.checksum),
            [data], max_size_bytes=min(settings.file_max_size_bytes, 5242880))
        clean = await asyncio.to_thread(sanitize_photo, data, source.mime_type, settings.file_max_pixels, 5242880)
    except Exception:
        raise AppError('AVATAR_PHOTO_INVALID', '照片损坏、过大或校验不一致，请重新选择。', 422) from None
    await settled(storage.write(source.object_key + '.safe', clean, source.mime_type))
    await settled(storage.delete(source.object_key))
    source.status, source.size_bytes, source.checksum = 'AVAILABLE', len(clean), hashlib.sha256(clean).hexdigest()
    source.retention_until = None
    row.status, row.updated_at = 'QUEUED', utcnow()
    await tasks.enqueue(db, 'AVATAR_GENERATE', row.family_id, row.id, row.version)
    await audit.record(db, actor.user_id, 'AVATAR_QUEUED', 'AVATAR', row.id, row.family_id, request_id, metadata=idem.metadata)
    return await view(db, row)


async def cleanup_assets(db, row, *, source_only=False):
    ids = [row.source_id] if source_only else [row.source_id, row.pack_id, row.preview_id]
    for asset_id in ids:
        asset = await db.get(FileAsset, asset_id) if asset_id else None
        if asset and asset.status != 'DELETED':
            asset.status, asset.deleted_at = 'DELETE_REQUESTED', utcnow()
            await tasks.enqueue(db, 'FILE_CLEANUP', row.family_id, asset.id, 1)


async def cancel(db, row):
    if row.deleted_at:
        return
    row.status, row.deleted_at, row.updated_at = 'CANCELLED', utcnow(), utcnow()
    await cleanup_assets(db, row)


async def confirm(db, actor, job_id, body, key, settings, request_id):
    row = await access(db, actor, job_id)
    pack = await db.get(FileAsset, row.pack_id)
    if row.status not in ('READY', 'ACTIVE') or not pack or pack.status != 'AVAILABLE' or pack.checksum != body.pack_checksum:
        raise AppError('AVATAR_PREVIEW_REQUIRED', '请下载并预览当前生成结果后再确认。', 409)
    idem = audit.Idempotency(key, 'avatar-confirm:' + str(job_id), body.model_dump())
    if not await idem.previous(db, actor.user_id, settings.idempotency_seconds) and row.status != 'ACTIVE':
        others = (await db.scalars(select(AvatarJob).where(AvatarJob.family_id == row.family_id,
            AvatarJob.owner_user_id == actor.user_id, AvatarJob.status == 'ACTIVE', AvatarJob.id != row.id))).all()
        for old in others:
            await cancel(db, old)
        await db.flush()
        row.status, row.confirmed_at, row.expires_at, row.updated_at = 'ACTIVE', utcnow(), None, utcnow()
        await audit.record(db, actor.user_id, 'AVATAR_CONFIRMED', 'AVATAR', row.id, row.family_id, request_id, metadata=idem.metadata)
    return await view(db, row)


async def asset_content(db, actor, job_id, kind, storage):
    row = await access(db, actor, job_id)
    if row.status not in ('READY', 'ACTIVE'):
        raise AppError('AVATAR_NOT_READY', '角色尚未生成完成。', 409)
    asset = await db.get(FileAsset, row.pack_id if kind == 'pack' else row.preview_id)
    if not asset or asset.status != 'AVAILABLE' or asset.deleted_at:
        raise AppError('AVATAR_NOT_FOUND', '角色资源已不可用。', 404)
    data = await storage.read(asset.object_key + '.safe', MAX_PACK if kind == 'pack' else 5 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != asset.checksum:
        raise AppError('AVATAR_CONTENT_INVALID', '角色资源校验失败，请重新制作。', 503)
    return data, asset.mime_type


async def latest(db, actor, fid):
    grant = await authorize(db, actor.user_id, fid)
    row = await db.scalar(select(AvatarJob).where(AvatarJob.family_id == fid, AvatarJob.owner_user_id == actor.user_id,
        AvatarJob.consent_id == grant, AvatarJob.deleted_at.is_(None)).order_by(AvatarJob.created_at.desc()).limit(1))
    if row and row.expires_at and row.expires_at <= utcnow():
        return None
    return await view(db, row) if row else None


async def invalidate_consent(db, fid, owner):
    rows = (await db.scalars(select(AvatarJob).where(AvatarJob.family_id == fid, AvatarJob.owner_user_id == owner,
        AvatarJob.deleted_at.is_(None)))).all()
    for row in rows:
        await cancel(db, row)


async def maintenance(db):
    dead = await tasks.dead_resource_ids(db, 'AVATAR_GENERATE')
    rows = (await db.scalars(select(AvatarJob).where(AvatarJob.deleted_at.is_(None)).order_by(AvatarJob.family_id, AvatarJob.id))).all()
    for row in rows:
        try:
            await access(db, SimpleNamespace(user_id=row.owner_user_id), row.id)
        except AppError:
            await cancel(db, row)
            continue
        if row.id in dead and row.status in RUNNING:
            row.status, row.error_code, row.updated_at = 'FAILED', 'WORKER_INTERRUPTED', utcnow()
            await cleanup_assets(db, row, source_only=True)


async def note_image_send(db, row, settings):
    await note_possible_copy(db, row.owner_user_id, 'IMAGE:' + (urlsplit(settings.avatar_image_base_url).hostname or 'unknown')[:150])
