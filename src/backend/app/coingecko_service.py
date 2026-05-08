"""CoinGecko + Fear-and-Greed adapter.

CoinGecko fills the crypto-specific gaps that Alpha Vantage and yfinance
don't cover well: market-cap rank, cross-exchange 24h volume, ATH/ATL
distance, and the developer + community-activity scores. Free tier needs
no auth; an optional `COINGECKO_API_KEY` env var unlocks higher per-IP
budgets when set.

The Fear-and-Greed-Index is fetched separately from `alternative.me`
(no auth, free) and is a market-wide signal independent of any specific
coin — it shows up in the macro-style cards alongside VIX/10Y/DXY.

Both calls go through `app.rate_limit.acquire("coingecko" / "fear_greed")`
so a busy scanner cycle doesn't burn the per-IP budget.
"""
from __future__ import annotations

import logging
import os
from copy import deepcopy
from time import monotonic
from typing import Any

import requests

from app.rate_limit import acquire as acquire_rate_limit

logger = logging.getLogger(__name__)

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
FEAR_GREED_URL = "https://api.alternative.me/fng/"
DEFAULT_TIMEOUT_SECONDS = 12.0
COIN_METRICS_TTL_SECONDS = 5 * 60
FEAR_GREED_TTL_SECONDS = 30 * 60

# Top-by-market-cap coin id mapping. The frontend ships symbols like
# `BTC/USD`, `ETH/USD`; we strip the quote currency and look up the
# CoinGecko id. Anything outside this map falls back to a `/coins/markets`
# probe so we still cover long-tail coins, just at one extra request.
COIN_ID_BY_SYMBOL: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "DOGE": "dogecoin",
    "TRX": "tron",
    "DOT": "polkadot",
    "MATIC": "polygon-pos",
    "LINK": "chainlink",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "XLM": "stellar",
    "NEAR": "near",
    "ETC": "ethereum-classic",
    "FIL": "filecoin",
    "ARB": "arbitrum",
    "OP": "optimism",
    "APT": "aptos",
    "ICP": "internet-computer",
    "INJ": "injective-protocol",
    "TON": "the-open-network",
    "SHIB": "shiba-inu",
    "PEPE": "pepe",
}


def _normalize_base_symbol(symbol: str) -> str:
    """`BTC/USD` -> `BTC`, `ETH-USD` -> `ETH`, `SOLUSDT` -> `SOLUSDT`.

    The simulator only feeds canonical pair forms with a slash separator
    today; we keep the dash variant as a defensive fallback because Alpaca
    occasionally surfaces them.
    """
    if not symbol:
        return ""
    upper = symbol.upper().strip()
    for sep in ("/", "-"):
        if sep in upper:
            return upper.split(sep, 1)[0]
    return upper


