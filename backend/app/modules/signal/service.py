from datetime import timedelta
import hashlib
from types import SimpleNamespace
from uuid import uuid5
from sqlalchemy import delete, select

from app.ai.signal_candidates import extract_mock, revalidate_semantic
from app.modules.audit import service as audit
from app.modules.audit.models import AuditLog
from app.modules.auth.service import active_user, codec, display_names
from app.modules.consent import service as consent
from app.modules.conversation import service as conversation
from app.modules.family import service as family
from app.modules.safety.rules import evaluate, RULE_VERSION
from app.modules.signal.models import SignalEvent
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7, iso_utc
from app.platform.pagination import page_rows
from app.platform.resource_access import authorize
from app.platform.tasks import enqueue

POLICY_VERSION = 'w7-mock-1.0.0'
POLICIES = {'MOCK': POLICY_VERSION, 'SEMANTIC': 'signals-semantic-1.0.0', 'RULE': 'signals-rule-1.0.0'}
COPY = {
    'SCAM_RISK': ('交流中出现需核实的敏感操作组合，请先联系家人核实。', 'PAUSE_AND_VERIFY_WITH_FAMILY'),
    'PHYSICAL_DISCOMFORT': ('老人提到身体不舒服，可主动关心并提供联系帮助。', 'CHECK_IN_AND_OFFER_CONTACT'),
    'EMOTION_EXPRESSION': ('有情绪相关表达，仅为交流观察线索。', 'OFFER_COMPANIONSHIP'),
    'MISS_FAMILY': ('老人表达了思念或联系家人的意愿。', 'OFFER_FAMILY_CONTACT'),
    'IMPORTANT_MEMORY': ('有待核实的往事线索，不代表已确认的家庭事实。', 'OFFER_MEMORY_REVIEW'),
}


def dedupe_key(fid, owner, kind, category, severity, now):
    return hashlib.sha256(f'{fid}:{owner}:{kind}:{category}:{severity}:{int(now.timestamp()) // 1800}'.encode()).hexdigest()


async def recipient(db, fid, owner, user_id, kind):
    if user_id == owner:
        raise AppError('PERMISSION_DENIED', '仅供获授权的家属查看。', 403)
    await active_user(db, user_id, lock=False)
    await active_user(db, owner, lock=False)
    await authorize(db, SimpleNamespace(user_id=user_id), fid, owner, 'SIGNAL_READ', allow_self=False)
    scopes = ['NOTIFICATION_TO_FAMILY'] + (['HEALTH_MEDICATION'] if kind == 'PHYSICAL_DISCOMFORT' else [])
    return tuple([await consent.explicit_scope(db, fid, owner, user_id, scope) for scope in scopes])


