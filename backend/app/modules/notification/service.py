import asyncio
from datetime import timedelta
import hashlib
from types import SimpleNamespace
from sqlalchemy import delete, select

from app.integrations.contracts import PushRequest
from app.integrations.mock import MockPush
from app.integrations.notifications import ExternalNotifications, DeliveryFailure, provider_name
from app.modules.audit import service as audit
from app.modules.auth.service import codec
from app.modules.notification.models import Notification, NotificationAttempt
from app.modules.notification import preferences
from app.modules.notification import contacts
from app.modules.signal import service as signals
from app.platform import tasks
from app.platform.errors import AppError
from app.platform.config import get_settings
from app.platform.identifiers import utcnow, uuid7, iso_utc
from app.platform.pagination import page_rows

SUMMARY = 'Mock 演示 · 有一条关注提示，请在应用内查看授权详情；未验证设备推送到达。'


async def create_for_event(db, source, recipients):
    now = utcnow()
    for uid in recipients:
        pref = await preferences.current(db, source['family_id'], source['owner_user_id'], uid)
        channels = pref.channels if source['type'] in ('SCAM_RISK','PHYSICAL_DISCOMFORT') else [c for c in pref.channels if c in ('IN_APP', 'PUSH')]
        for channel in channels:
            key = hashlib.sha256(f"{source['id']}:{uid}:{channel}".encode()).hexdigest()
            if await db.scalar(select(Notification.id).where(Notification.dedupe_key == key)):
                continue
            row = Notification(id=uuid7(), signal_event_id=source['id'], recipient_user_id=uid,
                channel=channel, status='QUEUED', summary=SUMMARY, policy_version=signals.POLICY_VERSION,
                provider=provider_name(get_settings(), channel), created_at=now, retention_until=min(now + timedelta(days=7), source['retention_until']),
                dispatch_deadline=now + timedelta(hours=24), dedupe_key=key)
            if source.get('recognition_mode', 'MOCK') != 'MOCK':
                row.summary = '有一条关注提示，请在应用内查看授权详情。'
            db.add(row)
            await db.flush()
            await tasks.enqueue(db, 'NOTIFICATION_DISPATCH', source['family_id'], row.id, 1)


async def context(db, row, *, for_delivery=True):
    if (not row or row.deleted_at or row.retention_until <= utcnow() or not row.recipient_user_id
            or not row.signal_event_id or row.status == 'CANCELLED'):
        return None
    return await signals.delivery_context(db, row.signal_event_id, row.recipient_user_id, for_delivery=for_delivery)


def view(row):
    result = dict(id=str(row.id), signal_event_id=str(row.signal_event_id), channel=row.channel,
        status=row.status, summary=row.summary, action=row.action, created_at=iso_utc(row.created_at),
        provider=row.provider, simulated=row.provider == 'mock' and row.channel != 'IN_APP', delivery_status=row.provider_status,
        error_code=row.error_code)
    if row.read_at:
        result['read_at'] = iso_utc(row.read_at)
    return result


async def detail(db, actor, notification_id, request_id, *, read_key=None, settings=None):
    row = await db.get(Notification, notification_id)
    source = await context(db, row, for_delivery=False) if row and row.recipient_user_id == actor.user_id else None
    if not source:
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
    return view(row) | dict(family_id=str(source['family_id']), owner_user_id=str(source['owner_user_id']))


async def mobile_inbox(db, actor, limit, cursor, settings, request_id):
    """Only routing IDs leave the API for local Android notifications.

    Recheck consent, source, channel and quiet hours on every synchronization,
    including notifications that the worker has already published.
    """
    from app.modules.signal.models import SignalEvent
    eligible = []
    now = utcnow()
    for event_id in await signals.visible_ids(db, actor):
        event = await db.get(SignalEvent, event_id)
        if event.status not in ('VALIDATED', 'NOTIFIED', 'NOTIFICATION_FAILED'):
            continue
        pref = await preferences.current(db, event.family_id, event.owner_user_id, actor.user_id)
        if 'IN_APP' in pref.channels and preferences.ready_at(pref, now) == now:
            eligible.append(event_id)
    query = select(Notification).where(Notification.recipient_user_id == actor.user_id,
        Notification.signal_event_id.in_(eligible), Notification.channel == 'IN_APP',
        Notification.status.in_(('SENT', 'DELIVERED')), Notification.deleted_at.is_(None),
        Notification.retention_until > now)
    rows, page = await page_rows(db, query, Notification, codec(settings), f'mobile-inbox:{actor.user_id}', limit, cursor)
    items = []
    for row in rows:
        event = await db.get(SignalEvent, row.signal_event_id)
        items.append(dict(id=str(row.id), signal_event_id=str(row.signal_event_id),
            family_id=str(event.family_id), owner_user_id=str(event.owner_user_id)))
    return dict(items=items, page=page, request_id=request_id)


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


