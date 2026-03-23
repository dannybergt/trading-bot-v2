from datetime import datetime, timezone
import unittest

from app.watchlist_alerts import build_watchlist_alert, summarize_watchlist_alerts


class _FakeILoc:
    def __init__(self, row):
        self._row = row

    def __getitem__(self, index):
        return self._row


class _FakeFrame:
    def __init__(self, row):
        self.empty = False
        self.iloc = _FakeILoc(row)


class WatchlistAlertTests(unittest.TestCase):
    def test_build_watchlist_alert_prioritizes_signal_news_and_tags(self):
        tracked_asset = {
            "symbol": "BTC/USD",
            "name": "Bitcoin",
            "tags": ["priority", "swing"],
            "assetClass": "crypto",
            "assetLabel": "Crypto",
            "market": "crypto",
            "exchange": "CRYPTO",
            "type": "CRYPTO",
            "isCrypto": True,
        }
        analysis_result = {
            "prediction": {
                "direction": "UP",
                "confidence": 0.87,
                "expected_yield_pct": 12.4,
                "required_yield_pct": 4.1,
                "reason": "BUY setup cleared",
            },
            "data": _FakeFrame({"Close": 123.4567}),
        }
        news_payload = {
            "aggregate_score": 0.41,
            "aggregate_label": "bullish",
            "items": [
                {
                    "title": "Bitcoin extends breakout",
                    "summary": "Momentum and liquidity improve.",
                    "score": 0.41,
                    "label": "bullish",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "url": "https://example.com/news/bitcoin-breakout",
                    "source": "Example Wire",
                }
            ],
        }

        alert = build_watchlist_alert(tracked_asset, analysis_result, news_payload, news_limit=1)

        self.assertEqual(alert["symbol"], "BTC/USD")
        self.assertEqual(alert["alertType"], "signal")
        self.assertEqual(alert["priorityLabel"], "high")
        self.assertGreaterEqual(alert["priorityScore"], 70)
        self.assertIn("buy-signal", alert["matches"])
        self.assertIn("news-support", alert["matches"])
        self.assertIn("tag:priority", alert["matches"])
        self.assertEqual(alert["signal"]["expectedYieldPct"], 12.4)
        self.assertEqual(alert["signal"]["requiredYieldPct"], 4.1)
        self.assertEqual(alert["news"]["itemCount"], 1)
        self.assertEqual(len(alert["news"]["headlines"]), 1)

    def test_summarize_watchlist_alerts_counts_priority_and_signal_types(self):
        items = [
            {
                "priorityLabel": "high",
                "alertType": "signal",
                "signal": {"direction": "UP"},
            },
            {
                "priorityLabel": "medium",
                "alertType": "news",
                "signal": {"direction": "DOWN"},
            },
            {
                "priorityLabel": "low",
                "alertType": "watchlist",
                "signal": {"direction": "HOLD"},
            },
        ]

        summary = summarize_watchlist_alerts(items)

        self.assertEqual(summary["alertItems"], 3)
        self.assertEqual(summary["highPriority"], 1)
        self.assertEqual(summary["mediumPriority"], 1)
        self.assertEqual(summary["lowPriority"], 1)
        self.assertEqual(summary["signalAlerts"], 1)
        self.assertEqual(summary["newsAlerts"], 1)
        self.assertEqual(summary["buySignals"], 1)
        self.assertEqual(summary["sellSignals"], 1)


if __name__ == "__main__":
    unittest.main()
