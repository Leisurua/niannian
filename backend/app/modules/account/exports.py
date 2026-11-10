"""Durable account export jobs; private results expire and join account erasure."""
import asyncio
from datetime import timedelta
import logging
from types import SimpleNamespace

from sqlalchemy import delete, or_, select, update

from app.modules.account.export import build_export
from app.modules.account.models import AccountExport
from app.modules.account.service import lock_families
from app.modules.auth.service import active_user, user_view
from app.modules.auth.tokens import digest
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7
from app.platform.logging import log_event


def view(row):
    status = 'EXPIRED' if row.expires_at <= utcnow() and row.status != 'CANCELLED' else row.status
    return dict(id=str(row.id), status=status, attempts=row.attempts, error_code=row.error_code,
        created_at=row.created_at, expires_at=row.expires_at,
        download_url=f'/v1/me/exports/{row.id}/download' if status == 'READY' else None)


async def owned(db, uid, job_id):
    row = await db.scalar(select(AccountExport).where(AccountExport.id == job_id, AccountExport.user_id == uid))
    if row is None:
        raise AppError('ACCOUNT_EXPORT_NOT_FOUND', '导出任务不存在。', 404)
    return row


async def request(db, actor, key, settings):
    if not key or len(key) > 128 or not key.isascii() or any(ord(c) < 33 for c in key):
        raise AppError('VALIDATION_ERROR', '请提供有效的幂等键。', 422)
    # Authentication's user lock serializes concurrent creation for this account.
    previous = await db.scalar(select(AccountExport).where(AccountExport.user_id == actor.user_id,
        AccountExport.request_hash == digest(key)))
    if previous:
        return view(previous)
    now = utcnow()
    pending = await db.scalar(select(AccountExport).where(AccountExport.user_id == actor.user_id,
        AccountExport.expires_at > now, or_(AccountExport.status.in_(('PENDING', 'RUNNING')),
            (AccountExport.status == 'READY') & (AccountExport.created_at > now - timedelta(minutes=5))))
        .order_by(AccountExport.created_at.desc()).limit(1))
    if pending:
        return view(pending)
    job_id = uuid7()
    expires = now + timedelta(hours=settings.account_export_hours)
    # A new, unclaimed job has no object to erase.
    row = AccountExport(id=job_id, user_id=actor.user_id, request_hash=digest(key),
        object_key=f'account-exports/{actor.user_id}/{job_id}.zip', status='PENDING', attempts=0,
        created_at=now, expires_at=expires, retry_at=now, cleanup_after=expires, purged_at=now)
    db.add(row)
    await db.flush()
    return view(row)


async def retry(db, actor, job_id, settings):
    row = await owned(db, actor.user_id, job_id)
    # API user lock prevents concurrent retry, but coordinate with storage cleanup too.
    await db.refresh(row, with_for_update=True)
    if row.expires_at <= utcnow() or row.status == 'CANCELLED':
        raise AppError('ACCOUNT_EXPORT_EXPIRED', '导出任务已到期，请重新申请。', 410)
    if row.status == 'FAILED':
        row.status, row.attempts, row.error_code = 'PENDING', 0, None
        row.retry_at = utcnow()
        row.expires_at = utcnow() + timedelta(hours=settings.account_export_hours)
        row.cleanup_after = row.expires_at
    return view(row)


async def download(db, actor, job_id, storage, settings):
    row = await owned(db, actor.user_id, job_id)
    if row.expires_at <= utcnow() or row.status in ('CANCELLED', 'EXPIRED'):
        raise AppError('ACCOUNT_EXPORT_EXPIRED', '导出已到期，请重新申请。', 410)
    if row.status != 'READY':
        raise AppError('ACCOUNT_EXPORT_NOT_READY', '导出尚未完成，请稍后查询。', 409)
    return await storage.read(row.object_key, settings.account_export_max_bytes + 1048576)


async def invalidate(db, uid):
    # Keep every attempted key until late storage I/O can no longer recreate bytes.
    now = utcnow()
    await db.execute(update(AccountExport).where(AccountExport.user_id == uid).values(
        status='CANCELLED', expires_at=now, cleanup_after=now + timedelta(seconds=360),
        lease_token=None, lease_until=None, error_code=None))


