from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class FamilyMessage(Base):
    __tablename__ = 'family_message'
    __table_args__ = (
        CheckConstraint("priority IN ('NORMAL','IMPORTANT')", name='ck_message_priority'),
        CheckConstraint('length(text) BETWEEN 1 AND 2000', name='ck_message_text'),
        CheckConstraint("destination_role IN ('ELDER','CHILD','CAREGIVER')", name='ck_message_role'),
        Index('ix_message_family_sequence', 'family_id', 'sequence'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey('family.id', ondelete='RESTRICT'))
    sender_user_id: Mapped[UUID] = mapped_column(ForeignKey('user.id', ondelete='RESTRICT'))
    destination_role: Mapped[str] = mapped_column(String(16))
    priority: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


class MessageDelivery(Base):
    __tablename__ = 'message_delivery'
    __table_args__ = (
        UniqueConstraint('message_id', 'recipient_member_id', name='uq_delivery_recipient'),
        Index('ix_delivery_recipient', 'recipient_member_id', 'message_id'),
        CheckConstraint('read_at IS NULL OR received_at IS NOT NULL', name='ck_delivery_read_received'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    message_id: Mapped[UUID] = mapped_column(ForeignKey('family_message.id', ondelete='CASCADE'))
    recipient_member_id: Mapped[UUID] = mapped_column(ForeignKey('family_member.id', ondelete='RESTRICT'))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
