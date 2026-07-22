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

from app import net_timeout  # noqa: E402
from app.net_timeout import call_with_timeout, reset_circuit  # noqa: E402


class NetTimeoutTests(unittest.TestCase):
    def setUp(self):
        reset_circuit()

    def tearDown(self):
        reset_circuit()

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

    def test_circuit_opens_after_repeated_timeouts_and_skips_fast(self):
        calls = {"n": 0}

        def slow():
            calls["n"] += 1
            time.sleep(2.0)
            return "late"

        # _FAIL_THRESHOLD consecutive timeouts open the circuit for the provider.
        for _ in range(net_timeout._FAIL_THRESHOLD):
            self.assertEqual(
                call_with_timeout(slow, default="x", label="p", timeout=0.2, provider="yf"),
                "x",
            )
        ran_before = calls["n"]

        # Next call must skip immediately without invoking `slow` again.
        started = time.monotonic()
        result = call_with_timeout(slow, default="x", label="p", timeout=5.0, provider="yf")
        elapsed = time.monotonic() - started
        self.assertEqual(result, "x")
        self.assertLess(elapsed, 0.5)          # returned without waiting
        self.assertEqual(calls["n"], ran_before)  # `slow` was not called again

    def test_success_keeps_circuit_closed(self):
        # A fast success must not open the circuit.
        for _ in range(net_timeout._FAIL_THRESHOLD + 1):
            self.assertEqual(
                call_with_timeout(lambda: 7, default=0, label="ok", provider="yf"), 7
            )


if __name__ == "__main__":
    unittest.main()
