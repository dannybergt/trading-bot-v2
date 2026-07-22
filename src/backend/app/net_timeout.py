"""Wall-clock bound + circuit breaker for best-effort external provider calls.

yfinance and similar clients can hang under upstream throttling (429 plus
retry/crumb-fetch backoff) even when a per-request ``timeout=`` is set, because
not every internal HTTP round-trip respects it. ``option_chain``/``options``
take no timeout argument at all.

Two layers of protection:

1. **Wall-clock timeout** — each call runs in a daemon thread with a hard
   deadline, so a single slow call degrades to a fast fallback value instead of
   hanging the request path.
2. **Per-provider circuit breaker** — a request-heavy endpoint (e.g.
   ``/api/research``) makes several provider calls in series; if each one waits
   out its full timeout under sustained throttling the sum still blows the
   caller's 60s read-timeout. After ``_FAIL_THRESHOLD`` consecutive timeouts for
   a provider the circuit opens for ``_COOLDOWN_SECONDS`` and further calls to
   that provider return their fallback immediately, so the endpoint stays
   responsive. A single success closes it again.

A timed-out call keeps running in its daemon thread until it finishes on its
own; the caller has already moved on with ``default``. Per-call threads (rather
than a shared pool) mean a hung provider can never starve later calls of
workers.
"""
from __future__ import annotations

import logging
import threading
from time import monotonic
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default deadline for a single provider network call. Healthy providers answer
# in well under a second; this only trips on genuinely slow/hung responses.
DEFAULT_TIMEOUT_SECONDS = 8.0

# Circuit breaker: after this many consecutive timeouts for a provider, skip
# further calls to it for the cooldown window.
_FAIL_THRESHOLD = 2
_COOLDOWN_SECONDS = 20.0

_breaker_lock = threading.Lock()
_breaker: dict[str, dict] = {}  # provider -> {"failures": int, "open_until": float}


def _circuit_open(provider: str | None) -> bool:
    if not provider:
        return False
    with _breaker_lock:
        state = _breaker.get(provider)
        return bool(state and state["open_until"] > monotonic())


def _record(provider: str | None, *, timed_out: bool) -> None:
    if not provider:
        return
    with _breaker_lock:
        state = _breaker.setdefault(provider, {"failures": 0, "open_until": 0.0})
        if timed_out:
            state["failures"] += 1
            if state["failures"] >= _FAIL_THRESHOLD:
                state["open_until"] = monotonic() + _COOLDOWN_SECONDS
                logger.warning(
                    "provider_circuit_opened provider=%s cooldown=%.0fs",
                    provider,
                    _COOLDOWN_SECONDS,
                )
        else:
            # A success (or a fast, non-hanging failure) closes the circuit.
            state["failures"] = 0
            state["open_until"] = 0.0


def reset_circuit(provider: str | None = None) -> None:
    """Clear breaker state (for tests, or a manual provider re-enable)."""
    with _breaker_lock:
        if provider is None:
            _breaker.clear()
        else:
            _breaker.pop(provider, None)


def call_with_timeout(
    fn: Callable[[], T],
    *,
    default: T,
    label: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    provider: str | None = None,
) -> T:
    """Run ``fn`` with a hard wall-clock deadline and per-provider breaker.

    Returns ``fn()`` if it finishes within ``timeout`` seconds, otherwise
    ``default`` (also on any exception raised by ``fn``, or immediately if the
    provider's circuit is open). Never raises.
    """
    if _circuit_open(provider):
        logger.info("provider_circuit_open provider=%s label=%s skip", provider, label)
        return default

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
        _record(provider, timed_out=True)
        logger.warning("provider_call_timeout label=%s timeout=%.1fs", label, timeout)
        return default
    _record(provider, timed_out=False)
    return result["value"]
