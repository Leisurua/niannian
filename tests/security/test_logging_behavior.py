"""PRIV-002 formatter checks without requiring the API test dependencies."""

import io
import json
import logging
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.platform.logging import StructuredFormatter, log_event  # noqa: E402


class LoggingBehaviorTest(unittest.TestCase):
    def test_structured_event_drops_unapproved_fields(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        logger = logging.getLogger("nianian.privacy-test")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            private_content = "private" + "content"
            log_event(
                logger, logging.INFO, "REQUEST_FAILED",
                request_id="req-safe", correlation_id="corr-safe", error_code="TIMEOUT",
                transcript=private_content, token=private_content,
            )
        finally:
            logger.removeHandler(handler)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["request_id"], "req-safe")
        self.assertEqual(payload["correlation_id"], "corr-safe")
        self.assertEqual(payload["error_code"], "TIMEOUT")
        self.assertNotIn(private_content, stream.getvalue())
        self.assertNotIn("transcript", payload)

    def test_unstructured_exception_and_phone_like_id_are_suppressed(self) -> None:
        content = "private" + "content"
        record = logging.LogRecord("nianian.test", logging.ERROR, __file__, 1, content, (), None)
        record.exc_info = (ValueError, ValueError(content), None)
        record.request_id = "1" + "3" * 10
        payload = json.loads(StructuredFormatter().format(record))
        self.assertEqual(payload["event"], "UNSTRUCTURED_LOG")
        self.assertNotIn(content, json.dumps(payload))
        self.assertNotIn("request_id", payload)


if __name__ == "__main__":
    unittest.main()