async def event_action(db, event_id, target):
    rows = (await db.scalars(select(Notification).where(Notification.signal_event_id == event_id,
        Notification.deleted_at.is_(None)))).all()
    for row in rows:
        if target in ('ACKNOWLEDGED', 'CONTACTED', 'FALSE_POSITIVE'):
            row.action, row.action_at = target, utcnow()
        if target in ('RESOLVED', 'FALSE_POSITIVE') and row.status in ('PENDING', 'QUEUED'):
            await cancel(db, row, 'EVENT_CLOSED')


async def aggregate(db, event_id):
    states = list((await db.scalars(select(Notification.status).where(Notification.signal_event_id == event_id,
        Notification.deleted_at.is_(None), Notification.status != 'CANCELLED'))).all())
    if any(s in ('SENT','DELIVERED','READ') for s in states):
        await signals.delivery_outcome(db, event_id, 'NOTIFIED')
    elif states and all(s == 'FAILED' for s in states):
        await signals.delivery_outcome(db, event_id, 'NOTIFICATION_FAILED')


async def prepare(db, task_id, token, notification_id):
    row = await db.get(Notification, notification_id, populate_existing=True)
    locked_source = await context(db, row)
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
    if not locked_source or row.dispatch_deadline <= utcnow():
        await cancel(db, row)
        await tasks.finish(db, task_id, token)
        return None
    pref = await preferences.current(db, locked_source['family_id'], locked_source['owner_user_id'], row.recipient_user_id)
    if row.channel not in pref.channels or row.channel not in ('IN_APP','PUSH','SMS','PHONE'):
        await cancel(db, row, 'CHANNEL_DISABLED')
        await tasks.finish(db, task_id, token)
        return None
    now = utcnow()
    ready = preferences.ready_at(pref, now)
    if ready > now:
        _defer_without_provider_attempt(task, min(ready, row.dispatch_deadline))
        return None
    old = (await db.scalars(select(NotificationAttempt).where(NotificationAttempt.notification_id == row.id,
        NotificationAttempt.status == 'STARTED'))).all()
    for attempt in old:
        attempt.status, attempt.finished_at, attempt.error_code = 'FAILED', now, 'LEASE_EXPIRED'
    if old and row.provider != 'mock' and row.channel != 'IN_APP':
        # The process may have died after the provider accepted the message.
        row.status, row.error_code = 'FAILED', 'DELIVERY_UNKNOWN'
        await tasks.finish(db, task_id, token)
        await aggregate(db, row.signal_event_id)
        return None
    db.add(NotificationAttempt(notification_id=row.id, attempt_no=task.attempts, provider=row.provider, status='STARTED'))
    if row.provider != 'mock' and row.channel != 'IN_APP':
        from app.modules.account.service import note_possible_copy
        for uid in sorted({row.recipient_user_id, locked_source['owner_user_id']}):
            await note_possible_copy(db, uid, 'NOTIFICATION:' + row.provider)
    await db.flush()
    return (locked_source, pref.version, row.channel, task.attempts, row.provider)


def _defer_without_provider_attempt(task, ready_at):
    task.status, task.available_at = 'RETRY', ready_at
    task.attempts -= 1
    task.lease_token, task.lease_until = None, None


async def dispatch(factory, task_id, token, notification_id, push=None):
    async with factory() as db:
        prepared = await prepare(db, task_id, token, notification_id)
        await db.commit()
    if not prepared:
        return
    if prepared[4] != 'mock' and prepared[2] != 'IN_APP':
        await dispatch_external(factory, task_id, token, notification_id, prepared)
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
            return
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


