"""StockTwits + Reddit social-sentiment adapter tests.

`requests.get` is stubbed so no real network traffic happens. Verifies
the symbol translation, payload aggregation, the 24h-vs-7d trend math,
and the cache.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.social_sentiment_service import (  # noqa: E402
    SocialSentimentService,
    _reddit_query,
    _stocktwits_symbol,
)


def _response(payload, status: int = 200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


def _http_error(status: int):
    import requests as real_requests

    response = MagicMock()
    response.status_code = status
    response.raise_for_status = MagicMock(
        side_effect=real_requests.HTTPError(f"{status}", response=response)
    )
    response.json = MagicMock(return_value={})
    return response


def _stocktwits_payload(messages):
    return {"messages": messages}


def _reddit_payload(posts):
    return {
        "data": {
            "children": [{"data": post} for post in posts],
        }
    }


class SocialSentimentServiceTests(unittest.TestCase):
    def test_stocktwits_symbol_handles_crypto(self):
        self.assertEqual("AAPL", _stocktwits_symbol("AAPL"))
        self.assertEqual("BTC.X", _stocktwits_symbol("BTC/USD"))
        self.assertEqual("", _stocktwits_symbol(""))

    def test_reddit_query_collapses_pair(self):
        self.assertEqual("AAPL", _reddit_query("aapl"))
        self.assertEqual("BTC", _reddit_query("BTC/USD"))

    def test_get_social_signal_aggregates_stocktwits_and_reddit(self):
        service = SocialSentimentService()
        st_messages = [
            {
                "body": "Stock surges, excellent quarterly results",
                "entities": {"sentiment": {"basic": "Bullish"}},
                "id": 1,
                "user": {"username": "alice", "avatar_url": "https://x"},
                "created_at": "2026-05-08T10:00:00Z",
            },
            {
                "body": "Terrible quarter, fraud allegations",
                "entities": {"sentiment": {"basic": "Bearish"}},
                "id": 2,
                "user": {"username": "bob", "avatar_url": "https://y"},
                "created_at": "2026-05-08T09:00:00Z",
            },
        ]
        # Reddit search.json returns the standard Reddit envelope; the
        # service issues the request once per subreddit, in this case
        # three times for stocks (wallstreetbets/stocks/investing) per
        # timeframe ("day" and "week").
        day_posts = [
            {
                "title": "Earnings beat estimates by a wide margin",
                "selftext": "Stock soars on excellent results",
                "score": 200,
                "num_comments": 30,
                "subreddit": "wallstreetbets",
                "permalink": "/r/wallstreetbets/p/123",
            }
        ]
        week_posts = day_posts * 6  # 6 posts in the 6-day baseline window

        response_queue = []
        # 1 StockTwits call
        response_queue.append(_response(_stocktwits_payload(st_messages)))
        # 3 reddit calls for "day", then 3 for "week"
        for _ in range(3):
            response_queue.append(_response(_reddit_payload(day_posts[:1])))
        for _ in range(3):
            response_queue.append(_response(_reddit_payload(week_posts[:2])))

        responses = iter(response_queue)
        with patch("app.social_sentiment_service.acquire_rate_limit", return_value=True), patch(
            "app.social_sentiment_service.requests.get",
            side_effect=lambda *a, **kw: next(responses),
        ):
            payload = service.get_social_signal("AAPL", asset_class="stock")

        self.assertEqual(2, payload["stocktwits"]["messageCount"])
        self.assertEqual(1, payload["stocktwits"]["bullishCount"])
        self.assertEqual(1, payload["stocktwits"]["bearishCount"])
        self.assertIsNotNone(payload["stocktwits"]["avgVaderScore"])

        # Reddit aggregates 1 post per subreddit -> 3 day, 6 week
        self.assertEqual(3, payload["reddit"]["mentionCount24h"])
        self.assertEqual(6, payload["reddit"]["mentionCount7d"])
        self.assertEqual(["wallstreetbets", "stocks", "investing"], payload["reddit"]["subreddits"])
        # baseline_7d = 6 - 3 = 3 over 6 days = 0.5/day; trend = (3 - 0.5) / 0.5 * 100 = 500
        self.assertAlmostEqual(500.0, payload["reddit"]["mentionTrendPct"])

        self.assertEqual(5, payload["combined"]["totalMessages"])
        self.assertIsNotNone(payload["combined"]["avgSentiment"])

    def test_crypto_uses_crypto_subreddits(self):
        service = SocialSentimentService()
        # 1 ST + 6 Reddit (3 crypto subs x 2 timeframes)
        responses = iter(
            [_response(_stocktwits_payload([]))]
            + [_response(_reddit_payload([])) for _ in range(6)]
        )
        with patch("app.social_sentiment_service.acquire_rate_limit", return_value=True), patch(
            "app.social_sentiment_service.requests.get",
            side_effect=lambda *a, **kw: next(responses),
        ):
            payload = service.get_social_signal("BTC/USD", asset_class="crypto")
        self.assertEqual(["CryptoCurrency", "Bitcoin", "ethereum"], payload["reddit"]["subreddits"])
        self.assertEqual("BTC.X", payload["stocktwits"]["symbol"])

    def test_stocktwits_404_returns_empty_block(self):
        service = SocialSentimentService()
        responses = iter(
            [_http_error(404)]
            + [_response(_reddit_payload([])) for _ in range(6)]
        )
        with patch("app.social_sentiment_service.acquire_rate_limit", return_value=True), patch(
            "app.social_sentiment_service.requests.get",
            side_effect=lambda *a, **kw: next(responses),
        ):
            payload = service.get_social_signal("UNKNOWN", asset_class="stock")
        self.assertEqual(0, payload["stocktwits"]["messageCount"])

    def test_reddit_all_failures_returns_zero_payload(self):
        service = SocialSentimentService()
        responses = iter(
            [_response(_stocktwits_payload([]))]
            + [_http_error(429) for _ in range(6)]
        )
        with patch("app.social_sentiment_service.acquire_rate_limit", return_value=True), patch(
            "app.social_sentiment_service.requests.get",
            side_effect=lambda *a, **kw: next(responses),
        ):
            payload = service.get_social_signal("AAPL", asset_class="stock")
        # All reddit subs failed → mentionCount stays 0, subreddits hint preserved
        self.assertEqual(0, payload["reddit"]["mentionCount24h"])
        self.assertEqual(["wallstreetbets", "stocks", "investing"], payload["reddit"]["subreddits"])

    def test_cache_hits_avoid_second_request(self):
        service = SocialSentimentService()
        # First call uses 7 responses
        first_round = (
            [_response(_stocktwits_payload([]))]
            + [_response(_reddit_payload([])) for _ in range(6)]
        )
        responses = iter(first_round)
        with patch("app.social_sentiment_service.acquire_rate_limit", return_value=True), patch(
            "app.social_sentiment_service.requests.get",
            side_effect=lambda *a, **kw: next(responses),
        ) as get_mock:
            service.get_social_signal("AAPL", asset_class="stock")
            calls_after_first = get_mock.call_count
            service.get_social_signal("AAPL", asset_class="stock")
            calls_after_second = get_mock.call_count
        self.assertEqual(calls_after_first, calls_after_second)


if __name__ == "__main__":
    unittest.main()
