"""Wall-clock provider-timeout helper tests.

Verifies that a slow or failing best-effort provider call degrades to the
fallback value instead of hanging the caller (the api-regression failure mode
under Yahoo throttling).
"""
import sys
import time
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.net_timeout import call_with_timeout  # noqa: E402


class NetTimeoutTests(unittest.TestCase):
    def test_returns_value_when_fast(self):
        self.assertEqual(call_with_timeout(lambda: 42, default=0, label="fast"), 42)

    def test_returns_default_on_timeout(self):
        def slow():
            time.sleep(2.0)
            return "late"

        started = time.monotonic()
        result = call_with_timeout(slow, default="fallback", label="slow", timeout=0.2)
        elapsed = time.monotonic() - started
        self.assertEqual(result, "fallback")
        self.assertLess(elapsed, 1.0)  # returned promptly, did not wait for `slow`

    def test_returns_default_on_exception(self):
        def boom():
            raise RuntimeError("provider blew up")

        self.assertIsNone(call_with_timeout(boom, default=None, label="boom"))


if __name__ == "__main__":
    unittest.main()
