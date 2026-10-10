from uuid import UUID

from sqlalchemy import or_, select

from app.modules.audit import service as audit
from app.modules.auth.service import codec
from app.modules.consent.models import Consent
from app.modules.family import service as family
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7
from app.platform.pagination import page_rows


def view(row: Consent) -> dict:
    result = {key: str(getattr(row, key)) for key in ('id', 'family_id', 'subject_user_id', 'grantee_user_id')}
    result.update(scope=row.scope, status=row.status, version=row.version, source=row.source)
    for key in ('granted_at', 'revoked_at', 'expires_at'):
        if getattr(row, key):
            result[key] = getattr(row, key).isoformat()
    return result


async def latest(db, family_id, subject, grantee, scope) -> Consent | None:
    return await db.scalar(select(Consent).where(Consent.family_id == family_id,
                            Consent.subject_user_id == subject, Consent.grantee_user_id == grantee,
                            Consent.scope == scope).order_by(Consent.created_at.desc(), Consent.id.desc()).limit(1))


async def require_scope(db, family_id: UUID, subject: UUID, grantee: UUID, scope: str) -> None:
    await family.context(db, grantee, family_id)
    await family.require_member(db, family_id, subject)
    if subject == grantee:
        return
    row = await latest(db, family_id, subject, grantee, scope)
    if not row or row.status != 'GRANTED' or row.expires_at and row.expires_at <= utcnow():
        raise AppError('PERMISSION_CONSENT_REQUIRED', '尚未获得此项授权，或授权已撤回。', 403)


async def visible(db, actor, row: Consent):
    fam, member = await family.context(db, actor.user_id, row.family_id)
    admin = fam.created_by_user_id == actor.user_id or member.permission_codes.get('MEMBER_ADMIN') is True
    if actor.user_id not in (row.subject_user_id, row.grantee_user_id) and not admin:
        raise AppError('CONSENT_NOT_FOUND', '授权记录不存在或无权查看。', 404)


async def detail(db, actor, consent_id: UUID, request_id: str) -> dict:
    row = await db.get(Consent, consent_id)
    if not row:
        raise AppError('CONSENT_NOT_FOUND', '授权记录不存在或无权查看。', 404)
    await visible(db, actor, row)
    await audit.record(db, actor.user_id, 'CONSENT_READ', 'CONSENT', row.id, row.family_id, request_id)
    return view(row)


async def grant(db, actor, body, key, settings, request_id):
    await family.context(db, actor.user_id, body.family_id)
    if body.subject_user_id != actor.user_id:
        raise AppError('CONSENT_SUBJECT_MISMATCH', '只能由数据主体本人授予授权。', 403)
    await family.require_member(db, body.family_id, body.grantee_user_id)
    idem = audit.Idempotency(key, 'consent-grant', body.model_dump(mode='json'))
    previous = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
    if previous:
        return await detail(db, actor, previous, request_id)
    now = utcnow()
    if body.expires_at and body.expires_at <= now:
        raise AppError('VALIDATION_ERROR', '授权到期时间必须晚于当前时间。', 422)
    old = await latest(db, body.family_id, actor.user_id, body.grantee_user_id, body.scope)
    row = Consent(id=uuid7(), family_id=body.family_id, subject_user_id=actor.user_id,
                  grantor_user_id=actor.user_id, grantee_user_id=body.grantee_user_id, scope=body.scope,
                  status='GRANTED', version=(old.version + 1 if old else 1), source=body.source,
                  granted_at=now, expires_at=body.expires_at, created_at=now)
    event = await audit.record(db, actor.user_id, 'CONSENT_GRANTED', 'CONSENT', row.id,
                               row.family_id, request_id, metadata=idem.metadata)
    row.audit_log_id = event.id
    db.add(row)
    await db.flush()
    return view(row)


async def revoke(db, actor, consent_id, body, key, settings, request_id):
    old = await db.get(Consent, consent_id)
    if not old:
        raise AppError('CONSENT_NOT_FOUND', '授权记录不存在或无权查看。', 404)
    await family.context(db, actor.user_id, old.family_id)
    if actor.user_id not in (old.subject_user_id, old.grantor_user_id):
        raise AppError('PERMISSION_DENIED', '只有数据主体或原授权人可撤回授权。', 403)
    idem = audit.Idempotency(key, 'consent-revoke:' + str(consent_id), body.model_dump(mode='json'))
    previous = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
    if previous:
        return await detail(db, actor, previous, request_id)
    current = await latest(db, old.family_id, old.subject_user_id, old.grantee_user_id, old.scope)
    if current.id != old.id:
        raise AppError('ETAG_MISMATCH', '授权已有新记录，请刷新后选择当前授权。', 409)
    if old.status != 'GRANTED':
        raise AppError('CONSENT_ALREADY_REVOKED', '此项授权已撤回或失效。', 409)
    now = utcnow()
    row = Consent(id=uuid7(), family_id=old.family_id, subject_user_id=old.subject_user_id,
                  grantor_user_id=actor.user_id, grantee_user_id=old.grantee_user_id, scope=old.scope,
                  status='REVOKED', version=old.version + 1, source='SETTINGS',
                  revoked_at=now, created_at=now)
    event = await audit.record(db, actor.user_id, 'CONSENT_REVOKED', 'CONSENT', row.id,
                               row.family_id, request_id, metadata=idem.metadata)
    row.audit_log_id = event.id
    db.add(row)
    await db.flush()
    return view(row)


async def listing(db, actor, family_id, subject, grantee, scope, limit, cursor, settings, request_id):
    families = await family.visibility(db, actor.user_id)
    allowed = []
    for fid, admin in families:
        if family_id and fid != family_id:
            continue
        predicate = Consent.family_id == fid
        if not admin:
            predicate = predicate & or_(Consent.subject_user_id == actor.user_id, Consent.grantee_user_id == actor.user_id)
        allowed.append(predicate)
    query = select(Consent).where(or_(*allowed) if allowed else Consent.id.is_(None))
    for column, value in [(Consent.subject_user_id, subject), (Consent.grantee_user_id, grantee), (Consent.scope, scope)]:
        if value is not None:
            query = query.where(column == value)
    binding = f'consents:{actor.user_id}:{family_id}:{subject}:{grantee}:{scope}'
    rows, page = await page_rows(db, query, Consent, codec(settings), binding, limit, cursor)
    await audit.record(db, actor.user_id, 'CONSENT_LIST_READ', 'CONSENT', request_id=request_id)
    return {'items': [view(row) for row in rows], 'page': page, 'request_id': request_id}
