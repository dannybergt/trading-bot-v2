"""Retail-sentiment adapter: StockTwits + Reddit.

Two free, no-auth feeds bundled into one payload:

- **StockTwits** `/streams/symbol/{SYMBOL}.json` — public message stream
  with each author's self-tagged Bullish/Bearish sentiment plus the body
  text we run through our existing VADER scorer.

- **Reddit public search** `/r/{sub}/search.json?q={symbol}&restrict_sr=1`
  — the same JSON the Reddit web app uses. No OAuth (and no PRAW
  dependency) as long as we send a stable User-Agent header. Searches
  the symbol in finance-relevant subreddits and aggregates mention
  count, VADER-averaged sentiment, and a 24h-vs-7d trend.

Both adapters are cached at the module level so repeated analysis-page
loads don't hammer the upstreams. Failures fall through to empty
payloads with structured logging — never raise into the request path.
"""
from __future__ import annotations

import logging
import os
from copy import deepcopy
from time import monotonic
from typing import Any

import requests

from app.rate_limit import acquire as acquire_rate_limit
from app.sentiment import analyze_sentiment_basic

logger = logging.getLogger(__name__)

STOCKTWITS_BASE_URL = "https://api.stocktwits.com/api/2"
REDDIT_BASE_URL = "https://www.reddit.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
SOCIAL_CACHE_TTL_SECONDS = 30 * 60
REDDIT_USER_AGENT = os.getenv(
    "REDDIT_USER_AGENT", "trading-bot-v2/1.0 (+https://github.com/dannybergt/trading-bot-v2)"
)

STOCK_SUBREDDITS = ["wallstreetbets", "stocks", "investing"]
CRYPTO_SUBREDDITS = ["CryptoCurrency", "Bitcoin", "ethereum"]


def _stocktwits_symbol(symbol: str) -> str:
    """`AAPL` -> `AAPL`, `BTC/USD` -> `BTC.X` (StockTwits crypto convention)."""
    if not symbol:
        return ""
    upper = symbol.upper().strip()
    if "/" in upper:
        base = upper.split("/", 1)[0]
        return f"{base}.X"
    return upper


def _reddit_query(symbol: str) -> str:
    """`AAPL` stays as is; `BTC/USD` collapses to `BTC` for the search query."""
    if not symbol:
        return ""
    upper = symbol.upper().strip()
    if "/" in upper:
        return upper.split("/", 1)[0]
    return upper


