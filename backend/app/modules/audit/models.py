from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (CheckConstraint("result IN ('SUCCEEDED','FAILED','DENIED')", name="ck_audit_result"),
                      CheckConstraint("jsonb_typeof(metadata_redacted) = 'object'", name="ck_audit_metadata"),
                      Index("ix_audit_actor_created", "actor_user_id", "created_at"))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"))
    family_id: Mapped[UUID | None] = mapped_column(ForeignKey("family.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(48))
    target_id: Mapped[UUID | None] = mapped_column()
    reason: Mapped[str | None] = mapped_column(String(240))
    request_id: Mapped[str | None] = mapped_column(String(96))
    result: Mapped[str] = mapped_column(String(16), default="SUCCEEDED", server_default="SUCCEEDED")
    metadata_redacted: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
