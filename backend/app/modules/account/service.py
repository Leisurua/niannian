"""Account boundaries: lock out first, erase owned data, report copies honestly."""
from datetime import timedelta
import hmac
from urllib.parse import urlsplit

from sqlalchemy import delete, or_, select, update, text
from sqlalchemy.dialects.postgresql import insert

from app.modules.account.models import AccountDeletion, ProviderCopy
from app.modules.audit.models import AuditLog
from app.modules.auth.models import DeviceSession, User
from app.modules.auth.tokens import digest
from app.modules.consent.models import Consent
from app.modules.conversation.models import Conversation
from app.modules.conversation.proactive_models import ProactivePreference
from app.modules.device.models import DeviceBinding
from app.modules.family.models import Family, FamilyInvitation, FamilyMember
from app.modules.memory.models import FileAsset, Memory
from app.modules.message.models import FamilyMessage, MessageDelivery
from app.modules.notification.models import FamilyContact, Notification, NotificationAttempt, NotificationPreference
from app.modules.reminder.models import Reminder, ReminderExecution
from app.modules.report.models import InteractionMetric
from app.modules.signal.models import SignalEvent
from app.modules.avatar.models import AvatarJob
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7
from app.platform.tasks import Task


async def note_possible_copy(db, user_id, provider):
    """Commit before external I/O. A timeout or canceled call is still uncertain."""
    now = utcnow()
    await db.execute(insert(ProviderCopy).values(id=uuid7(), user_id=user_id, provider=provider,
        first_possible_send_at=now, last_possible_send_at=now).on_conflict_do_update(
            constraint='uq_provider_copy_user', set_={'last_possible_send_at': now,
                'confirmed_at': None, 'evidence_hash': None}))


async def note_provider_resource(db, uid, provider, reference):
    await note_possible_copy(db, uid, provider)
    copy = await db.scalar(select(ProviderCopy).where(ProviderCopy.user_id == uid,
        ProviderCopy.provider == provider).with_for_update())
    if reference not in copy.resource_refs:
        copy.resource_refs = [*copy.resource_refs, reference]


async def send_gate(db, uid, *, shared=False):
    # An independent transaction holds only this advisory lock during network
    # I/O. Ordinary consent revocation must remain responsive during a slow LLM.
    key = int(digest('account-provider-send:' + str(uid))[:16], 16) & ((1 << 63) - 1)
    function = 'pg_advisory_xact_lock_shared' if shared else 'pg_advisory_xact_lock'
    await db.execute(text(f'SELECT {function}(:key)'), {'key': key})


def llm_copy_provider(settings):
    # Preserve the configured service identity across provider/config changes;
    # never retain API credentials, prompts or model replies.
    return 'LLM:' + (urlsplit(settings.llm_base_url or '').hostname or 'unknown')[:150]


async def lock_families(db, uid):
    ids = select(FamilyMember.family_id).where(FamilyMember.user_id == uid)
    await db.scalars(select(Family).where(Family.id.in_(ids)).order_by(Family.id).with_for_update())


async def request_deletion(db, actor, receipt_token, settings):
    uid, now = actor.user_id, utcnow()
    if await db.scalar(select(AccountDeletion.id).where(AccountDeletion.receipt_hash == digest(receipt_token))):
        raise AppError('ACCOUNT_RECEIPT_CONFLICT', '请重新生成独立的删除回执凭证。', 409)
    await lock_families(db, uid)
    row = AccountDeletion(id=uuid7(), user_id=uid, receipt_hash=digest(receipt_token),
        requested_at=now, retry_at=now, backup_due_at=now + timedelta(days=settings.backup_retention_days))
    db.add(row)
    await db.flush()
    # Authentication already holds the user lock. These changes and the durable
    # receipt commit atomically; failures cannot leave a half-disabled account.
    await db.execute(update(User).where(User.id == uid).values(global_status='DELETED', deleted_at=now,
        display_name='已删除账户', phone_ciphertext=None, phone_hash=None, phone_last4=None,
        accessibility_settings={}, timezone='UTC', created_at=now, updated_at=now))
    await db.execute(delete(DeviceSession).where(DeviceSession.user_id == uid))
    await erase_database(db, uid)
    return await deletion_view(db, row)


