from uuid import UUID

from sqlalchemy import and_, or_, select

from app.modules.audit import service as audit
from app.modules.auth.service import codec
from app.modules.family import service as family
from app.modules.memory.models import FileAsset, Memory
from app.platform.errors import AppError
from app.platform.identifiers import iso_utc, utcnow, uuid7
from app.platform.pagination import page_rows
from app.platform.resource_access import authorize, check_version, visible_subjects

SCOPES = ('VOICE', 'PORTRAIT', 'FAMILY_MEMORY', 'HEALTH_MEDICATION', 'CONVERSATION_SUMMARY', 'CAMERA_PROXIMITY', 'NOTIFICATION_TO_FAMILY')


async def access(db, actor, memory_id, *, write=False, removal=False):
    row = await db.get(Memory, memory_id)
    if row:
        try:
            await family.context(db, actor.user_id, row.family_id)
        except AppError as error:
            if error.status_code in (403, 404):
                raise AppError('MEMORY_NOT_FOUND', '记忆不存在或无权访问。', 404) from None
            raise
        await db.refresh(row)
    if not row or row.deleted_at or (not removal and (row.revoked_at or row.verification_status in ('REVOKED', 'DELETED'))):
        raise AppError('MEMORY_NOT_FOUND', '记忆不存在或无权访问。', 404)
    try:
        await authorize(db, actor, row.family_id, row.subject_user_id,
                        'MEMORY_WRITE' if write else 'MEMORY_READ', None if removal else row.required_consent_scope)
        if not removal:
            if row.expires_at and row.expires_at <= utcnow():
                raise AppError('MEMORY_NOT_FOUND', '记忆不存在或无权访问。', 404)
            if row.visibility == 'OWNER_ONLY' and actor.user_id != row.subject_user_id:
                raise AppError('MEMORY_NOT_FOUND', '记忆不存在或无权访问。', 404)
            if not write and row.verification_status != 'CONFIRMED':
                await authorize(db, actor, row.family_id, row.subject_user_id, 'MEMORY_WRITE', row.required_consent_scope)
    except AppError as error:
        if error.status_code in (403, 404):
            raise AppError('MEMORY_NOT_FOUND', '记忆不存在或无权访问。', 404) from None
        raise
    return row


def file_view(row):
    return dict(id=str(row.id), media_type=row.media_type, mime_type=row.mime_type,
                size_bytes=row.size_bytes, checksum=row.checksum, status=row.status,
                created_at=iso_utc(row.created_at))


async def view(db, row):
    result = {key: str(getattr(row, key)) for key in ('id', 'family_id', 'subject_user_id')}
    for key in ('type', 'title', 'content', 'source', 'verification_status', 'visibility', 'required_consent_scope', 'version'):
        result[key] = getattr(row, key)
    for key in ('expires_at', 'created_at', 'updated_at'):
        if getattr(row, key):
            result[key] = iso_utc(getattr(row, key))
    if row.verified_by:
        result['verified_by'] = str(row.verified_by)
    files = (await db.scalars(select(FileAsset).where(FileAsset.memory_id == row.id,
             FileAsset.status == 'AVAILABLE', FileAsset.deleted_at.is_(None)))).all()
    result['attachments'] = [dict(id=str(f.id), media_type=f.media_type, status=f.status) for f in files]
    result['source_label'] = '待确认候选' if row.verification_status != 'CONFIRMED' else '已人工确认的家庭记忆'
    result['access_scope_label'] = '仅本人' if row.visibility == 'OWNER_ONLY' else '按当前授权可见'
    return result


async def detail(db, actor, memory_id, request_id):
    row = await access(db, actor, memory_id)
    await audit.record(db, actor.user_id, 'MEMORY_READ', 'MEMORY', row.id, row.family_id, request_id)
    return await view(db, row)


