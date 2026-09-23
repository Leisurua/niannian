"""Allowlisted, content-free application logs.

Message and exception text are never serialized. Callers use stable event names
and metadata fields; unstructured third-party records lose their payload too.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any


request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
correlation_id_context: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_SYMBOL = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_EVENT = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PHONE_LIKE = re.compile(r"\d{10,}")
_ID_FIELDS = frozenset(
    {"request_id", "correlation_id", "user_id", "family_id", "conversation_id", "event_id", "device_id"}
)
_SYMBOL_FIELDS = frozenset({"provider", "result", "error_code"})
_SAFE_FIELDS = _ID_FIELDS | _SYMBOL_FIELDS | {"latency_ms"}


def _safe_field(name: str, value: Any) -> str | int | None:
    if name == "latency_ms":
        return value if type(value) is int and 0 <= value <= 86_400_000 else None
    if not isinstance(value, str):
        return None
    pattern = _IDENTIFIER if name in _ID_FIELDS else _SYMBOL
    if pattern.fullmatch(value) and not _PHONE_LIKE.search(value):
        return value
    return None


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = record.msg if getattr(record, "_structured_event", False) and isinstance(record.msg, str) and not record.args else "UNSTRUCTURED_LOG"
        if not _EVENT.fullmatch(event) or _PHONE_LIKE.search(event):
            event = "UNSTRUCTURED_LOG"
        payload: dict[str, str | int] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": event,
        }
        for name in _SAFE_FIELDS:
            value = getattr(record, name, None)
            if value is None and name == "request_id":
                value = request_id_context.get()
            if value is None and name == "correlation_id":
                value = correlation_id_context.get()
            safe = _safe_field(name, value)
            if safe is not None:
                payload[name] = safe
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit a stable event with approved metadata. Never pass content or exceptions."""
    metadata = {name: value for name, value in fields.items() if name in _SAFE_FIELDS}
    logger.log(level, event, extra={**metadata, "_structured_event": True})


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Uvicorn configures its own access/error handlers. Route them through the
    # same formatter so paths, query strings and exception text are discarded.
    for name in ("uvicorn.access", "uvicorn.error", "uvicorn.asgi"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True