async def record_turn(db, actor, conversation_id, request_id, text, candidates, *, candidate_mode='MOCK'):
    locked_source = await conversation.signal_source(db, conversation_id, actor=actor, active=True)
    if not locked_source:
        return []
    if candidate_mode not in POLICIES:
        return []
    if candidate_mode == 'SEMANTIC':
        expected = revalidate_semantic(candidates, conversation_id=conversation_id,
            message_id=uuid5(conversation_id, request_id), current_text=text)
    else:
        expected = extract_mock(text, conversation_id=conversation_id, message_id=uuid5(conversation_id, request_id))
        if candidate_mode == 'RULE':
            expected = tuple(c for c in expected if c.type in ('SCAM_RISK', 'EMERGENCY'))
    if tuple(candidates) != expected:
        return []
    idem = audit.Idempotency(request_id, 'signal-turn:' + str(conversation_id),
        {'candidates': [(c.type, c.trigger_category) for c in expected]})
    if await idem.previous(db, actor.user_id, 7 * 86400):
        return []
    now, events = utcnow(), []
    for candidate in expected:
        if candidate.type not in COPY:
            continue
        recipients = []
        for uid in await family.active_subjects(db, locked_source['family_id']):
            try:
                await recipient(db, locked_source['family_id'], actor.user_id, uid, candidate.type)
                recipients.append(uid)
            except AppError:
                continue
        if not recipients:
            continue
        rule = evaluate(text)
        severity = rule.severity if candidate.type == 'SCAM_RISK' else 'L1'
        key = dedupe_key(locked_source['family_id'], actor.user_id, candidate.type, candidate.trigger_category, severity, now)
        old = await db.scalar(select(SignalEvent).where(SignalEvent.dedupe_key == key,
            SignalEvent.deleted_at.is_(None), SignalEvent.retention_until > now))
        if old:
            await audit.record(db, actor.user_id, 'SIGNAL_DUPLICATE', 'SIGNAL', old.id, old.family_id,
                metadata=idem.metadata)
            continue
        row = SignalEvent(id=uuid7(), owner_user_id=actor.user_id, family_id=locked_source['family_id'],
            type=candidate.type, severity=severity, source_conversation_id=conversation_id,
            evidence_summary=COPY[candidate.type][0], rule_id=rule.rule_id if candidate.type == 'SCAM_RISK' else candidate.trigger_category,
            rule_version=RULE_VERSION, policy_version=POLICIES[candidate_mode], trigger_category=candidate.trigger_category,
            consent_check_result='ALLOWED', status='VALIDATED', dedupe_key=key, detected_at=now,
            validated_at=now, retention_until=now + timedelta(days=7))
        db.add(row)
        await db.flush()
        from app.modules.notification.service import create_for_event
        await create_for_event(db, snapshot(row), recipients)
        await audit.record(db, actor.user_id, 'SIGNAL_VALIDATED', 'SIGNAL', row.id, row.family_id,
            metadata={'rule_id': row.rule_id, 'rule_version': row.rule_version,
                'provider': {'MOCK': 'mock', 'SEMANTIC': 'openai_compatible', 'RULE': 'rules'}[candidate_mode], **idem.metadata})
        events.append(dict(signal_event_id=str(row.id), type=row.type, severity=row.severity))
    return events


def snapshot(row):
    return dict(id=row.id, family_id=row.family_id, owner_user_id=row.owner_user_id,
        type=row.type, retention_until=row.retention_until, recognition_mode=recognition_mode(row))


def recognition_mode(row):
    return next((mode for mode, version in POLICIES.items() if version == row.policy_version), 'MOCK')


async def internal_metadata(db, event_id):
    row = await db.get(SignalEvent, event_id) if event_id else None
    return snapshot(row) if row else None


async def accessible(db, row, actor, *, owner_status=False):
    if not row or row.deleted_at or row.retention_until <= utcnow() or row.type not in COPY:
        return False
    source = await conversation.signal_source(db, row.source_conversation_id) if row.source_conversation_id else None
    if not source or source['family_id'] != row.family_id or source['owner_user_id'] != row.owner_user_id:
        return False
    await db.refresh(row)
    if row.deleted_at or row.retention_until <= utcnow() or row.status in ('WITHHELD','DETECTED'):
        return False
    try:
        if owner_status and actor.user_id == row.owner_user_id:
            return True
        await recipient(db, row.family_id, row.owner_user_id, actor.user_id, row.type)
        return True
    except AppError:
        return False


async def delivery_context(db, event_id, recipient_id, *, for_delivery=True):
    row = await db.get(SignalEvent, event_id, populate_existing=True)
    authorized_with_family_lock = await accessible(db, row, SimpleNamespace(user_id=recipient_id))
    if not authorized_with_family_lock:
        return None
    await db.refresh(row)
    if row.deleted_at or (for_delivery and row.status in ('WITHHELD','FALSE_POSITIVE','RESOLVED')):
        return None
    grants = await recipient(db, row.family_id, row.owner_user_id, recipient_id, row.type)
    return snapshot(row) | {'grants': grants}


async def delivery_outcome(db, event_id, outcome):
    row = await db.get(SignalEvent, event_id, populate_existing=True)
    if row and not row.deleted_at and row.retention_until > utcnow() and row.status in ('VALIDATED','NOTIFIED','NOTIFICATION_FAILED'):
        row.status = outcome
        if outcome == 'NOTIFIED' and not row.notified_at:
            row.notified_at = utcnow()


