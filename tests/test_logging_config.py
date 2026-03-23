import json
import logging
import unittest

from app.logging_config import (
    JsonLogFormatter,
    RequestContextFilter,
    fingerprint_value,
    reset_request_log_context,
    set_request_log_context,
)


class LoggingConfigTests(unittest.TestCase):
    def test_json_formatter_includes_request_context_and_extra_fields(self):
        formatter = JsonLogFormatter()
        filter_ = RequestContextFilter()
        logger = logging.getLogger("tests.logging")

        token = set_request_log_context(
            request_id="req-123",
            method="GET",
            path="/api/health",
            client_ip="127.0.0.1",
        )
        try:
            record = logger.makeRecord(
                "tests.logging",
                logging.INFO,
                __file__,
                10,
                "request_completed",
                (),
                None,
                extra={"status_code": 200, "duration_ms": 12.5},
            )
            filter_.filter(record)
            payload = json.loads(formatter.format(record))
        finally:
            reset_request_log_context(token)

        self.assertEqual(payload["message"], "request_completed")
        self.assertEqual(payload["request_id"], "req-123")
        self.assertEqual(payload["method"], "GET")
        self.assertEqual(payload["path"], "/api/health")
        self.assertEqual(payload["client_ip"], "127.0.0.1")
        self.assertEqual(payload["status_code"], 200)
        self.assertEqual(payload["duration_ms"], 12.5)

    def test_fingerprint_value_is_stable_and_redacted(self):
        fingerprint_a = fingerprint_value(" User@example.com ")
        fingerprint_b = fingerprint_value("user@example.com")

        self.assertEqual(fingerprint_a, fingerprint_b)
        self.assertTrue(fingerprint_a.startswith("sha256:"))
        self.assertNotIn("user@example.com", fingerprint_a)


if __name__ == "__main__":
    unittest.main()