async def attachments(db, row, ids):
    for file_id in ids:
        asset = await db.get(FileAsset, file_id)
        if not asset or asset.memory_id != row.id or asset.family_id != row.family_id or asset.status != 'AVAILABLE' or asset.deleted_at:
            raise AppError('FILE_NOT_FOUND', '照片不可用，请重新选择。', 404)
    current = (await db.scalars(select(FileAsset).where(FileAsset.memory_id == row.id, FileAsset.status == 'AVAILABLE'))).all()
    for asset in current:
        if asset.id not in ids:
            asset.status, asset.deleted_at = 'DELETE_REQUESTED', utcnow()


async def create(db, actor, body, key, settings, request_id):
    await authorize(db, actor, body.family_id, body.subject_user_id, 'MEMORY_WRITE', body.required_consent_scope)
    if body.visibility == 'OWNER_ONLY' and actor.user_id != body.subject_user_id:
        raise AppError('PERMISSION_DENIED', '仅本人可创建仅本人可见的记忆。', 403)
    idem = audit.Idempotency(key, 'memory-create', body.model_dump(mode='json'))
    previous = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
    if previous:
        return await detail(db, actor, previous, request_id)
    if body.attachment_ids:
        raise AppError('VALIDATION_ERROR', '请先创建记忆，再为它上传照片。', 422)
    if body.expires_at and body.expires_at <= utcnow():
        raise AppError('VALIDATION_ERROR', '有效期必须晚于当前时间。', 422)
    now = utcnow()
    row = Memory(id=uuid7(), family_id=body.family_id, subject_user_id=body.subject_user_id,
        source_user_id=actor.user_id, type=body.type, title=body.title, content=body.content,
        source=body.source or ('USER' if actor.user_id == body.subject_user_id else 'FAMILY_MEMBER'),
        required_consent_scope=body.required_consent_scope, visibility=body.visibility,
        verification_status=body.verification_status, expires_at=body.expires_at,
        verified_by=actor.user_id if body.verification_status == 'CONFIRMED' else None,
        verified_at=now if body.verification_status == 'CONFIRMED' else None, created_at=now, updated_at=now)
    db.add(row)
    await db.flush()
    await audit.record(db, actor.user_id, 'MEMORY_CREATED', 'MEMORY', row.id, row.family_id, request_id, metadata=idem.metadata)
    return await view(db, row)


async def update(db, actor, memory_id, body, expected, request_id):
    row = await access(db, actor, memory_id, write=True)
    check_version(row, expected)
    if body.expires_at and body.expires_at <= utcnow():
        raise AppError('VALIDATION_ERROR', '有效期必须晚于当前时间。', 422)
    if body.visibility == 'OWNER_ONLY' and actor.user_id != row.subject_user_id:
        raise AppError('PERMISSION_DENIED', '仅本人可设为仅本人可见。', 403)
    values = body.model_dump(exclude_unset=True)
    if 'attachment_ids' in values:
        await attachments(db, row, values.pop('attachment_ids'))
    for key, value in values.items():
        setattr(row, key, value)
    if {'title', 'content', 'type'} & values.keys():
        row.verification_status, row.verified_by, row.verified_at = 'PENDING', None, None
    row.version += 1
    row.updated_at = utcnow()
    await audit.record(db, actor.user_id, 'MEMORY_UPDATED', 'MEMORY', row.id, row.family_id, request_id)
    return await view(db, row)


