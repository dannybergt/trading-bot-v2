"""Twelve Data adapter tests.

`requests.get` is stubbed so no real HTTP traffic happens. Verifies the
unconfigured short-circuit, the rate-limit short-circuit, the normalized
yfinance-compatible subset, and the defensive handling of Twelve Data's
`{"status":"error"}` response shape.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.twelve_data_service import TwelveDataService  # noqa: E402


def _response(payload, status: int = 200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


class TwelveDataServiceTests(unittest.TestCase):
    def test_unconfigured_returns_none_without_http(self):
        service = TwelveDataService(api_key="")
        with patch("app.twelve_data_service.requests.get") as get_mock:
            self.assertIsNone(service.get_quote("SAP.DE"))
            self.assertEqual({}, service.normalized_ticker_info("SAP.DE"))
        get_mock.assert_not_called()

    def test_rate_limit_skip_returns_none_without_http(self):
        service = TwelveDataService(api_key="k")
        with patch("app.twelve_data_service.acquire_rate_limit", return_value=False), patch(
            "app.twelve_data_service.requests.get"
        ) as get_mock:
            self.assertIsNone(service.get_quote("SAP.DE"))
        get_mock.assert_not_called()

    def test_get_quote_returns_payload(self):
        service = TwelveDataService(api_key="k")
        payload = {"symbol": "SAP", "name": "SAP SE", "close": "120.10"}
        with patch("app.twelve_data_service.acquire_rate_limit", return_value=True), patch(
            "app.twelve_data_service.requests.get",
            return_value=_response(payload),
        ) as get_mock:
            quote = service.get_quote("sap.de")
        self.assertEqual("SAP SE", quote["name"])
        self.assertEqual("k", get_mock.call_args.kwargs["params"]["apikey"])
        # Symbol is uppercased on the way out
        self.assertEqual("SAP.DE", get_mock.call_args.kwargs["params"]["symbol"])

    def test_error_payload_returns_none(self):
        # Twelve Data returns 200 with {"status":"error"} for invalid symbols
        # or quota-exceeded responses. We treat that as an empty result.
        service = TwelveDataService(api_key="k")
        error_payload = {"status": "error", "code": 404, "message": "Symbol not found"}
        with patch("app.twelve_data_service.acquire_rate_limit", return_value=True), patch(
            "app.twelve_data_service.requests.get",
            return_value=_response(error_payload),
        ):
            self.assertIsNone(service.get_quote("FAKE.TX"))

    def test_normalized_ticker_info_aggregates_profile_and_statistics(self):
        service = TwelveDataService(api_key="k")
        profile_payload = {"name": "SAP SE", "sector": "Technology", "industry": "Software"}
        statistics_payload = {
            "statistics": {
                "valuations_metrics": {
                    "market_capitalization": 175_000_000_000,
                    "trailing_pe": 22.5,
                    "forward_pe": 19.8,
                    "price_to_book_mrq": 5.2,
                },
                "dividends_and_splits": {"forward_annual_dividend_yield": 0.018},
            }
        }
        quote_payload = {"name": "SAP SE", "fifty_two_week": {"high": "150.40", "low": "98.10"}}
        responses = iter([
            _response(profile_payload),
            _response(statistics_payload),
            _response(quote_payload),
        ])
        with patch("app.twelve_data_service.acquire_rate_limit", return_value=True), patch(
            "app.twelve_data_service.requests.get",
            side_effect=lambda *a, **kw: next(responses),
        ):
            info = service.normalized_ticker_info("SAP.DE")
        self.assertEqual("SAP SE", info["shortName"])
        self.assertEqual("Technology", info["sector"])
        self.assertEqual(175_000_000_000, info["marketCap"])
        self.assertAlmostEqual(22.5, info["trailingPE"])
        self.assertAlmostEqual(19.8, info["forwardPE"])
        self.assertAlmostEqual(5.2, info["priceToBook"])
        self.assertAlmostEqual(150.40, info["fiftyTwoWeekHigh"])
        self.assertAlmostEqual(98.10, info["fiftyTwoWeekLow"])
        self.assertTrue(info["twelve_data_source"])

    def test_normalized_ticker_info_empty_when_all_endpoints_blank(self):
        service = TwelveDataService(api_key="k")
        responses = iter([
            _response({"status": "error"}),
            _response({"status": "error"}),
            _response({"status": "error"}),
        ])
        with patch("app.twelve_data_service.acquire_rate_limit", return_value=True), patch(
            "app.twelve_data_service.requests.get",
            side_effect=lambda *a, **kw: next(responses),
        ):
            self.assertEqual({}, service.normalized_ticker_info("FAKE.TX"))


if __name__ == "__main__":
    unittest.main()