class SocialSentimentService:
    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def get_social_signal(self, symbol: str, *, asset_class: str | None = None) -> dict[str, Any]:
        """Aggregate StockTwits + Reddit into one payload.

        Cache key is the canonical symbol. Asset-class only changes
        which subreddits Reddit searches; StockTwits handles the symbol
        translation itself.
        """
        if not symbol:
            return _empty_payload()

        cache_key = symbol.upper()
        cached = self._cache.get(cache_key)
        if cached and cached["expires_at"] > monotonic():
            return deepcopy(cached["value"])

        stocktwits = self._fetch_stocktwits(symbol)
        reddit = self._fetch_reddit(symbol, asset_class)

        payload = {
            "stocktwits": stocktwits,
            "reddit": reddit,
            "combined": {
                "totalMessages": (stocktwits.get("messageCount") or 0)
                + (reddit.get("mentionCount24h") or 0),
                "avgSentiment": _weighted_avg_sentiment(stocktwits, reddit),
            },
        }
        self._cache[cache_key] = {
            "expires_at": monotonic() + SOCIAL_CACHE_TTL_SECONDS,
            "value": payload,
        }
        return deepcopy(payload)

    def _fetch_stocktwits(self, symbol: str) -> dict[str, Any]:
        empty = {
            "symbol": _stocktwits_symbol(symbol),
            "messageCount": 0,
            "bullishCount": 0,
            "bearishCount": 0,
            "neutralCount": 0,
            "avgVaderScore": None,
            "topPosts": [],
        }
        if not acquire_rate_limit("stocktwits", timeout=2.0):
            logger.warning("stocktwits_rate_limit_skip symbol=%s", symbol)
            return empty

        try:
            response = requests.get(
                f"{STOCKTWITS_BASE_URL}/streams/symbol/{empty['symbol']}.json",
                timeout=DEFAULT_TIMEOUT_SECONDS,
                headers={"accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "n/a"
            # StockTwits returns 404 for unknown symbols and 429 when
            # they don't like the IP. Either way we surface zero data.
            logger.info("stocktwits_http_skip symbol=%s status=%s", symbol, status)
            return empty
        except requests.RequestException:
            logger.exception("stocktwits_request_failed symbol=%s", symbol)
            return empty
        except ValueError:
            logger.exception("stocktwits_invalid_json symbol=%s", symbol)
            return empty

        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(messages, list):
            return empty

        bullish = 0
        bearish = 0
        neutral = 0
        scores: list[float] = []
        top_posts: list[dict[str, Any]] = []
        for msg in messages[:30]:
            if not isinstance(msg, dict):
                continue
            body = str(msg.get("body") or "")
            entities = msg.get("entities") or {}
            sentiment = (entities.get("sentiment") or {}) if isinstance(entities, dict) else {}
            tag = str(sentiment.get("basic") or "").lower() if isinstance(sentiment, dict) else ""
            vader = analyze_sentiment_basic(body) if body else 0.0
            scores.append(vader)
            if tag == "bullish":
                bullish += 1
            elif tag == "bearish":
                bearish += 1
            else:
                neutral += 1
            if len(top_posts) < 5 and body:
                top_posts.append(
                    {
                        "body": body[:280],
                        "created": msg.get("created_at"),
                        "tag": tag or None,
                        "vader": round(vader, 4),
                        "url": (
                            msg.get("user", {}).get("avatar_url") and
                            f"https://stocktwits.com/{msg.get('user', {}).get('username')}/message/{msg.get('id')}"
                        )
                        if isinstance(msg.get("user"), dict)
                        else None,
                    }
                )

        return {
            "symbol": empty["symbol"],
            "messageCount": len(messages),
            "bullishCount": bullish,
            "bearishCount": bearish,
            "neutralCount": neutral,
            "avgVaderScore": round(sum(scores) / len(scores), 4) if scores else None,
            "topPosts": top_posts,
        }

    def _fetch_reddit(self, symbol: str, asset_class: str | None) -> dict[str, Any]:
        empty = {
            "query": _reddit_query(symbol),
            "subreddits": [],
            "mentionCount24h": 0,
            "mentionCount7d": 0,
            "mentionTrendPct": None,
            "avgSentiment": None,
            "topPosts": [],
        }
        query = _reddit_query(symbol)
        if not query:
            return empty
        subreddits = CRYPTO_SUBREDDITS if (asset_class or "").lower() == "crypto" else STOCK_SUBREDDITS
        empty["subreddits"] = subreddits

        day_posts = self._reddit_search(query, subreddits, timeframe="day")
        week_posts = self._reddit_search(query, subreddits, timeframe="week")
        if day_posts is None and week_posts is None:
            # Both probes failed — surface a zero payload but keep the
            # subreddits hint so the UI can show what was attempted.
            return empty

        day_posts = day_posts or []
        week_posts = week_posts or []
        # 7d baseline excluding the latest 24h to make the trend
        # comparison meaningful (raw 7d would always include 24h).
        baseline_7d = max(0, len(week_posts) - len(day_posts))
        trend_pct: float | None = None
        if baseline_7d > 0:
            # Project 7d baseline to a 24h average so the comparison
            # apples-to-apples. baseline_7d covers ~6 days here.
            avg_per_day = baseline_7d / 6
            if avg_per_day > 0:
                trend_pct = (len(day_posts) - avg_per_day) / avg_per_day * 100.0

        scores: list[float] = []
        top_posts: list[dict[str, Any]] = []
        for post in day_posts[:30]:
            title = str(post.get("title") or "")
            selftext = str(post.get("selftext") or "")
            text = f"{title}\n{selftext}".strip()
            if not text:
                continue
            score = analyze_sentiment_basic(text)
            scores.append(score)
            if len(top_posts) < 5:
                top_posts.append(
                    {
                        "title": title[:200],
                        "score": post.get("score"),
                        "comments": post.get("num_comments"),
                        "subreddit": post.get("subreddit"),
                        "permalink": (
                            f"https://www.reddit.com{post['permalink']}"
                            if post.get("permalink")
                            else None
                        ),
                        "vader": round(score, 4),
                    }
                )

        return {
            "query": query,
            "subreddits": subreddits,
            "mentionCount24h": len(day_posts),
            "mentionCount7d": len(week_posts),
            "mentionTrendPct": round(trend_pct, 2) if trend_pct is not None else None,
            "avgSentiment": round(sum(scores) / len(scores), 4) if scores else None,
            "topPosts": top_posts,
        }

    def _reddit_search(
        self, query: str, subreddits: list[str], *, timeframe: str
    ) -> list[dict[str, Any]] | None:
        """Run the same search across multiple subreddits and merge.

        Returns None when every probe failed (so the caller can tell
        partial-data apart from genuinely-empty data). Each individual
        subreddit failure logs and continues.
        """
        results: list[dict[str, Any]] = []
        any_success = False
        for sub in subreddits:
            if not acquire_rate_limit("reddit", timeout=2.0):
                logger.warning("reddit_rate_limit_skip sub=%s", sub)
                continue
            try:
                response = requests.get(
                    f"{REDDIT_BASE_URL}/r/{sub}/search.json",
                    params={
                        "q": query,
                        "restrict_sr": 1,
                        "t": timeframe,
                        "limit": 25,
                        "sort": "new",
                    },
                    headers={
                        "accept": "application/json",
                        "user-agent": REDDIT_USER_AGENT,
                    },
                    timeout=DEFAULT_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                payload = response.json()
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "n/a"
                logger.info("reddit_http_skip sub=%s status=%s", sub, status)
                continue
            except requests.RequestException:
                logger.exception("reddit_request_failed sub=%s", sub)
                continue
            except ValueError:
                logger.exception("reddit_invalid_json sub=%s", sub)
                continue
            any_success = True
            children = (
                (payload.get("data") or {}).get("children")
                if isinstance(payload, dict)
                else None
            )
            if not isinstance(children, list):
                continue
            for child in children:
                data = child.get("data") if isinstance(child, dict) else None
                if isinstance(data, dict):
                    results.append(data)
        return results if any_success else None


def _weighted_avg_sentiment(stocktwits: dict[str, Any], reddit: dict[str, Any]) -> float | None:
    """Weight each source's score by its message count so a quiet
    source doesn't drown out a noisy one with a single outlier post.
    """
    pieces: list[tuple[float, int]] = []
    if stocktwits.get("avgVaderScore") is not None and stocktwits.get("messageCount"):
        pieces.append((float(stocktwits["avgVaderScore"]), int(stocktwits["messageCount"])))
    if reddit.get("avgSentiment") is not None and reddit.get("mentionCount24h"):
        pieces.append((float(reddit["avgSentiment"]), int(reddit["mentionCount24h"])))
    if not pieces:
        return None
    total_weight = sum(weight for _, weight in pieces)
    if total_weight == 0:
        return None
    weighted = sum(score * weight for score, weight in pieces) / total_weight
    return round(weighted, 4)


def _empty_payload() -> dict[str, Any]:
    return {
        "stocktwits": {
            "symbol": "",
            "messageCount": 0,
            "bullishCount": 0,
            "bearishCount": 0,
            "neutralCount": 0,
            "avgVaderScore": None,
            "topPosts": [],
        },
        "reddit": {
            "query": "",
            "subreddits": [],
            "mentionCount24h": 0,
            "mentionCount7d": 0,
            "mentionTrendPct": None,
            "avgSentiment": None,
            "topPosts": [],
        },
        "combined": {"totalMessages": 0, "avgSentiment": None},
    }


_singleton: SocialSentimentService | None = None


def get_social_sentiment_service() -> SocialSentimentService:
    global _singleton
    if _singleton is None:
        _singleton = SocialSentimentService()
    return _singleton
