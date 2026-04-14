import unittest

from app.alpha_vantage_service import AlphaVantageService


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, url, params=None, timeout=None):
        function_name = params.get("function")
        self.calls.append((url, dict(params or {}), timeout))
        return _FakeResponse(self.payloads[function_name])


class AlphaVantageServiceTests(unittest.TestCase):
    def test_get_provider_snapshot_parses_etf_profile_and_history(self):
        session = _FakeSession(
            {
                "TIME_SERIES_DAILY": {
                    "Time Series (Daily)": {
                        "2026-03-24": {
                            "1. open": "500.00",
                            "2. high": "501.00",
                            "3. low": "499.00",
                            "4. close": "500.00",
                            "5. volume": "1000",
                        },
                        "2026-03-25": {
                            "1. open": "501.00",
                            "2. high": "503.00",
                            "3. low": "500.00",
                            "4. close": "502.00",
                            "5. volume": "1100",
                        },
                    }
                },
                "ETF_PROFILE": {
                    "net_assets": "395000000000",
                    "net_expense_ratio": "0.0018",
                    "dividend_yield": "0.0049",
                    "inception_date": "1999-03-10",
                    "holdings": [
                        {"symbol": "NVDA", "description": "NVIDIA CORP", "weight": "0.0867"},
                        {"symbol": "AAPL", "description": "APPLE INC", "weight": "0.0737"},
                    ],
                    "sectors": [
                        {"sector": "INFORMATION TECHNOLOGY", "weight": "0.489"},
                        {"sector": "COMMUNICATION SERVICES", "weight": "0.161"},
                    ],
                },
            }
        )
        service = AlphaVantageService(api_key="test-key", session=session)

        payload = service.get_provider_snapshot("QQQ", "etf")

        self.assertEqual(payload["status"], "live")
        self.assertEqual(payload["source"], "Alpha Vantage")
        self.assertEqual(payload["quote"]["price"], 502.0)
        self.assertEqual(payload["quote"]["changePercent"], 0.4)
        self.assertEqual(payload["research"]["expenseRatio"], 0.18)
        self.assertEqual(payload["research"]["dividendYield"], 0.49)
        self.assertEqual(payload["research"]["netAssets"], 395000000000.0)
        self.assertEqual(payload["research"]["topHoldings"][0]["symbol"], "NVDA")
        self.assertEqual(payload["research"]["topHoldings"][0]["weightPercent"], 8.67)
        self.assertEqual(payload["research"]["topSectors"][0]["sector"], "INFORMATION TECHNOLOGY")

    def test_get_provider_snapshot_parses_crypto_history(self):
        session = _FakeSession(
            {
                "DIGITAL_CURRENCY_DAILY": {
                    "Time Series (Digital Currency Daily)": {
                        "2026-03-24": {
                            "1a. open (USD)": "70000.00",
                            "2a. high (USD)": "70500.00",
                            "3a. low (USD)": "69500.00",
                            "4a. close (USD)": "70200.00",
                            "5. volume": "5000",
                        },
                        "2026-03-25": {
                            "1a. open (USD)": "70200.00",
                            "2a. high (USD)": "71000.00",
                            "3a. low (USD)": "70100.00",
                            "4a. close (USD)": "70800.00",
                            "5. volume": "5200",
                        },
                    }
                }
            }
        )
        service = AlphaVantageService(api_key="test-key", session=session)

        payload = service.get_provider_snapshot("BTC/USD", "crypto")

        self.assertEqual(payload["status"], "live")
        self.assertEqual(payload["quote"]["currency"], "USD")
        self.assertEqual(payload["quote"]["price"], 70800.0)
        self.assertEqual(payload["quote"]["change"], 600.0)
        self.assertEqual(payload["quote"]["changePercent"], 0.85)
        self.assertEqual(len(payload["quote"]["history"]), 2)

    def test_get_provider_snapshot_parses_crypto_history_with_generic_ohlc_keys(self):
        session = _FakeSession(
            {
                "DIGITAL_CURRENCY_DAILY": {
                    "Time Series (Digital Currency Daily)": {
                        "2026-04-13": {
                            "1. open": "73000.00",
                            "2. high": "74100.00",
                            "3. low": "72800.00",
                            "4. close": "74000.00",
                            "5. volume": "240.00",
                        },
                        "2026-04-14": {
                            "1. open": "74448.00",
                            "2. high": "74552.01",
                            "3. low": "74200.36",
                            "4. close": "74264.02",
                            "5. volume": "241.00",
                        },
                    }
                }
            }
        )
        service = AlphaVantageService(api_key="test-key", session=session)

        payload = service.get_provider_snapshot("BTC/USD", "crypto")

        self.assertEqual(payload["status"], "live")
        self.assertEqual(payload["quote"]["currency"], "USD")
        self.assertEqual(payload["quote"]["price"], 74264.02)
        self.assertEqual(payload["quote"]["change"], 264.02)
        self.assertEqual(payload["quote"]["changePercent"], 0.36)
        self.assertEqual(len(payload["quote"]["history"]), 2)

    def test_get_news_payload_parses_feed(self):
        session = _FakeSession(
            {
                "NEWS_SENTIMENT": {
                    "feed": [
                        {
                            "title": "Bitcoin breaks higher",
                            "summary": "Risk appetite improves.",
                            "time_published": "20260326T120000",
                            "url": "https://example.com/news/bitcoin-breaks-higher",
                            "source": "Example Wire",
                            "overall_sentiment_score": "0.35",
                            "overall_sentiment_label": "Bullish",
                        },
                        {
                            "title": "Crypto market steadies",
                            "summary": "Volatility cools.",
                            "time_published": "20260326T110000",
                            "url": "https://example.com/news/crypto-market-steadies",
                            "source": "Example Wire",
                            "overall_sentiment_score": "0.05",
                            "overall_sentiment_label": "Neutral",
                        },
                    ]
                }
            }
        )
        service = AlphaVantageService(api_key="test-key", session=session)

        payload = service.get_news_payload("BTC/USD", "crypto", limit=2)

        self.assertEqual(payload["provider"]["source"], "Alpha Vantage")
        self.assertEqual(payload["aggregate_label"], "bullish")
        self.assertEqual(payload["items"][0]["timestamp"], "2026-03-26T12:00:00Z")
        self.assertEqual(payload["items"][0]["label"], "bullish")
        self.assertEqual(payload["items"][1]["label"], "neutral")


if __name__ == "__main__":
    unittest.main()