async def cleanup_one(factory, storage):
    async with factory() as db:
        now = utcnow()
        row = await db.scalar(select(AccountExport).where(AccountExport.purged_at.is_(None),
            AccountExport.cleanup_after <= now, AccountExport.retry_at <= now,
            or_(AccountExport.expires_at <= now, AccountExport.status.in_(('CANCELLED', 'FAILED'))))
            .order_by(AccountExport.cleanup_after).limit(1).with_for_update(skip_locked=True))
        if row is None:
            return False
        try:
            if storage is None:
                raise RuntimeError('Storage unavailable')
            await getattr(storage, 'delete_all_versions', storage.delete)(row.object_key)
        except Exception:
            row.retry_at = now + timedelta(seconds=60)
            log_event(logging.getLogger('nianian.worker'), logging.ERROR, 'ACCOUNT_EXPORT_PURGE_FAILED',
                error_code='STORAGE_DELETE_FAILED')
        else:
            row.purged_at = now
            row.lease_token = row.lease_until = None
            if row.status not in ('CANCELLED', 'FAILED'):
                row.status = 'EXPIRED'
        await db.commit()
        return True


async def process_one(factory, storage, settings):
    if await cleanup_one(factory, storage):
        return True
    async with factory() as db:
        now = utcnow()
        row = await db.scalar(select(AccountExport).where(AccountExport.expires_at > now,
            or_((AccountExport.status == 'PENDING') & (AccountExport.retry_at <= now),
                (AccountExport.status == 'RUNNING') & (AccountExport.lease_until <= now)))
            .order_by(AccountExport.created_at).limit(1).with_for_update(skip_locked=True))
        if row is None:
            return False
        if row.attempts >= 3:
            row.status, row.error_code = 'FAILED', 'EXPORT_RETRY_EXHAUSTED'
            row.lease_token = row.lease_until = None
            row.cleanup_after = now + timedelta(seconds=360)
            await db.commit()
            return True
        job_id, uid, token = row.id, row.user_id, uuid7()
        row.status, row.attempts, row.error_code = 'RUNNING', row.attempts + 1, None
        # Claiming a job can lead to a write even when the attempt later fails.
        # Manual retries reset the attempt count but preserve this cleanup obligation.
        row.purged_at = None
        row.lease_token, row.lease_until = token, now + timedelta(seconds=300)
        await db.commit()
    try:
        async with asyncio.timeout(180), factory() as db:
            # No user write lock: status polling remains available during generation.
            await active_user(db, uid, lock=False)
            await lock_families(db, uid)
            row = await db.scalar(select(AccountExport).where(AccountExport.id == job_id,
                AccountExport.status == 'RUNNING', AccountExport.lease_token == token,
                AccountExport.lease_until > utcnow(), AccountExport.expires_at > utcnow()).with_for_update())
            if row is None:
                return True
            user = await active_user(db, uid, lock=False)
            if storage is None:
                raise RuntimeError('Storage unavailable')
            payload = await build_export(db, SimpleNamespace(user_id=uid, user=user_view(user)), storage, settings, str(job_id))
            await storage.write(row.object_key, payload, 'application/zip')
            row.status = 'READY'
            row.lease_token = row.lease_until = None
            await db.commit()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        async with factory() as db:
            row = await db.scalar(select(AccountExport).where(AccountExport.id == job_id,
                AccountExport.status == 'RUNNING', AccountExport.lease_token == token).with_for_update())
            if row:
                permanent = isinstance(error, AppError) and error.code in ('ACCOUNT_EXPORT_TOO_LARGE', 'AUTH_SESSION_REVOKED')
                row.status = 'FAILED' if permanent or row.attempts >= 3 else 'PENDING'
                row.error_code = error.code if permanent else 'EXPORT_DEPENDENCY_UNAVAILABLE'
                row.retry_at = utcnow() + timedelta(seconds=10 * row.attempts)
                row.lease_token = row.lease_until = None
                if row.status == 'FAILED':
                    row.cleanup_after = utcnow() + timedelta(seconds=360)
                await db.commit()
        log_event(logging.getLogger('nianian.worker'), logging.ERROR, 'ACCOUNT_EXPORT_FAILED',
            error_code='EXPORT_GENERATION_FAILED')
    return True


async def maintenance(db):
    # Cancelled account rows can disappear only after private bytes are purged.
    now = utcnow()
    await db.execute(delete(AccountExport).where(AccountExport.purged_at.is_not(None),
        or_(AccountExport.status == 'CANCELLED',
            (AccountExport.expires_at <= now) & (AccountExport.created_at < now - timedelta(days=7)))))
