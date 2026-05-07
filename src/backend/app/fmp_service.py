"""Financial Modeling Prep adapter for stock fundamentals, ratios, ETF holdings,
and news.

Lives alongside the existing yfinance and Alpha Vantage providers. The
service is intentionally narrow: every method returns dict/list/None and
swallows transport errors with structured logging. Callers in
`MarketDataService` chain providers and treat empty results as "skip this
source, try the next."

All outbound calls go through the shared rate limiter
(`app.rate_limit.acquire("fmp")`) so the FMP key budget stays predictable
even when scanner, alerts, and analysis paths fire concurrently.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from app.rate_limit import acquire as acquire_rate_limit

logger = logging.getLogger(__name__)

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
DEFAULT_TIMEOUT_SECONDS = 12.0


class FmpService:
    """Wraps FMP REST endpoints used by the trading-bot-v2 backend."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("FMP_API_KEY", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _request(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        if not self.configured:
            return None
        if not acquire_rate_limit("fmp", timeout=8.0):
            logger.warning("fmp_rate_limit_skip path=%s", path)
            return None
        merged = {"apikey": self.api_key}
        if params:
            merged.update(params)
        url = f"{FMP_BASE_URL}{path}"
        try:
            response = requests.get(url, params=merged, timeout=DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            logger.warning(
                "fmp_http_error path=%s status=%s",
                path,
                exc.response.status_code if exc.response is not None else "n/a",
            )
            return None
        except requests.RequestException:
            logger.exception("fmp_request_failed path=%s", path)
            return None
        except ValueError:
            logger.exception("fmp_invalid_json path=%s", path)
            return None

    def get_profile(self, symbol: str) -> dict[str, Any] | None:
        if not symbol:
            return None
        payload = self._request(f"/profile/{symbol.upper()}")
        if isinstance(payload, list) and payload:
            return payload[0]
        return None

    def get_key_metrics(self, symbol: str) -> dict[str, Any] | None:
        if not symbol:
            return None
        payload = self._request(f"/key-metrics/{symbol.upper()}", params={"limit": 1})
        if isinstance(payload, list) and payload:
            return payload[0]
        return None

    def get_ratios(self, symbol: str) -> dict[str, Any] | None:
        if not symbol:
            return None
        payload = self._request(f"/ratios/{symbol.upper()}", params={"limit": 1})
        if isinstance(payload, list) and payload:
            return payload[0]
        return None

    def get_etf_holdings(self, symbol: str) -> list[dict[str, Any]]:
        if not symbol:
            return []
        payload = self._request(f"/etf-holder/{symbol.upper()}")
        if isinstance(payload, list):
            return payload
        return []

    def get_dividends(self, symbol: str) -> list[dict[str, Any]]:
        """Recent dividend history for the symbol.

        FMP returns the payload nested as `{"symbol": ..., "historical": [...]}`
        on this endpoint; we unwrap and return only the inner list so callers
        get a uniform list-of-events shape.
        """
        if not symbol:
            return []
        payload = self._request(f"/historical-price-full/stock_dividend/{symbol.upper()}")
        if isinstance(payload, dict):
            historical = payload.get("historical")
            if isinstance(historical, list):
                return historical
        if isinstance(payload, list):
            return payload
        return []

    def get_splits(self, symbol: str) -> list[dict[str, Any]]:
        """Recent stock-split history for the symbol."""
        if not symbol:
            return []
        payload = self._request(f"/historical-price-full/stock_split/{symbol.upper()}")
        if isinstance(payload, dict):
            historical = payload.get("historical")
            if isinstance(historical, list):
                return historical
        if isinstance(payload, list):
            return payload
        return []

    def get_earnings(self, symbol: str, *, limit: int = 12) -> list[dict[str, Any]]:
        """Past earnings reports with EPS actual/estimate. FMP free tier
        coverage varies; an empty list is a normal "no data" signal."""
        if not symbol:
            return []
        payload = self._request(
            f"/historical/earning_calendar/{symbol.upper()}",
            params={"limit": max(1, min(limit, 50))},
        )
        if isinstance(payload, list):
            return payload
        return []

    def get_news(self, symbol: str, *, limit: int = 5) -> list[dict[str, Any]]:
        if not symbol:
            return []
        payload = self._request(
            "/stock_news",
            params={"tickers": symbol.upper(), "limit": max(1, min(limit, 50))},
        )
        if isinstance(payload, list):
            return payload
        return []

    def normalized_ticker_info(self, symbol: str) -> dict[str, Any]:
        """Return a yfinance-compatible subset so MarketDataService can use FMP
        as a drop-in fallback without rewriting downstream consumers.

        Empty dict if FMP is unconfigured, rate-limited, or has no data.
        """
        profile = self.get_profile(symbol) or {}
        metrics = self.get_key_metrics(symbol) or {}
        ratios = self.get_ratios(symbol) or {}
        if not profile and not metrics and not ratios:
            return {}

        info: dict[str, Any] = {
            "shortName": profile.get("companyName") or profile.get("symbol"),
            "longName": profile.get("companyName"),
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "marketCap": profile.get("mktCap"),
            "fiftyTwoWeekHigh": (
                _parse_range_high(profile.get("range")) if profile.get("range") else None
            ),
            "fiftyTwoWeekLow": (
                _parse_range_low(profile.get("range")) if profile.get("range") else None
            ),
            "dividendYield": ratios.get("dividendYielTTM") or ratios.get("dividendYieldTTM"),
            "trailingPE": metrics.get("peRatio") or ratios.get("priceEarningsRatioTTM"),
            "forwardPE": metrics.get("forwardPE"),
            "priceToBook": ratios.get("priceToBookRatioTTM") or metrics.get("pbRatio"),
            "fmp_source": True,
        }
        return {k: v for k, v in info.items() if v is not None}

    def normalized_events(self, symbol: str) -> dict[str, list[dict[str, Any]]]:
        """Aggregate dividends/splits/earnings into a single shape consumed by
        `/api/events/{symbol}`. Each list contains the raw provider rows
        normalized to camelCase keys the frontend expects.
        """
        dividends_raw = self.get_dividends(symbol)
        splits_raw = self.get_splits(symbol)
        earnings_raw = self.get_earnings(symbol)

        dividends = []
        for row in dividends_raw[:60]:
            if not isinstance(row, dict):
                continue
            dividends.append({
                "date": row.get("date"),
                "amount": row.get("dividend") or row.get("adjDividend"),
                "adjAmount": row.get("adjDividend"),
                "recordDate": row.get("recordDate"),
                "paymentDate": row.get("paymentDate"),
                "declarationDate": row.get("declarationDate"),
                "label": row.get("label"),
            })

        splits = []
        for row in splits_raw[:30]:
            if not isinstance(row, dict):
                continue
            splits.append({
                "date": row.get("date"),
                "numerator": row.get("numerator"),
                "denominator": row.get("denominator"),
                "label": row.get("label"),
            })

        earnings = []
        for row in earnings_raw[:30]:
            if not isinstance(row, dict):
                continue
            earnings.append({
                "date": row.get("date"),
                "epsEstimate": row.get("epsEstimated"),
                "epsActual": row.get("eps"),
                "revenueEstimate": row.get("revenueEstimated"),
                "revenueActual": row.get("revenue"),
                "fiscalDateEnding": row.get("fiscalDateEnding"),
                "time": row.get("time"),
                "updatedFromDate": row.get("updatedFromDate"),
            })

        return {
            "dividends": dividends,
            "splits": splits,
            "earnings": earnings,
        }

    def normalized_news_items(self, symbol: str, *, limit: int = 5) -> list[dict[str, Any]]:
        items = self.get_news(symbol, limit=limit)
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "title": item.get("title"),
                    "summary": item.get("text"),
                    "url": item.get("url"),
                    "timestamp": item.get("publishedDate"),
                    "source": item.get("site") or "FMP",
                    "label": None,
                    "score": None,
                }
            )
        return normalized


def _parse_range_high(value: str) -> float | None:
    try:
        parts = [p.strip() for p in str(value).split("-")]
        if len(parts) == 2:
            return float(parts[1])
    except (ValueError, TypeError):
        return None
    return None


def _parse_range_low(value: str) -> float | None:
    try:
        parts = [p.strip() for p in str(value).split("-")]
        if len(parts) == 2:
            return float(parts[0])
    except (ValueError, TypeError):
        return None
    return None
