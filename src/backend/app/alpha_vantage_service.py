from __future__ import annotations

import copy
import logging
import os
from datetime import datetime
from time import monotonic
from typing import Any

import pandas as pd
import requests

from app.asset_metadata import canonicalize_symbol

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10
PROFILE_TTL_SECONDS = 15 * 60
HISTORY_TTL_SECONDS = 5 * 60
NEWS_TTL_SECONDS = 60


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_percent(value: Any) -> float | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    if abs(numeric) <= 1:
        numeric *= 100
    return round(numeric, 2)


def _normalize_alpha_timestamp(raw_value: Any) -> str | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.isoformat() + "Z"
    return text


class AlphaVantageService:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self.api_key = (api_key or os.getenv("ALPHA_VANTAGE_API_KEY", "")).strip()
        self.base_url = "https://www.alphavantage.co/query"
        self.session = session or requests.Session()
        self._cache: dict[str, dict[str, Any]] = {}

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_cached_payload(self, key: str):
        entry = self._cache.get(key)
        if not entry:
            return None
        if entry["expires_at"] <= monotonic():
            self._cache.pop(key, None)
            return None
        return copy.deepcopy(entry["value"])

    def _set_cached_payload(self, key: str, value: Any, ttl_seconds: int):
        self._cache[key] = {
            "expires_at": monotonic() + ttl_seconds,
            "value": copy.deepcopy(value),
        }
        return copy.deepcopy(value)

    def _request(self, cache_key: str, ttl_seconds: int, **params) -> dict[str, Any]:
        if not self.is_configured():
            return {}

        cached = self._get_cached_payload(cache_key)
        if cached is not None:
            return cached

        try:
            response = self.session.get(
                self.base_url,
                params={**params, "apikey": self.api_key},
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.exception(
                "alpha_vantage_request_failed function=%s symbol=%s",
                params.get("function"),
                params.get("symbol") or params.get("tickers"),
            )
            return {}

        if not isinstance(payload, dict):
            logger.warning(
                "alpha_vantage_response_invalid function=%s symbol=%s",
                params.get("function"),
                params.get("symbol") or params.get("tickers"),
            )
            return {}

        for error_key in ("Note", "Information", "Error Message"):
            if payload.get(error_key):
                logger.warning(
                    "alpha_vantage_request_rejected function=%s key=%s message=%s",
                    params.get("function"),
                    error_key,
                    payload.get(error_key),
                )
                return self._set_cached_payload(
                    cache_key,
                    {"_warning_key": error_key, "_warning": str(payload.get(error_key))},
                    min(ttl_seconds, 60),
                )

        return self._set_cached_payload(cache_key, payload, ttl_seconds)

    def _build_empty_snapshot(self, asset_class: str, reason: str) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "source": "Alpha Vantage",
            "assetClass": asset_class,
            "reason": reason,
            "lastUpdated": None,
            "quote": {
                "price": None,
                "change": None,
                "changePercent": None,
                "currency": "USD",
                "history": [],
            },
            "research": {
                "expenseRatio": None,
                "dividendYield": None,
                "netAssets": None,
                "inceptionDate": None,
                "topHoldings": [],
                "topSectors": [],
            },
        }

    def _find_series_key(self, payload: dict[str, Any]) -> str | None:
        for key in payload:
            if key.lower().startswith("time series"):
                return key
        return None

    def _format_frame_timestamp(self, index: Any) -> str | None:
        if hasattr(index, "to_pydatetime"):
            index = index.to_pydatetime()
        if isinstance(index, datetime):
            return index.isoformat() + "Z"
        return None

    def _history_quote_payload(self, frame: pd.DataFrame, currency: str) -> dict[str, Any]:
        quote = {
            "price": None,
            "change": None,
            "changePercent": None,
            "currency": currency,
            "history": [],
        }
        if frame.empty:
            return quote

        latest = frame.iloc[-1]
        previous = frame.iloc[-2] if len(frame.index) > 1 else latest
        latest_close = _safe_float(latest.get("Close"))
        previous_close = _safe_float(previous.get("Close"))
        change = None
        change_percent = None
        if latest_close is not None and previous_close not in (None, 0):
            change = round(latest_close - previous_close, 4)
            change_percent = round(((latest_close - previous_close) / previous_close) * 100, 2)

        quote["price"] = round(latest_close, 4) if latest_close is not None else None
        quote["change"] = change
        quote["changePercent"] = change_percent
        quote["history"] = [
            {"close": round(float(row["Close"]), 2)}
            for _, row in frame.tail(20).iterrows()
            if _safe_float(row.get("Close")) is not None
        ]
        return quote

    def _normalize_etf_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        holdings_raw = payload.get("holdings") or []
        sectors_raw = payload.get("sectors") or []
        return {
            "expenseRatio": _normalize_percent(payload.get("net_expense_ratio")),
            "dividendYield": _normalize_percent(payload.get("dividend_yield")),
            "netAssets": _safe_float(payload.get("net_assets")),
            "inceptionDate": payload.get("inception_date"),
            "topHoldings": [
                {
                    "symbol": holding.get("symbol"),
                    "name": holding.get("description"),
                    "weightPercent": _normalize_percent(holding.get("weight")),
                }
                for holding in holdings_raw[:5]
                if holding.get("symbol") or holding.get("description")
            ],
            "topSectors": [
                {
                    "sector": sector.get("sector"),
                    "weightPercent": _normalize_percent(sector.get("weight")),
                }
                for sector in sectors_raw[:5]
                if sector.get("sector")
            ],
        }

    def get_history_df(self, symbol: str, asset_class: str, *, limit: int = 100) -> pd.DataFrame:
        if not self.is_configured():
            return pd.DataFrame()

        canonical_symbol = canonicalize_symbol(symbol)
        if asset_class == "etf":
            payload = self._request(
                f"alpha-history:etf:{canonical_symbol}",
                HISTORY_TTL_SECONDS,
                function="TIME_SERIES_DAILY",
                symbol=canonical_symbol,
                outputsize="compact",
            )
            series_key = self._find_series_key(payload)
            if not series_key:
                return pd.DataFrame()

            rows: list[tuple[str, dict[str, Any]]] = list((payload.get(series_key) or {}).items())
            if not rows:
                return pd.DataFrame()

            records: list[dict[str, Any]] = []
            for timestamp, values in rows:
                records.append(
                    {
                        "timestamp": pd.Timestamp(timestamp),
                        "Open": _safe_float(values.get("1. open")),
                        "High": _safe_float(values.get("2. high")),
                        "Low": _safe_float(values.get("3. low")),
                        "Close": _safe_float(values.get("4. close")),
                        "Volume": _safe_float(values.get("5. volume")) or 0.0,
                    }
                )

        elif asset_class == "crypto":
            base_symbol, market = (canonical_symbol.split("/", 1) + ["USD"])[:2]
            payload = self._request(
                f"alpha-history:crypto:{canonical_symbol}",
                HISTORY_TTL_SECONDS,
                function="DIGITAL_CURRENCY_DAILY",
                symbol=base_symbol,
                market=market,
            )
            series_key = self._find_series_key(payload)
            if not series_key:
                return pd.DataFrame()

            rows = list((payload.get(series_key) or {}).items())
            if not rows:
                return pd.DataFrame()

            open_key = f"1a. open ({market})"
            high_key = f"2a. high ({market})"
            low_key = f"3a. low ({market})"
            close_key = f"4a. close ({market})"

            records = []
            for timestamp, values in rows:
                records.append(
                    {
                        "timestamp": pd.Timestamp(timestamp),
                        "Open": _safe_float(values.get(open_key)),
                        "High": _safe_float(values.get(high_key)),
                        "Low": _safe_float(values.get(low_key)),
                        "Close": _safe_float(values.get(close_key)),
                        "Volume": _safe_float(values.get("5. volume")) or 0.0,
                    }
                )
        else:
            return pd.DataFrame()

        frame = pd.DataFrame.from_records(records).dropna(subset=["Open", "High", "Low", "Close"])
        if frame.empty:
            return frame
        frame = frame.sort_values("timestamp").set_index("timestamp")
        return frame.tail(limit)

    def get_provider_snapshot(self, symbol: str, asset_class: str) -> dict[str, Any] | None:
        if asset_class not in {"etf", "crypto"}:
            return None
        if not self.is_configured():
            return self._build_empty_snapshot(asset_class, "not_configured")

        snapshot = self._build_empty_snapshot(asset_class, "fetch_failed")
        history_frame = self.get_history_df(symbol, asset_class, limit=100)
        snapshot["quote"] = self._history_quote_payload(history_frame, "USD")
        if not history_frame.empty:
            snapshot["status"] = "live"
            snapshot["reason"] = None
            snapshot["lastUpdated"] = self._format_frame_timestamp(history_frame.index[-1])

        if asset_class == "etf":
            profile_payload = self._request(
                f"alpha-profile:etf:{canonicalize_symbol(symbol)}",
                PROFILE_TTL_SECONDS,
                function="ETF_PROFILE",
                symbol=canonicalize_symbol(symbol),
            )
            if profile_payload and not profile_payload.get("_warning"):
                snapshot["research"] = self._normalize_etf_profile(profile_payload)
                if snapshot["status"] == "unavailable":
                    snapshot["status"] = "partial"
                    snapshot["reason"] = None
        else:
            base_symbol, market = (canonicalize_symbol(symbol).split("/", 1) + ["USD"])[:2]
            snapshot["quote"]["currency"] = market

        return snapshot

    def get_news_payload(self, symbol: str, asset_class: str, *, limit: int = 15) -> dict[str, Any] | None:
        if asset_class not in {"etf", "crypto"} or not self.is_configured():
            return None

        canonical_symbol = canonicalize_symbol(symbol)
        if asset_class == "crypto":
            base_symbol = canonical_symbol.split("/", 1)[0]
            tickers = f"CRYPTO:{base_symbol}"
        else:
            tickers = canonical_symbol

        payload = self._request(
            f"alpha-news:{asset_class}:{canonical_symbol}:{int(limit)}",
            NEWS_TTL_SECONDS,
            function="NEWS_SENTIMENT",
            tickers=tickers,
            sort="LATEST",
            limit=int(limit),
        )
        feed = payload.get("feed") or []
        if not feed:
            return None

        items: list[dict[str, Any]] = []
        scores: list[float] = []
        for entry in feed[:limit]:
            score = _safe_float(entry.get("overall_sentiment_score")) or 0.0
            raw_label = str(entry.get("overall_sentiment_label") or "").lower()
            if raw_label not in {"bullish", "neutral", "bearish"}:
                raw_label = "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral"
            items.append(
                {
                    "title": entry.get("title"),
                    "summary": entry.get("summary"),
                    "score": round(score, 4),
                    "label": raw_label,
                    "timestamp": _normalize_alpha_timestamp(entry.get("time_published")),
                    "url": entry.get("url"),
                    "source": entry.get("source"),
                }
            )
            scores.append(score)

        aggregate_score = round(sum(scores) / len(scores), 4) if scores else 0.0
        aggregate_label = "bullish" if aggregate_score > 0.1 else "bearish" if aggregate_score < -0.1 else "neutral"
        last_updated = items[0]["timestamp"] if items else None

        return {
            "items": items,
            "aggregate_score": aggregate_score,
            "aggregate_label": aggregate_label,
            "provider": {
                "status": "live",
                "source": "Alpha Vantage",
                "assetClass": asset_class,
                "lastUpdated": last_updated,
            },
        }
