from datetime import time, timedelta
from types import SimpleNamespace
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import Field, model_validator
from sqlalchemy import select
from app.modules.auth.schemas import Input
from app.modules.auth.service import active_user
from app.modules.audit import service as audit
from app.modules.family import service as family
from app.modules.notification.models import NotificationPreference
from app.platform.errors import AppError
from app.platform.identifiers import utcnow
from app.platform.resource_access import authorize


class PreferenceInput(Input):
    channels: list[Literal['IN_APP','PUSH']] = Field(max_length=2)
    timezone: str = Field(max_length=64)
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None

    @model_validator(mode='after')
    def valid(self):
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError):
            raise ValueError('Invalid timezone') from None
        if len(set(self.channels)) != len(self.channels):
            raise ValueError('Duplicate channel')
        if (self.quiet_hours_start is None) != (self.quiet_hours_end is None):
            raise ValueError('Quiet hours must be paired')
        if any(t and (t.tzinfo or t.second or t.microsecond) for t in (self.quiet_hours_start,self.quiet_hours_end)):
            raise ValueError('Local minute precision required')
        return self


async def access(db, actor, fid, owner):
    await authorize(db, actor, fid, owner, 'SIGNAL_READ', allow_self=False)
    try:
        await active_user(db, owner, lock=False)
    except AppError:
        raise AppError('FAMILY_NOT_FOUND', '相关成员当前不可用。', 404) from None
    if (await family.require_member(db, fid, owner)).role != 'ELDER':
        raise AppError('PERMISSION_DENIED', '请选择当前家庭的长辈。', 403)


async def current(db, fid, owner, recipient):
    row = await db.scalar(select(NotificationPreference).where(NotificationPreference.family_id == fid,
        NotificationPreference.owner_user_id == owner, NotificationPreference.recipient_user_id == recipient).execution_options(populate_existing=True))
    # Existing Family has no timezone column: the baseline Demo timezone is Shanghai.
    return row or SimpleNamespace(version=0, channels=['IN_APP'], timezone='Asia/Shanghai',
        quiet_hours_start=time(22), quiet_hours_end=time(8))


def view(row, fid, owner, recipient):
    return dict(family_id=str(fid), owner_user_id=str(owner), recipient_user_id=str(recipient),
        version=row.version, channels=row.channels, timezone=row.timezone,
        quiet_hours_start=str(row.quiet_hours_start) if row.quiet_hours_start else None,
        quiet_hours_end=str(row.quiet_hours_end) if row.quiet_hours_end else None)


async def read(db, actor, fid, owner, request_id):
    await access(db, actor, fid, owner)
    row = await current(db, fid, owner, actor.user_id)
    await audit.record(db, actor.user_id, 'NOTIFICATION_PREFERENCE_READ', 'USER', owner, fid, request_id)
    return view(row, fid, owner, actor.user_id)


async def update(db, actor, fid, owner, body, version, request_id):
    await access(db, actor, fid, owner)
    row = await current(db, fid, owner, actor.user_id)
    if row.version != version:
        raise AppError('ETAG_MISMATCH', '设置已更新，请重新读取。', 409)
    if version == 0:
        row = NotificationPreference(family_id=fid, owner_user_id=owner, recipient_user_id=actor.user_id)
        db.add(row)
    for name, value in body.model_dump().items():
        setattr(row, name, value)
    row.version, row.updated_at = version + 1, utcnow()
    await audit.record(db, actor.user_id, 'NOTIFICATION_PREFERENCE_UPDATED', 'USER', owner, fid, request_id)
    return view(row, fid, owner, actor.user_id)


def ready_at(pref, now):
    def quiet(instant):
        clock = instant.astimezone(ZoneInfo(pref.timezone)).time().replace(tzinfo=None)
        start, end = pref.quiet_hours_start, pref.quiet_hours_end
        return bool(start is not None and end is not None and start != end and
            (start <= clock < end if start < end else clock >= start or clock < end))
    if not quiet(now):
        return now
    # Walk UTC minutes, preserving actual DST transitions rather than inventing local times.
    next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for n in range(26 * 60):
        candidate = next_minute + timedelta(minutes=n)
        if not quiet(candidate):
            return candidate
    return now + timedelta(hours=26)