class CoinGeckoService:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("COINGECKO_API_KEY", "")).strip()
        self._coin_metrics_cache: dict[str, dict[str, Any]] = {}
        self._fear_greed_cache: dict[str, Any] = {"expires_at": 0.0, "value": None}

    def _request(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        if not acquire_rate_limit("coingecko", timeout=4.0):
            logger.warning("coingecko_rate_limit_skip path=%s", path)
            return None
        merged: dict[str, Any] = dict(params or {})
        headers = {"accept": "application/json"}
        if self.api_key:
            # Pro keys go in a header; demo keys also accept the same
            # `x-cg-demo-api-key` shape — both are documented public knobs.
            headers["x-cg-pro-api-key"] = self.api_key
        url = f"{COINGECKO_BASE_URL}{path}"
        try:
            response = requests.get(url, params=merged, headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            logger.warning(
                "coingecko_http_error path=%s status=%s",
                path,
                exc.response.status_code if exc.response is not None else "n/a",
            )
            return None
        except requests.RequestException:
            logger.exception("coingecko_request_failed path=%s", path)
            return None
        except ValueError:
            logger.exception("coingecko_invalid_json path=%s", path)
            return None

    def _resolve_coin_id(self, symbol: str) -> str | None:
        base = _normalize_base_symbol(symbol)
        if not base:
            return None
        cached = COIN_ID_BY_SYMBOL.get(base)
        if cached:
            return cached
        # Fallback: ask `/coins/markets` for the symbol and pick the
        # highest-market-cap match. This is the slow path; we don't cache
        # it because `_request` is rate-limited and the metric fetch
        # itself is module-cached for 5 minutes.
        payload = self._request(
            "/coins/markets",
            params={"vs_currency": "usd", "symbols": base.lower(), "per_page": 5, "page": 1},
        )
        if not isinstance(payload, list) or not payload:
            return None
        best = max(
            (row for row in payload if isinstance(row, dict)),
            key=lambda row: row.get("market_cap") or 0,
            default=None,
        )
        return best.get("id") if isinstance(best, dict) else None

    def get_coin_metrics(self, symbol: str) -> dict[str, Any] | None:
        """Bundle market + community + developer signals for one crypto symbol.

        Empty dict (None) when CoinGecko is rate-limited or the symbol
        cannot be mapped to a coin id. Cached per base symbol for
        `COIN_METRICS_TTL_SECONDS` so repeated analysis-page loads don't
        burn the budget.
        """
        base = _normalize_base_symbol(symbol)
        if not base:
            return None

        cache_entry = self._coin_metrics_cache.get(base)
        if cache_entry and cache_entry["expires_at"] > monotonic():
            return deepcopy(cache_entry["value"])

        coin_id = self._resolve_coin_id(symbol)
        if not coin_id:
            return None

        payload = self._request(
            f"/coins/{coin_id}",
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "true",
                "developer_data": "true",
                "sparkline": "false",
            },
        )
        if not isinstance(payload, dict):
            return None

        market = payload.get("market_data") or {}
        community = payload.get("community_data") or {}
        developer = payload.get("developer_data") or {}

        def _usd(node: Any) -> float | None:
            return _safe_float(node.get("usd")) if isinstance(node, dict) else None

        snapshot: dict[str, Any] = {
            "coinId": coin_id,
            "symbol": base,
            "name": payload.get("name"),
            "marketCapRank": payload.get("market_cap_rank"),
            "marketCapUsd": _usd(market.get("market_cap")),
            "totalVolumeUsd": _usd(market.get("total_volume")),
            "currentPriceUsd": _usd(market.get("current_price")),
            "priceChange24hPct": _safe_float(market.get("price_change_percentage_24h")),
            "priceChange7dPct": _safe_float(market.get("price_change_percentage_7d")),
            "priceChange30dPct": _safe_float(market.get("price_change_percentage_30d")),
            "ath": {
                "valueUsd": _usd(market.get("ath")),
                "changePct": _safe_float((market.get("ath_change_percentage") or {}).get("usd")),
                "date": (market.get("ath_date") or {}).get("usd"),
            },
            "atl": {
                "valueUsd": _usd(market.get("atl")),
                "changePct": _safe_float((market.get("atl_change_percentage") or {}).get("usd")),
                "date": (market.get("atl_date") or {}).get("usd"),
            },
            "community": {
                "twitterFollowers": _safe_float(community.get("twitter_followers")),
                "redditSubscribers": _safe_float(community.get("reddit_subscribers")),
                "redditActive48h": _safe_float(community.get("reddit_accounts_active_48h")),
            },
            "developer": {
                "stars": _safe_float(developer.get("stars")),
                "forks": _safe_float(developer.get("forks")),
                "subscribers": _safe_float(developer.get("subscribers")),
                "commitCount4Weeks": _safe_float(developer.get("commit_count_4_weeks")),
            },
            "sentimentVotesUpPct": _safe_float(payload.get("sentiment_votes_up_percentage")),
            "sentimentVotesDownPct": _safe_float(payload.get("sentiment_votes_down_percentage")),
        }
        self._coin_metrics_cache[base] = {
            "expires_at": monotonic() + COIN_METRICS_TTL_SECONDS,
            "value": snapshot,
        }
        return deepcopy(snapshot)

    def get_fear_greed_index(self) -> dict[str, Any] | None:
        """Return the latest Crypto Fear & Greed Index reading.

        `alternative.me` returns the data wrapped in `{"data": [...]}`. We
        unwrap and surface only `{value, classification, timestamp}`.
        Cached for `FEAR_GREED_TTL_SECONDS` because it only updates daily.
        """
        if self._fear_greed_cache["value"] is not None and self._fear_greed_cache["expires_at"] > monotonic():
            return deepcopy(self._fear_greed_cache["value"])

        if not acquire_rate_limit("fear_greed", timeout=2.0):
            logger.warning("fear_greed_rate_limit_skip")
            return None

        try:
            response = requests.get(FEAR_GREED_URL, params={"limit": 1}, timeout=DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            logger.exception("fear_greed_request_failed")
            return None
        except ValueError:
            logger.exception("fear_greed_invalid_json")
            return None

        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            return None
        first = rows[0]
        if not isinstance(first, dict):
            return None
        snapshot = {
            "value": _safe_int(first.get("value")),
            "classification": first.get("value_classification"),
            "timestamp": first.get("timestamp"),
        }
        self._fear_greed_cache = {
            "expires_at": monotonic() + FEAR_GREED_TTL_SECONDS,
            "value": snapshot,
        }
        return deepcopy(snapshot)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_coingecko_singleton: CoinGeckoService | None = None


def get_coingecko_service() -> CoinGeckoService:
    global _coingecko_singleton
    if _coingecko_singleton is None:
        _coingecko_singleton = CoinGeckoService()
    return _coingecko_singleton
