from datetime import datetime, timezone
import unittest

from app.watchlist_alerts import (
    build_watchlist_alert,
    build_watchlist_alert_delivery_key,
    summarize_watchlist_alerts,
)


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
            "provider": {
                "status": "live",
                "source": "Alpha Vantage",
                "assetClass": "crypto",
                "lastUpdated": "2026-03-26T12:00:00Z",
                "quote": {
                    "price": 71234.5,
                    "changePercent": 2.4,
                    "currency": "USD",
                    "history": [{"close": 70000.0}, {"close": 71234.5}],
                },
                "research": {},
            },
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
        self.assertIn("provider-live", alert["matches"])
        self.assertIn("provider-move", alert["matches"])
        self.assertEqual(alert["signal"]["expectedYieldPct"], 12.4)
        self.assertEqual(alert["signal"]["requiredYieldPct"], 4.1)
        self.assertEqual(alert["news"]["itemCount"], 1)
        self.assertEqual(len(alert["news"]["headlines"]), 1)
        self.assertEqual(alert["providerContext"]["source"], "Alpha Vantage")
        self.assertEqual(alert["providerContext"]["status"], "live")
        self.assertEqual(alert["providerContext"]["changePercent"], 2.4)

    def test_summarize_watchlist_alerts_counts_priority_and_signal_types(self):
        items = [
            {
                "priorityLabel": "high",
                "alertType": "signal",
                "signal": {"direction": "UP"},
                "notification": {"popupEligible": True, "pushEligible": True},
                "providerContext": {
                    "status": "live",
                    "source": "Alpha Vantage",
                    "researchAvailable": True,
                    "changePercent": 1.2,
                },
            },
            {
                "priorityLabel": "medium",
                "alertType": "news",
                "signal": {"direction": "DOWN"},
                "notification": {"popupEligible": False, "pushEligible": False},
                "providerContext": {
                    "status": "partial",
                    "source": "Alpha Vantage",
                    "researchAvailable": False,
                    "changePercent": 0.2,
                },
            },
            {
                "priorityLabel": "low",
                "alertType": "watchlist",
                "signal": {"direction": "HOLD"},
                "notification": {"popupEligible": False, "pushEligible": False},
                "providerContext": {
                    "status": "unavailable",
                    "source": "Alpha Vantage",
                    "researchAvailable": False,
                    "changePercent": None,
                },
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
        self.assertEqual(summary["providerLive"], 1)
        self.assertEqual(summary["providerPartial"], 1)
        self.assertEqual(summary["providerUnavailable"], 1)
        self.assertEqual(summary["providerResearch"], 1)
        self.assertEqual(summary["providerMovers"], 1)

    def test_delivery_key_is_stable_for_same_alert_state(self):
        alert_item = {
            "symbol": "VOO",
            "alertType": "signal",
            "priorityLabel": "high",
            "priorityScore": 82,
            "signal": {"direction": "UP", "confidence": 0.871},
            "news": {"aggregateLabel": "bullish", "latestTimestamp": "2026-05-05T12:00:00+00:00"},
            "providerContext": {"status": "live", "changePercent": 1.2},
        }
        same_alert_item = {
            **alert_item,
            "signal": {"direction": "UP", "confidence": 0.874},
        }
        changed_alert_item = {
            **alert_item,
            "priorityScore": 65,
            "priorityLabel": "medium",
        }

        self.assertEqual(
            build_watchlist_alert_delivery_key(alert_item),
            build_watchlist_alert_delivery_key(same_alert_item),
        )
        self.assertNotEqual(
            build_watchlist_alert_delivery_key(alert_item),
            build_watchlist_alert_delivery_key(changed_alert_item),
        )


if __name__ == "__main__":
    unittest.main()
