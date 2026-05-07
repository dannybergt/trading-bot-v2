"""Tests for the token-bucket rate limiter.

The bucket is given controllable `now` and `sleep` callables so the tests can
drive virtual time deterministically rather than calling `time.sleep`.
"""

import unittest
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent  # in-container layout
sys.path.insert(0, str(BACKEND_ROOT))

from app.rate_limit import TokenBucket, ProviderRateLimitRegistry  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, delta: float) -> None:
        self.t += delta


class TokenBucketTests(unittest.TestCase):
    def test_capacity_is_initial_balance(self):
        clock = FakeClock()
        bucket = TokenBucket(rate_per_second=1.0, capacity=3.0, _now=clock.now, _sleep=clock.sleep)
        self.assertTrue(bucket.try_acquire())
        self.assertTrue(bucket.try_acquire())
        self.assertTrue(bucket.try_acquire())
        self.assertFalse(bucket.try_acquire())

    def test_refill_after_elapsed_time(self):
        clock = FakeClock()
        bucket = TokenBucket(rate_per_second=2.0, capacity=2.0, _now=clock.now, _sleep=clock.sleep)
        self.assertTrue(bucket.try_acquire())
        self.assertTrue(bucket.try_acquire())
        self.assertFalse(bucket.try_acquire())
        clock.t += 0.5  # 0.5 s -> 1 token at 2/s
        self.assertTrue(bucket.try_acquire())
        self.assertFalse(bucket.try_acquire())

    def test_acquire_waits_until_token_available(self):
        clock = FakeClock()
        bucket = TokenBucket(rate_per_second=1.0, capacity=1.0, _now=clock.now, _sleep=clock.sleep)
        self.assertTrue(bucket.try_acquire())
        # Next acquire should sleep ~1 s (controlled clock advances).
        ok = bucket.acquire(timeout=2.0)
        self.assertTrue(ok)
        self.assertGreaterEqual(clock.t, 1.0)

    def test_acquire_returns_false_on_timeout(self):
        clock = FakeClock()
        bucket = TokenBucket(rate_per_second=0.5, capacity=1.0, _now=clock.now, _sleep=clock.sleep)
        bucket.try_acquire()
        ok = bucket.acquire(timeout=0.1)
        self.assertFalse(ok)

    def test_capacity_caps_refill(self):
        clock = FakeClock()
        bucket = TokenBucket(rate_per_second=1.0, capacity=2.0, _now=clock.now, _sleep=clock.sleep)
        clock.t += 100.0  # would refill 100 tokens absent the cap
        # Capacity is 2; should not exceed it.
        self.assertTrue(bucket.try_acquire())
        self.assertTrue(bucket.try_acquire())
        self.assertFalse(bucket.try_acquire())


class ProviderRegistryTests(unittest.TestCase):
    def test_for_provider_returns_same_instance(self):
        registry = ProviderRateLimitRegistry()
        a = registry.for_provider("alpha_vantage")
        b = registry.for_provider("alpha_vantage")
        self.assertIs(a, b)

    def test_unknown_provider_uses_default_capacity(self):
        registry = ProviderRateLimitRegistry()
        bucket = registry.for_provider("custom_provider")
        # Defaults to (1.0, 5)
        self.assertEqual(5.0, bucket.capacity)
        self.assertEqual(1.0, bucket.rate_per_second)


if __name__ == "__main__":
    unittest.main()
