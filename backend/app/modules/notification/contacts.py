"""Member-owned contact routes. Numbers are never editable by another member."""
from types import SimpleNamespace

from cryptography.fernet import Fernet, InvalidToken
from pydantic import Field
from sqlalchemy import delete, select

from app.modules.audit import service as audit
from app.modules.auth.schemas import Input
from app.modules.auth.service import active_user, display_names
from app.modules.consent import service as consent
from app.modules.family import service as family
from app.modules.family.models import FamilyMember
from app.modules.notification.models import FamilyContact
from app.platform.config import get_settings
from app.platform.errors import AppError
from app.platform.identifiers import utcnow


class ContactInput(Input):
    phone: str = Field(default='', pattern=r'^(?:\+[1-9][0-9]{6,14})?$')
    share_phone: bool = False
    emergency: bool = False
    ntfy_topic: str = Field(default='', pattern=r'^[A-Za-z0-9_-]{0,120}$')


def cipher():
    try:
        return Fernet(get_settings().contact_encryption_key.get_secret_value().encode())
    except (ValueError, TypeError):
        raise AppError('CONTACT_CONFIGURATION_REQUIRED', '服务端尚未配置联系人加密密钥。', 503) from None


def decrypt(value):
    if not value:
        return ''
    try:
        return cipher().decrypt(value.encode()).decode()
    except InvalidToken:
        raise AppError('CONTACT_CONFIGURATION_REQUIRED', '联系人暂时不可用，请检查服务端加密配置。', 503) from None


async def current(db, fid, uid):
    return await db.scalar(select(FamilyContact).where(FamilyContact.family_id == fid,
        FamilyContact.user_id == uid).execution_options(populate_existing=True))


def view(row):
    return dict(version=row.version if row else 0, phone=decrypt(row.phone_ciphertext) if row else '',
        share_phone=row.share_phone if row else False, emergency=row.emergency if row else False,
        ntfy_topic=decrypt(row.topic_ciphertext) if row else '')


async def read(db, actor, fid):
    fam, member = await family.context(db, actor.user_id, fid)
    result = view(await current(db, fid, actor.user_id))
    result['recipients'] = []
    if member.role == 'ELDER':
        members = (await db.scalars(select(FamilyMember).where(FamilyMember.family_id == fid,
            FamilyMember.status == 'ACTIVE', FamilyMember.role.in_(('CHILD', 'CAREGIVER', 'EMERGENCY_CONTACT'))))).all()
        names = await display_names(db, [m.user_id for m in members])
        for target in members:
            if target.user_id not in names:
                continue
            scopes = {}
            for scope in ('NOTIFICATION_TO_FAMILY', 'HEALTH_MEDICATION'):
                grant = await consent.latest(db, fid, actor.user_id, target.user_id, scope)
                scopes[scope] = str(grant.id) if grant and grant.status == 'GRANTED' and (
                    grant.expires_at is None or grant.expires_at > utcnow()) else None
            result['recipients'].append(dict(user_id=str(target.user_id), display_name=names[target.user_id],
                role=target.role, grants=scopes))
    return result


async def update(db, actor, fid, body, version, request_id):
    await family.context(db, actor.user_id, fid)
    row = await current(db, fid, actor.user_id)
    if (row.version if row else 0) != version:
        raise AppError('ETAG_MISMATCH', '联系人已更新，请刷新。', 409)
    if not row:
        row = FamilyContact(family_id=fid, user_id=actor.user_id)
        db.add(row)
    row.phone_ciphertext = cipher().encrypt(body.phone.encode()).decode() if body.phone else None
    row.topic_ciphertext = cipher().encrypt(body.ntfy_topic.encode()).decode() if body.ntfy_topic else None
    row.share_phone, row.emergency, row.version = body.share_phone, body.emergency, version + 1
    await audit.record(db, actor.user_id, 'CONTACT_UPDATED', 'USER', actor.user_id, fid, request_id)
    return view(row)


async def remove(db, actor, fid, request_id):
    await family.context(db, actor.user_id, fid)
    await delete_member(db, fid, actor.user_id)
    await audit.record(db, actor.user_id, 'CONTACT_DELETED', 'USER', actor.user_id, fid, request_id)


async def delete_member(db, fid, uid):
    await db.execute(delete(FamilyContact).where(FamilyContact.family_id == fid, FamilyContact.user_id == uid))


async def event_contacts(db, actor, event):
    from app.modules.signal.service import can_handle, recipient
    if not await can_handle(db, actor, event):
        return []
    rows = (await db.scalars(select(FamilyContact).join(FamilyMember,
        (FamilyMember.family_id == FamilyContact.family_id) & (FamilyMember.user_id == FamilyContact.user_id))
        .where(FamilyContact.family_id == event.family_id, FamilyContact.share_phone.is_(True),
            FamilyMember.status == 'ACTIVE').order_by(FamilyContact.user_id))).all()
    names = await display_names(db, [r.user_id for r in rows])
    result = []
    for row in rows:
        if row.user_id == actor.user_id or not row.phone_ciphertext:
            continue
        try:
            await active_user(db, row.user_id, lock=False)
            if row.user_id != event.owner_user_id:
                if not row.emergency:
                    continue
                await recipient(db, event.family_id, event.owner_user_id, row.user_id, event.type)
            result.append(dict(user_id=str(row.user_id), display_name=names.get(row.user_id, ''),
                phone=decrypt(row.phone_ciphertext), emergency=row.emergency))
        except AppError:
            continue
    return result


async def destination(db, source, uid, channel):
    row = await current(db, source['family_id'], uid)
    if not row:
        return None
    value = decrypt(row.topic_ciphertext if channel == 'PUSH' else row.phone_ciphertext)
    return SimpleNamespace(value=value, version=row.version) if value else None
