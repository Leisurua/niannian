"""W7 notification persistence, current permission checks and fenced Mock dispatch."""
import asyncio
from datetime import timedelta
import hashlib
from types import SimpleNamespace
from sqlalchemy import delete, select

from app.integrations.contracts import PushRequest
from app.integrations.mock import MockPush
from app.modules.audit import service as audit
from app.modules.auth.service import codec
from app.modules.notification.models import Notification, NotificationAttempt
from app.modules.notification import preferences
from app.modules.signal import service as signals
from app.platform import tasks
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7, iso_utc
from app.platform.pagination import page_rows

SUMMARY = 'Mock 演示 · 有一条关注提示，请在应用内查看授权详情；未验证设备推送到达。'


async def create_for_event(db, source, recipients):
    now = utcnow()
    for uid in recipients:
        pref = await preferences.current(db, source['family_id'], source['owner_user_id'], uid)
        channels = pref.channels if source['type'] in ('SCAM_RISK','PHYSICAL_DISCOMFORT') else [c for c in pref.channels if c == 'IN_APP']
        for channel in channels:
            key = hashlib.sha256(f"{source['id']}:{uid}:{channel}".encode()).hexdigest()
            if await db.scalar(select(Notification.id).where(Notification.dedupe_key == key)):
                continue
            row = Notification(id=uuid7(), signal_event_id=source['id'], recipient_user_id=uid,
                channel=channel, status='QUEUED', summary=SUMMARY, policy_version=signals.POLICY_VERSION,
                provider='mock', created_at=now, retention_until=min(now + timedelta(days=7), source['retention_until']),
                dispatch_deadline=now + timedelta(hours=24), dedupe_key=key)
            db.add(row)
            await db.flush()
            await tasks.enqueue(db, 'NOTIFICATION_DISPATCH', source['family_id'], row.id, 1)


async def context(db, row):
    if (not row or row.deleted_at or row.retention_until <= utcnow() or not row.recipient_user_id
            or not row.signal_event_id or row.status == 'CANCELLED'):
        return None
    return await signals.delivery_context(db, row.signal_event_id, row.recipient_user_id)


def view(row):
    result = dict(id=str(row.id), signal_event_id=str(row.signal_event_id), channel=row.channel,
        status=row.status, summary=row.summary, action=row.action, created_at=iso_utc(row.created_at))
    if row.read_at:
        result['read_at'] = iso_utc(row.read_at)
    return result


async def detail(db, actor, notification_id, request_id, *, read_key=None, settings=None):
    row = await db.get(Notification, notification_id)
    if not row or row.recipient_user_id != actor.user_id or not await context(db, row):
        raise AppError('NOTIFICATION_NOT_FOUND', '通知不存在或无权查看。', 404)
    await db.refresh(row)
    if row.deleted_at or row.status not in ('SENT','DELIVERED','READ','FAILED'):
        raise AppError('NOTIFICATION_NOT_FOUND', '通知尚未发布或已取消。', 404)
    if read_key is not None:
        if row.status == 'FAILED':
            raise AppError('RESOURCE_STATE_CONFLICT', '未发送的通知不能标记已读。', 409)
        idem = audit.Idempotency(read_key, 'notification-read:' + str(row.id), {})
        previous = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
        if not previous:
            row.status, row.read_at = 'READ', row.read_at or utcnow()
            await audit.record(db, actor.user_id, 'NOTIFICATION_READ', 'NOTIFICATION', row.id,
                request_id=request_id, metadata=idem.metadata)
    else:
        await audit.record(db, actor.user_id, 'NOTIFICATION_DETAIL', 'NOTIFICATION', row.id, request_id=request_id)
    return view(row)


async def listing(db, actor, status, channel, limit, cursor, settings, request_id):
    ids = await signals.visible_ids(db, actor)
    query = select(Notification).where(Notification.recipient_user_id == actor.user_id,
        Notification.signal_event_id.in_(ids), Notification.deleted_at.is_(None), Notification.retention_until > utcnow(),
        Notification.status.in_(('SENT','DELIVERED','READ','FAILED')))
    if status:
        query = query.where(Notification.status == status)
    if channel:
        query = query.where(Notification.channel == channel)
    rows, page = await page_rows(db, query, Notification, codec(settings), f'notifications:{actor.user_id}:{status}:{channel}', limit, cursor)
    return dict(items=[view(r) for r in rows], page=page, request_id=request_id)


