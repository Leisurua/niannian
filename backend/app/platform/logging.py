"""Allowlisted, content-free application logs.

Message and exception text are never serialized. Callers use stable event names
and metadata fields; unstructured third-party records lose their payload too.
"""

import json
import logging
import re
import sys
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any


request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
correlation_id_context: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_SYMBOL = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_EVENT = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PHONE_LIKE = re.compile(r"\d{10,}")
_SECRET_LIKE = re.compile(
    r"(?:sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|"
    r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})"
)
_LOGGER_NAMES = frozenset({
    "nianian.api", "nianian.worker", "nianian.runtime",
    "uvicorn", "uvicorn.access", "uvicorn.error", "uvicorn.asgi",
})
_LEVEL_NAMES = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_ID_FIELDS = frozenset(
    {"request_id", "correlation_id", "user_id", "family_id", "conversation_id", "event_id", "device_id"}
)
_SYMBOL_FIELDS = frozenset({"provider", "result", "error_code"})
_SAFE_FIELDS = _ID_FIELDS | _SYMBOL_FIELDS | {"latency_ms"}


def is_safe_identifier(value: str) -> bool:
    return bool(
        _IDENTIFIER.fullmatch(value)
        and not _PHONE_LIKE.search(value)
        and not _SECRET_LIKE.search(value)
    )


def _safe_field(name: str, value: Any) -> str | int | None:
    if name == "latency_ms":
        return value if type(value) is int and 0 <= value <= 86_400_000 else None
    if not isinstance(value, str):
        return None
    if name in _ID_FIELDS:
        return value if is_safe_identifier(value) else None
    if _SYMBOL.fullmatch(value) and not _PHONE_LIKE.search(value) and not _SECRET_LIKE.search(value):
        return value
    return None


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = (
            record.msg
            if getattr(record, "_structured_event", False)
            and isinstance(record.msg, str)
            and not record.args
            else "UNSTRUCTURED_LOG"
        )
        if not _EVENT.fullmatch(event) or _PHONE_LIKE.search(event) or _SECRET_LIKE.search(event):
            event = "UNSTRUCTURED_LOG"
        payload: dict[str, str | int] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname if record.levelname in _LEVEL_NAMES else "ERROR",
            "logger": record.name if record.name in _LOGGER_NAMES else "external",
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


def _report_logging_failure() -> None:
    """Best-effort fixed diagnostic; never format a record or sink exception."""
    try:
        sys.stderr.write(
            '{"level":"ERROR","logger":"nianian.runtime",'
            '"event":"LOGGING_FAILED","error_code":"LOG_SINK_FAILED"}\n'
        )
    except BaseException:
        # A failed fallback must not reach Python's exception-hook diagnostics,
        # which would print the original sensitive exception as well.
        pass


class RedactedStreamHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except BaseException:
            # StreamHandler only catches Exception. A sink may also raise a
            # BaseException; neither kind may escape into crash diagnostics.
            self.handleError(record)

    def flush(self) -> None:
        try:
            super().flush()
        except BaseException:
            # logging.shutdown() flushes handlers outside emit/excepthook.
            # Its atexit failure would otherwise expose the sink exception.
            _report_logging_failure()

    def handleError(self, record: logging.LogRecord) -> None:
        # The standard handler prints raw message/args and the sink traceback.
        # Do not inspect record or call the parent error handler here.
        _report_logging_failure()


def _redacted_excepthook(_exc_type: type[BaseException], _exc_value: BaseException, _traceback: Any) -> None:
    try:
        log_event(
            logging.getLogger("nianian.runtime"),
            logging.CRITICAL,
            "UNHANDLED_PROCESS_ERROR",
            error_code="UNHANDLED_EXCEPTION",
        )
    except BaseException:
        # Filters or other configured handlers can fail before our sink runs.
        # Never let a failed hook cause Python to print the original exception.
        _report_logging_failure()


def _redacted_thread_excepthook(args: threading.ExceptHookArgs) -> None:
    _redacted_excepthook(args.exc_type, args.exc_value, args.exc_traceback)


def configure_logging(level: str = "INFO") -> None:
    handler = RedactedStreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    sys.excepthook = _redacted_excepthook
    threading.excepthook = _redacted_thread_excepthook
    # Uvicorn configures its own access/error handlers. Route them through the
    # same formatter so paths, query strings and exception text are discarded.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "uvicorn.asgi"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True
