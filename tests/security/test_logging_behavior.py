"""PRIV-002 formatter checks without requiring the API test dependencies."""

import io
import json
import logging
import subprocess
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

    def test_uncaught_process_crash_emits_redacted_event(self) -> None:
        private = "private" + "content"
        code = (
            "from app.platform.logging import configure_logging\n"
            "configure_logging()\n"
            f"raise RuntimeError({private!r})\n"
        )
        process = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[2] / "backend",
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertNotIn(private, process.stdout + process.stderr)
        payload = json.loads(process.stdout.strip())
        self.assertEqual(payload["event"], "UNHANDLED_PROCESS_ERROR")
        self.assertEqual(payload["error_code"], "UNHANDLED_EXCEPTION")
        self.assertEqual(process.stderr, "")


    def test_uncaught_thread_crash_emits_redacted_event(self) -> None:
        private = "private" + "content"
        code = (
            "import threading\n"
            "from app.platform.logging import configure_logging\n"
            "configure_logging()\n"
            f"def fail(): raise RuntimeError({private!r})\n"
            "thread = threading.Thread(target=fail)\n"
            "thread.start()\n"
            "thread.join()\n"
        )
        process = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[2] / "backend",
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 0)
        self.assertNotIn(private, process.stdout + process.stderr)
        payload = json.loads(process.stdout.strip())
        self.assertEqual(payload["event"], "UNHANDLED_PROCESS_ERROR")
        self.assertEqual(process.stderr, "")


if __name__ == "__main__":
    unittest.main()
