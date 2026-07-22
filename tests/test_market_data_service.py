import unittest
from unittest.mock import patch

import pandas as pd

from app.services import MarketDataService, fundamentals_detail_from_ticker_info


class _FakePredictor:
    is_trained = True

    def train(self, df):
        self.last_train_size = len(df.index)
        return {"accuracy": 0.0, "features": []}

    def predict_next_movement(self, df, *, user=None):  # accepts new kwarg
        return {"direction": "HOLD", "confidence": 0.0}


def _seed_fake_predictor(service, symbol: str) -> _FakePredictor:
    """Drop a fake into the per-symbol cache so the persistence layer is bypassed."""
    fake = _FakePredictor()
    service._predictor_cache[symbol] = {
        "predictor": fake,
        "metadata": None,
        "expires_at": float("inf"),
    }
    return fake


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
        # Cache hits bypass _get_or_train_predictor's disk path.
        _seed_fake_predictor(service, "BTC/USD")
        _seed_fake_predictor(service, "VOO")

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

    def test_get_stock_data_marks_synthetic_and_suppresses_recommendation(self):
        # When no provider returns bars, the chart falls back to a synthetic
        # random walk. The payload must be flagged synthetic AND the ML verdict
        # must be neutralised to a non-actionable HOLD/0.0 so no buy/sell
        # recommendation ever rides on fabricated prices.
        service = MarketDataService()

        class _UpPredictor:
            is_trained = True

            def train(self, df):
                return {"accuracy": 0.9, "features": []}

            def predict_next_movement(self, df, *, user=None):
                return {"direction": "UP", "confidence": 0.9}

        service._predictor_cache["FAKE"] = {
            "predictor": _UpPredictor(),
            "metadata": None,
            "expires_at": float("inf"),
        }

        with patch.object(service, "get_provider_history_df", return_value=pd.DataFrame()), patch.object(
            service,
            "get_market_news",
            return_value={"items": [], "aggregate_score": 0.0, "aggregate_label": "neutral", "provider": None},
        ), patch.object(service, "get_ticker_info", return_value={}):
            payload = service.get_stock_data("FAKE", period="6mo", interval="1d")

        self.assertTrue(payload["synthetic"])
        prediction = payload["prediction"]
        self.assertTrue(prediction["synthetic"])
        self.assertEqual(prediction["direction"], "HOLD")
        self.assertEqual(prediction["confidence"], 0.0)

    def test_get_stock_data_uses_yfinance_stock_history_before_synthetic(self):
        # Without an Alpaca key, stock bars used to fall straight to the
        # synthetic placeholder. The free yfinance history fallback must fill
        # them first, so the payload is NOT flagged synthetic.
        idx = pd.date_range("2026-01-01", periods=120, freq="D")
        hist = pd.DataFrame(
            {
                "Open": [100 + i * 0.1 for i in range(120)],
                "High": [101 + i * 0.1 for i in range(120)],
                "Low": [99 + i * 0.1 for i in range(120)],
                "Close": [100 + i * 0.1 for i in range(120)],
                "Volume": [1_000_000] * 120,
            },
            index=idx,
        )

        class _FakeYfTicker:
            def __init__(self, sym):
                pass

            def history(self, period=None, interval=None):
                return hist

        service = MarketDataService()  # no Alpaca configured
        _seed_fake_predictor(service, "AAPL")

        with patch("app.services.yf.Ticker", _FakeYfTicker), patch(
            "app.services.acquire_rate_limit", return_value=True
        ), patch.object(
            service,
            "get_market_news",
            return_value={"items": [], "aggregate_score": 0.0, "aggregate_label": "neutral", "provider": None},
        ), patch.object(service, "get_ticker_info", return_value={}):
            payload = service.get_stock_data("AAPL", period="6mo", interval="1d")

        self.assertFalse(payload["synthetic"])
        self.assertGreater(len(payload["data"].index), 30)

    def test_fundamentals_detail_from_ticker_info_maps_and_normalises_units(self):
        info = {
            "exchange": "NMS",
            "currency": "USD",
            "beta": 1.29,
            "marketCap": 3_000_000_000_000,
            "trailingPE": 32.5,
            "forwardPE": 28.1,
            "priceToBook": 47.2,
            "priceToSalesTrailing12Months": 8.3,
            "trailingEps": 6.13,
            "totalRevenue": 391_000_000_000,
            "netIncomeToCommon": 93_700_000_000,
            "returnOnEquity": 1.47,       # already a fraction (147%)
            "debtToEquity": 154.49,       # yfinance percent -> 1.5449 ratio
            "dividendRate": 1.00,
            "currentPrice": 200.0,        # -> yield 0.005 (0.5%)
            "payoutRatio": 0.15,
        }
        detail = fundamentals_detail_from_ticker_info(info)
        self.assertEqual(detail["source"], "yfinance")
        self.assertEqual(detail["peRatioTtm"], 32.5)
        self.assertEqual(detail["marketCap"], 3_000_000_000_000)
        self.assertEqual(detail["epsTtm"], 6.13)
        self.assertEqual(detail["revenue"], 391_000_000_000)
        # Unit normalisation: debtToEquity percent -> ratio
        self.assertAlmostEqual(detail["debtToEquityTtm"], 1.5449, places=4)
        # Dividend yield derived from rate/price, not the ambiguous yf field
        self.assertAlmostEqual(detail["dividendYieldTtm"], 0.005, places=6)
        self.assertEqual(detail["annualDividend"], 1.00)
        self.assertEqual(detail["returnOnEquityTtm"], 1.47)
        self.assertEqual(detail["payoutRatioTtm"], 0.15)

    def test_fundamentals_detail_from_ticker_info_omits_yield_without_price(self):
        self.assertEqual(fundamentals_detail_from_ticker_info({}), {})
        detail = fundamentals_detail_from_ticker_info({"dividendRate": 2.0, "trailingPE": 10.0})
        self.assertNotIn("dividendYieldTtm", detail)   # no price -> no fabricated yield
        self.assertEqual(detail["annualDividend"], 2.0)
        self.assertEqual(detail["peRatioTtm"], 10.0)

    def test_get_stock_data_uses_alpha_vantage_history_for_etf(self):
        alpha_vantage = _FakeAlphaVantage()
        service = MarketDataService(alpha_vantage_service=alpha_vantage)
        # Cache hits bypass _get_or_train_predictor's disk path.
        _seed_fake_predictor(service, "BTC/USD")
        _seed_fake_predictor(service, "VOO")

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

    def test_get_ticker_info_falls_back_to_twelve_data_when_yfinance_and_fmp_empty(self):
        service = MarketDataService()
        service.fmp = type(
            "FakeFmp",
            (),
            {
                "configured": True,
                "normalized_ticker_info": staticmethod(lambda symbol: {}),
            },
        )()
        service.twelve_data = type(
            "FakeTwelveData",
            (),
            {
                "configured": True,
                "normalized_ticker_info": staticmethod(
                    lambda symbol: {
                        "shortName": "SAP SE",
                        "sector": "Technology",
                        "marketCap": 175_000_000_000,
                        "twelve_data_source": True,
                    }
                ),
            },
        )()

        with patch("app.services.acquire_rate_limit", return_value=True), patch(
            "app.services.yf.Ticker"
        ) as ticker_ctor:
            ticker_ctor.return_value.info = {}
            payload = service.get_ticker_info("SAP.DE", asset_profile={"isCrypto": False})

        self.assertEqual("SAP SE", payload["shortName"])
        self.assertEqual("Technology", payload["sector"])
        self.assertTrue(payload["twelve_data_source"])

    def test_get_ticker_info_does_not_call_twelve_data_when_fmp_filled_in(self):
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
                        "trailingPE": 28.5,
                        "fmp_source": True,
                    }
                ),
            },
        )()
        called = []
        service.twelve_data = type(
            "FakeTwelveData",
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
            ticker_ctor.return_value.info = {}
            service.get_ticker_info("AAPL", asset_profile={"isCrypto": False})

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
