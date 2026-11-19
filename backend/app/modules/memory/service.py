import re
import unicodedata
from types import SimpleNamespace
from uuid import UUID, uuid5

from sqlalchemy import and_, or_, select

from app.modules.audit import service as audit
from app.modules.auth.service import codec
from app.modules.consent import service as consent
from app.modules.family import service as family
from app.modules.memory.models import FileAsset, Memory
from app.modules.memory.schemas import MemoryDraft
from app.platform.errors import AppError
from app.platform.identifiers import iso_utc, utcnow, uuid7
from app.platform.pagination import page_rows
from app.platform.resource_access import authorize, check_version, visible_subjects

SCOPES = ('VOICE', 'PORTRAIT', 'FAMILY_MEMORY', 'HEALTH_MEDICATION', 'CONVERSATION_SUMMARY', 'CAMERA_PROXIMITY', 'NOTIFICATION_TO_FAMILY')

# Chat drafts use FAMILY_MEMORY only. Health details must be entered through
# the separately authorized health workflow, even if an LLM calls them a hobby.
_MEDICAL_PLACE = r'(?:医科大学|医学院|医药公司|制药厂|医院|卫生院|诊所|医务室|药店|药房|药厂)'
_ORDINARY_MEDICAL_CONTEXT = re.compile(
    _MEDICAL_PLACE + r'(?:里|内|里面)?(?:工作|上班|任职|实习|读书|上学|学习|毕业)|'
    + _MEDICAL_PLACE + r'(?:里|内|里面)?(?:当|做|担任)(?:过|了)?(?:医生|医师|护士|药剂师|药师|保洁员?|会计|门卫|保安|司机|收银员|售货员)|'
    + _MEDICAL_PLACE + r'的(?:医生|医师|护士|药剂师|药师)|'
    + _MEDICAL_PLACE + r'(?:的)?(?:旁边|附近|对面|门口|隔壁|后面|前面)|'
    r'(?:当|做|担任|成为|是)(?:过|了)?(?:一名|一位)?(?:医生|医师|护士|药剂师|药师)')
_HEALTH_DRAFT = re.compile(
    r'药|醫|医|病|诊|症|疾|血压|血糖|血脂|胰岛素|过敏|过敏源|手术|住院|治疗|疗程|'
    r'疼|痛|头晕|胸闷|心慌|不舒服|呼吸困难|失眠|抑郁|焦虑|咳嗽|发烧|发热|癌|肿瘤|'
    r'患者|就诊|体检|复查|化验|拍片|输液|打针|服用|剂量|毫克|毫升|mg\b|ml\b|insulin|medication|diagnos|diabet|hypertension|'
    r'aspirin|阿司匹林|二甲双胍|硝苯地平|氨氯地平', re.IGNORECASE)


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


async def recall_prompts(db, actor, family_id, request_id):
    subject = actor.user_id
    member = await authorize(db, actor, family_id, subject, 'MEMORY_READ')
    if member.role != 'ELDER':
        return {'titles': []}
    try:
        await consent.explicit_scope(db, family_id, subject, subject, 'FAMILY_MEMORY')
    except AppError as error:
        if error.status_code in (403, 404):
            return {'titles': []}
        raise
    rows = await db.scalars(select(Memory.title).where(
        Memory.family_id == family_id, Memory.subject_user_id == subject,
        Memory.required_consent_scope == 'FAMILY_MEMORY', Memory.type.in_(('EVENT', 'PLACE', 'PREFERENCE')),
        Memory.verification_status == 'CONFIRMED', Memory.verified_at.is_not(None),
        Memory.revoked_at.is_(None), Memory.deleted_at.is_(None),
        or_(Memory.expires_at.is_(None), Memory.expires_at > utcnow()),
    ).order_by(Memory.updated_at.desc(), Memory.id.desc()).limit(8))
    await audit.record(db, subject, 'MEMORY_LIST_READ', 'MEMORY', family_id=family_id, request_id=request_id)
    return {'titles': list(dict.fromkeys(rows.all()))}


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
    from app.modules.memory.rag import changed
    await changed(db, row)
    await audit.record(db, actor.user_id, 'MEMORY_CREATED', 'MEMORY', row.id, row.family_id, request_id, metadata=idem.metadata)
    return await view(db, row)


async def draft_from_turn(db, actor, conversation, text, request_id, candidates, settings):
    """Save only an explicitly requested, grounded draft for an authorized reviewer."""
    from app.ai.signal_candidates import revalidate_semantic
    match = re.fullmatch(r'\s*请把这段记忆交给家人确认\s*[:：，,]?\s*(.+)', text)
    if not match:
        return False
    content = match[1].strip()
    normalized = ''.join(char for char in unicodedata.normalize('NFKC', content)
        if not char.isspace() and unicodedata.category(char) != 'Cf')
    # Remove only the matched occupation/place phrase from the screening copy.
    # The rest of the statement must still pass, e.g. "医院工作时每天吃药".
    if _HEALTH_DRAFT.search(_ORDINARY_MEDICAL_CONTEXT.sub('', normalized)):
        return False
    titles = {'LIFE_STORY': ('EVENT', '交流中的往事'), 'PREFERENCE_OR_TABOO': ('PREFERENCE', '交流中的偏好'),
              'PHOTO_BACKGROUND': ('EVENT', '交流中的照片背景')}
    candidates = revalidate_semantic(candidates, conversation_id=conversation.id,
        message_id=uuid5(conversation.id, request_id), current_text=text)
    selected = next((c for c in candidates if c.trigger_category in titles
        and c.attributes['semantic_evidence'].strip('。！! ') == content.strip('。！! ')), None)
    if not selected or re.search(r'\d{5,}|https?://|密码|验证码|银行卡|身份证|账号|电话号码|手机号码|药量|病历|诊断', content):
        return False
    fid, subject = conversation.family_id, actor.user_id
    try:
        await consent.explicit_scope(db, fid, subject, subject, 'FAMILY_MEMORY')
    except AppError as error:
        if error.status_code in (403, 404):
            return False
        raise
    for reviewer in await family.active_subjects(db, fid):
        if reviewer == subject:
            continue
        try:
            for permission in ('MEMORY_READ', 'MEMORY_WRITE'):
                await authorize(db, SimpleNamespace(user_id=reviewer), fid, subject, permission, 'FAMILY_MEMORY')
        except AppError as error:
            if error.status_code in (403, 404):
                continue
            raise
        kind, title = titles[selected.trigger_category]
        await create(db, actor, MemoryDraft(family_id=fid, subject_user_id=subject, type=kind, title=title,
            content=content, source='AI_CANDIDATE', required_consent_scope='FAMILY_MEMORY'),
            f'chat-memory:{conversation.id}:{request_id}', settings, request_id)
        return True
    return False


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
    from app.modules.memory.rag import changed
    await changed(db, row)
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
        if action == 'confirm' and row.source == 'AI_CANDIDATE' and actor.user_id == row.subject_user_id == row.source_user_id:
            raise AppError('PERMISSION_DENIED', '这条交流候选需由获准家属确认。', 403)
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
    from app.modules.memory.rag import changed
    await changed(db, row)
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
