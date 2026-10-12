import asyncio
import hmac
from datetime import timedelta

from sqlalchemy import select

from app.modules.audit import service as audit
from app.modules.auth.service import codec
from app.modules.memory import service as memory
from app.modules.memory.file_validation import FilePreflightError, UploadDeclaration, verify_upload_bytes
from app.modules.memory.images import sanitize_photo
from app.modules.memory.models import FileAsset
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7
from app.platform.storage import S3Storage


def store(request, settings):
    return getattr(request.app.state, 'object_storage', None) or S3Storage(settings)


async def access(db, actor, file_id, *, write=False, removal=False):
    row = await db.get(FileAsset, file_id)
    if not row or not row.memory_id:
        raise AppError('FILE_NOT_FOUND', '照片不存在或不可访问。', 404)
    try:
        parent = await memory.access(db, actor, row.memory_id, write=write, removal=removal)
    except AppError as error:
        if error.status_code in (403, 404):
            raise AppError('FILE_NOT_FOUND', '照片不存在或不可访问。', 404) from None
        raise
    await db.refresh(row)
    if row.family_id != parent.family_id or row.owner_user_id != parent.subject_user_id or row.deleted_at or row.status in ('DELETE_REQUESTED', 'DELETED'):
        raise AppError('FILE_NOT_FOUND', '照片不存在或不可访问。', 404)
    return row


async def upload(db, actor, body, storage, settings, request_id):
    parent = await memory.access(db, actor, body.memory_id, write=True)
    declaration = UploadDeclaration(body.media_type, body.mime_type, body.size_bytes, body.checksum)
    try:
        declaration.validate(max_size_bytes=settings.file_max_size_bytes)
    except FilePreflightError as error:
        raise AppError(str(error), '仅支持大小符合要求的 JPG、PNG 或 WebP 照片。', 422) from None
    now = utcnow()
    file_id = uuid7()
    row = FileAsset(id=file_id, owner_user_id=parent.subject_user_id, family_id=parent.family_id,
        memory_id=parent.id, object_key=f'private/{parent.family_id}/{file_id}/upload', media_type=body.media_type,
        mime_type=body.mime_type, size_bytes=body.size_bytes, checksum=body.checksum.lower(),
        status='PENDING_UPLOAD', retention_until=now + timedelta(seconds=settings.upload_expiry_seconds), created_at=now)
    url = await storage.upload_url(row.object_key, row.mime_type, row.size_bytes, settings.file_url_seconds)
    db.add(row)
    await audit.record(db, actor.user_id, 'FILE_UPLOAD_REQUESTED', 'FILE', row.id, row.family_id, request_id)
    return dict(file=memory.file_view(row), upload_url=url, expires_at=(now + timedelta(seconds=settings.file_url_seconds)).isoformat(),
                required_headers={'Content-Type': row.mime_type, 'Content-Length': str(row.size_bytes)})


async def confirm(db, actor, file_id, body, key, storage, settings, request_id):
    row = await access(db, actor, file_id, write=True)
    if not await audit.performed(db, actor.user_id, 'FILE_UPLOAD_REQUESTED', row.id):
        raise AppError('PERMISSION_DENIED', '请由上传请求的发起人确认。', 403)
    idem = audit.Idempotency(key, f'file-confirm:{file_id}', body.model_dump(mode='json'))
    if await idem.previous(db, actor.user_id, settings.idempotency_seconds):
        return memory.file_view(row)
    if row.status != 'PENDING_UPLOAD' or row.retention_until and row.retention_until <= utcnow():
        raise AppError('VALIDATION_ERROR', '此上传已确认或失效，请重新上传。', 400)
    if not hmac.compare_digest(body.checksum.lower(), row.checksum):
        raise AppError('FILE_CHECKSUM_MISMATCH', '照片校验不一致，请重新上传。', 422)
    try:
        data = await storage.read(row.object_key, settings.file_max_size_bytes)
        verify_upload_bytes(UploadDeclaration(row.media_type, row.mime_type, row.size_bytes, row.checksum),
                            [data], max_size_bytes=settings.file_max_size_bytes)
        clean = await asyncio.to_thread(sanitize_photo, data, row.mime_type, settings.file_max_pixels, settings.file_max_size_bytes)
    except FilePreflightError:
        row.status = 'QUARANTINED'
        await audit.record(db, actor.user_id, 'FILE_QUARANTINED', 'FILE', row.id, row.family_id, request_id, metadata=idem.metadata)
        # A committed quarantine response is explicit and is never AVAILABLE.
        return memory.file_view(row)
    await storage.write(row.object_key + '.safe', clean, row.mime_type)
    await storage.delete(row.object_key)
    row.status, row.retention_until = 'AVAILABLE', None
    await audit.record(db, actor.user_id, 'FILE_CONFIRMED', 'FILE', row.id, row.family_id, request_id, metadata=idem.metadata)
    return memory.file_view(row)


