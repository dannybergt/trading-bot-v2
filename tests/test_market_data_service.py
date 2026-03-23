import unittest
from unittest.mock import patch

import pandas as pd

from app.services import MarketDataService


class _FakePredictor:
    def train(self, df):
        self.last_train_size = len(df.index)

    def predict_next_movement(self, df):
        return {"direction": "HOLD", "confidence": 0.0}


class _FakeAlpaca:
    def __init__(self):
        self.news_calls = []

    def get_news(self, symbol, limit=15):
        self.news_calls.append((symbol, limit))
        return [
            {
                "headline": "ETF inflows rise",
                "summary": "Flows stay constructive.",
                "created_at": "2026-03-23T12:00:00Z",
                "url": "https://example.com/etf-inflows",
                "source": "Example Wire",
            }
        ]

    def get_all_assets(self):
        return []

    def get_bars_df(self, symbol, timeframe="1Day", limit=100):
        return pd.DataFrame()


class MarketDataServiceTests(unittest.TestCase):
    def test_get_ticker_info_skips_yfinance_for_crypto(self):
        service = MarketDataService()

        with patch("app.services.yf.Ticker") as ticker_ctor:
            payload = service.get_ticker_info("BTC/USD", asset_profile={"isCrypto": True})

        ticker_ctor.assert_not_called()
        self.assertEqual(payload, {})

    def test_get_ticker_info_caches_non_crypto_lookup(self):
        service = MarketDataService()

        with patch("app.services.yf.Ticker") as ticker_ctor:
            ticker_ctor.return_value.info = {"quoteType": "ETF", "shortName": "Vanguard S&P 500 ETF"}
            first = service.get_ticker_info("VOO", asset_profile={"isCrypto": False})
            second = service.get_ticker_info("VOO", asset_profile={"isCrypto": False})

        self.assertEqual(ticker_ctor.call_count, 1)
        self.assertEqual(first["quoteType"], "ETF")
        self.assertEqual(second["shortName"], "Vanguard S&P 500 ETF")

    def test_get_market_news_uses_cache(self):
        alpaca = _FakeAlpaca()
        service = MarketDataService(alpaca)

        with patch(
            "app.services.analyze_news",
            return_value=[
                {
                    "title": "ETF inflows rise",
                    "summary": "Flows stay constructive.",
                    "score": 0.4,
                    "label": "bullish",
                    "timestamp": "2026-03-23T12:00:00Z",
                    "url": "https://example.com/etf-inflows",
                    "source": "Example Wire",
                }
            ],
        ):
            first = service.get_market_news("QQQ", limit=5)
            first["items"][0]["title"] = "mutated"
            second = service.get_market_news("QQQ", limit=5)

        self.assertEqual(alpaca.news_calls, [("QQQ", 5)])
        self.assertEqual(second["items"][0]["title"], "ETF inflows rise")
        self.assertEqual(second["aggregate_label"], "bullish")

    def test_get_stock_data_can_skip_news_and_fundamentals(self):
        service = MarketDataService()
        service.predictor = _FakePredictor()

        with patch.object(service, "get_market_news", return_value={}) as news_mock, patch.object(
            service,
            "get_ticker_info",
            return_value={"trailingPE": 21.5},
        ) as ticker_info_mock:
            payload = service.get_stock_data(
                "BTC/USD",
                period="1mo",
                interval="1d",
                include_news=False,
                include_fundamentals=False,
            )

        news_mock.assert_not_called()
        ticker_info_mock.assert_not_called()
        self.assertEqual(payload["asset"]["assetClass"], "crypto")
        self.assertEqual(payload["info"]["trailingPE"], 0.0)
        self.assertEqual(payload["info"]["assetClass"], "crypto")


if __name__ == "__main__":
    unittest.main()
