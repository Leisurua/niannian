from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, synonym
from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class SignalEvent(Base):
    __tablename__ = 'signal_event'
    __table_args__ = (
        CheckConstraint("type IN ('PHYSICAL_DISCOMFORT','EMOTION_EXPRESSION','IMPORTANT_MEMORY','MISS_FAMILY','SCAM_RISK','EMERGENCY')", name='ck_signal_type'),
        CheckConstraint("severity IN ('L0','L1','L2','L3','L4')", name='ck_signal_severity'),
        CheckConstraint("status IN ('DETECTED','VALIDATED','NOTIFIED','ACKNOWLEDGED','CONTACTED','FALSE_POSITIVE','RESOLVED','WITHHELD','NOTIFICATION_FAILED')", name='ck_signal_status'),
        CheckConstraint("consent_check_result IN ('ALLOWED','DENIED','WITHHELD')", name='ck_signal_consent'),
        CheckConstraint('confidence BETWEEN 0 AND 1', name='ck_signal_confidence'),
        CheckConstraint('retention_until >= detected_at', name='ck_signal_retention'),
        CheckConstraint('source_message_id IS NULL AND evidence_hash IS NULL', name='ck_signal_mock_source'),
        Index('ix_signal_family_owner', 'family_id', 'owner_user_id', 'detected_at'),
        Index('ix_signal_dedupe', 'dedupe_key'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'))
    type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(8), default='L1', server_default='L1')
    source_conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey('conversation.id', ondelete='SET NULL'))
    source_message_id: Mapped[UUID | None]
    evidence_summary: Mapped[str | None] = mapped_column(Text)
    evidence_hash: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    rule_id: Mapped[str | None] = mapped_column(String(96))
    rule_version: Mapped[str | None] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(64))
    trigger_category: Mapped[str] = mapped_column(String(64))
    consent_check_result: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default='DETECTED', server_default='DETECTED')
    dedupe_key: Mapped[str | None] = mapped_column(String(64))
    duplicate_of_id: Mapped[UUID | None] = mapped_column(ForeignKey('signal_event.id', ondelete='SET NULL'))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    created_at = synonym('detected_at')
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_action_by: Mapped[UUID | None] = mapped_column(ForeignKey('user.id', ondelete='SET NULL'))
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_code: Mapped[str | None] = mapped_column(String(32))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
