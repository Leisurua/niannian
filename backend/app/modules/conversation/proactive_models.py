"""W6-04 reviewed preferences and bounded non-content counters."""
from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, SmallInteger, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base


class ProactivePreference(Base):
    __tablename__ = 'proactive_preference'
    __table_args__ = (
        CheckConstraint('daily_cap BETWEEN 0 AND 3', name='ck_proactive_cap'),
        CheckConstraint('version > 0', name='ck_proactive_version'),
        CheckConstraint('(quiet_start IS NULL) = (quiet_end IS NULL)', name='ck_proactive_quiet'),
        CheckConstraint('(confirmed_by_user_id IS NULL AND confirmed_version IS NULL) OR '
            '(confirmed_by_user_id IS NOT NULL AND confirmed_version IS NOT NULL AND confirmed_by_user_id = owner_user_id AND confirmed_version = version)', name='ck_proactive_confirmation'),
    )
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'), primary_key=True)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'), primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64))
    window_start: Mapped[time] = mapped_column(Time)
    window_end: Mapped[time] = mapped_column(Time)
    quiet_start: Mapped[time | None] = mapped_column(Time)
    quiet_end: Mapped[time | None] = mapped_column(Time)
    daily_cap: Mapped[int] = mapped_column(SmallInteger, default=0, server_default='0')
    version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    proposed_by_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    confirmed_version: Mapped[int | None] = mapped_column(Integer)
    paused_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProactiveDailyCounter(Base):
    __tablename__ = 'proactive_daily_counter'
    __table_args__ = (
        ForeignKeyConstraint(['family_id', 'owner_user_id'], ['proactive_preference.family_id', 'proactive_preference.owner_user_id'], ondelete='CASCADE'),
        CheckConstraint('used_count BETWEEN 0 AND 3', name='ck_proactive_count'),
    )
    family_id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_user_id: Mapped[UUID] = mapped_column(primary_key=True)
    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    used_count: Mapped[int] = mapped_column(SmallInteger, default=0, server_default='0')
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