async def erase_database(db, uid):
    """Erase the subject's rows; other subjects' records retain a nameless FK.

    Family locks serialize with shared writes and notification dispatch. Pending
    object keys stay private until a successful physical delete after PUT expiry.
    """
    memories = select(Memory.id).where(Memory.subject_user_id == uid)
    conversations = select(Conversation.id).where(Conversation.owner_user_id == uid)
    reminders = select(Reminder.id).where(Reminder.owner_user_id == uid)
    executions = select(ReminderExecution.id).where(ReminderExecution.owner_user_id == uid)
    signals = select(SignalEvent.id).where(SignalEvent.owner_user_id == uid)
    notifications = select(Notification.id).where(or_(Notification.recipient_user_id == uid,
        Notification.signal_event_id.in_(signals), Notification.reminder_execution_id.in_(executions)))
    consents = or_(Consent.subject_user_id == uid, Consent.grantee_user_id == uid, Consent.grantor_user_id == uid)
    file_filter = or_(FileAsset.owner_user_id == uid, FileAsset.memory_id.in_(memories),
        FileAsset.conversation_id.in_(conversations))
    # Keep the remote IDs required to actually request supplier erasure even
    # after the originating notification and attempt are physically removed.
    external = (await db.execute(select(Notification, NotificationAttempt).join(NotificationAttempt,
        NotificationAttempt.notification_id == Notification.id).where(Notification.id.in_(notifications),
            NotificationAttempt.provider != 'mock'))).all()
    for notification, attempt in external:
        await note_provider_resource(db, uid, 'NOTIFICATION:' + attempt.provider,
            dict(channel=notification.channel, resource_id=attempt.provider_message_id, service_account='LEGACY_UNVERIFIED'))
    # Collect identifiers before removing rows so audit/idempotency/outbox rows
    # cannot retain references or recreate deleted work.
    targets = {uid}
    for query in (memories, conversations, reminders, executions, signals, notifications,
            select(AvatarJob.id).where(AvatarJob.owner_user_id == uid),
            select(Consent.id).where(consents), select(FileAsset.id).where(file_filter),
            select(FamilyMember.id).where(FamilyMember.user_id == uid),
            select(FamilyInvitation.id).where(FamilyInvitation.created_by_user_id == uid),
            select(DeviceBinding.id).where(DeviceBinding.owner_user_id == uid),
            select(FamilyMessage.id).where(FamilyMessage.sender_user_id == uid)):
        targets.update((await db.scalars(query)).all())
    await db.execute(delete(Task).where(Task.resource_id.in_(targets)))
    await db.execute(delete(AuditLog).where(or_(AuditLog.actor_user_id == uid, AuditLog.target_id.in_(targets))))
    # Account deletion always rechecks even previously soft-deleted files.
    await db.execute(update(FileAsset).where(file_filter).values(status='DELETE_REQUESTED', deleted_at=utcnow(), owner_user_id=uid))
    await db.execute(delete(AvatarJob).where(AvatarJob.owner_user_id == uid))
    await db.execute(delete(Notification).where(Notification.id.in_(notifications)))
    await db.execute(delete(SignalEvent).where(SignalEvent.owner_user_id == uid))
    await db.execute(delete(InteractionMetric).where(InteractionMetric.owner_user_id == uid))
    await db.execute(delete(Consent).where(consents))
    await db.execute(delete(Memory).where(Memory.subject_user_id == uid))
    await db.execute(delete(ReminderExecution).where(ReminderExecution.owner_user_id == uid))
    await db.execute(delete(Reminder).where(Reminder.owner_user_id == uid))
    await db.execute(delete(Conversation).where(Conversation.owner_user_id == uid))
    await db.execute(delete(ProactivePreference).where(ProactivePreference.owner_user_id == uid))
    await db.execute(delete(NotificationPreference).where(or_(NotificationPreference.owner_user_id == uid,
        NotificationPreference.recipient_user_id == uid)))
    await db.execute(delete(FamilyContact).where(FamilyContact.user_id == uid))
    await db.execute(delete(DeviceBinding).where(DeviceBinding.owner_user_id == uid))
    await db.execute(delete(FamilyMessage).where(FamilyMessage.sender_user_id == uid))
    await db.execute(delete(MessageDelivery).where(MessageDelivery.recipient_member_id.in_(
        select(FamilyMember.id).where(FamilyMember.user_id == uid))))
    await db.execute(delete(FamilyInvitation).where(FamilyInvitation.created_by_user_id == uid))
    family_ids = list((await db.scalars(select(FamilyMember.family_id).where(FamilyMember.user_id == uid))).all())
    await db.execute(delete(FamilyMember).where(FamilyMember.user_id == uid))
    await db.execute(update(FamilyMember).where(FamilyMember.invited_by_user_id == uid).values(invited_by_user_id=None))
    await db.execute(update(Memory).where(Memory.verified_by == uid).values(verified_by=None))
    await db.execute(update(SignalEvent).where(SignalEvent.last_action_by == uid).values(last_action_by=None))
    for fid in family_ids:
        if not await db.scalar(select(FamilyMember.id).where(FamilyMember.family_id == fid,
                FamilyMember.status.in_(('ACTIVE', 'PENDING'))).limit(1)):
            await db.execute(update(Family).where(Family.id == fid).values(name='已删除家庭', status='DELETED', deleted_at=utcnow()))
            await db.execute(delete(FamilyInvitation).where(FamilyInvitation.family_id == fid))


async def receipt(db, deletion_id, token):
    row = await db.get(AccountDeletion, deletion_id)
    if not row or not hmac.compare_digest(row.receipt_hash, digest(token)):
        raise AppError('ACCOUNT_DELETION_NOT_FOUND', '删除回执不存在或凭证无效。', 404)
    return row


