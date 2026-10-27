from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class AvatarJob(Base):
    __tablename__ = 'avatar_job'
    __table_args__ = (
        CheckConstraint("status IN ('UPLOADING','QUEUED','STYLIZING','PREPARING','RENDERING','READY','ACTIVE','FAILED','CANCELLED')", name='ck_avatar_status'),
        CheckConstraint('version > 0', name='ck_avatar_version'),
        Index('ix_avatar_owner', 'family_id', 'owner_user_id', 'created_at'),
        Index('uq_avatar_active', 'family_id', 'owner_user_id', unique=True, postgresql_where=text("status = 'ACTIVE'")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    consent_id: Mapped[UUID]
    provider_id: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey('file_asset.id', ondelete='SET NULL'))
    pack_id: Mapped[UUID | None] = mapped_column(ForeignKey('file_asset.id', ondelete='SET NULL'))
    preview_id: Mapped[UUID | None] = mapped_column(ForeignKey('file_asset.id', ondelete='SET NULL'))
    status: Mapped[str] = mapped_column(String(16), default='UPLOADING')
    version: Mapped[int] = mapped_column(Integer, default=1)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
