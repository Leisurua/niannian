from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class Reminder(Base):
    __tablename__ = 'reminder'
    __table_args__ = (
        CheckConstraint("type IN ('CALENDAR','WEATHER','MEDICATION','WATER','CLOTHING','COMPANIONSHIP')", name='ck_reminder_type'),
        CheckConstraint("recurrence_kind IN ('ONCE','DAILY','WEEKLY','INTERVAL')", name='ck_reminder_recurrence'),
        CheckConstraint('recurrence_interval > 0 AND version > 0', name='ck_reminder_interval'),
        CheckConstraint('end_date IS NULL OR end_date >= start_date', name='ck_reminder_dates'),
        CheckConstraint('days_of_week <@ ARRAY[0,1,2,3,4,5,6]::smallint[]', name='ck_reminder_days'),
        CheckConstraint('(quiet_hours_start IS NULL AND quiet_hours_end IS NULL AND quiet_hours_timezone IS NULL) OR (quiet_hours_start IS NOT NULL AND quiet_hours_end IS NOT NULL AND quiet_hours_timezone IS NOT NULL)', name='ck_reminder_quiet'),
        CheckConstraint("jsonb_typeof(escalation_policy) = 'object'", name='ck_reminder_escalation'),
        Index('ix_reminder_due', 'owner_user_id', 'active', 'next_due_at'),
        Index('ix_reminder_family_owner', 'family_id', 'owner_user_id'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    type: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    schedule_time_local: Mapped[time] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String(64))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    recurrence_kind: Mapped[str] = mapped_column(String(24), default='ONCE', server_default='ONCE')
    recurrence_interval: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    days_of_week: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), default=list, server_default='{}')
    quiet_hours_start: Mapped[time | None] = mapped_column(Time)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time)
    quiet_hours_timezone: Mapped[str | None] = mapped_column(String(64))
    escalation_policy: Mapped[dict] = mapped_column(JSONB, default=dict, server_default='{}')
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReminderExecution(Base):
    __tablename__ = 'reminder_execution'
    __table_args__ = (
        UniqueConstraint('reminder_id', 'occurrence_key', name='uq_reminder_occurrence'),
        CheckConstraint("feedback_status IN ('PENDING','DONE','LATER','SKIPPED','NO_RESPONSE')", name='ck_execution_feedback'),
        CheckConstraint("source IN ('ONLINE','OFFLINE')", name='ck_execution_source'),
        CheckConstraint('attempt_count >= 0', name='ck_execution_attempts'),
        Index('ix_execution_owner_time', 'owner_user_id', 'scheduled_at', 'feedback_status'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    reminder_id: Mapped[UUID] = mapped_column(ForeignKey('reminder.id', ondelete='RESTRICT'))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    occurrence_key: Mapped[str] = mapped_column(String(96))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    local_date: Mapped[date] = mapped_column(Date)
    local_time: Mapped[time] = mapped_column(Time)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feedback_status: Mapped[str] = mapped_column(String(20), default='PENDING', server_default='PENDING')
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feedback_note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default='ONLINE', server_default='ONLINE')
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