async def cancel(db, row, code='AUTHORIZATION_OR_SOURCE_CHANGED'):
    row.status, row.error_code = 'CANCELLED', code
    open_attempts = (await db.scalars(select(NotificationAttempt).where(
        NotificationAttempt.notification_id == row.id, NotificationAttempt.status == 'STARTED'))).all()
    for attempt in open_attempts:
        attempt.status, attempt.finished_at, attempt.error_code = 'FAILED', utcnow(), code


async def aggregate(db, event_id):
    states = list((await db.scalars(select(Notification.status).where(Notification.signal_event_id == event_id,
        Notification.deleted_at.is_(None), Notification.status != 'CANCELLED'))).all())
    if any(s in ('SENT','DELIVERED','READ') for s in states):
        await signals.delivery_outcome(db, event_id, 'NOTIFIED')
    elif states and all(s == 'FAILED' for s in states):
        await signals.delivery_outcome(db, event_id, 'NOTIFICATION_FAILED')


async def prepare(db, task_id, token, notification_id):
    row = await db.get(Notification, notification_id, populate_existing=True)
    source = await context(db, row)  # family lock before task fence
    task = await tasks.leased(db, task_id, token)
    if not task:
        return None
    if not row:
        await tasks.finish(db, task_id, token)
        return None
    await db.refresh(row)
    if row.status in ('SENT','DELIVERED','READ','FAILED','CANCELLED'):
        await tasks.finish(db, task_id, token)
        return None
    if not source or row.dispatch_deadline <= utcnow():
        await cancel(db, row)
        await tasks.finish(db, task_id, token)
        return None
    pref = await preferences.current(db, source['family_id'], source['owner_user_id'], row.recipient_user_id)
    if row.channel not in pref.channels or row.channel not in ('IN_APP','PUSH'):
        await cancel(db, row, 'CHANNEL_DISABLED')
        await tasks.finish(db, task_id, token)
        return None
    now = utcnow()
    ready = preferences.ready_at(pref, now)
    if ready > now:
        task.status, task.available_at = 'RETRY', min(ready, row.dispatch_deadline)
        task.attempts -= 1  # waiting for quiet hours is not a provider attempt
        task.lease_token, task.lease_until = None, None
        return None
    # An abandoned attempt is an observed failure, not a delivery success.
    old = (await db.scalars(select(NotificationAttempt).where(NotificationAttempt.notification_id == row.id,
        NotificationAttempt.status == 'STARTED'))).all()
    for attempt in old:
        attempt.status, attempt.finished_at, attempt.error_code = 'FAILED', now, 'LEASE_EXPIRED'
    db.add(NotificationAttempt(notification_id=row.id, attempt_no=task.attempts, provider='mock', status='STARTED'))
    await db.flush()
    return (source, pref.version, row.channel, task.attempts)


