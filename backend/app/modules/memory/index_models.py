"""Frozen chunk/vector entities. No vendor SDK or new vector dependency."""
from datetime import datetime
import json
from uuid import UUID

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.platform.db import Base
from app.platform.identifiers import utcnow, uuid7


class Vector(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw):
        return 'VECTOR'

    def bind_processor(self, dialect):
        return lambda value: json.dumps(value, allow_nan=False) if value is not None else None

    def result_processor(self, dialect, coltype):
        return lambda value: json.loads(value) if isinstance(value, str) else value


# Let Alembic reflect the existing pgvector type instead of treating it as NullType.
from sqlalchemy.dialects.postgresql.base import ischema_names
ischema_names.setdefault('vector', Vector)


class MemoryChunk(Base):
    __tablename__ = 'memory_chunk'
    __table_args__ = (
        UniqueConstraint('memory_id', 'ordinal', name='uq_chunk_ordinal'),
        CheckConstraint('ordinal >= 0', name='ck_chunk_ordinal'),
        CheckConstraint("status IN ('ACTIVE','STALE','DELETED')", name='ck_chunk_status'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    memory_id: Mapped[UUID] = mapped_column(ForeignKey('memory.id', ondelete='CASCADE'))
    ordinal: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(CHAR(64))
    status: Mapped[str] = mapped_column(String(16), default='ACTIVE', server_default='ACTIVE')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryEmbedding(Base):
    __tablename__ = 'memory_embedding'
    __table_args__ = (
        CheckConstraint('dimension > 0', name='ck_embedding_dimension'),
        CheckConstraint("status IN ('PENDING','ACTIVE','STALE','DELETED','FAILED')", name='ck_embedding_status'),
        CheckConstraint("status <> 'ACTIVE' OR (embedding IS NOT NULL AND vector_dims(embedding) = dimension AND vector_norm(embedding) > 0)", name='ck_embedding_active'),
        CheckConstraint("jsonb_typeof(metadata) = 'object'", name='ck_embedding_metadata'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    memory_chunk_id: Mapped[UUID] = mapped_column(ForeignKey('memory_chunk.id', ondelete='CASCADE'))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    model_version: Mapped[str] = mapped_column(String(64))
    dimension: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list | None] = mapped_column(Vector())
    status: Mapped[str] = mapped_column(String(16), default='PENDING', server_default='PENDING')
    metadata_redacted: Mapped[dict] = mapped_column('metadata', JSONB, default=dict, server_default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
