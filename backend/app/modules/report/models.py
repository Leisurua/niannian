from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base


class InteractionMetric(Base):
    """One successfully completed turn. No input, reply or free-form labels."""
    __tablename__ = 'interaction_metric'
    __table_args__ = (
        CheckConstraint('sequence > 0 AND duration_seconds BETWEEN 0 AND 300', name='ck_metric_duration'),
        CheckConstraint('retention_until > occurred_at', name='ck_metric_retention'),
        Index('ix_metric_family_owner_time', 'family_id', 'owner_user_id', 'occurred_at'),
    )
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey('conversation.id', ondelete='CASCADE'), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='CASCADE'))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='CASCADE'))
    consent_id: Mapped[UUID] = mapped_column(ForeignKey('consent.id', ondelete='CASCADE'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    emotions: Mapped[list[str]] = mapped_column(ARRAY(String(24)))
    topics: Mapped[list[str]] = mapped_column(ARRAY(String(24)))
    simulated: Mapped[bool] = mapped_column(Boolean)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
