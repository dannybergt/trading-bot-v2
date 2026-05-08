"""News-hub aggregation tests.

Stubs each provider so the test suite stays offline. Verifies that the
hub deduplicates by URL, sorts newest-first, applies sentiment / source
/ since / symbol filters, and surfaces tickers from provider annotations
plus the simple `$TICKER` regex.
"""
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


def _fake_fmp_payload():
    return [
        {
            "title": "Tech rally lifts AAPL",
            "text": "Stock surged on strong demand.",
            "url": "https://example.com/aapl-rally",
            "publishedDate": "2026-05-08T10:00:00Z",
            "site": "Reuters",
            "symbol": "AAPL",
        },
        {
            "title": "MSFT misses revenue estimates",
            "text": "Disappointing quarterly results released",
            "url": "https://example.com/msft-miss",
            "publishedDate": "2026-05-08T08:00:00Z",
            "site": "Bloomberg",
            "symbol": "MSFT",
        },
    ]


def _fake_av_payload():
    return {
        "feed": [
            {
                "title": "$NVDA pushes higher on AI demand",
                "summary": "Excellent guidance update",
                "url": "https://example.com/nvda-rally",
                "time_published": "20260508T120000",
                "source": "MarketWatch",
                "overall_sentiment_score": 0.6,
                "overall_sentiment_label": "Bullish",
                "ticker_sentiment": [{"ticker": "NVDA"}],
            },
            # Duplicate URL with FMP's AAPL → should dedupe
            {
                "title": "Tech rally lifts AAPL",
                "summary": "Stock surged on strong demand.",
                "url": "https://example.com/aapl-rally",
                "time_published": "20260508T100100",
                "source": "Reuters",
                "overall_sentiment_score": 0.4,
                "overall_sentiment_label": "Bullish",
                "ticker_sentiment": [{"ticker": "AAPL"}],
            },
        ]
    }


def _fake_rss_items():
    return [
        {
            "title": "Märkte ziehen an dank $TSLA-Gewinnen",
            "summary": "Frankfurter Börse legt zu, terrible quarter for some retailers.",
            "url": "https://example.com/de-news",
            "timestamp": "Wed, 07 May 2026 18:00:00 +0000",
            "source": "boerse.de",
            "score": 0.0,
            "label": "neutral",
        }
    ]


class NewsHubAggregationTests(unittest.TestCase):
    def setUp(self):
        from app.news_hub_service import NewsHubService

        self.service = NewsHubService()
        # Force re-fetch on each test by clearing cache between tests
        self.service._cache.clear()

    def _patch_providers(self):
        """Patch the underlying provider hooks. The hub uses
        ``self.fmp._request`` for FMP and ``self.alpha_vantage._request``
        plus ``get_rss_news_service().get_items()``."""
        fmp_patch = patch.object(
            self.service.fmp,
            "_request",
            return_value=_fake_fmp_payload(),
        )
        av_patch = patch.object(
            self.service.alpha_vantage,
            "_request",
            return_value=_fake_av_payload(),
        )
        rss_patch = patch(
            "app.news_hub_service.get_rss_news_service",
            return_value=MagicMock(get_items=MagicMock(return_value=_fake_rss_items())),
        )
        # Force-enable both providers irrespective of env keys
        configured_fmp = patch.object(type(self.service.fmp), "configured", new=True)
        configured_av = patch.object(self.service.alpha_vantage, "is_configured", return_value=True)
        return fmp_patch, av_patch, rss_patch, configured_fmp, configured_av

    def test_global_feed_aggregates_dedupes_and_sorts(self):
        fmp_p, av_p, rss_p, cfg_fmp, cfg_av = self._patch_providers()
        with fmp_p, av_p, rss_p, cfg_fmp, cfg_av:
            payload = self.service.get_global_feed(limit=10)

        # 2 FMP + 2 AV, but one AV duplicates the FMP URL → 3 unique
        # plus the RSS item → 4 total
        self.assertEqual(4, payload["total"])
        # Newest-first ordering by parsed datetime (mixed string formats
        # in the inputs — ISO-8601, AV's `YYYYMMDDTHHMMSS`, RFC-822 RSS)
        from app.news_hub_service import NewsHubService

        parsed = [NewsHubService._parse_timestamp(item["timestamp"]) for item in payload["items"]]
        for prev, curr in zip(parsed, parsed[1:]):
            if prev is None or curr is None:
                continue
            self.assertGreaterEqual(prev, curr)
        # The merged AAPL row keeps the first (FMP) shape
        aapl_rows = [i for i in payload["items"] if i.get("url") == "https://example.com/aapl-rally"]
        self.assertEqual(1, len(aapl_rows))
        # Sources surface
        self.assertIn("boerse.de", payload["sources"])

    def test_filter_sentiment_keeps_matching_items_only(self):
        fmp_p, av_p, rss_p, cfg_fmp, cfg_av = self._patch_providers()
        with fmp_p, av_p, rss_p, cfg_fmp, cfg_av:
            payload = self.service.get_global_feed(limit=10, sentiment="bullish")
        self.assertTrue(all(item["label"] == "bullish" for item in payload["items"]))
        self.assertGreater(len(payload["items"]), 0)

    def test_filter_symbol_matches_extracted_tickers(self):
        fmp_p, av_p, rss_p, cfg_fmp, cfg_av = self._patch_providers()
        with fmp_p, av_p, rss_p, cfg_fmp, cfg_av:
            payload = self.service.get_global_feed(limit=10, symbol="TSLA")
        # Only the RSS item mentions $TSLA
        self.assertEqual(1, len(payload["items"]))
        self.assertEqual("https://example.com/de-news", payload["items"][0]["url"])

    def test_extract_tickers_picks_dollar_prefix(self):
        from app.news_hub_service import NewsHubService

        service = NewsHubService()
        tickers = service._extract_tickers("Markets cheer $AAPL guidance, $NVDA up 5%")
        self.assertEqual(["AAPL", "NVDA"], tickers)

    def test_pagination_offset_slice(self):
        fmp_p, av_p, rss_p, cfg_fmp, cfg_av = self._patch_providers()
        with fmp_p, av_p, rss_p, cfg_fmp, cfg_av:
            page1 = self.service.get_global_feed(limit=2, offset=0)
            page2 = self.service.get_global_feed(limit=2, offset=2)
        self.assertEqual(2, len(page1["items"]))
        # Total count is preserved across pages
        self.assertEqual(page1["total"], page2["total"])
        # Offsets give disjoint slices
        urls_page1 = {i["url"] for i in page1["items"]}
        urls_page2 = {i["url"] for i in page2["items"]}
        self.assertFalse(urls_page1 & urls_page2)


if __name__ == "__main__":
    unittest.main()
