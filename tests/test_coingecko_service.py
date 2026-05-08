"""CoinGecko + Fear-and-Greed adapter tests.

`requests.get` is stubbed so no real network traffic happens. Verifies
the symbol-to-coin-id mapping, the metric snapshot shape, and the
in-process caches for both endpoints.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.coingecko_service import CoinGeckoService, _normalize_base_symbol  # noqa: E402


def _response(payload, status: int = 200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


class CoinGeckoServiceTests(unittest.TestCase):
    def test_normalize_base_symbol_strips_quote(self):
        self.assertEqual("BTC", _normalize_base_symbol("btc/usd"))
        self.assertEqual("ETH", _normalize_base_symbol("ETH-USD"))
        self.assertEqual("SOLUSDT", _normalize_base_symbol("SOLUSDT"))
        self.assertEqual("", _normalize_base_symbol(""))

    def test_get_coin_metrics_uses_known_id_without_lookup(self):
        service = CoinGeckoService()
        coin_payload = {
            "name": "Bitcoin",
            "market_cap_rank": 1,
            "sentiment_votes_up_percentage": 80.0,
            "sentiment_votes_down_percentage": 20.0,
            "market_data": {
                "market_cap": {"usd": 1_300_000_000_000},
                "total_volume": {"usd": 25_000_000_000},
                "current_price": {"usd": 65_500.0},
                "price_change_percentage_24h": 1.2,
                "price_change_percentage_7d": -3.5,
                "price_change_percentage_30d": 8.4,
                "ath": {"usd": 73_000.0},
                "ath_change_percentage": {"usd": -10.5},
                "ath_date": {"usd": "2024-03-14T00:00:00Z"},
                "atl": {"usd": 67.81},
                "atl_change_percentage": {"usd": 96000.0},
                "atl_date": {"usd": "2013-07-05T00:00:00Z"},
            },
            "community_data": {
                "twitter_followers": 6_000_000,
                "reddit_subscribers": 5_000_000,
                "reddit_accounts_active_48h": 30_000,
            },
            "developer_data": {
                "stars": 75_000,
                "forks": 35_000,
                "subscribers": 4_000,
                "commit_count_4_weeks": 35,
            },
        }

        with patch("app.coingecko_service.acquire_rate_limit", return_value=True), patch(
            "app.coingecko_service.requests.get",
            return_value=_response(coin_payload),
        ) as get_mock:
            metrics = service.get_coin_metrics("BTC/USD")

        # No /coins/markets fallback because BTC is in the static map
        self.assertEqual(1, get_mock.call_count)
        self.assertIn("/coins/bitcoin", get_mock.call_args.args[0])
        self.assertEqual("bitcoin", metrics["coinId"])
        self.assertEqual(1, metrics["marketCapRank"])
        self.assertAlmostEqual(1_300_000_000_000.0, metrics["marketCapUsd"])
        self.assertAlmostEqual(-10.5, metrics["ath"]["changePct"])
        self.assertEqual(35_000, metrics["developer"]["forks"])
        self.assertEqual(80.0, metrics["sentimentVotesUpPct"])

    def test_get_coin_metrics_falls_back_to_markets_lookup(self):
        # Symbol not in the static map → we expect first a /coins/markets
        # call to resolve the id, then the /coins/<id> fetch.
        service = CoinGeckoService()
        markets_payload = [
            {"id": "fakecoin", "symbol": "fak", "market_cap": 5_000_000},
            {"id": "fakecoin-fork", "symbol": "fak", "market_cap": 3_000_000},
        ]
        coin_payload = {
            "name": "FakeCoin",
            "market_data": {"market_cap": {"usd": 5_000_000}},
            "community_data": {},
            "developer_data": {},
        }
        responses = iter([_response(markets_payload), _response(coin_payload)])
        with patch("app.coingecko_service.acquire_rate_limit", return_value=True), patch(
            "app.coingecko_service.requests.get",
            side_effect=lambda *a, **kw: next(responses),
        ) as get_mock:
            metrics = service.get_coin_metrics("FAK/USD")

        self.assertEqual(2, get_mock.call_count)
        # Ordered by market_cap desc, so "fakecoin" wins
        self.assertEqual("fakecoin", metrics["coinId"])

    def test_coin_metrics_cache_hits_avoid_second_request(self):
        service = CoinGeckoService()
        coin_payload = {
            "name": "Bitcoin",
            "market_data": {"market_cap": {"usd": 1}},
            "community_data": {},
            "developer_data": {},
        }
        with patch("app.coingecko_service.acquire_rate_limit", return_value=True), patch(
            "app.coingecko_service.requests.get",
            return_value=_response(coin_payload),
        ) as get_mock:
            service.get_coin_metrics("BTC/USD")
            calls_after_first = get_mock.call_count
            service.get_coin_metrics("BTC/USD")
            calls_after_second = get_mock.call_count
        self.assertEqual(calls_after_first, calls_after_second)

    def test_get_fear_greed_index_unwraps_data_envelope(self):
        service = CoinGeckoService()
        payload = {
            "data": [
                {
                    "value": "45",
                    "value_classification": "Fear",
                    "timestamp": "1715000000",
                }
            ]
        }
        with patch("app.coingecko_service.acquire_rate_limit", return_value=True), patch(
            "app.coingecko_service.requests.get",
            return_value=_response(payload),
        ):
            snapshot = service.get_fear_greed_index()
        self.assertEqual(45, snapshot["value"])
        self.assertEqual("Fear", snapshot["classification"])

    def test_get_fear_greed_index_returns_none_on_invalid_payload(self):
        service = CoinGeckoService()
        with patch("app.coingecko_service.acquire_rate_limit", return_value=True), patch(
            "app.coingecko_service.requests.get",
            return_value=_response({"unexpected": "shape"}),
        ):
            snapshot = service.get_fear_greed_index()
        self.assertIsNone(snapshot)

    def test_rate_limit_skip_returns_none(self):
        service = CoinGeckoService()
        with patch("app.coingecko_service.acquire_rate_limit", return_value=False), patch(
            "app.coingecko_service.requests.get"
        ) as get_mock:
            metrics = service.get_coin_metrics("BTC/USD")
            fg = service.get_fear_greed_index()
        get_mock.assert_not_called()
        self.assertIsNone(metrics)
        self.assertIsNone(fg)


if __name__ == "__main__":
    unittest.main()
