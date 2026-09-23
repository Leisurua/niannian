import json
import logging

from fastapi.testclient import TestClient

from app.main import app
from app.platform.logging import StructuredFormatter, configure_logging, log_event


def _format(message: str, *, args: tuple[object, ...] = (), structured: bool = True, **extra: object) -> dict[str, object]:
    record = logging.LogRecord("nianian.test", logging.ERROR, __file__, 1, message, args, None)
    record._structured_event = structured
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(StructuredFormatter().format(record))


def test_allowlisted_fields_and_unknown_content_are_not_logged() -> None:
    canary = "private" + "content"
    payload = _format(
        "SAFE_EVENT",
        request_id="req-test",
        correlation_id="corr-test",
        provider="mock",
        latency_ms=12,
        result="FAILED",
        error_code="PROVIDER_TIMEOUT",
        transcript=canary,
        token=canary,
    )
    assert payload["event"] == "SAFE_EVENT"
    assert payload["request_id"] == "req-test"
    assert payload["correlation_id"] == "corr-test"
    assert payload["error_code"] == "PROVIDER_TIMEOUT"
    assert payload["latency_ms"] == 12
    assert canary not in json.dumps(payload)
    assert "transcript" not in payload
    assert "token" not in payload


def test_unstructured_message_exception_and_phone_like_metadata_are_suppressed() -> None:
    private = "private" + "content"
    phone_like = "1" + "3" * 10
    payload = _format(
        f"user message {private}",
        request_id=phone_like,
        user_id=private + " space",
    )
    assert payload["event"] == "UNSTRUCTURED_LOG"
    assert phone_like not in json.dumps(payload)
    assert private not in json.dumps(payload)

    interpolated = _format("error %s", args=(private,))
    assert interpolated["event"] == "UNSTRUCTURED_LOG"
    assert private not in json.dumps(interpolated)

    unstructured = _format("SECRET_WORD", structured=False)
    assert unstructured["event"] == "UNSTRUCTURED_LOG"


def test_server_access_log_uses_safe_formatter() -> None:
    configure_logging()
    server_logger = logging.getLogger("uvicorn.access")
    assert server_logger.propagate
    assert not server_logger.handlers
    private_query = "signed" + "secret"
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        "GET /download?signature=%s", (private_query,), None,
    )
    assert private_query not in StructuredFormatter().format(record)


def test_request_context_correlates_event_and_resets_between_requests() -> None:
    seen: list[dict[str, object]] = []
    logger = logging.getLogger("nianian.test.capture")

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(json.loads(StructuredFormatter().format(record)))

    capture = Capture()
    logger.addHandler(capture)
    try:
        @app.get("/test-log-context")
        async def test_log_context() -> dict[str, bool]:
            log_event(logger, logging.INFO, "REQUEST_OBSERVED", error_code="NONE")
            return {"ok": True}

        with TestClient(app) as client:
            response = client.get("/test-log-context", headers={"X-Request-ID": "req-123"})
            second = client.get("/test-log-context", headers={"X-Request-ID": "req-456"})
        assert response.status_code == 200
        assert second.status_code == 200
        assert [item["request_id"] for item in seen[-2:]] == ["req-123", "req-456"]
        assert [item["correlation_id"] for item in seen[-2:]] == ["req-123", "req-456"]
    finally:
        logger.removeHandler(capture)
        app.router.routes.pop()
