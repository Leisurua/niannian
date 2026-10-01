import secrets
import time
from datetime import datetime, timezone
from uuid import UUID


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid7() -> UUID:
    return UUID(int=(time.time_ns() // 1_000_000 << 80) | (7 << 76) |
                (secrets.randbits(12) << 64) | (2 << 62) | secrets.randbits(62))
