from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CHAR, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class Memory(Base):
    __tablename__ = 'memory'
    __table_args__ = (
        CheckConstraint("type IN ('PERSON','RELATIONSHIP','EVENT','PLACE','PREFERENCE','TABOO','PHOTO')", name='ck_memory_type'),
        CheckConstraint("source IN ('FAMILY_MEMBER','USER','AI_CANDIDATE','IMPORT')", name='ck_memory_source'),
        CheckConstraint("verification_status IN ('PENDING','CONFIRMED','REJECTED','REVOKED','DELETED')", name='ck_memory_status'),
        CheckConstraint("visibility IN ('OWNER_ONLY','AUTHORIZED_SCOPE','SPECIFIC_CONSENT')", name='ck_memory_visibility'),
        CheckConstraint("required_consent_scope IN ('VOICE','PORTRAIT','FAMILY_MEMORY','HEALTH_MEDICATION','CONVERSATION_SUMMARY','CAMERA_PROXIMITY','NOTIFICATION_TO_FAMILY')", name='ck_memory_scope'),
        CheckConstraint("verification_status <> 'CONFIRMED' OR verified_at IS NOT NULL", name='ck_memory_confirmed'),
        CheckConstraint('version > 0 AND length(title) > 0', name='ck_memory_version_title'),
        CheckConstraint("jsonb_typeof(attributes) = 'object'", name='ck_memory_attributes'),
        Index('ix_memory_scope', 'family_id', 'subject_user_id', 'verification_status'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'))
    subject_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    source_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    type: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(24))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, server_default='{}')
    required_consent_scope: Mapped[str] = mapped_column(String(40), default='FAMILY_MEMORY', server_default='FAMILY_MEMORY')
    verification_status: Mapped[str] = mapped_column(String(16), default='PENDING', server_default='PENDING')
    verified_by: Mapped[UUID | None] = mapped_column(ForeignKey('user.id', ondelete='SET NULL'))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    visibility: Mapped[str] = mapped_column(String(24), default='AUTHORIZED_SCOPE', server_default='AUTHORIZED_SCOPE')
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


class FileAsset(Base):
    __tablename__ = 'file_asset'
    __table_args__ = (
        CheckConstraint("media_type IN ('PHOTO','AUDIO','OTHER')", name='ck_file_media'),
        CheckConstraint("status IN ('PENDING_UPLOAD','AVAILABLE','QUARANTINED','DELETE_REQUESTED','DELETED','FAILED')", name='ck_file_status'),
        CheckConstraint('size_bytes >= 0', name='ck_file_size'),
        Index('ix_file_memory_status', 'memory_id', 'status'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'))
    memory_id: Mapped[UUID | None] = mapped_column(ForeignKey('memory.id', ondelete='SET NULL'))
    conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey('conversation.id', ondelete='SET NULL'))
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    media_type: Mapped[str] = mapped_column(String(24))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(CHAR(64))
    status: Mapped[str] = mapped_column(String(24), default='PENDING_UPLOAD', server_default='PENDING_UPLOAD')
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
