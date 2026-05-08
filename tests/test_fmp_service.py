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

    def test_normalized_research_depth_aggregates_four_endpoints(self):
        service = FmpService(api_key="k")
        cashflow_payload = [
            {
                "date": "2025-12-31",
                "operatingCashFlow": 100_000_000,
                "capitalExpenditure": -10_000_000,
                "freeCashFlow": 90_000_000,
            }
        ]
        balance_payload = [
            {
                "date": "2025-12-31",
                "totalDebt": 50_000_000,
                "longTermDebt": 40_000_000,
                "shortTermDebt": 10_000_000,
                "totalStockholdersEquity": 250_000_000,
                "netDebt": 20_000_000,
            }
        ]
        rating_payload = [
            {
                "date": "2026-04-01",
                "rating": "S+",
                "ratingScore": 5,
                "ratingRecommendation": "Strong Buy",
            }
        ]
        estimates_payload = [
            {
                "date": "2026-12-31",
                "estimatedRevenueAvg": 1_200_000_000,
                "estimatedEpsAvg": 5.10,
                "numberAnalystsEstimatedEps": 18,
            }
        ]
        responses = iter([
            _response(cashflow_payload),
            _response(balance_payload),
            _response(rating_payload),
            _response(estimates_payload),
        ])
        with patch("app.fmp_service.acquire_rate_limit", return_value=True), patch(
            "app.fmp_service.requests.get", side_effect=lambda *a, **kw: next(responses)
        ):
            depth = service.normalized_research_depth("AAPL")

        self.assertEqual(1, len(depth["cashflow"]))
        self.assertEqual(90_000_000, depth["cashflow"][0]["freeCashFlow"])
        self.assertEqual(1, len(depth["debt"]))
        self.assertEqual(250_000_000, depth["debt"][0]["totalEquity"])
        self.assertIsNotNone(depth["rating"])
        self.assertEqual("Strong Buy", depth["rating"]["ratingRecommendation"])
        self.assertEqual(1, len(depth["estimates"]))
        self.assertAlmostEqual(5.10, depth["estimates"][0]["estimatedEpsAvg"])

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

    def test_insider_trades_uses_v4_base_url(self):
        service = FmpService(api_key="k")
        with patch("app.fmp_service.acquire_rate_limit", return_value=True), patch(
            "app.fmp_service.requests.get",
            return_value=_response([{"symbol": "AAPL", "transactionType": "P-Purchase"}]),
        ) as get_mock:
            service.get_insider_trades("AAPL")
        called_url = get_mock.call_args.args[0]
        self.assertIn("/api/v4/", called_url)
        self.assertIn("/insider-trading", called_url)
        self.assertEqual("AAPL", get_mock.call_args.kwargs["params"]["symbol"])

    def test_normalized_research_signals_aggregates_all_sources(self):
        from datetime import datetime, timedelta, timezone

        service = FmpService(api_key="k")
        recent = (datetime.now(timezone.utc).date() - timedelta(days=10)).isoformat()
        old = (datetime.now(timezone.utc).date() - timedelta(days=120)).isoformat()
        upcoming_date = (datetime.now(timezone.utc).date() + timedelta(days=14)).isoformat()

        insider_payload = [
            {
                "transactionDate": recent,
                "transactionType": "P-Purchase",
                "reportingName": "CEO Smith",
                "typeOfOwner": "officer: CEO",
                "securitiesTransacted": 1000,
                "price": 200.0,
            },
            {
                "transactionDate": recent,
                "transactionType": "S-Sale",
                "reportingName": "CFO Doe",
                "securitiesTransacted": 500,
                "price": 195.0,
            },
            {
                "transactionDate": old,  # outside 90d window
                "transactionType": "P-Purchase",
                "securitiesTransacted": 100000,
                "price": 100.0,
            },
        ]
        institutional_payload = [
            {"holder": "Vanguard", "shares": 5_000_000, "weightPercent": 8.5, "change": 100000, "dateReported": "2026-04-30"},
            {"holder": "BlackRock", "shares": 4_500_000, "weightPercent": 7.6, "change": -50000, "dateReported": "2026-04-30"},
        ]
        surprises_payload = [
            {"date": "2026-02-01", "actualEarningResult": 2.10, "estimatedEarning": 2.00},
            {"date": "2025-11-01", "actualEarningResult": 1.80, "estimatedEarning": 1.85},
            {"date": "2025-08-01", "actualEarningResult": 1.90, "estimatedEarning": 1.85},
        ]
        upcoming_payload = [
            {"date": upcoming_date, "symbol": "AAPL", "epsEstimated": 2.20, "revenueEstimated": 1.25e11, "time": "amc"},
            {"date": upcoming_date, "symbol": "MSFT", "epsEstimated": 3.00},  # filtered out
        ]
        responses = iter([
            _response(insider_payload),
            _response(institutional_payload),
            _response(surprises_payload),
            _response(upcoming_payload),
        ])
        with patch("app.fmp_service.acquire_rate_limit", return_value=True), patch(
            "app.fmp_service.requests.get", side_effect=lambda *a, **kw: next(responses)
        ):
            signals = service.normalized_research_signals("AAPL")

        # Insider summary: only the 90d-window rows count
        self.assertEqual(1000, signals["insiderSummary"]["buys90dShares"])
        self.assertEqual(500, signals["insiderSummary"]["sells90dShares"])
        # Net value = 1000 * 200 - 500 * 195 = 200000 - 97500 = 102500
        self.assertAlmostEqual(102_500.0, signals["insiderSummary"]["netValue90d"])
        self.assertEqual(3, len(signals["insiderTrades"]))
        self.assertTrue(signals["insiderTrades"][0]["isBuy"])
        self.assertFalse(signals["insiderTrades"][1]["isBuy"])

        # Institutional sorted by shares desc, top entries
        self.assertEqual("Vanguard", signals["institutionalHoldings"][0]["holder"])
        self.assertEqual(2, len(signals["institutionalHoldings"]))

        # Beat rate: 2 of 3 quarters beat
        self.assertEqual(3, len(signals["earningsSurprises"]))
        self.assertAlmostEqual(2 / 3, signals["earningsBeatRate"], places=2)

        # Upcoming earnings filtered to AAPL
        self.assertIsNotNone(signals["upcomingEarnings"])
        self.assertEqual(upcoming_date, signals["upcomingEarnings"]["date"])
        self.assertEqual(14, signals["daysUntilEarnings"])

    def test_normalized_research_signals_handles_empty_inputs(self):
        service = FmpService(api_key="k")
        responses = iter([_response([]), _response([]), _response([]), _response([])])
        with patch("app.fmp_service.acquire_rate_limit", return_value=True), patch(
            "app.fmp_service.requests.get", side_effect=lambda *a, **kw: next(responses)
        ):
            signals = service.normalized_research_signals("UNKNOWN")
        self.assertEqual([], signals["insiderTrades"])
        self.assertEqual(0, signals["insiderSummary"]["buys90dShares"])
        self.assertIsNone(signals["earningsBeatRate"])
        self.assertIsNone(signals["upcomingEarnings"])
        self.assertIsNone(signals["daysUntilEarnings"])

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