def view(row, *, owner=False, detail=False):
    mode = recognition_mode(row)
    prefix = {'MOCK': 'Mock · ', 'SEMANTIC': 'AI 语义线索 · ', 'RULE': '规则提示 · '}[mode]
    summary = prefix + (('安全提示已记录，请先联系家人核实。' if row.type == 'SCAM_RISK'
        else '您的关注提示已记录，可查看家人的处理进度。') if owner else COPY[row.type][0])
    result = dict(id=str(row.id), owner_user_id=str(row.owner_user_id), family_id=str(row.family_id),
        type=row.type, severity=row.severity, summary=summary, status=row.status,
        recognition_mode=mode, created_at=iso_utc(row.detected_at))
    if not owner:
        result.update(reason={'category': row.trigger_category, 'display_text': COPY[row.type][0]}, recommended_action=COPY[row.type][1])
        if detail:
            result.update(source_conversation_id=str(row.source_conversation_id), occurred_at=iso_utc(row.detected_at))
            if row.last_action_at:
                result.update(actioned_at=iso_utc(row.last_action_at), last_action_by=str(row.last_action_by) if row.last_action_by else None)
            if row.resolved_at:
                result.update(resolved_at=iso_utc(row.resolved_at), resolution_code=row.resolution_code)
    return result


async def can_handle(db, actor, row):
    try:
        await authorize(db, actor, row.family_id, row.owner_user_id, 'SIGNAL_WRITE', allow_self=False)
        return True
    except AppError:
        return False


async def detail(db, actor, event_id, request_id):
    row = await db.get(SignalEvent, event_id)
    if not await accessible(db, row, actor, owner_status=True):
        raise AppError('SIGNAL_NOT_FOUND', '提示不存在或无权查看。', 404)
    await audit.record(db, actor.user_id, 'SIGNAL_READ', 'SIGNAL', row.id, row.family_id, request_id)
    result = view(row, owner=actor.user_id == row.owner_user_id, detail=True)
    result['can_handle'] = actor.user_id != row.owner_user_id and await can_handle(db, actor, row)
    if actor.user_id == row.owner_user_id:
        result['history'] = await action_history(db, row.id)
        if row.last_action_at:
            result['actioned_at'] = iso_utc(row.last_action_at)
        if row.resolved_at:
            result.update(resolved_at=iso_utc(row.resolved_at), resolution_code=row.resolution_code)
    if actor.user_id != row.owner_user_id:
        result['history'] = await action_history(db, row.id)
        from app.modules.notification.contacts import event_contacts
        result['contacts'] = await event_contacts(db, actor, row)
    return result


async def action_history(db, event_id):
    rows = (await db.scalars(select(AuditLog).where(AuditLog.target_id == event_id,
        AuditLog.target_type == 'SIGNAL', AuditLog.action.in_(
            ('SIGNAL_ACKNOWLEDGE', 'SIGNAL_CONTACT', 'SIGNAL_FALSE_POSITIVE', 'SIGNAL_RESOLVE')))
        .order_by(AuditLog.created_at, AuditLog.id))).all()
    names = await display_names(db, [r.actor_user_id for r in rows if r.actor_user_id])
    return [dict(action=r.action.removeprefix('SIGNAL_'), actor_user_id=str(r.actor_user_id) if r.actor_user_id else None,
        actor_display_name=names.get(r.actor_user_id, '家庭成员'), occurred_at=iso_utc(r.created_at)) for r in rows]


