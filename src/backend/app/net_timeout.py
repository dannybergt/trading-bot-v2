"""Wall-clock bound for best-effort external provider calls.

yfinance and similar clients can hang under upstream throttling (429 plus
retry/crumb-fetch backoff) even when a per-request ``timeout=`` is set, because
not every internal HTTP round-trip respects it. ``option_chain``/``options``
take no timeout argument at all. This wraps the whole call in a daemon thread
with a hard wall-clock deadline, so a slow provider degrades to a fast fallback
value instead of hanging the request path (which otherwise blows the caller's
60s read-timeout — see the api-regression on a throttled host).

A timed-out call keeps running in its daemon thread until it finishes on its
own; the caller has already moved on with ``default``. Per-call threads (rather
than a shared pool) mean a hung provider can never starve later calls of
workers. Upstream rate limiting keeps the number of live threads small.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default deadline for a single provider network call. Healthy providers answer
# in well under a second; this only trips on genuinely slow/hung responses.
DEFAULT_TIMEOUT_SECONDS = 8.0


def call_with_timeout(
    fn: Callable[[], T],
    *,
    default: T,
    label: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> T:
    """Run ``fn`` with a hard wall-clock deadline.

    Returns ``fn()`` if it finishes within ``timeout`` seconds, otherwise
    ``default`` (also on any exception raised by ``fn``). Never raises.
    """
    result: dict[str, T] = {"value": default}

    def _run() -> None:
        try:
            result["value"] = fn()
        except Exception:
            logger.exception("provider_call_failed label=%s", label)

    thread = threading.Thread(target=_run, daemon=True, name=f"provider-{label}")
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        logger.warning("provider_call_timeout label=%s timeout=%.1fs", label, timeout)
        return default
    return result["value"]
