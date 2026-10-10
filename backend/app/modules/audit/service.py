import hashlib
import json
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7


async def record(db: AsyncSession, actor: UUID | None, action: str, target_type: str,
                 target_id: UUID | None = None, family_id: UUID | None = None,
                 request_id: str | None = None, result: str = "SUCCEEDED", metadata: dict | None = None) -> AuditLog:
    row = AuditLog(id=uuid7(), actor_user_id=actor, family_id=family_id, action=action,
                   target_type=target_type, target_id=target_id, request_id=request_id,
                   result=result, metadata_redacted=metadata or {})
    db.add(row)
    await db.flush()
    return row


async def event_target(db: AsyncSession, actor: UUID, action: str, key: str, value: str) -> UUID | None:
    return await db.scalar(select(AuditLog.target_id).where(AuditLog.actor_user_id == actor,
                           AuditLog.action == action, AuditLog.metadata_redacted[key].astext == value)
                           .order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(1))


class Idempotency:
    def __init__(self, key: str, operation: str, payload: dict):
        if not 1 <= len(key) <= 128 or not key.isascii() or any(ord(c) < 32 or ord(c) > 126 for c in key):
            raise AppError("VALIDATION_ERROR", "请提供有效的幂等请求标识。", 422)
        self.key_hash = hashlib.sha256((operation + "\0" + key).encode()).hexdigest()
        self.body_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

    async def previous(self, db: AsyncSession, actor: UUID, seconds: int) -> UUID | None:
        row = await db.scalar(select(AuditLog).where(
            AuditLog.actor_user_id == actor,
            AuditLog.metadata_redacted["idempotency_key_hash"].astext == self.key_hash,
            AuditLog.created_at >= utcnow() - timedelta(seconds=seconds),
        ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(1))
        if row:
            if row.metadata_redacted.get("request_hash") != self.body_hash:
                raise AppError("IDEMPOTENCY_KEY_REUSED", "同一请求标识不能用于不同内容。", 409)
            return row.target_id
        return None

    @property
    def metadata(self) -> dict:
        return {"idempotency_key_hash": self.key_hash, "request_hash": self.body_hash}
