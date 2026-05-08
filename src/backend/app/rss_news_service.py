"""RSS-News-Adapter — feeds curated for the news-hub page.

Symbol-agnostic news (boerse.de, ariva.de, Reuters market headlines)
that we parse into the same item shape every other news provider in
the codebase already uses. The concrete feed list is intentionally
short and editable via the `RSS_NEWS_FEEDS` env var (semicolon-
separated `label|url` pairs) so an operator can add or swap feeds
without a redeploy.

Each item carries a VADER score so the news-hub feed can colour
sentiment without an extra round-trip to the sentiment service.
"""
from __future__ import annotations

import logging
import os
from copy import deepcopy
from time import monotonic
from typing import Any

import feedparser

from app.rate_limit import acquire as acquire_rate_limit
from app.sentiment import analyze_sentiment_basic

logger = logging.getLogger(__name__)

DEFAULT_FEEDS: list[dict[str, str]] = [
    {"label": "boerse.de", "url": "https://www.boerse.de/feeds/Boerse-de-News.xml"},
    {"label": "ariva.de", "url": "https://www.ariva.de/news/news.xml"},
    {"label": "Reuters Markets", "url": "https://www.reutersagency.com/feed/?best-topics=markets&post_type=best"},
]

RSS_CACHE_TTL_SECONDS = 5 * 60


def _parse_feed_env(raw: str | None) -> list[dict[str, str]] | None:
    if not raw:
        return None
    feeds: list[dict[str, str]] = []
    for token in raw.split(";"):
        token = token.strip()
        if not token:
            continue
        if "|" not in token:
            continue
        label, url = token.split("|", 1)
        label = label.strip()
        url = url.strip()
        if not label or not url:
            continue
        feeds.append({"label": label, "url": url})
    return feeds or None


class RssNewsService:
    def __init__(self, feeds: list[dict[str, str]] | None = None) -> None:
        configured = _parse_feed_env(os.getenv("RSS_NEWS_FEEDS"))
        self.feeds = feeds or configured or list(DEFAULT_FEEDS)
        self._cache: dict[str, dict[str, Any]] = {}

    def get_items(self, *, limit: int = 50) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for feed in self.feeds:
            label = feed.get("label") or "RSS"
            url = feed.get("url")
            if not url:
                continue
            cached = self._cache.get(url)
            if cached and cached["expires_at"] > monotonic():
                out.extend(deepcopy(cached["value"]))
                continue
            if not acquire_rate_limit("rss", timeout=2.0):
                logger.warning("rss_rate_limit_skip url=%s", url)
                continue
            try:
                parsed = feedparser.parse(url)
            except Exception:
                logger.exception("rss_parse_failed url=%s", url)
                continue
            entries = getattr(parsed, "entries", None) or []
            normalized = []
            for entry in entries[:limit]:
                title = (entry.get("title") or "").strip()
                summary = (entry.get("summary") or entry.get("description") or "").strip()
                link = entry.get("link") or entry.get("id")
                ts = (
                    entry.get("published")
                    or entry.get("updated")
                    or entry.get("pubDate")
                )
                text = f"{title} {summary}".strip()
                score = analyze_sentiment_basic(text) if text else 0.0
                label_sentiment = (
                    "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral"
                )
                normalized.append(
                    {
                        "title": title,
                        "summary": summary[:600],
                        "url": link,
                        "timestamp": ts,
                        "source": label,
                        "score": round(score, 4),
                        "label": label_sentiment,
                    }
                )
            self._cache[url] = {
                "expires_at": monotonic() + RSS_CACHE_TTL_SECONDS,
                "value": normalized,
            }
            out.extend(normalized)
        return out


_singleton: RssNewsService | None = None


def get_rss_news_service() -> RssNewsService:
    global _singleton
    if _singleton is None:
        _singleton = RssNewsService()
    return _singleton