async def deletion_view(db, row):
    copies = (await db.scalars(select(ProviderCopy).where(ProviderCopy.user_id == row.user_id)
        .order_by(ProviderCopy.provider))).all()
    complete = row.local_status == 'ERASED' and row.backup_confirmed_at and all(c.confirmed_at for c in copies)
    return dict(id=str(row.id), status='COMPLETED' if complete else 'PENDING', local_status=row.local_status,
        requested_at=row.requested_at, local_erased_at=row.local_erased_at, last_error_code=row.last_error_code,
        backup=dict(status='CONFIRMED' if row.backup_confirmed_at else 'REQUIRES_OPERATOR',
            due_at=row.backup_due_at, overdue=not row.backup_confirmed_at and row.backup_due_at < utcnow()),
        providers=[dict(provider=c.provider, status='CONFIRMED' if c.confirmed_at else 'REQUIRES_OPERATOR') for c in copies],
        retained='仅保留无姓名账户占位、删除回执和副本核验摘要；其他主体拥有的共享业务记录保留。',
        device_notice='断网设备需重新联网或缓存到期后清理；已下载的导出文件由持有人保管。')


async def process_one(factory, storage, settings):
    """Row lock is the lease: concurrent workers skip it; crashes roll back.

    Storage deletion is idempotent. A failed transaction leaves all keys available
    for retry. Requests without files also pass here before local completion.
    """
    async with factory() as db:
        row = await db.scalar(select(AccountDeletion).where(AccountDeletion.local_status != 'ERASED',
            AccountDeletion.retry_at <= utcnow()).order_by(AccountDeletion.requested_at)
            .limit(1).with_for_update(skip_locked=True))
        if row is None:
            return False
        # All previously authorized provider sends must finish/cancel before
        # final erasure can be confirmed. New turns fail account authentication.
        await send_gate(db, row.user_id)
        files = (await db.scalars(select(FileAsset).where(FileAsset.owner_user_id == row.user_id))).all()
        wait_until = max((f.created_at + timedelta(seconds=360) for f in files), default=utcnow())
        if wait_until > utcnow():
            row.retry_at, row.last_error_code = wait_until, 'UPLOAD_WINDOW_OPEN'
        else:
            try:
                if files and storage is None:
                    raise RuntimeError('Storage unavailable')
                for asset in files:
                    # Delete all object versions when the adapter supports them.
                    purge = getattr(storage, 'delete_all_versions', storage.delete)
                    await purge(asset.object_key)
                    await purge(asset.object_key + '.safe')
            except Exception:
                row.local_status, row.last_error_code = 'RETRY', 'STORAGE_DELETE_FAILED'
                row.retry_at = utcnow() + timedelta(seconds=60)
            else:
                await db.execute(delete(FileAsset).where(FileAsset.owner_user_id == row.user_id))
                row.local_status, row.local_erased_at, row.last_error_code = 'ERASED', utcnow(), None
                # Snapshot the accepted retention interval; a later config change
                # must not silently extend an existing deletion's backup promise.
                row.backup_due_at = row.local_erased_at + (row.backup_due_at - row.requested_at)
        await db.commit()
        return True


async def maintenance(db, settings):
    now = utcnow()
    # Idempotency keys live in audit rows; never prune inside the replay window.
    days = max(settings.audit_retention_days, settings.idempotency_seconds / 86400 + 1)
    await db.execute(delete(AuditLog).where(AuditLog.created_at < now - timedelta(days=days),
        or_(AuditLog.action != 'FILE_UPLOAD_WINDOW_CLOSED', ~AuditLog.target_id.in_(
            select(FileAsset.id).where(FileAsset.status == 'AVAILABLE')))))
    await db.execute(delete(Task).where(Task.status == 'SUCCEEDED',
        Task.updated_at < now - timedelta(days=settings.task_retention_days)))


async def confirm_copy(db, deletion_id, kind, evidence, provider=None):
    """Operator-only CLI, intentionally absent from public HTTP routes.

    Evidence is a reference to a verified deletion/inventory report, not a claim
    inferred from elapsed time. Store its digest, never a ticket with personal data.
    """
    row = await db.get(AccountDeletion, deletion_id, with_for_update=True)
    if not row or row.local_status != 'ERASED':
        raise ValueError('Local erasure must finish first')
    if not evidence.strip():
        raise ValueError('Verified evidence reference required')
    if kind == 'backup':
        row.backup_confirmed_at, row.backup_evidence_hash = utcnow(), digest(evidence)
    else:
        copy = await db.scalar(select(ProviderCopy).where(ProviderCopy.user_id == row.user_id,
            ProviderCopy.provider == provider).with_for_update())
        if copy is None:
            raise ValueError('Unknown provider copy')
        copy.confirmed_at, copy.evidence_hash = utcnow(), digest(evidence)
        copy.resource_refs = []
