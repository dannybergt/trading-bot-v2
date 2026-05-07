"""Tests for the FMP adapter.

The adapter calls the FMP REST API; tests stub `requests.get` so no real
HTTP traffic happens. The rate limiter is also stubbed so tests run
synchronously.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.fmp_service import FmpService  # noqa: E402


def _response(payload, status: int = 200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


class FmpServiceTests(unittest.TestCase):
    def test_unconfigured_returns_none_without_http(self):
        service = FmpService(api_key="")
        with patch("app.fmp_service.requests.get") as get_mock:
            self.assertIsNone(service.get_profile("AAPL"))
            self.assertEqual({}, service.normalized_ticker_info("AAPL"))
            self.assertEqual([], service.get_etf_holdings("VOO"))
        get_mock.assert_not_called()

    def test_get_profile_returns_first_payload_entry(self):
        service = FmpService(api_key="k")
        with patch("app.fmp_service.acquire_rate_limit", return_value=True), \
             patch(
                 "app.fmp_service.requests.get",
                 return_value=_response(
                     [{"symbol": "AAPL", "companyName": "Apple", "mktCap": 3_000_000_000_000}]
                 ),
             ) as get_mock:
            profile = service.get_profile("aapl")
        get_mock.assert_called_once()
        self.assertEqual("Apple", profile["companyName"])
        # API key carried in the params
        self.assertEqual("k", get_mock.call_args.kwargs["params"]["apikey"])

    def test_rate_limit_skip_returns_none_without_http(self):
        service = FmpService(api_key="k")
        with patch("app.fmp_service.acquire_rate_limit", return_value=False), \
             patch("app.fmp_service.requests.get") as get_mock:
            self.assertIsNone(service.get_profile("AAPL"))
        get_mock.assert_not_called()

    def test_normalized_ticker_info_covers_yfinance_subset(self):
        service = FmpService(api_key="k")
        profile_payload = [{
            "symbol": "AAPL",
            "companyName": "Apple",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "mktCap": 3_000_000_000_000,
            "range": "150.00-220.00",
        }]
        metrics_payload = [{"peRatio": 28.5, "forwardPE": 25.1, "pbRatio": 40.0}]
        ratios_payload = [{
            "dividendYieldTTM": 0.005,
            "priceToBookRatioTTM": 39.5,
            "priceEarningsRatioTTM": 28.0,
        }]
        responses = iter([
            _response(profile_payload),
            _response(metrics_payload),
            _response(ratios_payload),
        ])
        with patch("app.fmp_service.acquire_rate_limit", return_value=True), \
             patch("app.fmp_service.requests.get", side_effect=lambda *a, **kw: next(responses)):
            info = service.normalized_ticker_info("AAPL")

        self.assertEqual("Apple", info["shortName"])
        self.assertEqual("Technology", info["sector"])
        self.assertEqual(3_000_000_000_000, info["marketCap"])
        self.assertEqual(220.0, info["fiftyTwoWeekHigh"])
        self.assertEqual(150.0, info["fiftyTwoWeekLow"])
        self.assertAlmostEqual(0.005, info["dividendYield"])
        self.assertAlmostEqual(28.5, info["trailingPE"])
        self.assertAlmostEqual(25.1, info["forwardPE"])
        # Either of the ratios sources is acceptable; we just need a value.
        self.assertGreater(info["priceToBook"], 0)
        self.assertTrue(info["fmp_source"])

    def test_normalized_news_items_strips_unknown_fields(self):
        service = FmpService(api_key="k")
        news_payload = [
            {
                "title": "Headline",
                "text": "Summary",
                "url": "https://example.com/x",
                "publishedDate": "2026-05-07T12:00:00Z",
                "site": "Reuters",
            },
            "not a dict",
        ]
        with patch("app.fmp_service.acquire_rate_limit", return_value=True), \
             patch("app.fmp_service.requests.get", return_value=_response(news_payload)):
            items = service.normalized_news_items("AAPL")
        self.assertEqual(1, len(items))
        self.assertEqual("Reuters", items[0]["source"])
        self.assertEqual("https://example.com/x", items[0]["url"])

    def test_normalized_events_unwraps_historical_payloads(self):
        service = FmpService(api_key="k")
        dividends_payload = {
            "symbol": "AAPL",
            "historical": [
                {
                    "date": "2026-02-09",
                    "dividend": 0.24,
                    "adjDividend": 0.24,
                    "recordDate": "2026-02-12",
                    "paymentDate": "2026-02-16",
                    "declarationDate": "2026-02-01",
                    "label": "Q4 2025",
                }
            ],
        }
        splits_payload = {
            "symbol": "AAPL",
            "historical": [
                {"date": "2020-08-31", "numerator": 4, "denominator": 1, "label": "4-for-1"}
            ],
        }
        earnings_payload = [
            {
                "date": "2026-02-01",
                "epsEstimated": 2.10,
                "eps": 2.18,
                "revenueEstimated": 1.18e11,
                "revenue": 1.20e11,
                "fiscalDateEnding": "2025-12-31",
                "time": "amc",
            }
        ]
        responses = iter([
            _response(dividends_payload),
            _response(splits_payload),
            _response(earnings_payload),
        ])
        with patch("app.fmp_service.acquire_rate_limit", return_value=True), patch(
            "app.fmp_service.requests.get", side_effect=lambda *a, **kw: next(responses)
        ):
            events = service.normalized_events("AAPL")

        self.assertEqual(1, len(events["dividends"]))
        self.assertEqual(0.24, events["dividends"][0]["amount"])
        self.assertEqual(1, len(events["splits"]))
        self.assertEqual(4, events["splits"][0]["numerator"])
        self.assertEqual(1, len(events["earnings"]))
        self.assertEqual(2.18, events["earnings"][0]["epsActual"])

    def test_http_error_returns_empty_without_raising(self):
        service = FmpService(api_key="k")
        bad_response = MagicMock()
        bad_response.status_code = 503
        # raise_for_status throws to mimic requests behavior
        import requests as real_requests
        bad_response.raise_for_status.side_effect = real_requests.HTTPError(
            "503 service unavailable", response=bad_response,
        )
        with patch("app.fmp_service.acquire_rate_limit", return_value=True), \
             patch("app.fmp_service.requests.get", return_value=bad_response):
            self.assertIsNone(service.get_profile("AAPL"))


if __name__ == "__main__":
    unittest.main()
