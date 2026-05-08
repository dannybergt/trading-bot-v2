"""Tests for the FRED adapter.

The adapter calls the FRED REST API; tests stub `requests.get` so no real
HTTP traffic happens. The rate limiter is also stubbed so tests run
synchronously.
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.fred_service import FredService  # noqa: E402


def _response(payload, status: int = 200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


class FredServiceTests(unittest.TestCase):
    def test_unconfigured_returns_empty_calendar_without_http(self):
        service = FredService(api_key="")
        with patch("app.fred_service.requests.get") as get_mock:
            calendar = service.normalized_macro_calendar()
        get_mock.assert_not_called()
        self.assertFalse(calendar["configured"])
        self.assertEqual(calendar["upcomingReleases"], [])
        self.assertEqual(calendar["treasury"], {})

    def test_get_series_observations_skips_missing_values(self):
        service = FredService(api_key="k")
        payload = {
            "observations": [
                {"date": "2026-05-01", "value": "4.42"},
                {"date": "2026-04-30", "value": "."},
                {"date": "2026-04-29", "value": "4.40"},
            ]
        }
        with patch("app.fred_service.acquire_rate_limit", return_value=True), \
             patch("app.fred_service.requests.get", return_value=_response(payload)):
            obs = service.get_series_observations("DGS10", limit=5)
        self.assertEqual(len(obs), 2)
        self.assertEqual(obs[0]["value"], 4.42)
        self.assertEqual(obs[1]["value"], 4.40)

    def test_get_series_observations_uses_cache(self):
        service = FredService(api_key="k")
        payload = {"observations": [{"date": "2026-05-01", "value": "4.42"}]}
        with patch("app.fred_service.acquire_rate_limit", return_value=True), \
             patch("app.fred_service.requests.get", return_value=_response(payload)) as get_mock:
            service.get_series_observations("DGS10", limit=5)
            service.get_series_observations("DGS10", limit=5)
            service.get_series_observations("DGS10", limit=5)
        self.assertEqual(get_mock.call_count, 1)

    def test_get_release_dates_filters_to_future_plus_recent(self):
        service = FredService(api_key="k")
        today = datetime.now(timezone.utc).date()
        future_a = (today + timedelta(days=10)).isoformat()
        future_b = (today + timedelta(days=40)).isoformat()
        past = (today - timedelta(days=5)).isoformat()
        payload = {
            "release_dates": [
                {"date": past},
                {"date": future_a},
                {"date": future_b},
            ]
        }
        with patch("app.fred_service.acquire_rate_limit", return_value=True), \
             patch("app.fred_service.requests.get", return_value=_response(payload)):
            dates = service.get_release_dates(10, limit=5)
        self.assertEqual(dates, [future_a, future_b])

    def test_get_release_dates_returns_last_past_when_no_future(self):
        service = FredService(api_key="k")
        today = datetime.now(timezone.utc).date()
        past_a = (today - timedelta(days=20)).isoformat()
        past_b = (today - timedelta(days=5)).isoformat()
        payload = {"release_dates": [{"date": past_a}, {"date": past_b}]}
        with patch("app.fred_service.acquire_rate_limit", return_value=True), \
             patch("app.fred_service.requests.get", return_value=_response(payload)):
            dates = service.get_release_dates(10, limit=5)
        self.assertEqual(dates, [past_b])

    def test_normalized_macro_calendar_assembles_full_payload(self):
        service = FredService(api_key="k")
        today = datetime.now(timezone.utc).date()
        upcoming_iso = (today + timedelta(days=5)).isoformat()

        def fake_get(url, params, timeout):
            path = url.split("https://api.stlouisfed.org/fred", 1)[1]
            if path == "/series/observations":
                series_id = params["series_id"]
                if series_id == "T10Y2Y":
                    # Inverted curve to verify the spreadInverted flag
                    return _response({"observations": [
                        {"date": "2026-05-01", "value": "-0.15"},
                        {"date": "2026-04-30", "value": "-0.10"},
                    ]})
                return _response({"observations": [
                    {"date": "2026-05-01", "value": "4.42"},
                    {"date": "2026-04-30", "value": "4.40"},
                ]})
            if path == "/release/dates":
                return _response({"release_dates": [{"date": upcoming_iso}]})
            return _response({})

        with patch("app.fred_service.acquire_rate_limit", return_value=True), \
             patch("app.fred_service.requests.get", side_effect=fake_get):
            calendar = service.normalized_macro_calendar()

        self.assertTrue(calendar["configured"])
        self.assertEqual(calendar["treasury"]["ten"]["value"], 4.42)
        self.assertEqual(calendar["treasury"]["spread"]["value"], -0.15)
        self.assertTrue(calendar["treasury"]["spreadInverted"])
        self.assertEqual(calendar["commodities"]["wti"]["value"], 4.42)
        self.assertGreaterEqual(len(calendar["upcomingReleases"]), 1)
        nearest = calendar["upcomingReleases"][0]
        self.assertEqual(nearest["date"], upcoming_iso)
        self.assertEqual(nearest["daysUntil"], 5)

    def test_normalized_macro_calendar_caches_result(self):
        service = FredService(api_key="k")
        # Pre-populate the cache so we can prove the second call doesn't
        # hit the HTTP layer.
        service._calendar_cache = {
            "expires_at": float("inf"),
            "value": {"configured": True, "treasury": {}, "commodities": {}, "policy": {}, "upcomingReleases": [], "asOf": "x"},
        }
        with patch("app.fred_service.requests.get") as get_mock:
            service.normalized_macro_calendar()
        get_mock.assert_not_called()

    def test_http_error_returns_empty_observations_without_raising(self):
        service = FredService(api_key="k")
        bad_response = MagicMock()
        bad_response.status_code = 503
        import requests as real_requests
        bad_response.raise_for_status.side_effect = real_requests.HTTPError(
            "503 service unavailable", response=bad_response,
        )
        with patch("app.fred_service.acquire_rate_limit", return_value=True), \
             patch("app.fred_service.requests.get", return_value=bad_response):
            self.assertEqual([], service.get_series_observations("DGS10"))


if __name__ == "__main__":
    unittest.main()
