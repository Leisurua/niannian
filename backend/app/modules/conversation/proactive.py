from datetime import datetime, time, timedelta
import hashlib
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator
from sqlalchemy import delete, select, text

from app.ai.proactive import ProactiveSnapshot, decide
from app.modules.audit import service as audit
from app.modules.auth.schemas import Input
from app.modules.auth.service import active_user
from app.modules.family import service as family
from app.modules.conversation.models import Conversation
from app.modules.conversation.proactive_models import ProactivePreference, ProactiveDailyCounter
from app.platform.errors import AppError
from app.platform.identifiers import utcnow
from app.platform.resource_access import authorize, check_version

INVITATION = 'Mock · 要不要聊聊今天想做的事？不想聊可以说“今天少打扰我”，或点“今天少打扰我”。'


class PreferenceInput(Input):
    timezone: str = Field(max_length=64)
    window_start: time
    window_end: time
    quiet_start: time | None = None
    quiet_end: time | None = None
    daily_cap: int = Field(ge=0, le=3, strict=True)

    @model_validator(mode='after')
    def valid(self):
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError):
            raise ValueError('Invalid timezone') from None
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError('Quiet hours must be paired')
        if any(t is not None and (t.tzinfo is not None or t.second or t.microsecond)
               for t in (self.window_start, self.window_end, self.quiet_start, self.quiet_end)):
            raise ValueError('Local minute precision required')
        return self


class ConfirmInput(Input):
    version: int = Field(gt=0, strict=True)


def lock_id(conversation_id):
    return int.from_bytes(hashlib.sha256(conversation_id.bytes).digest()[:8], 'big', signed=True)


async def access(db, actor, fid, owner, *, write=False):
    await authorize(db, actor, fid, owner, 'REMINDER_WRITE' if write else 'REMINDER_READ')
    member = await family.require_member(db, fid, owner)
    if member.role != 'ELDER':
        raise AppError('PERMISSION_DENIED', '主动陪伴设置仅适用于长辈本人。', 403)
    return await db.get(ProactivePreference, (fid, owner), populate_existing=True)


def view(row, fid, owner):
    return dict(family_id=str(fid), owner_user_id=str(owner), timezone=row.timezone if row else 'Asia/Shanghai',
        window_start=str(row.window_start) if row else '08:00:00', window_end=str(row.window_end) if row else '20:00:00',
        quiet_start=str(row.quiet_start) if row and row.quiet_start else None,
        quiet_end=str(row.quiet_end) if row and row.quiet_end else None, daily_cap=row.daily_cap if row else 0,
        version=row.version if row else 1, confirmed=bool(row and row.confirmed_version == row.version),
        paused_on=row.paused_on.isoformat() if row and row.paused_on else None)


async def read(db, actor, fid, owner, request_id):
    row = await access(db, actor, fid, owner)
    await audit.record(db, actor.user_id, 'PROACTIVE_PREFERENCE_READ', 'USER', owner, fid, request_id)
    return view(row, fid, owner)


async def update(db, actor, fid, owner, body, version, request_id):
    row = await access(db, actor, fid, owner, write=True)
    if actor.user_id == owner:
        raise AppError('PERMISSION_DENIED', '请由家人提出设置，再由长辈本人确认。', 403)
    if (row.version if row else 1) != version:
        raise AppError('ETAG_MISMATCH', '设置已更新，请刷新后重试。', 409)
    now = utcnow()
    if row and row.timezone != body.timezone:
        old_day, new_day = now.astimezone(ZoneInfo(row.timezone)).date(), now.astimezone(ZoneInfo(body.timezone)).date()
        counters = (await db.scalars(select(ProactiveDailyCounter).where(ProactiveDailyCounter.family_id == fid,
            ProactiveDailyCounter.owner_user_id == owner, ProactiveDailyCounter.updated_at > now - timedelta(hours=24)))).all()
        carried = min(3, sum(c.used_count for c in counters))
        current = await db.get(ProactiveDailyCounter, (fid, owner, new_day))
        if current:
            current.used_count, current.updated_at = max(current.used_count, carried), now
        else:
            db.add(ProactiveDailyCounter(family_id=fid, owner_user_id=owner, local_date=new_day, used_count=carried, updated_at=now))
        if row.paused_on == old_day:
            row.paused_on = new_day
    if row is None:
        row = ProactivePreference(family_id=fid, owner_user_id=owner, proposed_by_user_id=actor.user_id,
            version=1, **body.model_dump())
        db.add(row)
    else:
        for name, value in body.model_dump().items():
            setattr(row, name, value)
    row.version = version + 1
    row.proposed_by_user_id, row.confirmed_by_user_id, row.confirmed_version = actor.user_id, None, None
    row.updated_at = now
    await audit.record(db, actor.user_id, 'PROACTIVE_PREFERENCE_PROPOSED', 'USER', owner, fid, request_id)
    return view(row, fid, owner)


