"""Shared enforcement through public Family/Consent services, never UI flags."""
import re

from app.modules.family import service as family
from app.modules.consent import service as consent
from app.platform.errors import AppError


async def resolve_family(db, actor, subject, family_id):
    if family_id is None:
        choices = []
        for fid, _ in await family.visibility(db, actor.user_id):
            if subject in await family.active_subjects(db, fid):
                choices.append(fid)
        if len(choices) != 1:
            raise AppError('VALIDATION_ERROR', '请选择明确的家庭。', 422)
        family_id = choices[0]
    await family.context(db, actor.user_id, family_id)
    await family.require_member(db, family_id, subject)
    return family_id


async def authorize(db, actor, family_id, subject, permission, scope=None, *, allow_self=True):
    fam, member = await family.context(db, actor.user_id, family_id)
    await family.require_member(db, family_id, subject)
    if actor.user_id == subject and allow_self:
        return member
    allowed_roles = ('CHILD', 'CAREGIVER', 'EMERGENCY_CONTACT') if permission in ('SIGNAL_READ', 'SIGNAL_WRITE') else ('CHILD', 'CAREGIVER')
    if member.role not in allowed_roles or not (
        fam.created_by_user_id == actor.user_id or member.permission_codes.get(permission) is True
    ):
        raise AppError('PERMISSION_DENIED', '当前成员没有此项权限。', 403)
    if scope:
        await consent.require_scope(db, family_id, subject, actor.user_id, scope)
    return member


async def visible_subjects(db, actor, family_id, permission, scope=None):
    fam, member = await family.context(db, actor.user_id, family_id)
    subjects = {actor.user_id}
    if member.role in ('CHILD', 'CAREGIVER') and (
        fam.created_by_user_id == actor.user_id or member.permission_codes.get(permission) is True
    ):
        active = set(await family.active_subjects(db, family_id))
        subjects |= active if scope is None else active & set(await consent.granted_subjects(db, family_id, actor.user_id, scope))
    return subjects


def expected_version(header, *, allow_zero=False):
    number = r'(?:0|[1-9][0-9]*)' if allow_zero else r'[1-9][0-9]*'
    match = re.fullmatch(fr'(?:"({number})"|({number}))', header) if len(header) <= 64 else None
    if not match:
        raise AppError('ETAG_MISMATCH', '请刷新后重试。', 409)
    return int(match[1] or match[2])


def check_version(row, expected):
    if row.version != expected:
        raise AppError('ETAG_MISMATCH', '内容已更新，请刷新后确认。', 409)