def ticket(settings, row, user_id, expires):
    return codec(settings).opaque('file-download', f'{row.id}:{user_id}:{expires}')


async def download_url(db, actor, file_id, settings, request_id):
    row = await access(db, actor, file_id)
    if row.status != 'AVAILABLE':
        raise AppError('FILE_NOT_FOUND', '照片尚不可用。', 404)
    expires = int(utcnow().timestamp()) + settings.file_url_seconds
    signature = ticket(settings, row, actor.user_id, expires)
    await audit.record(db, actor.user_id, 'FILE_DOWNLOAD_URL', 'FILE', row.id, row.family_id, request_id)
    return dict(download_url=f'{settings.public_base_url.rstrip("/")}/v1/files/{row.id}/content?expires={expires}&signature={signature}',
                expires_at=(utcnow() + timedelta(seconds=settings.file_url_seconds)).isoformat())


async def content(db, actor, file_id, expires, signature, storage, settings, request_id):
    row = await access(db, actor, file_id)
    now = int(utcnow().timestamp())
    if row.status != 'AVAILABLE' or not now < expires <= now + settings.file_url_seconds or not hmac.compare_digest(
        signature, ticket(settings, row, actor.user_id, expires)
    ):
        raise AppError('FILE_NOT_FOUND', '照片链接已失效，请重新打开。', 404)
    data = await storage.read(row.object_key + '.safe', settings.file_max_size_bytes)
    await audit.record(db, actor.user_id, 'FILE_READ', 'FILE', row.id, row.family_id, request_id)
    return data, row.mime_type


async def delete(db, actor, file_id, key, settings, request_id):
    idem = audit.Idempotency(key, f'file-delete:{file_id}', {})
    if await idem.previous(db, actor.user_id, settings.idempotency_seconds):
        previous = await db.get(FileAsset, file_id)
        from app.platform.resource_access import authorize
        await authorize(db, actor, previous.family_id, previous.owner_user_id, 'MEMORY_WRITE')
        return {'status': 'PENDING'}
    row = await access(db, actor, file_id, write=True, removal=True)
    row.status, row.deleted_at = 'DELETE_REQUESTED', utcnow()
    await audit.record(db, actor.user_id, 'FILE_DELETE_REQUESTED', 'FILE', row.id, row.family_id, request_id, metadata=idem.metadata)
    return {'status': 'PENDING'}


async def cleanup(db, storage, now=None):
    now = now or utcnow()
    rows = (await db.scalars(select(FileAsset).where(
        (FileAsset.status == 'DELETE_REQUESTED') | ((FileAsset.status.in_(('PENDING_UPLOAD', 'QUARANTINED'))) & (FileAsset.retention_until <= now))
    ).limit(100).with_for_update(skip_locked=True))).all()
    for row in rows:
        try:
            await storage.delete(row.object_key)
            await storage.delete(row.object_key + '.safe')
            row.status, row.deleted_at = 'DELETED', now
        except AppError:
            # Leave a durable non-readable state for the next bounded cleanup run.
            await audit.record(db, None, 'FILE_CLEANUP_FAILED', 'FILE', row.id, row.family_id, result='FAILED')
    # A still-live signed PUT may recreate the raw upload after confirmation.
    # Sweep it once the maximum configured URL lifetime (300s) plus clock
    # margin has elapsed. The client can never write the separate .safe key.
    available = (await db.scalars(select(FileAsset).where(FileAsset.status == 'AVAILABLE',
        FileAsset.created_at < now - timedelta(seconds=360),
        ~FileAsset.id.in_(audit.recorded_targets('FILE_UPLOAD_WINDOW_CLOSED', 'FILE'))
    ).limit(100).with_for_update(skip_locked=True))).all()
    for row in available:
        if await audit.performed(db, None, 'FILE_UPLOAD_WINDOW_CLOSED', row.id):
            continue
        try:
            await storage.delete(row.object_key)
            await audit.record(db, None, 'FILE_UPLOAD_WINDOW_CLOSED', 'FILE', row.id, row.family_id)
        except AppError:
            await audit.record(db, None, 'FILE_CLEANUP_FAILED', 'FILE', row.id, row.family_id, result='FAILED')
    return len(rows)