async def handle_action(db, actor, event_id, body, key, request_id, settings):
    row = await db.get(SignalEvent, event_id)
    # Recheck source, family, membership and current consent before idempotent replay too.
    # accessible() acquires the family lock used by consent changes and notification delivery.
    if not await accessible(db, row, actor):
        raise AppError('SIGNAL_NOT_FOUND', '提示不存在或无权处理。', 404)
    if not await can_handle(db, actor, row):
        raise AppError('PERMISSION_DENIED', '当前成员没有关注事件处理权限。', 403)
    idem = audit.Idempotency(key, 'signal-action:' + str(event_id), body.model_dump())
    previous = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
    if not previous:
        target, allowed = {
            'ACKNOWLEDGE': ('ACKNOWLEDGED', ('VALIDATED', 'NOTIFIED', 'NOTIFICATION_FAILED')),
            'CONTACT': ('CONTACTED', ('ACKNOWLEDGED',)),
            'RESOLVE': ('RESOLVED', ('ACKNOWLEDGED', 'CONTACTED')),
            'FALSE_POSITIVE': ('FALSE_POSITIVE', ('VALIDATED', 'NOTIFIED', 'NOTIFICATION_FAILED', 'ACKNOWLEDGED', 'CONTACTED')),
        }[body.action]
        if row.status != target:
            if row.status != body.expected_status or row.status not in allowed:
                raise AppError('RESOURCE_STATE_CONFLICT', '处理状态已变化，请刷新后确认；不能跳过确认或退回旧状态。', 409)
            row.status = target
            row.last_action_by, row.last_action_at = actor.user_id, utcnow()
            if target in ('RESOLVED', 'FALSE_POSITIVE'):
                row.resolved_at = row.last_action_at
                row.resolution_code = 'FALSE_POSITIVE' if target == 'FALSE_POSITIVE' else 'FAMILY_CONFIRMED'
            from app.modules.notification.service import event_action
            await event_action(db, row.id, target)
        else:
            return await detail(db, actor, event_id, request_id)
        await audit.record(db, actor.user_id, 'SIGNAL_' + body.action, 'SIGNAL', row.id, row.family_id,
            request_id, metadata=idem.metadata)
    return await detail(db, actor, event_id, request_id)


async def visible_ids(db, actor, *, owner_status=False):
    authorized_event_ids = []
    permission_candidates = (await db.scalars(select(SignalEvent).where(SignalEvent.deleted_at.is_(None),
        SignalEvent.retention_until > utcnow()).order_by(SignalEvent.family_id, SignalEvent.id))).all()
    for row in permission_candidates:
        if await accessible(db, row, actor, owner_status=owner_status):
            authorized_event_ids.append(row.id)
    return authorized_event_ids


async def listing(db, actor, filters, limit, cursor, settings, request_id):
    ids = await visible_ids(db, actor, owner_status=True)
    query = select(SignalEvent).where(SignalEvent.id.in_(ids))
    for name, value in filters.items():
        if value is not None:
            query = query.where(SignalEvent.detected_at >= value if name == 'from' else
                SignalEvent.detected_at <= value if name == 'to' else getattr(SignalEvent, name) == value)
    rows, page = await page_rows(db, query, SignalEvent, codec(settings), f'signals:{actor.user_id}:{filters}', limit, cursor)
    await audit.record(db, actor.user_id, 'SIGNAL_LIST_READ', 'SIGNAL', request_id=request_id)
    return dict(items=[view(r, owner=actor.user_id == r.owner_user_id) for r in rows], page=page, request_id=request_id)


async def maintenance(db):
    rows = (await db.scalars(select(SignalEvent).order_by(SignalEvent.family_id, SignalEvent.id))).all()
    for row in rows:
        source = await conversation.signal_source(db, row.source_conversation_id) if row.source_conversation_id else None
        if row.deleted_at or row.retention_until <= utcnow() or not source:
            row.deleted_at = row.deleted_at or utcnow()
            await enqueue(db, 'SIGNAL_CLEANUP', row.family_id, row.id, 1)


async def cleanup(db, event_id):
    row = await db.get(SignalEvent, event_id)
    if row and (row.deleted_at or row.retention_until <= utcnow()):
        from app.modules.notification.service import delete_for_event
        await delete_for_event(db, event_id)
        await db.execute(delete(SignalEvent).where(SignalEvent.id == event_id))
