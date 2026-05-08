"""Discovery-engine tests.

Drives the service against stubbed news-hub + FMP responses so the
suite stays offline. Verifies trending aggregation math, insider-
cluster detection, and the mover-normalisation pipeline.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


def _now_iso(offset_hours: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=offset_hours)).isoformat()


class DiscoveryServiceTests(unittest.TestCase):
    def setUp(self):
        from app.discovery_service import DiscoveryService

        self.fmp = MagicMock()
        self.fmp.configured = True
        self.service = DiscoveryService(fmp_service=self.fmp)
        self.service._cache.clear()

    def _stub_news_feed(self, items):
        from app import discovery_service

        return patch.object(
            discovery_service,
            "get_news_hub_service",
            return_value=MagicMock(
                get_global_feed=MagicMock(return_value={"items": items}),
            ),
        )

    def test_trending_ranks_by_mention_count_with_trend_and_burst(self):
        items = [
            # Recent window (4h ago) — AAPL +3 mentions, NVDA +2
            {"timestamp": _now_iso(-4), "tickers": ["AAPL"], "score": 0.6},
            {"timestamp": _now_iso(-5), "tickers": ["AAPL"], "score": 0.5},
            {"timestamp": _now_iso(-6), "tickers": ["AAPL"], "score": 0.4},
            {"timestamp": _now_iso(-3), "tickers": ["NVDA"], "score": 0.3},
            {"timestamp": _now_iso(-2), "tickers": ["NVDA"], "score": 0.2},
            # Baseline window (4 days ago) — AAPL +1, NVDA +0
            {"timestamp": _now_iso(-96), "tickers": ["AAPL"], "score": -0.1},
        ]
        with self._stub_news_feed(items):
            trending = self.service.get_trending_symbols(window_hours=24, baseline_hours=168, limit=5)

        symbols_in_order = [row["symbol"] for row in trending]
        self.assertEqual(["AAPL", "NVDA"], symbols_in_order)
        aapl = trending[0]
        self.assertEqual(3, aapl["mentionCountRecent"])
        self.assertEqual(1, aapl["mentionCountBaseline"])
        # Avg recent sentiment = (0.6+0.5+0.4)/3 = 0.5; baseline -0.1
        self.assertAlmostEqual(0.5, aapl["avgSentimentRecent"], places=4)
        self.assertAlmostEqual(0.6, aapl["sentimentBurst"], places=4)
        # Trend percent: baseline projected = 1 / (168-24) * 24 ≈ 0.1667
        # so (3 - 0.1667) / 0.1667 * 100 ≈ 1700%
        self.assertGreater(aapl["mentionTrendPct"], 500)

    def test_trending_handles_empty_feed(self):
        with self._stub_news_feed([]):
            trending = self.service.get_trending_symbols()
        self.assertEqual([], trending)

    def test_top_movers_normalizes_fmp_payload(self):
        self.fmp.get_market_movers.return_value = {
            "gainers": [
                {
                    "symbol": "abcd",
                    "name": "ABCD Inc",
                    "price": "150.10",
                    "change": "+5.20",
                    "changesPercentage": "+5.20%",
                }
            ],
            "losers": [],
            "actives": [
                {
                    "symbol": "EFGH",
                    "name": "EFGH Corp",
                    "price": 80.0,
                    "change": -1.2,
                    "changesPercentage": -1.5,
                }
            ],
        }
        movers = self.service.get_top_movers()
        self.assertEqual("ABCD", movers["gainers"][0]["symbol"])
        self.assertAlmostEqual(150.10, movers["gainers"][0]["price"])
        # Percent string with %-suffix is parsed
        self.assertAlmostEqual(5.20, movers["gainers"][0]["changesPercentage"])
        self.assertEqual([], movers["losers"])
        self.assertEqual("EFGH", movers["actives"][0]["symbol"])

    def test_insider_clusters_require_min_unique_insiders(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        self.fmp.get_insider_trading_feed.return_value = [
            # AAPL — 3 distinct buyers within 90d → cluster
            {"symbol": "AAPL", "transactionDate": recent, "transactionType": "P-Purchase",
             "reportingName": "CEO Smith", "securitiesTransacted": 1000, "price": 200.0},
            {"symbol": "AAPL", "transactionDate": recent, "transactionType": "P-Purchase",
             "reportingName": "CFO Doe", "securitiesTransacted": 500, "price": 198.0},
            {"symbol": "AAPL", "transactionDate": recent, "transactionType": "P-Purchase",
             "reportingName": "Director Roe", "securitiesTransacted": 300, "price": 199.0},
            # MSFT — only 2 distinct buyers → does not cluster
            {"symbol": "MSFT", "transactionDate": recent, "transactionType": "P-Purchase",
             "reportingName": "CEO X", "securitiesTransacted": 1000, "price": 400.0},
            {"symbol": "MSFT", "transactionDate": recent, "transactionType": "P-Purchase",
             "reportingName": "CFO Y", "securitiesTransacted": 500, "price": 401.0},
        ]
        clusters = self.service.get_insider_clusters(lookback_days=90, min_unique_insiders=3)
        symbols = [c["symbol"] for c in clusters]
        self.assertEqual(["AAPL"], symbols)
        aapl = clusters[0]
        self.assertEqual(3, aapl["uniqueInsiders"])
        self.assertEqual("buy_cluster", aapl["direction"])
        # Net value = 1000*200 + 500*198 + 300*199 = 200000 + 99000 + 59700 = 358700
        self.assertAlmostEqual(358700.0, aapl["netValue"])

    def test_insider_clusters_excludes_old_filings(self):
        old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        self.fmp.get_insider_trading_feed.return_value = [
            {"symbol": "AAPL", "transactionDate": old, "transactionType": "P-Purchase",
             "reportingName": f"Insider {i}", "securitiesTransacted": 100, "price": 200}
            for i in range(5)
        ]
        clusters = self.service.get_insider_clusters(lookback_days=90, min_unique_insiders=3)
        self.assertEqual([], clusters)

    def test_dashboard_returns_three_blocks(self):
        self.fmp.get_market_movers.return_value = {"gainers": [], "losers": [], "actives": []}
        self.fmp.get_insider_trading_feed.return_value = []
        with self._stub_news_feed([]):
            dashboard = self.service.get_dashboard()
        self.assertIn("trending", dashboard)
        self.assertIn("topMovers", dashboard)
        self.assertIn("insiderClusters", dashboard)


if __name__ == "__main__":
    unittest.main()
