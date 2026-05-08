"""News-Hub aggregator — global news feed across every provider.

Where `MarketDataService.get_market_news(symbol)` ties news to a
specific ticker, this service deliberately fans out across providers
without a symbol filter. The point is discovery: the user can browse
incoming financial news for *any* listed company, see which symbols
each item references, and use that as a launching pad to add new
tickers to a watchlist.

Sources combined:
- FMP `/stock_news?limit=...` (no ticker filter → broad market feed)
- Alpha Vantage `NEWS_SENTIMENT?topics=technology,finance,earnings`
- RSS feeds via `rss_news_service` (boerse.de, ariva.de, Reuters)

Each item is normalised to the same shape the existing news
consumers already use, deduplicated by URL, sorted newest-first,
optionally filtered by source / sentiment / since-timestamp / symbol.
A 5-minute cache caps upstream pressure when the page refreshes.
"""
from __future__ import annotations

import logging
import re
from copy import deepcopy
from datetime import datetime, timezone
from time import monotonic
from typing import Any

from app.alpha_vantage_service import AlphaVantageService
from app.fmp_service import FmpService
from app.rss_news_service import get_rss_news_service
from app.sentiment import analyze_sentiment_basic

logger = logging.getLogger(__name__)

NEWS_HUB_CACHE_TTL_SECONDS = 5 * 60
TICKER_PATTERN = re.compile(r"\$?([A-Z]{1,5})\b")
DEFAULT_AV_TOPICS = "technology,finance,earnings,economy_macro,economy_monetary"


