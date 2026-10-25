"""Authenticated, bounded ZIP export assembled in memory, with explicit fields."""
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.encoders import jsonable_encoder
from sqlalchemy import or_, select

from app.modules.account.service import lock_families
from app.modules.audit.models import AuditLog
from app.modules.audit.service import record
from app.modules.auth.models import DeviceSession
from app.modules.consent.models import Consent
from app.modules.conversation.models import Conversation
from app.modules.conversation.proactive_models import ProactiveDailyCounter, ProactivePreference
from app.modules.conversation.summary import readable
from app.modules.device.models import DeviceBinding
from app.modules.family.models import FamilyMember
from app.modules.memory.models import FileAsset, Memory
from app.modules.message.models import FamilyMessage, MessageDelivery
from app.modules.notification.contacts import view as contact_view
from app.modules.notification.models import FamilyContact, Notification, NotificationPreference
from app.modules.reminder.models import Reminder, ReminderExecution
from app.modules.report.models import InteractionMetric
from app.modules.signal.models import SignalEvent
from app.platform.errors import AppError
from app.platform.identifiers import utcnow


def too_large():
    return AppError('ACCOUNT_EXPORT_TOO_LARGE', '导出超过单次上限，请联系服务管理员处理。', 413)


async def build_export(db, actor, storage, settings, request_id):
    uid, now = actor.user_id, utcnow()
    await lock_families(db, uid)
    data = dict(format_version=1, generated_at=now, user=actor.user, collections={},
        scope='本人资料、授权、本人业务内容和已发送留言；不批量导出其他主体的家庭内容。',
        excluded=['访问/刷新令牌、邀请码和凭证摘要', '供应商内部标识、向量和运维元数据',
            '已删除、撤回或到期的内容', '未持久化的逐字稿与录音', '其他主体的业务内容'])
    budget = settings.account_export_max_bytes

    async def rows(model, condition):
        values = list((await db.scalars(select(model).where(condition).limit(10001))).all())
        if len(values) > 10000:
            raise too_large()
        return values

    async def add(model, condition, fields):
        data['collections'][model.__tablename__] = [
            {name: getattr(row, name) for name in fields.split()} for row in await rows(model, condition)]

    await add(FamilyMember, FamilyMember.user_id == uid, 'id family_id role status permission_codes joined_at left_at')
    await add(Consent, or_(Consent.subject_user_id == uid, Consent.grantee_user_id == uid),
        'id family_id subject_user_id grantee_user_id scope status version source granted_at revoked_at expires_at')
    await add(DeviceSession, DeviceSession.user_id == uid, 'id issued_at expires_at revoked_at last_seen_at')
    await add(DeviceBinding, DeviceBinding.owner_user_id == uid,
        'id family_id client_kind device_type app_version os_version capabilities status created_at last_seen_at')
    await add(Memory, (Memory.subject_user_id == uid) & Memory.deleted_at.is_(None) & Memory.revoked_at.is_(None)
        & ~Memory.verification_status.in_(('DELETED', 'REVOKED')) & or_(Memory.expires_at.is_(None), Memory.expires_at > now),
        'id family_id type title content source version attributes required_consent_scope verification_status visibility created_at updated_at')
    await add(Reminder, (Reminder.owner_user_id == uid) & Reminder.deleted_at.is_(None),
        'id family_id type title content schedule_time_local timezone start_date end_date recurrence_kind recurrence_interval days_of_week quiet_hours_start quiet_hours_end quiet_hours_timezone escalation_policy active version next_due_at created_at updated_at')
    await add(ReminderExecution, (ReminderExecution.owner_user_id == uid) & ReminderExecution.reminder_id.in_(
        select(Reminder.id).where(Reminder.deleted_at.is_(None))),
        'id reminder_id scheduled_at triggered_at feedback_status feedback_at feedback_note source next_due_at')
    conversations = []
    for row in await rows(Conversation, (Conversation.owner_user_id == uid) & Conversation.deleted_at.is_(None)):
        conversations.append(dict(id=row.id, family_id=row.family_id, started_at=row.started_at,
            ended_at=row.ended_at, status=row.status, summary=await readable(db, row)))
    data['collections']['conversation'] = conversations
    await add(InteractionMetric, (InteractionMetric.owner_user_id == uid) & (InteractionMetric.retention_until > now),
        'conversation_id sequence family_id occurred_at duration_seconds emotions topics simulated retention_until')
    await add(ProactivePreference, ProactivePreference.owner_user_id == uid,
        'family_id timezone window_start window_end quiet_start quiet_end daily_cap version confirmed_version paused_on')
    await add(ProactiveDailyCounter, ProactiveDailyCounter.owner_user_id == uid, 'family_id local_date used_count')
    await add(NotificationPreference, or_(NotificationPreference.owner_user_id == uid, NotificationPreference.recipient_user_id == uid),
        'family_id owner_user_id recipient_user_id channels timezone quiet_hours_start quiet_hours_end version')
    from app.modules.notification.service import context as notification_context
    notifications = []
    for row in await rows(Notification, Notification.recipient_user_id == uid):
        if row.status in ('SENT', 'DELIVERED', 'READ', 'FAILED') and await notification_context(db, row, for_delivery=False):
            notifications.append({name: getattr(row, name) for name in (
                'id', 'channel', 'status', 'summary', 'created_at', 'sent_at', 'delivered_at', 'read_at', 'action')})
    data['collections']['notification'] = notifications
    data['collections']['family_contact'] = [dict(family_id=row.family_id, **contact_view(row))
        for row in await rows(FamilyContact, FamilyContact.user_id == uid)]
    await add(SignalEvent, (SignalEvent.owner_user_id == uid) & SignalEvent.deleted_at.is_(None) & (SignalEvent.retention_until > now),
        'id family_id type severity status detected_at resolved_at resolution_code')
    await add(FamilyMessage, FamilyMessage.sender_user_id == uid, 'id family_id destination_role priority text created_at')
    await add(MessageDelivery, MessageDelivery.recipient_member_id.in_(select(FamilyMember.id).where(FamilyMember.user_id == uid)),
        'message_id received_at read_at')
    await add(AuditLog, AuditLog.actor_user_id == uid, 'action target_type result created_at')
    available_memories = [row['id'] for row in data['collections']['memory']]
    assets = await rows(FileAsset, (FileAsset.owner_user_id == uid) & (FileAsset.status == 'AVAILABLE')
        & FileAsset.deleted_at.is_(None) & FileAsset.memory_id.in_(available_memories))
    data['collections']['file_asset'] = [dict(id=f.id, memory_id=f.memory_id, mime_type=f.mime_type,
        archive_path=f'photos/{f.id}') for f in assets]
    payload = json.dumps(jsonable_encoder(data), ensure_ascii=False).encode('utf-8')
    size = len(payload)
    if size + sum(f.size_bytes for f in assets) > budget:
        raise too_large()
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('account.json', payload)
        for asset in assets:
            # Storage failure aborts the export; never return an incomplete ZIP.
            content = await storage.read(asset.object_key + '.safe', settings.file_max_size_bytes)
            size += len(content)
            if size > budget:
                raise too_large()
            archive.writestr(f'photos/{asset.id}', content)
    await record(db, uid, 'ACCOUNT_EXPORTED', 'USER', uid, request_id=request_id)
    return output.getvalue()