async def dispatch(factory, task_id, token, notification_id, push=None):
    async with factory() as db:
        prepared = await prepare(db, task_id, token, notification_id)
        await db.commit()
    if not prepared:
        return
    failure = False
    if prepared[2] == 'PUSH':
        try:
            provider = push or MockPush()
            if provider.capabilities().provider != 'mock':
                raise ValueError('Real Push is not enabled')
            async with asyncio.timeout(5):
                result = await provider.send(PushRequest(request_id=str(notification_id),
                    event_id=str(prepared[0]['id']), summary_key='attention.open_authorized_app'))
            if result.provider != 'mock' or not result.simulated or result.delivery_observed:
                raise ValueError('Unobserved delivery claim')
        except Exception:
            failure = True
    async with factory() as db:
        row = await db.get(Notification, notification_id, populate_existing=True)
        source = await context(db, row)
        task = await tasks.leased(db, task_id, token)
        if not task:
            return  # stale worker cannot write completion
        if not row:
            await tasks.finish(db, task_id, token)
            await db.commit()
            return
        await db.refresh(row)
        pref = await preferences.current(db, source['family_id'], source['owner_user_id'], row.recipient_user_id) if source else None
        attempt = await db.scalar(select(NotificationAttempt).where(NotificationAttempt.notification_id == row.id,
            NotificationAttempt.attempt_no == prepared[3]))
        if (source != prepared[0] or not pref or pref.version != prepared[1] or row.deleted_at
                or row.status == 'CANCELLED' or row.dispatch_deadline <= utcnow()):
            await cancel(db, row)
            await tasks.finish(db, task_id, token)
        elif failure:
            await tasks.finish(db, task_id, token, error=True)
            row.status = 'FAILED' if task.status == 'DEAD' else 'QUEUED'
            row.error_code = 'MOCK_PROVIDER_UNAVAILABLE'
            attempt.status = 'FAILED' if task.status == 'DEAD' else 'RETRY_SCHEDULED'
            attempt.finished_at, attempt.error_code = utcnow(), row.error_code
            attempt.retry_at = task.available_at if task.status != 'DEAD' else None
        else:
            row.status, row.sent_at, row.error_code = 'SENT', utcnow(), None
            attempt.status, attempt.finished_at = 'SUCCEEDED', utcnow()
            await tasks.finish(db, task_id, token)
        await aggregate(db, row.signal_event_id)
        await db.commit()


async def invalidate(db, fid, owner, grantee, scope):
    if scope not in ('NOTIFICATION_TO_FAMILY','HEALTH_MEDICATION'):
        return
    rows = (await db.scalars(select(Notification).where(Notification.recipient_user_id == grantee,
        Notification.deleted_at.is_(None)))).all()
    # Public signal metadata, never a cross-module model import.
    for row in rows:
        source = await signals.internal_metadata(db, row.signal_event_id)
        if source and source['family_id'] == fid and source['owner_user_id'] == owner and (
                scope == 'NOTIFICATION_TO_FAMILY' or source['type'] == 'PHYSICAL_DISCOMFORT'):
            row.deleted_at = utcnow()
            await cancel(db, row)
            await tasks.enqueue(db, 'NOTIFICATION_CLEANUP', fid, row.id, 1)


async def maintenance(db):
    dead = await tasks.dead_resource_ids(db, 'NOTIFICATION_DISPATCH')
    rows = (await db.scalars(select(Notification).order_by(Notification.id))).all()
    for row in rows:
        source = await signals.internal_metadata(db, row.signal_event_id)
        if source is None:
            await db.delete(row)  # orphan source: worker erases payload and cascading attempts
            continue
        current = await context(db, row)
        if row.deleted_at or row.retention_until <= utcnow() or not current:
            row.deleted_at = row.deleted_at or utcnow()
            await cancel(db, row)
            if source:
                await tasks.enqueue(db, 'NOTIFICATION_CLEANUP', source['family_id'], row.id, 1)
        elif row.status in ('PENDING','QUEUED'):
            if row.dispatch_deadline <= utcnow():
                await cancel(db, row, 'DISPATCH_EXPIRED')
            elif row.id in dead:
                row.status, row.error_code = 'FAILED', 'LEASE_EXHAUSTED'
                for attempt in (await db.scalars(select(NotificationAttempt).where(NotificationAttempt.notification_id == row.id,
                        NotificationAttempt.status == 'STARTED'))).all():
                    attempt.status, attempt.finished_at, attempt.error_code = 'FAILED', utcnow(), 'LEASE_EXHAUSTED'
                await aggregate(db, row.signal_event_id)


async def cleanup(db, notification_id):
    row = await db.get(Notification, notification_id)
    if row and (row.deleted_at or row.retention_until <= utcnow()):
        await db.execute(delete(Notification).where(Notification.id == notification_id))


async def delete_for_event(db, event_id):
    await db.execute(delete(Notification).where(Notification.signal_event_id == event_id))