async def command(db, actor, fid, owner, kind, body, key, settings, request_id):
    row = await access(db, actor, fid, owner)
    if actor.user_id != owner or row is None:
        raise AppError('PERMISSION_DENIED', '需要长辈本人确认已有设置。', 403)
    idem = audit.Idempotency(key, f'proactive-{kind}:{fid}:{owner}', body)
    if await idem.previous(db, actor.user_id, settings.idempotency_seconds):
        return view(row, fid, owner)
    if kind == 'confirm':
        check_version(row, body['version'])
        await authorize(db, SimpleNamespace(user_id=row.proposed_by_user_id), fid, owner, 'REMINDER_WRITE', allow_self=False)
        row.confirmed_by_user_id, row.confirmed_version = owner, row.version
    else:
        row.paused_on = utcnow().astimezone(ZoneInfo(row.timezone)).date()
    row.updated_at = utcnow()
    await audit.record(db, actor.user_id, 'PROACTIVE_' + kind.upper(), 'USER', owner, fid, request_id, metadata=idem.metadata)
    return view(row, fid, owner)


async def snapshot(db, conversation, now, *, reserved=False, last_interaction=None):
    await active_user(db, conversation.owner_user_id, lock=False)
    preference = await access(db, SimpleNamespace(user_id=conversation.owner_user_id), conversation.family_id, conversation.owner_user_id)
    if not preference or preference.confirmed_version != preference.version:
        return None
    await active_user(db, preference.proposed_by_user_id, lock=False)
    await authorize(db, SimpleNamespace(user_id=preference.proposed_by_user_id), preference.family_id,
        preference.owner_user_id, 'REMINDER_WRITE', allow_self=False)
    local_day = now.astimezone(ZoneInfo(preference.timezone)).date()
    counter = await db.get(ProactiveDailyCounter, (preference.family_id, preference.owner_user_id, local_day), populate_existing=True)
    count = counter.used_count if counter else 0
    recent = last_interaction or conversation.started_at
    if counter and not reserved:
        recent = max(recent, counter.updated_at)
    state = ProactiveSnapshot(now=now, timezone=preference.timezone, window_start=preference.window_start,
        window_end=preference.window_end, jointly_enabled=True, daily_cap=preference.daily_cap,
        daily_count=max(0, count - 1) if reserved else count, counter_date=local_day,
        quiet_start=preference.quiet_start, quiet_end=preference.quiet_end, paused_on=preference.paused_on,
        last_interaction=recent, content_authorized=True)
    return preference, counter, state


async def tick(db, settings, now=None):
    if settings.provider_mode != 'mock':
        return
    now = now or utcnow()
    await db.execute(delete(ProactiveDailyCounter).where(ProactiveDailyCounter.updated_at <= now - timedelta(hours=48)))
    conversations = (await db.scalars(select(Conversation).where(Conversation.status == 'ACTIVE',
        Conversation.deleted_at.is_(None), Conversation.backend_state.in_(('IDLE', 'LISTENING')))
        .order_by(Conversation.started_at.desc()).limit(128))).all()
    visited = set()
    for conversation in conversations:
        identity = (conversation.family_id, conversation.owner_user_id)
        if identity in visited or not conversation.provider_metadata.get('identity_disclosed'):
            continue
        # A live API holds this xact advisory lease. Unconnected rows never spend quota.
        if await db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': lock_id(conversation.id)}):
            continue
        visited.add(identity)
        try:
            data = await snapshot(db, conversation, now)
        except AppError:
            continue
        if not data:
            continue
        preference, counter, state = data
        if decide(state).action == 'NO_ACTION':
            continue
        if counter is None:
            counter = ProactiveDailyCounter(family_id=conversation.family_id, owner_user_id=conversation.owner_user_id,
                local_date=state.counter_date, used_count=0)
            db.add(counter)
        counter.used_count += 1
        counter.updated_at = now
        await db.flush()
        await db.execute(text('SELECT pg_notify(:channel, :payload)'), dict(channel='nn_proactive_' + conversation.id.hex,
            payload=json.dumps(dict(version=preference.version, stamp=now.isoformat()))))


async def accept(db, conversation, payload, last_interaction):
    try:
        message = json.loads(payload)
        stamp = datetime.fromisoformat(message['stamp'])
        now = utcnow()
        if stamp.tzinfo is None or not timedelta(0) <= now - stamp <= timedelta(seconds=30):
            return False
        data = await snapshot(db, conversation, now, reserved=True, last_interaction=last_interaction)
        if not data:
            return False
        preference, counter, state = data
        return bool(counter and counter.used_count > 0 and counter.updated_at == stamp and preference.version == message['version']
            and decide(state).action != 'NO_ACTION' and conversation.status == 'ACTIVE'
            and conversation.backend_state in ('IDLE', 'LISTENING'))
    except (AppError, ValueError, TypeError, KeyError):
        return False
