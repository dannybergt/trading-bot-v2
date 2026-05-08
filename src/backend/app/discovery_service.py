"""Stock discovery — surfaces tickers the user does not yet track.

Builds three orthogonal "what is interesting right now?" views on top
of the data the platform already pulls:

- **Trending** — symbols mentioned most often in the global news feed
  over the last 24 h, with a sentiment-burst score against the 7-day
  baseline. Powered by `news_hub_service.get_global_feed`.
- **Top movers** — today's gainers / losers / most-active stocks,
  pulled from FMP's `/stock_market/{gainers|losers|actives}`. The
  list is symbol-discovery-relevant by definition: tickers we don't
  track but the market is acting on right now.
- **Insider clusters** — symbols where multiple insiders have filed
  trades in the same direction over the last 90 days. Driven by FMP's
  global `/insider-trading-rss-feed`.

Every block is cached at the module level for `DISCOVERY_CACHE_TTL`
because the underlying data only changes on the order of minutes and
discovery views are typically refreshed by repeated tab-switching.
"""
from __future__ import annotations

import logging
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any

from app.fmp_service import FmpService
from app.news_hub_service import get_news_hub_service

logger = logging.getLogger(__name__)

DISCOVERY_CACHE_TTL_SECONDS = 15 * 60


class DiscoveryService:
    def __init__(self, *, fmp_service: FmpService | None = None) -> None:
        self.fmp = fmp_service or FmpService()
        self._cache: dict[str, dict[str, Any]] = {}

    def _cached(self, key: str, builder, ttl: int = DISCOVERY_CACHE_TTL_SECONDS):
        entry = self._cache.get(key)
        if entry and entry["expires_at"] > monotonic():
            return deepcopy(entry["value"])
        value = builder()
        self._cache[key] = {"expires_at": monotonic() + ttl, "value": deepcopy(value)}
        return value

    def get_trending_symbols(
        self, *, window_hours: int = 24, baseline_hours: int = 24 * 7, limit: int = 20
    ) -> list[dict[str, Any]]:
        return self._cached(
            f"trending:{window_hours}:{baseline_hours}:{limit}",
            lambda: self._build_trending(
                window_hours=window_hours, baseline_hours=baseline_hours, limit=limit
            ),
        )

    def _build_trending(
        self, *, window_hours: int, baseline_hours: int, limit: int
    ) -> list[dict[str, Any]]:
        feed = get_news_hub_service().get_global_feed(limit=200, offset=0)
        items = feed.get("items") or []
        if not items:
            return []

        now = datetime.now(timezone.utc)
        window_cutoff = now - timedelta(hours=window_hours)
        baseline_cutoff = now - timedelta(hours=max(window_hours + 1, baseline_hours))

        # Per-symbol counters for the recent window and the baseline
        # window. The baseline excludes the recent window so the trend
        # comparison is apples-to-apples.
        recent_counts: Counter[str] = Counter()
        baseline_counts: Counter[str] = Counter()
        recent_sentiments: dict[str, list[float]] = {}
        baseline_sentiments: dict[str, list[float]] = {}
        recent_items: dict[str, list[dict[str, Any]]] = {}

        for item in items:
            ts = self._parse_timestamp(item.get("timestamp"))
            tickers = item.get("tickers") or []
            if not tickers or ts is None:
                continue
            score = float(item.get("score") or 0.0)
            if ts >= window_cutoff:
                for ticker in tickers:
                    recent_counts[ticker] += 1
                    recent_sentiments.setdefault(ticker, []).append(score)
                    recent_items.setdefault(ticker, []).append(item)
            elif ts >= baseline_cutoff:
                for ticker in tickers:
                    baseline_counts[ticker] += 1
                    baseline_sentiments.setdefault(ticker, []).append(score)

        recent_baseline_window_hours = max(1, baseline_hours - window_hours)
        out: list[dict[str, Any]] = []
        for ticker, count_recent in recent_counts.most_common():
            count_baseline = baseline_counts.get(ticker, 0)
            # Project the baseline count to the same `window_hours`
            # length so the trend percent compares like-for-like.
            baseline_per_window = (
                count_baseline / recent_baseline_window_hours * window_hours
            )
            trend_pct: float | None = None
            if baseline_per_window > 0:
                trend_pct = (count_recent - baseline_per_window) / baseline_per_window * 100.0
            avg_recent = (
                sum(recent_sentiments.get(ticker, [])) / len(recent_sentiments.get(ticker, []))
                if recent_sentiments.get(ticker)
                else 0.0
            )
            avg_baseline = (
                sum(baseline_sentiments.get(ticker, [])) / len(baseline_sentiments.get(ticker, []))
                if baseline_sentiments.get(ticker)
                else 0.0
            )
            sentiment_burst = round(avg_recent - avg_baseline, 4)
            sample = (recent_items.get(ticker) or [None])[0]
            out.append(
                {
                    "symbol": ticker,
                    "mentionCountRecent": count_recent,
                    "mentionCountBaseline": count_baseline,
                    "mentionTrendPct": round(trend_pct, 2) if trend_pct is not None else None,
                    "avgSentimentRecent": round(avg_recent, 4),
                    "sentimentBurst": sentiment_burst,
                    "sampleTitle": sample.get("title") if isinstance(sample, dict) else None,
                    "sampleUrl": sample.get("url") if isinstance(sample, dict) else None,
                }
            )
            if len(out) >= limit:
                break
        return out

    def get_top_movers(self) -> dict[str, list[dict[str, Any]]]:
        return self._cached("top_movers", self._build_top_movers)

    def _build_top_movers(self) -> dict[str, list[dict[str, Any]]]:
        if not self.fmp.configured:
            return {"gainers": [], "losers": [], "actives": []}
        raw = self.fmp.get_market_movers()
        normalized: dict[str, list[dict[str, Any]]] = {}
        for bucket, rows in raw.items():
            normalized[bucket] = [
                {
                    "symbol": str(row.get("symbol") or "").upper(),
                    "name": row.get("name") or row.get("companyName"),
                    "price": _safe_float(row.get("price")),
                    "change": _safe_float(row.get("change") or row.get("changes")),
                    "changesPercentage": _safe_float(
                        row.get("changesPercentage")
                        or row.get("changesPercentageString")
                    ),
                }
                for row in rows[:20]
                if isinstance(row, dict) and row.get("symbol")
            ]
        return normalized

    def get_insider_clusters(
        self, *, lookback_days: int = 90, min_unique_insiders: int = 3, limit: int = 20
    ) -> list[dict[str, Any]]:
        return self._cached(
            f"insider_clusters:{lookback_days}:{min_unique_insiders}:{limit}",
            lambda: self._build_insider_clusters(
                lookback_days=lookback_days,
                min_unique_insiders=min_unique_insiders,
                limit=limit,
            ),
        )

    def _build_insider_clusters(
        self, *, lookback_days: int, min_unique_insiders: int, limit: int
    ) -> list[dict[str, Any]]:
        if not self.fmp.configured:
            return []
        feed = self.fmp.get_insider_trading_feed(limit=400)
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        per_symbol: dict[str, dict[str, Any]] = {}
        for row in feed:
            tx_date = self._parse_timestamp(row.get("transactionDate") or row.get("filingDate"))
            if tx_date is None or tx_date < cutoff:
                continue
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            transaction_type = str(row.get("transactionType") or "").strip()
            acq_disp = str(row.get("acquistionOrDisposition") or "").strip()
            is_buy = transaction_type.startswith("P") or acq_disp == "A"
            insider = row.get("reportingName") or row.get("typeOfOwner")
            shares = _safe_float(row.get("securitiesTransacted")) or 0.0
            price = _safe_float(row.get("price")) or 0.0
            value = shares * price

            bucket = per_symbol.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "uniqueInsiders": set(),
                    "buyValue": 0.0,
                    "sellValue": 0.0,
                    "buyCount": 0,
                    "sellCount": 0,
                    "lastDate": None,
                },
            )
            if insider:
                bucket["uniqueInsiders"].add(insider)
            if is_buy:
                bucket["buyValue"] += value
                bucket["buyCount"] += 1
            else:
                bucket["sellValue"] += value
                bucket["sellCount"] += 1
            if bucket["lastDate"] is None or (tx_date and tx_date > bucket["lastDate"]):
                bucket["lastDate"] = tx_date

        clusters: list[dict[str, Any]] = []
        for symbol, bucket in per_symbol.items():
            if len(bucket["uniqueInsiders"]) < min_unique_insiders:
                continue
            net_value = bucket["buyValue"] - bucket["sellValue"]
            direction = (
                "buy_cluster"
                if bucket["buyCount"] > bucket["sellCount"]
                else "sell_cluster"
                if bucket["sellCount"] > bucket["buyCount"]
                else "mixed"
            )
            clusters.append(
                {
                    "symbol": symbol,
                    "uniqueInsiders": len(bucket["uniqueInsiders"]),
                    "buyCount": bucket["buyCount"],
                    "sellCount": bucket["sellCount"],
                    "netValue": round(net_value, 2),
                    "direction": direction,
                    "lastTransactionDate": (
                        bucket["lastDate"].date().isoformat() if bucket["lastDate"] else None
                    ),
                }
            )

        # Strongest clusters first: prefer larger insider count, then absolute net value.
        clusters.sort(
            key=lambda c: (c["uniqueInsiders"], abs(c["netValue"])),
            reverse=True,
        )
        return clusters[:limit]

    def get_dashboard(self) -> dict[str, Any]:
        return {
            "trending": self.get_trending_symbols(),
            "topMovers": self.get_top_movers(),
            "insiderClusters": self.get_insider_clusters(),
        }

    @staticmethod
    def _parse_timestamp(raw: Any) -> datetime | None:
        if not raw:
            return None
        text = str(raw).strip()
        for fmt in (None, "%Y%m%dT%H%M%S", "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%d"):
            try:
                if fmt is None:
                    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                else:
                    parsed = datetime.strptime(text, fmt)
            except (TypeError, ValueError):
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        # FMP sometimes ships percent values as `"+5.20%"` strings
        try:
            return float(str(value).replace("%", "").replace("+", "").strip() or "0")
        except (TypeError, ValueError):
            return None


_singleton: DiscoveryService | None = None


def get_discovery_service() -> DiscoveryService:
    global _singleton
    if _singleton is None:
        _singleton = DiscoveryService()
    return _singleton
