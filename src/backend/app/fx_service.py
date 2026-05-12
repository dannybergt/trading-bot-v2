"""Foreign-exchange rate adapter.

Uses the free, no-auth `frankfurter.app` service which serves the European
Central Bank reference rates (daily). One module-level cache per base
currency, 60-minute TTL — the rates only refresh once a day upstream so
re-pulling more often is wasted budget.

Defensive failure model: every request that raises or returns a payload
without a `rates` dict ends in `None`. Callers must therefore tolerate a
missing rates table and degrade to "no conversion" (treat the source
currency as the display currency).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

from app.rate_limit import acquire as acquire_rate_limit

logger = logging.getLogger(__name__)

FRANKFURTER_BASE_URL = "https://api.frankfurter.app"
DEFAULT_TIMEOUT_SECONDS = 8.0
CACHE_TTL_SECONDS = 60 * 60  # 60 minutes
DEFAULT_BASE = "USD"
# Common currencies we surface as toggle options. The provider supports
# the full ECB reference list; we keep this small to bound the UI.
SUPPORTED_CURRENCIES: tuple[str, ...] = (
    "USD",
    "EUR",
    "GBP",
    "CHF",
    "JPY",
    "CAD",
    "AUD",
    "CNY",
)


class FxService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key: base symbol; value: (timestamp_seconds, payload_dict)
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def supported_currencies(self) -> tuple[str, ...]:
        return SUPPORTED_CURRENCIES

    def get_rates(self, base: str = DEFAULT_BASE) -> dict[str, Any] | None:
        """Return `{base, date, rates: {SYMBOL: float, ...}}` or None.

        Identity entry (`rates[base] = 1.0`) is added so callers can treat
        the response uniformly without a special case for the base.
        """
        base = (base or DEFAULT_BASE).upper().strip()
        if base not in SUPPORTED_CURRENCIES:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(base)
            if entry and now - entry[0] < CACHE_TTL_SECONDS:
                return entry[1]
        if not acquire_rate_limit("fx", timeout=4.0):
            logger.warning("fx_rate_limit_skip base=%s", base)
            return None
        params = {
            "from": base,
            "to": ",".join(c for c in SUPPORTED_CURRENCIES if c != base),
        }
        url = f"{FRANKFURTER_BASE_URL}/latest"
        try:
            response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            logger.exception("fx_request_failed base=%s", base)
            return None
        except ValueError:
            logger.exception("fx_invalid_json base=%s", base)
            return None
        rates = payload.get("rates") if isinstance(payload, dict) else None
        if not isinstance(rates, dict):
            return None
        # Coerce + sanitize
        clean_rates: dict[str, float] = {base: 1.0}
        for symbol, value in rates.items():
            try:
                clean_rates[symbol.upper()] = float(value)
            except (TypeError, ValueError):
                continue
        result = {
            "base": base,
            "date": payload.get("date"),
            "rates": clean_rates,
            "supported": list(SUPPORTED_CURRENCIES),
        }
        with self._lock:
            self._cache[base] = (now, result)
        return result

    def reset_caches_for_tests(self) -> None:
        with self._lock:
            self._cache.clear()


_service: FxService | None = None


def get_fx_service() -> FxService:
    global _service
    if _service is None:
        _service = FxService()
    return _service
