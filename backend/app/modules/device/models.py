from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class DeviceBinding(Base):
    __tablename__ = "device_binding"
    __table_args__ = (
        CheckConstraint("device_type IN ('ANDROID_TABLET','ANDROID_PHONE','OTHER')", name="ck_device_type"),
        CheckConstraint("kiosk_status IN ('UNKNOWN','ACTIVE','CONFIG_ERROR','DISABLED')", name="ck_device_kiosk"),
        CheckConstraint("wakeword_status IN ('UNKNOWN','READY','DISABLED','ERROR')", name="ck_device_wakeword"),
        CheckConstraint("ble_status IN ('DISCONNECTED','CONNECTING','CONNECTED','LOW_BATTERY','ERROR')", name="ck_device_ble"),
        CheckConstraint("camera_permission IN ('UNKNOWN','GRANTED','DENIED')", name="ck_device_camera"),
        CheckConstraint("phone_permission IN ('UNKNOWN','GRANTED','DENIED')", name="ck_device_phone"),
        CheckConstraint("status IN ('ACTIVE','UNBOUND','LOST','DISABLED')", name="ck_device_status"),
        CheckConstraint("jsonb_typeof(capabilities) = 'object'", name="ck_device_capabilities"),
        Index("ix_device_owner_seen", "owner_user_id", "last_seen_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    device_id_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    device_type: Mapped[str] = mapped_column(String(32))
    app_version: Mapped[str] = mapped_column(String(64))
    os_version: Mapped[str] = mapped_column(String(64))
    kiosk_status: Mapped[str] = mapped_column(String(24), default="UNKNOWN", server_default="UNKNOWN")
    wakeword_status: Mapped[str] = mapped_column(String(24), default="UNKNOWN", server_default="UNKNOWN")
    ble_status: Mapped[str] = mapped_column(String(24), default="DISCONNECTED", server_default="DISCONNECTED")
    camera_permission: Mapped[str] = mapped_column(String(16), default="UNKNOWN", server_default="UNKNOWN")
    phone_permission: Mapped[str] = mapped_column(String(16), default="UNKNOWN", server_default="UNKNOWN")
    capabilities: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_state_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
