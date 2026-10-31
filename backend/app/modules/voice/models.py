from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column
from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class VoiceProfile(Base):
    __tablename__ = 'voice_profile'
    __table_args__ = (
        CheckConstraint("status IN ('UPLOADING','PENDING','QUEUED','GENERATING','READY','ACTIVE','FAILED','REVOKED','DELETED')", name='ck_voice_status'),
        Index('uq_voice_active', 'family_id', 'owner_user_id', unique=True, postgresql_where=text("status = 'ACTIVE'")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'))
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    creator_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    display_name: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(16), default='UPLOADING')
    version: Mapped[int] = mapped_column(Integer, default=1)
    sample_key: Mapped[str | None] = mapped_column(String(200))
    sample_hash: Mapped[str | None] = mapped_column(String(64))
    preview_key: Mapped[str | None] = mapped_column(String(200))
    provider_voice_id: Mapped[str | None] = mapped_column(String(200))
    provider_workspace: Mapped[str | None] = mapped_column(String(100))
    provider_model: Mapped[str] = mapped_column(String(64), default='cosyvoice-v3.5-flash')
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))


class VoicePreference(Base):
    __tablename__ = 'voice_preference'
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'), primary_key=True)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'), primary_key=True)
    voice_profile_id: Mapped[UUID | None] = mapped_column(ForeignKey('voice_profile.id', ondelete='SET NULL'))
    cloud_tts_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
