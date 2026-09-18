"""Rate limiters: token buckets for outbound provider calls, a sliding
window for inbound requests.

Each provider gets its own bucket sized to the worst-case allowed cadence.
The bucket is thread-safe so background tasks (auto-scanner, watchlist alert
dispatcher, backup scheduler) can share it with HTTP request threads without
clashing. `SlidingWindowLimit` counts hits per key (client, account, user)
over a fixed window; the login and password-reset routes raise 429 on it,
the backtest registry turns an enqueue away on it.

This is intentionally minimal: no distributed coordination, no Redis.
Single-process throttling is sufficient for the current
deployment shape and avoids a new infra dependency. Move to a shared store if
the backend ever scales horizontally.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
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


class SlidingWindowLimit:
    """At most `limit` hits per `key` in any `window_seconds`.

    `try_acquire(key)` records a hit and answers True, or answers False
    without recording when the key is at its limit — a refused attempt does
    not extend the window. Process-local like the buckets above; the same
    lid applies (a second backend process needs a shared store).
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._now = now
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    #: Every this many calls, keys whose hits all expired are dropped. Keys
    #: are caller-chosen (a login limit is keyed on the typed e-mail), so
    #: without a sweep the map grows by one deque per string ever tried.
    SWEEP_EVERY = 1024

    def try_acquire(self, key: str) -> bool:
        with self._lock:
            now = self._now()
            self._calls += 1
            if self._calls % self.SWEEP_EVERY == 0:
                self._sweep_locked(now)
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window_seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def _sweep_locked(self, now: float) -> None:
        cutoff = now - self.window_seconds
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


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
        "rss": (1.0, 10),  # public RSS feeds — generous, but cached 5 min
        "fred": (1.5, 10),  # free tier ~120 req/min; very generous for our use
        "fx": (1.0, 5),  # frankfurter.app — no documented limit; refreshes daily
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