class NewsHubService:
    def __init__(
        self,
        *,
        fmp_service: FmpService | None = None,
        alpha_vantage_service: AlphaVantageService | None = None,
        symbol_directory: callable | None = None,
    ) -> None:
        self.fmp = fmp_service or FmpService()
        self.alpha_vantage = alpha_vantage_service or AlphaVantageService()
        # Optional callable returning the set of tradable symbols
        # (e.g. `MarketDataService.get_asset_reference`-backed lookup)
        # — used to validate symbols extracted from titles.
        self.symbol_directory = symbol_directory
        self._cache: dict[str, dict[str, Any]] = {}

    def _cache_key(self, *, sources: tuple[str, ...] | None) -> str:
        if sources is None:
            return "*"
        return ",".join(sorted(sources))

    def _fetch_fmp(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self.fmp.configured:
            return []
        items = self.fmp.normalized_news_items("", limit=limit) if False else []
        # FMP's /stock_news without tickers returns the global feed; the
        # existing FmpService.get_news() requires a symbol, so we go to
        # `/stock_news` directly through the same private helper.
        try:
            payload = self.fmp._request("/stock_news", params={"limit": min(limit, 50)})
        except Exception:
            logger.exception("news_hub_fmp_fetch_failed")
            return []
        if not isinstance(payload, list):
            return []
        out: list[dict[str, Any]] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            title = (entry.get("title") or "").strip()
            text = (entry.get("text") or "").strip()
            if not title:
                continue
            score = analyze_sentiment_basic(f"{title} {text}".strip()) if title else 0.0
            label = "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral"
            out.append(
                {
                    "title": title,
                    "summary": text[:600],
                    "url": entry.get("url"),
                    "timestamp": entry.get("publishedDate"),
                    "source": entry.get("site") or "FMP",
                    "score": round(score, 4),
                    "label": label,
                    "tickers": [str(entry.get("symbol")).upper()] if entry.get("symbol") else [],
                }
            )
        return out

    def _fetch_alpha_vantage(self, *, limit: int = 50, topics: str = DEFAULT_AV_TOPICS) -> list[dict[str, Any]]:
        if not self.alpha_vantage.is_configured():
            return []
        try:
            payload = self.alpha_vantage._request(
                f"av-news-topics:{topics}:{limit}",
                15 * 60,
                function="NEWS_SENTIMENT",
                topics=topics,
                sort="LATEST",
                limit=int(limit),
            )
        except Exception:
            logger.exception("news_hub_alpha_vantage_fetch_failed")
            return []
        feed = payload.get("feed") if isinstance(payload, dict) else None
        if not isinstance(feed, list):
            return []
        out: list[dict[str, Any]] = []
        for entry in feed[:limit]:
            if not isinstance(entry, dict):
                continue
            title = (entry.get("title") or "").strip()
            summary = (entry.get("summary") or "").strip()
            if not title:
                continue
            try:
                score = float(entry.get("overall_sentiment_score") or 0.0)
            except (TypeError, ValueError):
                score = analyze_sentiment_basic(f"{title} {summary}".strip())
            raw_label = str(entry.get("overall_sentiment_label") or "").lower()
            if raw_label in {"bullish", "bearish", "neutral"}:
                label = raw_label
            else:
                label = "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral"
            tickers: list[str] = []
            for ticker_block in entry.get("ticker_sentiment", []) or []:
                if not isinstance(ticker_block, dict):
                    continue
                t = ticker_block.get("ticker")
                if t:
                    tickers.append(str(t).upper())
            out.append(
                {
                    "title": title,
                    "summary": summary[:600],
                    "url": entry.get("url"),
                    "timestamp": entry.get("time_published"),
                    "source": entry.get("source") or "Alpha Vantage",
                    "score": round(score, 4),
                    "label": label,
                    "tickers": sorted(set(tickers)),
                }
            )
        return out

    def _fetch_rss(self) -> list[dict[str, Any]]:
        try:
            items = get_rss_news_service().get_items()
        except Exception:
            logger.exception("news_hub_rss_fetch_failed")
            return []
        # RSS items are symbol-agnostic; we run a cheap regex over the
        # title to surface obvious tickers, but we don't try to validate
        # them against an asset directory unless one is wired in.
        for item in items:
            text = f"{item.get('title') or ''} {item.get('summary') or ''}"
            tickers = self._extract_tickers(text)
            item["tickers"] = tickers
        return items

    def _extract_tickers(self, text: str) -> list[str]:
        """Pull obvious `$AAPL`-style tickers from the text. Falls back
        to plain uppercase words 1-5 chars when no `$` present, but
        only validates against `symbol_directory` if one is wired in
        (otherwise the risk of `THE`/`AND`/`USD` matching is too high
        and we just trust `$`-prefixed mentions)."""
        if not text:
            return []
        seen: set[str] = set()
        for match in re.finditer(r"\$([A-Z]{1,5})\b", text):
            seen.add(match.group(1))
        if self.symbol_directory and len(seen) == 0:
            for match in re.finditer(r"\b([A-Z]{2,5})\b", text):
                token = match.group(1)
                try:
                    if self.symbol_directory(token):
                        seen.add(token)
                except Exception:
                    continue
        return sorted(seen)

    def get_global_feed(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        sources: list[str] | None = None,
        sentiment: str | None = None,
        since: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        cache_key = self._cache_key(sources=tuple(sources) if sources else None)
        cached = self._cache.get(cache_key)
        if cached and cached["expires_at"] > monotonic():
            items = deepcopy(cached["value"])
        else:
            items: list[dict[str, Any]] = []
            requested = set(s.lower() for s in sources or [])
            if not requested or "fmp" in requested:
                items.extend(self._fetch_fmp())
            if not requested or "alpha_vantage" in requested:
                items.extend(self._fetch_alpha_vantage())
            if not requested or "rss" in requested:
                items.extend(self._fetch_rss())
            items = self._dedupe_and_sort(items)
            self._cache[cache_key] = {
                "expires_at": monotonic() + NEWS_HUB_CACHE_TTL_SECONDS,
                "value": deepcopy(items),
            }

        filtered = items
        if sentiment in {"bullish", "bearish", "neutral"}:
            filtered = [i for i in filtered if i.get("label") == sentiment]
        if since:
            try:
                since_dt = self._parse_timestamp(since)
            except Exception:
                since_dt = None
            if since_dt:
                filtered = [
                    i for i in filtered
                    if (ts := self._parse_timestamp(i.get("timestamp")))
                    and ts >= since_dt
                ]
        if symbol:
            target = symbol.upper()
            filtered = [i for i in filtered if target in (i.get("tickers") or [])]

        total = len(filtered)
        sliced = filtered[max(0, offset): max(0, offset) + max(1, limit)]
        return {
            "items": sliced,
            "total": total,
            "limit": limit,
            "offset": offset,
            "sources": sorted({i.get("source") for i in items if i.get("source")}),
        }

    def _dedupe_and_sort(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for item in items:
            key = item.get("url") or f"{item.get('source')}::{item.get('title')}"
            if not key or key in seen:
                continue
            seen[key] = item

        def _sort_key(entry: dict[str, Any]) -> str:
            ts = self._parse_timestamp(entry.get("timestamp"))
            if ts:
                return ts.isoformat()
            return ""

        return sorted(seen.values(), key=_sort_key, reverse=True)

    @staticmethod
    def _parse_timestamp(raw: Any) -> datetime | None:
        if not raw:
            return None
        text = str(raw).strip()
        for fmt in (None, "%Y%m%dT%H%M%S", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
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


_singleton: NewsHubService | None = None


def get_news_hub_service() -> NewsHubService:
    global _singleton
    if _singleton is None:
        _singleton = NewsHubService()
    return _singleton
