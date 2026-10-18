from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class Conversation(Base):
    __tablename__ = 'conversation'
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','COMPLETED','INTERRUPTED','FAILED','DELETED')", name='ck_conversation_status'),
        CheckConstraint("summary_status IN ('NOT_REQUESTED','PENDING','READY','FAILED','DELETED')", name='ck_conversation_summary'),
        CheckConstraint("backend_state IN ('IDLE','LISTENING','THINKING','SPEAKING','WARNING','OFFLINE','ERROR')", name='ck_conversation_state'),
        CheckConstraint("input_mode IN ('VOICE','TEXT','LOCAL_WAKEWORD')", name='ck_conversation_input'),
        CheckConstraint('client_sequence >= 0 AND server_sequence >= 0', name='ck_conversation_sequence'),
        CheckConstraint('ended_at IS NULL OR ended_at >= started_at', name='ck_conversation_ended'),
        CheckConstraint("jsonb_typeof(provider_metadata) = 'object'", name='ck_conversation_metadata'),
        CheckConstraint('summary_version > 0', name='ck_conversation_summary_version'),
        Index('ix_conversation_owner_started', 'owner_user_id', 'started_at'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'))
    device_binding_id: Mapped[UUID | None] = mapped_column(ForeignKey('device_binding.id', ondelete='SET NULL'))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default='ACTIVE', server_default='ACTIVE')
    summary_status: Mapped[str] = mapped_column(String(20), default='NOT_REQUESTED', server_default='NOT_REQUESTED')
    summary_text: Mapped[str | None] = mapped_column(Text)
    summary_version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    summary_retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, server_default='{}')
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backend_state: Mapped[str] = mapped_column(String(16), default='IDLE', server_default='IDLE')
    input_mode: Mapped[str] = mapped_column(String(24), default='TEXT', server_default='TEXT')
    client_sequence: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    server_sequence: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
