"""Tests for the FX-rate adapter.

The adapter calls frankfurter.app; tests stub `requests.get` so no real
HTTP traffic happens. The rate limiter is also stubbed.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.fx_service import FxService, SUPPORTED_CURRENCIES  # noqa: E402


def _response(payload):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


class FxServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = FxService()
        self.service.reset_caches_for_tests()

    def test_get_rates_returns_normalized_payload_with_identity_entry(self):
        upstream = {
            "amount": 1.0,
            "base": "USD",
            "date": "2026-05-09",
            "rates": {"EUR": 0.9234, "GBP": 0.7901, "CHF": 0.8801},
        }
        with patch("app.fx_service.acquire_rate_limit", return_value=True), patch(
            "app.fx_service.requests.get", return_value=_response(upstream)
        ):
            result = self.service.get_rates("USD")

        self.assertIsNotNone(result)
        self.assertEqual("USD", result["base"])
        self.assertEqual("2026-05-09", result["date"])
        self.assertAlmostEqual(0.9234, result["rates"]["EUR"])
        self.assertAlmostEqual(1.0, result["rates"]["USD"])
        self.assertIn("USD", result["supported"])

    def test_cached_response_avoids_second_http_call(self):
        upstream = {"base": "EUR", "date": "2026-05-09", "rates": {"USD": 1.083}}
        with patch("app.fx_service.acquire_rate_limit", return_value=True), patch(
            "app.fx_service.requests.get", return_value=_response(upstream)
        ) as get_mock:
            first = self.service.get_rates("EUR")
            second = self.service.get_rates("EUR")
        self.assertEqual(first, second)
        get_mock.assert_called_once()

    def test_unsupported_base_returns_none_without_http(self):
        with patch("app.fx_service.requests.get") as get_mock:
            self.assertIsNone(self.service.get_rates("XXX"))
        get_mock.assert_not_called()

    def test_http_error_returns_none(self):
        bad = MagicMock()
        bad.raise_for_status.side_effect = Exception("503")
        import requests as real_requests

        bad.raise_for_status.side_effect = real_requests.RequestException("503 server error")
        with patch("app.fx_service.acquire_rate_limit", return_value=True), patch(
            "app.fx_service.requests.get", return_value=bad
        ):
            self.assertIsNone(self.service.get_rates("USD"))

    def test_invalid_payload_returns_none(self):
        payload = {"base": "USD", "rates": "not a dict"}
        with patch("app.fx_service.acquire_rate_limit", return_value=True), patch(
            "app.fx_service.requests.get", return_value=_response(payload)
        ):
            self.assertIsNone(self.service.get_rates("USD"))

    def test_rates_strip_non_numeric_entries(self):
        upstream = {
            "base": "USD",
            "date": "2026-05-09",
            "rates": {"EUR": 0.92, "GBP": "n/a", "CHF": None, "JPY": 154.3},
        }
        with patch("app.fx_service.acquire_rate_limit", return_value=True), patch(
            "app.fx_service.requests.get", return_value=_response(upstream)
        ):
            result = self.service.get_rates("USD")
        self.assertIn("EUR", result["rates"])
        self.assertIn("JPY", result["rates"])
        self.assertNotIn("GBP", result["rates"])
        self.assertNotIn("CHF", result["rates"])

    def test_supported_currencies_contains_expected_set(self):
        self.assertIn("USD", SUPPORTED_CURRENCIES)
        self.assertIn("EUR", SUPPORTED_CURRENCIES)
        self.assertIn("JPY", SUPPORTED_CURRENCIES)


if __name__ == "__main__":
    unittest.main()
