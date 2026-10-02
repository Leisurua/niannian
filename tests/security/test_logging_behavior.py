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
    def _run_fault_script(self, script: str) -> subprocess.CompletedProcess[str]:
        canaries = (
            "Bearer " + "synthetic" * 4, "sk-" + "S" * 24,
            "SYNTHETIC_AUDIO_PAYLOAD", "synthetic transcript", "1" + "3" * 10,
            "synthetic health", "synthetic memory", "https://example.invalid/?signature=synthetic",
        )
        process = subprocess.run(
            [sys.executable, "-c", f"private = {' | '.join(canaries)!r}\n" + script],
            cwd=Path(__file__).resolve().parents[2] / "backend",
            capture_output=True, text=True, check=False, timeout=10,
        )
        output = process.stdout + process.stderr
        self.assertFalse(any(value in output for value in canaries), "Synthetic sensitive content leaked")
        self.assertNotIn("Traceback", output, "Raw crash diagnostics leaked")
        self.assertNotIn("Logging error", output, "Default logging diagnostics escaped")
        return process

    def _assert_logging_failure(self, output: str, count: int = 1) -> None:
        lines = output.splitlines()
        self.assertEqual(len(lines), count)
        for line in lines:
            self.assertEqual(json.loads(line), {
                "level": "ERROR", "logger": "nianian.runtime",
                "event": "LOGGING_FAILED", "error_code": "LOG_SINK_FAILED",
            })

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


    def test_failed_write_flush_and_formatter_never_use_raw_diagnostics(self) -> None:
        setup = (
            "import logging, threading\n"
            "from app.platform.logging import configure_logging\n"
            "configure_logging()\n"
            "logging.raiseExceptions = True\n"
            "handler = logging.getLogger().handlers[0]\n"
            "def fail():\n"
            "    try: raise ValueError(private)\n"
            "    except ValueError as original: raise RuntimeError(private) from original\n"
        )
        for failure_type in ("RuntimeError", "BaseException"):
            for phase in ("write", "flush", "format"):
                if phase == "format":
                    fault = (
                        "class BrokenFormatter(logging.Formatter):\n"
                        f"    def format(self, record): raise {failure_type}(private)\n"
                        "handler.setFormatter(BrokenFormatter())\n"
                    )
                else:
                    fault = (
                        "class BrokenStream:\n"
                        f"    def write(self, value): {'raise ' + failure_type + '(private)' if phase == 'write' else 'pass'}\n"
                        f"    def flush(self): {'raise ' + failure_type + '(private)' if phase == 'flush' else 'pass'}\n"
                        "handler.stream = BrokenStream()\n"
                    )
                for context, body in (
                    ("normal", "logging.getLogger('nianian.api').error(private, private)\n"),
                    ("process", "fail()\n"),
                    ("thread", "worker = threading.Thread(target=fail, name=private)\nworker.start()\nworker.join()\n"),
                ):
                    with self.subTest(failure_type=failure_type, phase=phase, context=context):
                        process = self._run_fault_script(setup + fault + body)
                        self.assertEqual(process.returncode, 1 if context == "process" else 0)
                        self.assertEqual(process.stdout, "")
                        # A broken flush is also exercised by logging.shutdown.
                        self._assert_logging_failure(process.stderr, 2 if phase == "flush" else 1)

    def test_failed_crash_hook_filter_does_not_trigger_python_fallback(self) -> None:
        setup = (
            "import logging, threading\n"
            "from app.platform.logging import configure_logging\n"
            "configure_logging()\n"
            "class BrokenFilter(logging.Filter):\n"
            "    def filter(self, record): raise BaseException(private)\n"
            "logging.getLogger('nianian.runtime').addFilter(BrokenFilter())\n"
            "def fail(): raise RuntimeError(private)\n"
        )
        for context, body in (
            ("process", "fail()\n"),
            ("thread", "worker = threading.Thread(target=fail)\nworker.start()\nworker.join()\n"),
        ):
            with self.subTest(context=context):
                process = self._run_fault_script(setup + body)
                self.assertEqual(process.returncode, 1 if context == "process" else 0)
                self.assertEqual(process.stdout, "")
                self._assert_logging_failure(process.stderr)

    def test_failed_primary_and_fallback_streams_do_not_escape(self) -> None:
        setup = (
            "import logging, sys, threading\n"
            "from app.platform.logging import configure_logging\n"
            "configure_logging()\n"
            "class BrokenStream:\n"
            "    def write(self, value): raise BaseException(private)\n"
            "    def flush(self): pass\n"
            "logging.getLogger().handlers[0].stream = BrokenStream()\n"
            "sys.stderr = BrokenStream()\n"
            "def fail(): raise RuntimeError(private)\n"
        )
        for context, body in (
            ("normal", "logging.getLogger('nianian.api').error(private)\n"),
            ("process", "fail()\n"),
            ("thread", "worker = threading.Thread(target=fail)\nworker.start()\nworker.join()\n"),
        ):
            with self.subTest(context=context):
                process = self._run_fault_script(setup + body)
                self.assertEqual(process.returncode, 1 if context == "process" else 0)
                self.assertEqual(process.stdout + process.stderr, "")

    def test_failed_sink_does_not_format_hostile_message_or_arguments(self) -> None:
        process = self._run_fault_script(
            "import logging\n"
            "from app.platform.logging import configure_logging\n"
            "configure_logging()\n"
            "class Hostile:\n"
            "    calls = 0\n"
            "    def __str__(self):\n"
            "        Hostile.calls += 1\n"
            "        raise AssertionError(private)\n"
            "    def __repr__(self):\n"
            "        Hostile.calls += 1\n"
            "        raise AssertionError(private)\n"
            "class BrokenStream:\n"
            "    def write(self, value): raise RuntimeError(private)\n"
            "    def flush(self): pass\n"
            "logging.getLogger().handlers[0].stream = BrokenStream()\n"
            "logging.getLogger('nianian.api').error(Hostile(), Hostile())\n"
            "assert Hostile.calls == 0\n"
        )
        self.assertEqual(process.returncode, 0)
        self.assertEqual(process.stdout, "")
        self._assert_logging_failure(process.stderr)


if __name__ == "__main__":
    unittest.main()
