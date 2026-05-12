"""Twelve Data adapter — third fallback for ticker fundamentals.

Purpose: yfinance and FMP both lean US-heavy. Twelve Data closes the
non-US coverage gap (Frankfurt XETR, Paris EPA, London LSE, Tokio TSE,
Hong Kong HKG) and accepts the canonical exchange-suffix symbols
(`SAP.DE`, `BMW.DE`, `LVMH.PA`, `BARC.LON`, `7203.T`).

Free tier is ~8 requests/min, so the adapter goes through the shared
`twelve_data` rate-limiter bucket. An optional `TWELVE_DATA_API_KEY`
env var unlocks the higher-tier limits when set.

The output of `normalized_ticker_info` mirrors the yfinance keys the
rest of the backend expects (`sector`, `industry`, `marketCap`,
`trailingPE`, …) so it's a drop-in fallback inside
`MarketDataService.get_ticker_info`.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

from app.rate_limit import acquire as acquire_rate_limit

logger = logging.getLogger(__name__)

TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
DEFAULT_TIMEOUT_SECONDS = 12.0


class TwelveDataService:
    """Wraps Twelve Data REST endpoints used as a non-US fallback."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("TWELVE_DATA_API_KEY", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _request(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        if not self.configured:
            return None
        if not acquire_rate_limit("twelve_data", timeout=8.0):
            logger.warning("twelve_data_rate_limit_skip path=%s", path)
            return None
        merged: dict[str, Any] = {"apikey": self.api_key}
        if params:
            merged.update(params)
        url = f"{TWELVE_DATA_BASE_URL}{path}"
        try:
            response = requests.get(url, params=merged, timeout=DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "n/a"
            logger.warning("twelve_data_http_error path=%s status=%s", path, status)
            return None
        except requests.RequestException:
            logger.exception("twelve_data_request_failed path=%s", path)
            return None
        except ValueError:
            logger.exception("twelve_data_invalid_json path=%s", path)
            return None
        # Twelve Data wraps errors in a 200 with `{"status":"error","code":...}`
        if isinstance(payload, dict) and payload.get("status") == "error":
            logger.info(
                "twelve_data_error_payload path=%s code=%s message=%s",
                path,
                payload.get("code"),
                payload.get("message"),
            )
            return None
        return payload

    def get_quote(self, symbol: str) -> dict[str, Any] | None:
        if not symbol:
            return None
        payload = self._request("/quote", params={"symbol": symbol.upper()})
        return payload if isinstance(payload, dict) else None

    def get_profile(self, symbol: str) -> dict[str, Any] | None:
        if not symbol:
            return None
        payload = self._request("/profile", params={"symbol": symbol.upper()})
        return payload if isinstance(payload, dict) else None

    def get_statistics(self, symbol: str) -> dict[str, Any] | None:
        """`/statistics` returns nested blocks (valuations_metrics,
        financials_data, …). We hand the whole dict back; the
        normalisation layer picks the fields it needs.
        """
        if not symbol:
            return None
        payload = self._request("/statistics", params={"symbol": symbol.upper()})
        return payload if isinstance(payload, dict) else None

    def normalized_ticker_info(self, symbol: str) -> dict[str, Any]:
        """Return a yfinance-compatible subset so MarketDataService can use
        Twelve Data as a drop-in fallback without rewriting downstream
        consumers.

        Empty dict if the service is unconfigured, rate-limited, or has no
        usable data for the symbol. Wert-Felder werden nur dann gesetzt,
        wenn sie in [-something, +something] valide sind.
        """
        profile = self.get_profile(symbol) or {}
        statistics = self.get_statistics(symbol) or {}
        quote = self.get_quote(symbol) or {}
        if not profile and not statistics and not quote:
            return {}

        valuations = (
            statistics.get("statistics", {}).get("valuations_metrics")
            if isinstance(statistics.get("statistics"), dict)
            else None
        )
        financials = (
            statistics.get("statistics", {}).get("financials")
            if isinstance(statistics.get("statistics"), dict)
            else None
        )
        dividends_split = (
            statistics.get("statistics", {}).get("dividends_and_splits")
            if isinstance(statistics.get("statistics"), dict)
            else None
        )

        valuations = valuations if isinstance(valuations, dict) else {}
        financials = financials if isinstance(financials, dict) else {}
        dividends_split = dividends_split if isinstance(dividends_split, dict) else {}

        info: dict[str, Any] = {
            "shortName": profile.get("name") or quote.get("name"),
            "longName": profile.get("name"),
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "currency": profile.get("currency") or quote.get("currency"),
            "marketCap": _safe_int(valuations.get("market_capitalization")),
            "fiftyTwoWeekHigh": _safe_float(quote.get("fifty_two_week", {}).get("high"))
            if isinstance(quote.get("fifty_two_week"), dict)
            else None,
            "fiftyTwoWeekLow": _safe_float(quote.get("fifty_two_week", {}).get("low"))
            if isinstance(quote.get("fifty_two_week"), dict)
            else None,
            "dividendYield": _safe_float(dividends_split.get("forward_annual_dividend_yield")),
            "trailingPE": _safe_float(valuations.get("trailing_pe")),
            "forwardPE": _safe_float(valuations.get("forward_pe")),
            "priceToBook": _safe_float(valuations.get("price_to_book_mrq")),
            "twelve_data_source": True,
        }
        return {k: v for k, v in info.items() if v is not None}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    f = _safe_float(value)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None
