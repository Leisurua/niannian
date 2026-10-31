from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class Task(Base):
    __tablename__ = 'task_outbox'
    __table_args__ = (
        CheckConstraint('resource_version > 0', name='ck_task_version'),
        CheckConstraint("kind IN ('MEMORY_INDEX','MEMORY_CLEANUP','FILE_CLEANUP','CONVERSATION_SUMMARY','CONVERSATION_SUMMARY_CLEANUP','NOTIFICATION_DISPATCH','SIGNAL_CLEANUP','NOTIFICATION_CLEANUP','AVATAR_GENERATE','VOICE_GENERATE','VOICE_CLEANUP')", name='ck_task_kind'),
        CheckConstraint("status IN ('PENDING','RUNNING','RETRY','SUCCEEDED','DEAD')", name='ck_task_status'),
        CheckConstraint('attempts >= 0 AND max_attempts > 0 AND attempts <= max_attempts', name='ck_task_attempts'),
        CheckConstraint("(status = 'RUNNING' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR (status <> 'RUNNING' AND lease_token IS NULL AND lease_until IS NULL)", name='ck_task_lease'),
        Index('ix_task_ready', 'status', 'available_at'), Index('ix_task_lease', 'status', 'lease_until'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'))
    resource_id: Mapped[UUID]
    resource_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    business_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(16), default='PENDING', server_default='PENDING')
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default='5')
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


async def enqueue(db, kind, family_id, resource_id, version, epoch='source', rearm=False):
    key = f'{kind}:{resource_id}:{version}:{epoch}'
    command = insert(Task).values(id=uuid7(), kind=kind, family_id=family_id,
        resource_id=resource_id, resource_version=version, business_key=key,
        max_attempts=1 if kind in ('AVATAR_GENERATE', 'VOICE_GENERATE') else 5)
    if rearm:
        command = command.on_conflict_do_update(index_elements=['business_key'],
            set_={'status': 'PENDING', 'attempts': 0, 'available_at': utcnow(), 'updated_at': utcnow()},
            where=Task.status == 'SUCCEEDED')
    else:
        command = command.on_conflict_do_nothing(index_elements=['business_key'])
    await db.execute(command)


async def claim(db, now=None, *, kinds=None, exclude_kinds=()):
    now = now or utcnow()
    query = select(Task).where(
        ((Task.status.in_(('PENDING', 'RETRY'))) & (Task.available_at <= now)) |
        ((Task.status == 'RUNNING') & (Task.lease_until <= now))
    )
    if kinds is not None:
        query = query.where(Task.kind.in_(kinds))
    if exclude_kinds:
        query = query.where(~Task.kind.in_(exclude_kinds))
    rows = (await db.scalars(query.order_by(Task.available_at, Task.id).limit(20).with_for_update(skip_locked=True))).all()
    for row in rows:
        if row.attempts >= row.max_attempts:
            row.status, row.lease_token, row.lease_until = 'DEAD', None, None
            row.last_error_code, row.updated_at = 'LEASE_EXHAUSTED', now
            continue
        row.status, row.attempts = 'RUNNING', row.attempts + 1
        row.lease_token, row.lease_until, row.updated_at = uuid7(), now + timedelta(seconds=30), now
        await db.flush()
        return row
    return None


async def leased(db, task_id, token):
    return await db.scalar(select(Task).where(Task.id == task_id, Task.status == 'RUNNING',
        Task.lease_token == token, Task.lease_until > utcnow()).with_for_update())


async def finish(db, task_id, token, error=None):
    row = await leased(db, task_id, token)
    if row is None:
        return False
    row.status = ('DEAD' if row.attempts >= row.max_attempts else 'RETRY') if error else 'SUCCEEDED'
    row.last_error_code = 'DEPENDENCY_UNAVAILABLE' if error else None
    row.available_at = utcnow() + timedelta(seconds=min(300, 2 ** row.attempts))
    row.lease_token, row.lease_until, row.updated_at = None, None, utcnow()
    return True


async def defer_cleanup(db, task_id, token, available_at):
    row = await leased(db, task_id, token)
    if row is None:
        return False
    row.status = 'RETRY' if row.attempts < row.max_attempts else 'DEAD'
    row.available_at, row.last_error_code = available_at, 'UPLOAD_WINDOW_OPEN'
    row.lease_token, row.lease_until, row.updated_at = None, None, utcnow()
    return True


async def dead_resource_ids(db, kind):
    return set((await db.scalars(select(Task.resource_id).where(Task.kind == kind, Task.status == 'DEAD'))).all())
