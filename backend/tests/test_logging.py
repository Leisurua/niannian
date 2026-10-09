import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app, handle_unexpected_error
from app.platform.logging import StructuredFormatter, configure_logging, log_event
from app.platform.request_id import RequestIdMiddleware


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
        user_id="user-1",
        family_id="family-1",
        conversation_id="conversation-1",
        event_id="event-1",
        device_id="device-1",
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
    assert payload["user_id"] == "user-1"
    assert payload["family_id"] == "family-1"
    assert payload["conversation_id"] == "conversation-1"
    assert payload["event_id"] == "event-1"
    assert payload["device_id"] == "device-1"
    assert payload["provider"] == "mock"
    assert payload["result"] == "FAILED"
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


def test_logger_name_and_credential_shaped_metadata_are_suppressed() -> None:
    private = "private" + "content"
    credential = "sk-" + "A" * 24
    record = logging.LogRecord(private, logging.ERROR, __file__, 1, "SAFE_EVENT", (), None)
    record._structured_event = True
    record.user_id = credential
    record.error_code = credential
    payload = json.loads(StructuredFormatter().format(record))
    assert payload["logger"] == "external"
    assert payload["event"] == "SAFE_EVENT"
    assert "user_id" not in payload
    assert "error_code" not in payload
    assert private not in json.dumps(payload)
    assert credential not in json.dumps(payload)


def test_unexpected_error_keeps_request_correlation_without_exception_content() -> None:
    seen: list[dict[str, object]] = []
    private = "synthetic" + " transcript"
    isolated_app = FastAPI()
    isolated_app.add_middleware(RequestIdMiddleware)
    isolated_app.add_exception_handler(Exception, handle_unexpected_error)

    @isolated_app.get("/fail")
    async def fail() -> None:
        raise RuntimeError(private)

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(json.loads(StructuredFormatter().format(record)))

    logger = logging.getLogger("nianian.api")
    capture = Capture()
    logger.addHandler(capture)
    try:
        with TestClient(isolated_app, raise_server_exceptions=False) as client:
            response = client.get("/fail", headers={"X-Request-ID": "req-error-1"})
            second = client.get("/fail", headers={"X-Request-ID": "req-error-2"})
        assert response.status_code == second.status_code == 500
        assert response.json()["request_id"] == "req-error-1"
        assert second.json()["request_id"] == "req-error-2"
        assert [item["request_id"] for item in seen] == ["req-error-1", "req-error-2"]
        assert [item["correlation_id"] for item in seen] == ["req-error-1", "req-error-2"]
        assert all(item["error_code"] == "INTERNAL_ERROR" for item in seen)
        assert private not in json.dumps(seen) + response.text + second.text
    finally:
        logger.removeHandler(capture)


def test_credential_shaped_event_is_suppressed() -> None:
    credential = "AKIA" + "A" * 16
    payload = _format(credential)
    assert payload["event"] == "UNSTRUCTURED_LOG"
    assert credential not in json.dumps(payload)
