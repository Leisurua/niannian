"""Approved W7 delivery truth and per-recipient preferences."""
from datetime import datetime, time
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class Notification(Base):
    __tablename__ = 'notification'
    __table_args__ = (
        CheckConstraint("channel IN ('IN_APP','PUSH','SMS','PHONE')", name='ck_notification_channel'),
        CheckConstraint("status IN ('PENDING','QUEUED','SENT','DELIVERED','READ','FAILED','CANCELLED')", name='ck_notification_status'),
        CheckConstraint("action IN ('NONE','ACKNOWLEDGED','CONTACTED','FALSE_POSITIVE')", name='ck_notification_action'),
        CheckConstraint('length(summary) <= 240', name='ck_notification_minimal'),
        CheckConstraint('retention_until >= created_at AND dispatch_deadline >= created_at', name='ck_notification_retention'),
        Index('ux_notification_active_dedupe', 'dedupe_key', unique=True,
              postgresql_where="status <> 'CANCELLED' AND deleted_at IS NULL"),
        Index('ix_notification_recipient', 'recipient_user_id', 'created_at'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    signal_event_id: Mapped[UUID | None] = mapped_column(ForeignKey('signal_event.id', ondelete='SET NULL'))
    reminder_execution_id: Mapped[UUID | None] = mapped_column(ForeignKey('reminder_execution.id', ondelete='SET NULL'))
    recipient_user_id: Mapped[UUID | None] = mapped_column(ForeignKey('user.id', ondelete='SET NULL'))
    recipient_contact_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    channel: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20), default='PENDING', server_default='PENDING')
    summary: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(24), default='NONE', server_default='NONE')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    dedupe_key: Mapped[str | None] = mapped_column(String(64))
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dispatch_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationAttempt(Base):
    __tablename__ = 'notification_attempt'
    __table_args__ = (
        UniqueConstraint('notification_id', 'attempt_no', name='uq_notification_attempt'),
        CheckConstraint('attempt_no > 0', name='ck_notification_attempt_number'),
        CheckConstraint("status IN ('STARTED','SUCCEEDED','FAILED','RETRY_SCHEDULED')", name='ck_notification_attempt_status'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    notification_id: Mapped[UUID] = mapped_column(ForeignKey('notification.id', ondelete='CASCADE'))
    attempt_no: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default='STARTED', server_default='STARTED')
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_message_id: Mapped[str | None] = mapped_column(String(160))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail_redacted: Mapped[str | None] = mapped_column(Text)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationPreference(Base):
    __tablename__ = 'notification_preference'
    __table_args__ = (
        UniqueConstraint('family_id', 'owner_user_id', 'recipient_user_id', name='uq_notification_preference'),
        CheckConstraint('version > 0', name='ck_notification_preference_version'),
        CheckConstraint('(quiet_hours_start IS NULL) = (quiet_hours_end IS NULL)', name='ck_notification_preference_quiet'),
        CheckConstraint("jsonb_typeof(channels) = 'array' AND channels <@ '[\"IN_APP\",\"PUSH\"]'::jsonb", name='ck_notification_preference_channels'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    recipient_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    channels: Mapped[list] = mapped_column(JSONB)
    timezone: Mapped[str] = mapped_column(String(64))
    quiet_hours_start: Mapped[time | None] = mapped_column(Time)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
