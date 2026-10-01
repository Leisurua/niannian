from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7

ROLES = ("ELDER", "CHILD", "CAREGIVER", "EMERGENCY_CONTACT")


class Family(Base):
    __tablename__ = "family"
    __table_args__ = (CheckConstraint("status IN ('ACTIVE','SUSPENDED','DELETED')", name="ck_family_status"),
                      CheckConstraint("length(name) > 0", name="ck_family_name"))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(120))
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FamilyMember(Base):
    __tablename__ = "family_member"
    __table_args__ = (
        CheckConstraint("role IN ('ELDER','CHILD','CAREGIVER','EMERGENCY_CONTACT')", name="ck_member_role"),
        CheckConstraint("status IN ('PENDING','ACTIVE','REVOKED','LEFT')", name="ck_member_status"),
        CheckConstraint("jsonb_typeof(permission_codes) = 'object'", name="ck_member_permissions"),
        Index("uq_member_current", "family_id", "user_id", unique=True, postgresql_where=text("status IN ('PENDING','ACTIVE')")),
        Index("ix_member_family_status", "family_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("family.id", ondelete="RESTRICT"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING")
    permission_codes: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    invited_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


class FamilyInvitation(Base):
    __tablename__ = "family_invitation"
    __table_args__ = (
        CheckConstraint("target_role IN ('ELDER','CHILD','CAREGIVER','EMERGENCY_CONTACT')", name="ck_invitation_role"),
        CheckConstraint("status IN ('ACTIVE','USED','REVOKED','EXPIRED')", name="ck_invitation_status"),
        CheckConstraint("expires_at > created_at", name="ck_invitation_expiry"),
        CheckConstraint("max_usage > 0 AND used_count >= 0 AND used_count <= max_usage", name="ck_invitation_usage"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("family.id", ondelete="RESTRICT"))
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    target_role: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_usage: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
