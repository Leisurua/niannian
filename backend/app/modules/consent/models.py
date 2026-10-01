from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7

SCOPES = ("VOICE", "PORTRAIT", "FAMILY_MEMORY", "HEALTH_MEDICATION", "CONVERSATION_SUMMARY", "CAMERA_PROXIMITY", "NOTIFICATION_TO_FAMILY")


class Consent(Base):
    __tablename__ = "consent"
    __table_args__ = (
        CheckConstraint("scope IN ('VOICE','PORTRAIT','FAMILY_MEMORY','HEALTH_MEDICATION','CONVERSATION_SUMMARY','CAMERA_PROXIMITY','NOTIFICATION_TO_FAMILY')", name="ck_consent_scope"),
        CheckConstraint("status IN ('GRANTED','REVOKED','EXPIRED')", name="ck_consent_status"),
        CheckConstraint("source IN ('ONBOARDING','SETTINGS','IMPORT')", name="ck_consent_source"),
        CheckConstraint("version > 0", name="ck_consent_version"),
        CheckConstraint("status <> 'GRANTED' OR granted_at IS NOT NULL", name="ck_consent_granted"),
        CheckConstraint("status <> 'REVOKED' OR revoked_at IS NOT NULL", name="ck_consent_revoked"),
        Index("ix_consent_granted", "family_id", "subject_user_id", "grantee_user_id", "scope", postgresql_where=text("status = 'GRANTED'")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("family.id", ondelete="RESTRICT"))
    subject_user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    grantor_user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    grantee_user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    scope: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="GRANTED", server_default="GRANTED")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    source: Mapped[str] = mapped_column(String(24), default="SETTINGS", server_default="SETTINGS")
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("consent.id", ondelete="SET NULL"))
    audit_log_id: Mapped[UUID | None] = mapped_column(ForeignKey("audit_log.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
