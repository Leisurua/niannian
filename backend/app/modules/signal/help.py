"""Explicit elder requests, sharing the existing signal and notification lifecycle."""
from datetime import timedelta

from sqlalchemy import select

from app.modules.audit import service as audit
from app.modules.auth.service import active_user
from app.modules.family import service as family
from app.modules.notification import preferences, service as notifications
from app.modules.notification.models import Notification
from app.modules.signal.models import SignalEvent
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7

POLICY = 'explicit-help-1.0.0'
FALLBACK = '如需立即帮助，请同时联系身边的人或使用系统电话。'


def is_request(row):
    return row.type in ('EMERGENCY', 'PHYSICAL_DISCOMFORT') and row.policy_version == POLICY \
        and row.trigger_category in ('EXPLICIT_HELP_BUTTON', 'EXPLICIT_HELP_VOICE', 'EXPLICIT_HELP_BLE')


async def source(db, row):
    if not is_request(row):
        return None
    try:
        await active_user(db, row.owner_user_id, lock=False)
        _, member = await family.context(db, row.owner_user_id, row.family_id)
        if member.role == 'ELDER':
            return dict(family_id=row.family_id, owner_user_id=row.owner_user_id)
    except AppError:
        pass
    return None


async def request(db, actor, fid, key, request_id, *, origin='BUTTON', kind='CONTACT_FAMILY'):
    from app.modules.signal import service
    if origin not in ('BUTTON', 'VOICE', 'BLE') or kind not in ('CONTACT_FAMILY', 'PHYSICAL_DISCOMFORT'):
        raise AppError('VALIDATION_ERROR', '求助来源或类型无效。', 422)
    _, member = await family.context(db, actor.user_id, fid)
    if member.role != 'ELDER':
        raise AppError('PERMISSION_DENIED', '仅长辈本人可以主动求助。', 403)
    # The family lock serializes different devices/keys as well as consent changes.
    # Existing keys for contact requests were hashed with the source alone.
    payload = {'origin': origin}
    if kind != 'CONTACT_FAMILY':
        payload['kind'] = kind
    idem = audit.Idempotency(key, 'help-request:' + str(fid), payload)
    previous = await idem.previous(db, actor.user_id, 7 * 86400)
    now = utcnow()
    row = await db.get(SignalEvent, previous) if previous else None
    if previous and (not row or row.deleted_at or row.retention_until <= now):
        raise AppError('HELP_REQUEST_EXPIRED', '这次求助记录已到期，请重新发起求助。', 409)
    event_type = 'PHYSICAL_DISCOMFORT' if kind == 'PHYSICAL_DISCOMFORT' else 'EMERGENCY'
    if not row:
        row = await db.scalar(select(SignalEvent).where(SignalEvent.family_id == fid,
            SignalEvent.owner_user_id == actor.user_id, SignalEvent.policy_version == POLICY,
            SignalEvent.type == event_type,
            SignalEvent.deleted_at.is_(None), SignalEvent.retention_until > now,
            SignalEvent.detected_at >= now - timedelta(seconds=120))
            .order_by(SignalEvent.detected_at.desc()).limit(1))
    duplicate = row is not None
    if not row:
        recipients = []
        for uid in await family.active_subjects(db, fid):
            try:
                await service.recipient(db, fid, actor.user_id, uid, event_type)
                recipients.append(uid)
            except AppError:
                continue
        row = SignalEvent(id=uuid7(), family_id=fid, owner_user_id=actor.user_id,
            type=event_type, severity='L3', policy_version=POLICY,
            trigger_category='EXPLICIT_HELP_' + origin, rule_id='EXPLICIT_HELP', rule_version='1.0.0',
            evidence_summary=service.COPY['EMERGENCY'][0], consent_check_result='ALLOWED' if recipients else 'WITHHELD',
            status='VALIDATED', detected_at=now, validated_at=now, retention_until=now + timedelta(days=7))
        db.add(row)
        await db.flush()
        await notifications.create_for_event(db, service.snapshot(row), recipients)
        if not await db.scalar(select(Notification.id).where(Notification.signal_event_id == row.id).limit(1)):
            row.status = 'NOTIFICATION_FAILED'
            row.rule_id = 'NO_AUTHORIZED_CONTACT' if not recipients else 'CHANNELS_DISABLED'
            row.failure_code = 'NO_AUTHORIZED_RECIPIENT' if not recipients else 'ALL_NOTIFICATION_CHANNELS_FAILED'
    await audit.record(db, actor.user_id, 'HELP_REQUEST_DUPLICATE' if duplicate else 'HELP_REQUESTED',
        'SIGNAL', row.id, fid, request_id, metadata=idem.metadata)
    return (await service.detail(db, actor, row.id, request_id)) | {'duplicate': duplicate}


async def progress(db, row):
    """No recipient identity/phone is exposed to the elder; never infer a connection."""
    from app.modules.signal import service
    deliveries = []
    rows = (await db.scalars(select(Notification).where(Notification.signal_event_id == row.id,
        Notification.deleted_at.is_(None)).order_by(Notification.created_at, Notification.id))).all()
    for notice in rows:
        try:
            await service.recipient(db, row.family_id, row.owner_user_id, notice.recipient_user_id, row.type)
        except AppError:
            continue
        pref = await preferences.current(db, row.family_id, row.owner_user_id, notice.recipient_user_id)
        if notice.channel not in pref.channels or notice.status == 'CANCELLED':
            continue
        deliveries.append(dict(channel=notice.channel, status=notice.status,
            simulated=notice.provider == 'mock' and notice.channel != 'IN_APP',
            delivery_status=notice.provider_status, error_code=notice.error_code,
            deferred=notice.status in ('PENDING', 'QUEUED') and preferences.ready_at(pref, utcnow()) > utcnow()))
    if row.status in ('RESOLVED', 'FALSE_POSITIVE'):
        message = '家属已人工标记解决或误报，尚未发送的通知已取消。'
    elif not deliveries:
        message = ('没有可用的已授权联系人，请在家庭设置中检查成员及通知授权。'
            if row.rule_id == 'NO_AUTHORIZED_CONTACT' else
            '没有可用的通知渠道，请检查家属通知偏好和当前授权。')
    elif any(d['error_code'] == 'DELIVERY_UNKNOWN' for d in deliveries):
        message = '部分通知的发送结果未知，请人工核实；不会自动重复外发。'
    elif all(d['status'] == 'FAILED' for d in deliveries):
        message = '求助通知发送失败，尚未确认联系到家人。'
    elif any(d['status'] == 'FAILED' for d in deliveries):
        message = '部分求助通知发送失败，请查看各渠道结果；尚未确认联系到家人。'
    elif any(d['status'] in ('PENDING', 'QUEUED') for d in deliveries):
        message = '求助已记录，通知等待发送；家属免打扰设置可能延迟通知。'
    else:
        message = '求助已记录，请查看通知结果和家人的处理进度；通知发送不代表已联系到家人。'
    return dict(help_message=message + FALLBACK, deliveries=deliveries, contact_result='UNKNOWN')