async def action(db, actor, memory_id, action, body, key, settings, request_id):
    if action == 'delete':
        idem = audit.Idempotency(key, f'memory-delete:{memory_id}', {})
        prior = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
        if prior:
            old = await db.get(Memory, memory_id)
            if old:
                await authorize(db, actor, old.family_id, old.subject_user_id, 'MEMORY_WRITE')
                return dict(id=str(prior), status='PENDING', created_at=iso_utc(old.updated_at))
    removal = action in ('revoke', 'delete')
    row = await access(db, actor, memory_id, write=True, removal=removal)
    idem = audit.Idempotency(key, f'memory-{action}:{memory_id}', {}) if key else None
    if idem and await idem.previous(db, actor.user_id, settings.idempotency_seconds):
        return await view(db, row)
    now = utcnow()
    if action in ('confirm', 'reject'):
        if row.verification_status != 'PENDING':
            raise AppError('VALIDATION_ERROR', '只有待确认候选可进行此操作。', 400)
        row.verification_status = 'CONFIRMED' if action == 'confirm' else 'REJECTED'
        if action == 'confirm':
            row.verified_by, row.verified_at = actor.user_id, now
    elif action == 'revoke':
        row.verification_status, row.revoked_at = 'REVOKED', now
    elif action == 'delete':
        row.verification_status, row.deleted_at = 'DELETED', now
        files = (await db.scalars(select(FileAsset).where(FileAsset.memory_id == row.id, FileAsset.status != 'DELETED'))).all()
        for asset in files:
            asset.status, asset.deleted_at = 'DELETE_REQUESTED', now
    row.version += 1
    row.updated_at = now
    event = await audit.record(db, actor.user_id, 'MEMORY_' + action.upper(), 'MEMORY', row.id, row.family_id,
                               request_id, metadata=idem.metadata if idem else {})
    if action == 'delete':
        return dict(id=str(row.id), status='PENDING', created_at=iso_utc(row.updated_at))
    return await view(db, row)


async def feedback(db, actor, memory_id, body, key, settings, request_id):
    row = await access(db, actor, memory_id)
    idem = audit.Idempotency(key, f'memory-feedback:{memory_id}', body.model_dump(mode='json'))
    if await idem.previous(db, actor.user_id, settings.idempotency_seconds):
        return {'status': 'RECEIVED'}
    await audit.record(db, actor.user_id, 'MEMORY_FEEDBACK', 'MEMORY', row.id, row.family_id,
                       request_id, metadata={'kind': body.kind, **idem.metadata})
    return {'status': 'RECEIVED'}


async def listing(db, actor, filters, limit, cursor, settings, request_id):
    clauses = []
    pending = filters.get('pending_confirmation') or filters.get('verification_status') in ('PENDING', 'REJECTED')
    for fid, _ in sorted(await family.visibility(db, actor.user_id), key=lambda x: str(x[0])):
        if filters.get('family_id') and filters['family_id'] != fid:
            continue
        for scope in SCOPES:
            subjects = await visible_subjects(db, actor, fid, 'MEMORY_WRITE' if pending else 'MEMORY_READ', scope)
            clauses.append(and_(Memory.family_id == fid, Memory.subject_user_id.in_(subjects), Memory.required_consent_scope == scope))
    query = select(Memory).where(or_(*clauses) if clauses else Memory.id.is_(None),
        Memory.deleted_at.is_(None), Memory.revoked_at.is_(None),
        or_(Memory.expires_at.is_(None), Memory.expires_at > utcnow()),
        or_(Memory.visibility != 'OWNER_ONLY', Memory.subject_user_id == actor.user_id))
    desired = 'PENDING' if filters.get('pending_confirmation') else filters.get('verification_status') or 'CONFIRMED'
    query = query.where(Memory.verification_status == desired, Memory.verification_status.in_(('CONFIRMED', 'PENDING', 'REJECTED')))
    for key in ('subject_user_id', 'type', 'visibility'):
        if filters.get(key):
            query = query.where(getattr(Memory, key) == filters[key])
    if filters.get('q'):
        query = query.where(or_(Memory.title.contains(filters['q'], autoescape=True), Memory.content.contains(filters['q'], autoescape=True)))
    binding = 'memories:' + str(actor.user_id) + ':' + str(sorted((k, str(v)) for k, v in filters.items()))
    rows, page = await page_rows(db, query, Memory, codec(settings), binding, limit, cursor)
    await audit.record(db, actor.user_id, 'MEMORY_LIST_READ', 'MEMORY', request_id=request_id)
    return dict(items=[await view(db, row) for row in rows], page=page, request_id=request_id)