async def dispatch_external(factory, task_id, token, notification_id, prepared):
    # Revalidate immediately before I/O and serialize with consent, membership and
    # event actions. The short provider timeout bounds the family lock duration.
    async with factory() as db:
        row = await db.get(Notification, notification_id, populate_existing=True)
        source = await context(db, row)
        task = await tasks.leased(db, task_id, token)
        if not task:
            return
        if not row:
            await tasks.finish(db, task_id, token)
            await db.commit()
            return
        await db.refresh(row)
        pref = await preferences.current(db, source['family_id'], source['owner_user_id'], row.recipient_user_id) if source else None
        attempt = await db.scalar(select(NotificationAttempt).where(NotificationAttempt.notification_id == row.id,
            NotificationAttempt.attempt_no == prepared[3]))
        if source != prepared[0] or not pref or pref.version != prepared[1] or row.status == 'CANCELLED' or row.dispatch_deadline <= utcnow():
            await cancel(db, row)
        else:
            try:
                settings = get_settings()
                if provider_name(settings, row.channel) != row.provider:
                    raise DeliveryFailure('CHANNEL_CONFIGURATION_CHANGED')
                destination = await contacts.destination(db, source, row.recipient_user_id, row.channel)
                async with asyncio.timeout(5):
                    routing = dict(notification_id=row.id, recipient_id=row.recipient_user_id) if row.channel == 'PUSH' else {}
                    receipt = await ExternalNotifications(settings).send(row.channel, destination.value if destination else '', **routing)
                row.status, row.sent_at, row.error_code = 'SENT', utcnow(), None
                apply_receipt(row, receipt.status)
                attempt.provider_message_id = receipt.message_id
                from app.modules.account.service import note_provider_resource
                for uid in sorted({row.recipient_user_id, source['owner_user_id']}):
                    await note_provider_resource(db, uid, 'NOTIFICATION:' + row.provider,
                        dict(channel=row.channel, resource_id=receipt.message_id,
                            service_account=settings.twilio_account_sid if row.provider == 'twilio' else settings.ntfy_base_url))
                attempt.status = 'SUCCEEDED'
            except (DeliveryFailure, AppError) as exc:
                row.status, row.error_code = 'FAILED', exc.code
                attempt.status, attempt.error_code = 'FAILED', exc.code
            except Exception:
                row.status, row.error_code = 'FAILED', 'DELIVERY_UNKNOWN'
                attempt.status, attempt.error_code = 'FAILED', 'DELIVERY_UNKNOWN'
            attempt.finished_at = utcnow()
        await tasks.finish(db, task_id, token)
        await aggregate(db, row.signal_event_id)
        await db.commit()


async def refresh_receipt(db, row):
    if row.provider != 'twilio' or row.status not in ('SENT', 'READ') or row.provider_status in (
            'delivered', 'completed', 'busy', 'no-answer', 'failed', 'undelivered', 'canceled'):
        return
    settings = get_settings()
    if not settings.notification_external_enabled:
        return
    attempt = await db.scalar(select(NotificationAttempt).where(NotificationAttempt.notification_id == row.id,
        NotificationAttempt.status == 'SUCCEEDED').order_by(NotificationAttempt.attempt_no.desc()).limit(1))
    if not attempt or not attempt.provider_message_id:
        return
    try:
        async with asyncio.timeout(5):
            status = await ExternalNotifications(settings).status(row.channel, attempt.provider_message_id)
    except Exception:
        return  # Read-only polling retries on the next maintenance cycle.
    if status not in ('queued', 'accepted', 'sending', 'sent', 'delivered', 'undelivered',
            'scheduled', 'canceled', 'failed', 'ringing', 'in-progress', 'completed', 'busy', 'no-answer'):
        return
    apply_receipt(row, status)
    await aggregate(db, row.signal_event_id)


def apply_receipt(row, status):
    row.provider_status = status
    if status == 'delivered' and row.channel == 'SMS':
        row.delivered_at = row.delivered_at or utcnow()
        if row.status != 'READ':
            row.status = 'DELIVERED'
    elif status in ('failed', 'undelivered', 'canceled', 'busy', 'no-answer'):
        row.error_code = 'PROVIDER_DELIVERY_FAILED'
        if row.status != 'READ':
            row.status = 'FAILED'
    # A completed voice call may be voicemail. It never becomes CONTACTED/RESOLVED.


async def invalidate(db, fid, owner, grantee, scope):
    if scope not in ('NOTIFICATION_TO_FAMILY','HEALTH_MEDICATION'):
        return
    rows = (await db.scalars(select(Notification).where(Notification.recipient_user_id == grantee,
        Notification.deleted_at.is_(None)))).all()
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
            await db.delete(row)
            continue
        current = await context(db, row, for_delivery=row.status not in ('SENT','DELIVERED','READ','FAILED'))
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
        else:
            await refresh_receipt(db, row)


async def cleanup(db, notification_id):
    row = await db.get(Notification, notification_id)
    if row and (row.deleted_at or row.retention_until <= utcnow()):
        await db.execute(delete(Notification).where(Notification.id == notification_id))


async def delete_for_event(db, event_id):
    await db.execute(delete(Notification).where(Notification.signal_event_id == event_id))
