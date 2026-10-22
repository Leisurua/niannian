from datetime import timezone

from sqlalchemy import select

from app.modules.audit import service as audit
from app.modules.device.service import current_binding
from app.modules.family.models import FamilyMember
from app.modules.message.models import FamilyMessage, MessageDelivery
from app.platform.errors import AppError
from app.platform.identifiers import utcnow


def validate_receipt_key(key):
    if not 1 <= len(key) <= 128 or any(not 32 <= ord(char) <= 126 for char in key):
        raise AppError("VALIDATION_ERROR", "请提供有效的幂等请求标识。", 422)


def delivery_view(row, recipient_user_id):
    return dict(id=str(row.id), recipient_user_id=str(recipient_user_id),
                status='READ' if row.read_at else 'RECEIVED' if row.received_at else 'QUEUED',
                received_at=row.received_at.astimezone(timezone.utc) if row.received_at else None,
                read_at=row.read_at.astimezone(timezone.utc) if row.read_at else None)


async def view(db, row, actor):
    query = select(MessageDelivery, FamilyMember.user_id).join(FamilyMember).where(
        MessageDelivery.message_id == row.id).order_by(MessageDelivery.id)
    if row.sender_user_id != actor.user_id:
        query = query.where(FamilyMember.user_id == actor.user_id, FamilyMember.status == 'ACTIVE')
    deliveries = (await db.execute(query)).all()
    return dict(id=str(row.id), sequence=row.sequence, family_id=str(row.family_id),
                sender_user_id=str(row.sender_user_id), message_type='TEXT', priority=row.priority,
                destination={'type': 'FAMILY_ROLE', 'role': row.destination_role}, payload={'text': row.text},
                created_at=row.created_at.astimezone(timezone.utc), deliveries=[delivery_view(d, user) for d, user in deliveries])


async def detail(db, actor, message_id, family_id=None):
    binding = await current_binding(db, actor, family_id)
    row = await db.get(FamilyMessage, message_id)
    if not row or row.family_id != binding.family_id or (row.sender_user_id != actor.user_id and not await db.scalar(
        select(MessageDelivery.id).join(FamilyMember).where(MessageDelivery.message_id == message_id,
            FamilyMember.user_id == actor.user_id, FamilyMember.status == 'ACTIVE'))):
        raise AppError('MESSAGE_NOT_FOUND', '留言不存在或无权访问。', 404)
    return row


async def send(db, actor, body, key, settings, request_id):
    binding = await current_binding(db, actor, body.family_id)
    idem = audit.Idempotency(key, 'message-send', {**body.model_dump(mode='json'), 'family_id': str(binding.family_id)})
    previous = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
    if previous:
        return await view(db, await detail(db, actor, previous, binding.family_id), actor)
    recipients = (await db.scalars(select(FamilyMember.id).where(
        FamilyMember.family_id == binding.family_id, FamilyMember.status == 'ACTIVE',
        FamilyMember.role == body.destination.role, FamilyMember.user_id != actor.user_id))).all()
    if not recipients:
        raise AppError('MESSAGE_NO_RECIPIENTS', '家庭中尚无已确认加入的接收成员。', 409)
    row = FamilyMessage(family_id=binding.family_id, sender_user_id=actor.user_id,
                        destination_role=body.destination.role, priority=body.priority, text=body.payload.text)
    db.add(row)
    await db.flush()
    db.add_all([MessageDelivery(message_id=row.id, recipient_member_id=member) for member in recipients])
    await audit.record(db, actor.user_id, 'MESSAGE_SENT', 'FAMILY_MESSAGE', row.id,
                       binding.family_id, request_id, metadata=idem.metadata)
    return await view(db, row, actor)


async def listing(db, actor, box, after_sequence, limit, family_id):
    binding = await current_binding(db, actor, family_id)
    query = select(FamilyMessage).where(FamilyMessage.family_id == binding.family_id,
                                       FamilyMessage.sequence > after_sequence)
    if box == 'OUTBOX':
        query = query.where(FamilyMessage.sender_user_id == actor.user_id)
    else:
        query = query.where(select(MessageDelivery.id).join(FamilyMember).where(MessageDelivery.message_id == FamilyMessage.id,
                            FamilyMember.user_id == actor.user_id, FamilyMember.status == 'ACTIVE').exists())
    rows = (await db.scalars(query.order_by(FamilyMessage.sequence).limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return dict(items=[await view(db, row, actor) for row in rows],
                page={'limit': limit, 'has_more': has_more, 'next_cursor': str(rows[-1].sequence) if has_more else None})


async def acknowledge(db, actor, delivery_id, read, key, request_id):
    binding = await current_binding(db, actor)
    row = await db.scalar(select(MessageDelivery).join(FamilyMessage).join(FamilyMember,
        FamilyMember.id == MessageDelivery.recipient_member_id).where(
        MessageDelivery.id == delivery_id, FamilyMember.user_id == actor.user_id, FamilyMember.status == 'ACTIVE',
        FamilyMessage.family_id == binding.family_id).with_for_update(of=MessageDelivery))
    if not row:
        raise AppError('MESSAGE_DELIVERY_NOT_FOUND', '回执不存在或无权确认。', 404)
    validate_receipt_key(key)
    changed = row.received_at is None or read and row.read_at is None
    row.received_at = row.received_at or utcnow()
    if read:
        row.read_at = row.read_at or utcnow()
    if changed:
        await audit.record(db, actor.user_id, 'MESSAGE_READ' if read else 'MESSAGE_RECEIVED',
                           'MESSAGE_DELIVERY', row.id, binding.family_id, request_id)
    return delivery_view(row, actor.user_id)
