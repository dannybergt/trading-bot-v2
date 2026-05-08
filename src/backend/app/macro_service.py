"""Macro context for the recommendation layer.

Pulls VIX (equity-market fear gauge), 10-year Treasury yield (^TNX, decimal
percent), and the U.S. Dollar Index (DX-Y.NYB) via yfinance. These three
together give every per-symbol recommendation a "weather report" that the
explainer and Net-Yield-Gate can lean on later.

Cached at module level for `MACRO_CACHE_TTL_SECONDS` so repeated requests
across scanner/alerts/analysis paths don't burn the yfinance budget.
"""
from __future__ import annotations

import logging
from copy import deepcopy
from time import monotonic
from typing import Any

import yfinance as yf

from app.rate_limit import acquire as acquire_rate_limit

logger = logging.getLogger(__name__)

MACRO_CACHE_TTL_SECONDS = 5 * 60

MACRO_INSTRUMENTS: dict[str, dict[str, str]] = {
    "vix": {"symbol": "^VIX", "label": "VIX (S&P 500 implied volatility)"},
    "yield10y": {"symbol": "^TNX", "label": "U.S. 10Y Treasury yield"},
    "dxy": {"symbol": "DX-Y.NYB", "label": "U.S. Dollar Index (DXY)"},
}


class MacroService:
    """Lightweight cached fetcher for macro context.

    Returns a mapping with `value` (last close), `changePct` (1-day delta),
    `asOf` (last available bar date as ISO string) and `label` for each
    instrument. Best-effort: instruments that fail to fetch surface as
    `None` values rather than failing the whole payload.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {"expires_at": 0.0, "value": None}

    def get_context(self, *, force_refresh: bool = False) -> dict[str, Any]:
        if not force_refresh and self._cache["value"] is not None and self._cache["expires_at"] > monotonic():
            return deepcopy(self._cache["value"])

        snapshot: dict[str, Any] = {}
        for key, spec in MACRO_INSTRUMENTS.items():
            snapshot[key] = self._fetch_instrument(spec["symbol"], spec["label"])

        self._cache = {
            "expires_at": monotonic() + MACRO_CACHE_TTL_SECONDS,
            "value": snapshot,
        }
        return deepcopy(snapshot)

    def _fetch_instrument(self, symbol: str, label: str) -> dict[str, Any]:
        empty = {"symbol": symbol, "label": label, "value": None, "changePct": None, "asOf": None}
        if not acquire_rate_limit("yfinance", timeout=2.0):
            logger.warning("macro_yfinance_rate_limit_skip symbol=%s", symbol)
            return empty
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            if hist is None or hist.empty or "Close" not in hist.columns:
                return empty
            last_close = float(hist["Close"].iloc[-1])
            change_pct: float | None = None
            if len(hist) >= 2:
                prev_close = float(hist["Close"].iloc[-2])
                if prev_close:
                    change_pct = (last_close - prev_close) / prev_close * 100.0
            as_of = hist.index[-1]
            return {
                "symbol": symbol,
                "label": label,
                "value": round(last_close, 4),
                "changePct": round(change_pct, 4) if change_pct is not None else None,
                "asOf": str(as_of)[:10],
            }
        except Exception:
            logger.exception("macro_fetch_failed symbol=%s", symbol)
            return empty


_macro_service_singleton: MacroService | None = None


def get_macro_service() -> MacroService:
    global _macro_service_singleton
    if _macro_service_singleton is None:
        _macro_service_singleton = MacroService()
    return _macro_service_singleton
