"""Token-bucket rate limiter for outbound provider calls.

Each provider gets its own bucket sized to the worst-case allowed cadence.
The bucket is thread-safe so background tasks (auto-scanner, watchlist alert
dispatcher, backup scheduler) can share it with HTTP request threads without
clashing.

This is intentionally minimal: no distributed coordination, no Redis, no
sliding window. Single-process throttling is sufficient for the current
deployment shape and avoids a new infra dependency. Move to a shared store if
the backend ever scales horizontally.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    """Refills tokens at `rate_per_second`, capped at `capacity`.

    `acquire(timeout=None)` blocks until a token is available or the timeout
    elapses. `try_acquire()` is the non-blocking variant.
    """

    rate_per_second: float
    capacity: float
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    _now: Callable[[], float] = field(default=time.monotonic)
    _sleep: Callable[[float], None] = field(default=time.sleep)

    def __post_init__(self) -> None:
        if self.rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        self._tokens = self.capacity
        self._last_refill = self._now()

    def _refill_locked(self) -> None:
        now = self._now()
        elapsed = max(0.0, now - self._last_refill)
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_second)
            self._last_refill = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        with self._lock:
            self._refill_locked()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def acquire(self, tokens: float = 1.0, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else self._now() + timeout
        while True:
            with self._lock:
                self._refill_locked()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                missing = tokens - self._tokens
                wait = missing / self.rate_per_second

            if deadline is not None:
                remaining = deadline - self._now()
                if remaining <= 0:
                    return False
                wait = min(wait, remaining)
            # Sleep is outside the lock so other threads can refill if a token
            # becomes available concurrently.
            self._sleep(max(0.001, wait))


class ProviderRateLimitRegistry:
    """Process-wide registry mapping provider name -> TokenBucket.

    Instantiate one registry per backend process; use `for_provider(name)` to
    fetch or lazily construct a bucket. Defaults are intentionally
    conservative; tune via env if a particular provider key has higher
    headroom.
    """

    DEFAULTS: dict[str, tuple[float, float]] = {
        # provider_name -> (rate_per_second, capacity)
        "alpha_vantage": (1.0 / 12.0, 5),  # free tier: 5 req/min, 25/day
        "fmp": (1.0, 5),  # ~60 req/min, conservative for free plan
        "yfinance": (2.0, 10),  # unofficial; 2/s burst of 10
        "coingecko": (0.5, 10),  # free tier ~30 req/min, conservative
        "fear_greed": (0.05, 1),  # alternative.me, daily-updated, called rarely
        "stocktwits": (1.0, 5),  # public stream API; conservative w/o auth
        "reddit": (0.5, 6),  # public search.json budget is ~60 req/10min
        "twelve_data": (0.13, 5),  # ~8 req/min on the free tier
    }

    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def for_provider(self, name: str) -> TokenBucket:
        with self._lock:
            bucket = self._buckets.get(name)
            if bucket is None:
                rate, capacity = self.DEFAULTS.get(name, (1.0, 5))
                bucket = TokenBucket(rate_per_second=rate, capacity=capacity)
                self._buckets[name] = bucket
                logger.info(
                    "rate_limit_bucket_created provider=%s rate=%.4f capacity=%.1f",
                    name,
                    rate,
                    capacity,
                )
            return bucket


registry = ProviderRateLimitRegistry()


def acquire(provider: str, *, timeout: float = 10.0) -> bool:
    """Convenience wrapper: block up to `timeout` for a token from `provider`.

    Returns True if a token was acquired, False on timeout. Callers should
    treat False as "skip this provider for now"; downstream cache or fallback
    should pick up the slack.
    """
    return registry.for_provider(provider).acquire(timeout=timeout)


def try_acquire(provider: str) -> bool:
    """Non-blocking variant — returns False immediately if no token."""
    return registry.for_provider(provider).try_acquire()
