from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class User(Base):
    __tablename__ = "user"
    __table_args__ = (CheckConstraint("global_status IN ('ACTIVE','SUSPENDED','DELETED')", name="ck_user_status"),
                      CheckConstraint("length(display_name) > 0", name="ck_user_name"),
                      CheckConstraint("jsonb_typeof(accessibility_settings) = 'object'", name="ck_user_settings"))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    global_status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    display_name: Mapped[str] = mapped_column(String(120))
    phone_ciphertext: Mapped[str | None] = mapped_column(Text)
    phone_hash: Mapped[str | None] = mapped_column(CHAR(64), unique=True)
    phone_last4: Mapped[str | None] = mapped_column(CHAR(4))
    accessibility_settings: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai", server_default="Asia/Shanghai")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceSession(Base):
    __tablename__ = "device_session"
    __table_args__ = (CheckConstraint("expires_at > issued_at", name="ck_session_expiry"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    device_binding_id: Mapped[UUID | None] = mapped_column(ForeignKey("device_binding.id", ondelete="SET NULL"))
    refresh_token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    logout_reason: Mapped[str | None] = mapped_column(String(32))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    ip_hash: Mapped[str | None] = mapped_column(CHAR(64))
    user_agent_hash: Mapped[str | None] = mapped_column(CHAR(64))
