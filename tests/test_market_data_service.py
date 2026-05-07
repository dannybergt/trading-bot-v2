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


class _FakeAlphaVantage:
    def __init__(self):
        self.news_calls = []
        self.history_calls = []

    def get_news_payload(self, symbol, asset_class, limit=15):
        self.news_calls.append((symbol, asset_class, limit))
        return {
            "items": [
                {
                    "title": "Bitcoin demand builds",
                    "summary": "Provider-backed crypto flow remains constructive.",
                    "score": 0.55,
                    "label": "bullish",
                    "timestamp": "2026-03-26T12:00:00Z",
                    "url": "https://example.com/provider/bitcoin-demand",
                    "source": "Alpha Vantage",
                }
            ],
            "aggregate_score": 0.55,
            "aggregate_label": "bullish",
            "provider": {
                "status": "live",
                "source": "Alpha Vantage",
                "assetClass": asset_class,
                "lastUpdated": "2026-03-26T12:00:00Z",
            },
        }

    def get_provider_snapshot(self, symbol, asset_class):
        return {
            "status": "live",
            "source": "Alpha Vantage",
            "assetClass": asset_class,
            "reason": None,
            "lastUpdated": "2026-03-26T12:00:00Z",
            "quote": {
                "price": 510.12 if asset_class == "etf" else 71234.5,
                "change": 2.13,
                "changePercent": 0.42,
                "currency": "USD",
                "history": [{"close": 500.0}, {"close": 510.12}],
            },
            "research": {
                "expenseRatio": 0.18 if asset_class == "etf" else None,
                "dividendYield": 0.49 if asset_class == "etf" else None,
                "netAssets": 395000000000.0 if asset_class == "etf" else None,
                "inceptionDate": "1999-03-10" if asset_class == "etf" else None,
                "topHoldings": [{"symbol": "NVDA", "name": "NVIDIA", "weightPercent": 8.67}] if asset_class == "etf" else [],
                "topSectors": [{"sector": "INFORMATION TECHNOLOGY", "weightPercent": 48.9}] if asset_class == "etf" else [],
            },
        }

    def get_history_df(self, symbol, asset_class, limit=100):
        self.history_calls.append((symbol, asset_class, limit))
        closes = [500.0 + index for index in range(20)]
        return pd.DataFrame(
            {
                "Open": closes,
                "High": [value + 1.0 for value in closes],
                "Low": [value - 1.0 for value in closes],
                "Close": closes,
                "Volume": [1000.0 + index * 10 for index in range(20)],
            },
            index=pd.date_range("2026-03-01", periods=20, freq="D"),
        )


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

    def test_get_market_news_prefers_alpha_vantage_for_crypto(self):
        alpha_vantage = _FakeAlphaVantage()
        alpaca = _FakeAlpaca()
        service = MarketDataService(alpaca, alpha_vantage_service=alpha_vantage)

        payload = service.get_market_news(
            "BTC/USD",
            asset_profile={"symbol": "BTC/USD", "assetClass": "crypto", "isCrypto": True},
        )

        self.assertEqual(alpha_vantage.news_calls, [("BTC/USD", "crypto", 15)])
        self.assertEqual(alpaca.news_calls, [])
        self.assertEqual(payload["provider"]["source"], "Alpha Vantage")
        self.assertEqual(payload["aggregate_label"], "bullish")

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

    def test_get_stock_data_uses_alpha_vantage_history_for_etf(self):
        alpha_vantage = _FakeAlphaVantage()
        service = MarketDataService(alpha_vantage_service=alpha_vantage)
        service.predictor = _FakePredictor()

        with patch.object(service, "_generate_mock_data") as mock_data, patch.object(
            service,
            "get_ticker_info",
            return_value={"quoteType": "ETF", "shortName": "Vanguard S&P 500 ETF"},
        ):
            payload = service.get_stock_data(
                "VOO",
                period="1mo",
                interval="1d",
                include_news=False,
                include_fundamentals=False,
            )

        mock_data.assert_not_called()
        self.assertEqual(alpha_vantage.history_calls, [("VOO", "etf", 22)])
        self.assertEqual(payload["asset"]["assetClass"], "etf")
        self.assertEqual(payload["provider"]["source"], "Alpha Vantage")
        self.assertEqual(payload["provider"]["quote"]["price"], 510.12)


class FmpFallbackTests(unittest.TestCase):
    def test_get_ticker_info_falls_back_to_fmp_when_yfinance_empty(self):
        service = MarketDataService()
        service.fmp = type(
            "FakeFmp",
            (),
            {
                "configured": True,
                "normalized_ticker_info": staticmethod(
                    lambda symbol: {
                        "shortName": "Apple Inc.",
                        "sector": "Technology",
                        "marketCap": 3_000_000_000_000,
                        "fmp_source": True,
                    }
                ),
            },
        )()

        with patch("app.services.acquire_rate_limit", return_value=True), patch(
            "app.services.yf.Ticker"
        ) as ticker_ctor:
            ticker_ctor.return_value.info = {}
            payload = service.get_ticker_info("AAPL", asset_profile={"isCrypto": False})

        self.assertEqual("Apple Inc.", payload["shortName"])
        self.assertEqual("Technology", payload["sector"])
        self.assertTrue(payload["fmp_source"])

    def test_get_ticker_info_does_not_call_fmp_when_yfinance_returned_data(self):
        service = MarketDataService()
        called = []
        service.fmp = type(
            "FakeFmp",
            (),
            {
                "configured": True,
                "normalized_ticker_info": staticmethod(
                    lambda symbol: called.append(symbol) or {"shortName": "should not be used"}
                ),
            },
        )()

        with patch("app.services.acquire_rate_limit", return_value=True), patch(
            "app.services.yf.Ticker"
        ) as ticker_ctor:
            ticker_ctor.return_value.info = {
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "marketCap": 1_000,
                "trailingPE": 25.0,
            }
            payload = service.get_ticker_info("AAPL", asset_profile={"isCrypto": False})

        self.assertEqual("Technology", payload["sector"])
        self.assertEqual([], called)

    def test_get_market_news_falls_back_to_fmp_when_alpaca_empty(self):
        service = MarketDataService(alpaca_service=None)
        service.fmp = type(
            "FakeFmp",
            (),
            {
                "configured": True,
                "normalized_news_items": staticmethod(
                    lambda symbol, *, limit: [
                        {
                            "title": "FMP headline",
                            "summary": "Backup provider",
                            "url": "https://example.com",
                            "timestamp": "2026-05-07T12:00:00Z",
                            "source": "Reuters",
                        }
                    ]
                ),
            },
        )()

        with patch(
            "app.services.analyze_news",
            return_value=[
                {
                    "title": "FMP headline",
                    "summary": "Backup provider",
                    "score": 0.3,
                    "label": "bullish",
                    "timestamp": "2026-05-07T12:00:00Z",
                    "url": "https://example.com",
                    "source": "Reuters",
                }
            ],
        ):
            payload = service.get_market_news("AAPL", limit=5)

        self.assertEqual("Reuters", payload["provider"]["source"])
        self.assertEqual("bullish", payload["aggregate_label"])


if __name__ == "__main__":
    unittest.main()
