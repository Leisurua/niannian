"""Minimal deletion receipts and external-copy work, never exported content."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class AccountDeletion(Base):
    __tablename__ = 'account_deletion'
    __table_args__ = (CheckConstraint("local_status IN ('PENDING','RETRY','ERASED')", name='ck_account_deletion_local'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'), unique=True)
    receipt_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    local_status: Mapped[str] = mapped_column(String(16), default='PENDING')
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    local_erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    backup_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    backup_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backup_evidence_hash: Mapped[str | None] = mapped_column(CHAR(64))


class ProviderCopy(Base):
    __tablename__ = 'provider_copy'
    __table_args__ = (UniqueConstraint('user_id', 'provider', name='uq_provider_copy_user'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    provider: Mapped[str] = mapped_column(String(160))
    first_possible_send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_possible_send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_hash: Mapped[str | None] = mapped_column(CHAR(64))
    resource_refs: Mapped[list] = mapped_column(JSONB, default=list, server_default='[]')


class AccountExport(Base):
    __tablename__ = 'account_export'
    __table_args__ = (
        UniqueConstraint('user_id', 'request_hash', name='uq_account_export_request'),
        CheckConstraint("status IN ('PENDING','RUNNING','READY','FAILED','CANCELLED','EXPIRED')", name='ck_account_export_status'),
        CheckConstraint('attempts BETWEEN 0 AND 3', name='ck_account_export_attempts'),
        CheckConstraint("(status = 'RUNNING' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status <> 'RUNNING' AND lease_token IS NULL AND lease_until IS NULL)", name='ck_account_export_lease'),
        Index('ix_account_export_queue', 'status', 'retry_at'),
        Index('ix_account_export_cleanup', 'cleanup_after'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    request_hash: Mapped[str] = mapped_column(CHAR(64))
    object_key: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(16), default='PENDING')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cleanup_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
