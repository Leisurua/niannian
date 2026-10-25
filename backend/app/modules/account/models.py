"""Minimal deletion receipts and external-copy work, never exported content."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
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
