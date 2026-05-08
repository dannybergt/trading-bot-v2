"""Options-flow service tests.

yfinance Ticker is stubbed so no real network traffic happens. Verifies
expiry selection, ratio math, the ATM-IV window, top-strike sorting,
defensive fall-throughs, and the per-symbol cache.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import pandas as pd

from app.options_flow_service import OptionsFlowService, _select_expiry  # noqa: E402


def _ticker(*, expiries, calls, puts, last_close=100.0):
    chain = MagicMock()
    chain.calls = calls
    chain.puts = puts
    ticker = MagicMock()
    ticker.options = expiries
    ticker.option_chain = MagicMock(return_value=chain)
    ticker.history = MagicMock(
        return_value=pd.DataFrame(
            {"Close": [last_close]},
            index=pd.date_range(end=datetime.now(timezone.utc), periods=1, freq="D"),
        )
    )
    return ticker


def _calls_frame():
    return pd.DataFrame(
        [
            # In-the-money / OTM mix; ATM at 100, band 95-105
            {"strike": 90, "volume": 50, "openInterest": 200, "impliedVolatility": 0.45, "lastPrice": 11.0},
            {"strike": 100, "volume": 800, "openInterest": 1500, "impliedVolatility": 0.30, "lastPrice": 2.5},
            {"strike": 105, "volume": 600, "openInterest": 1200, "impliedVolatility": 0.32, "lastPrice": 1.5},
            {"strike": 120, "volume": 100, "openInterest": 300, "impliedVolatility": 0.55, "lastPrice": 0.4},
        ]
    )


def _puts_frame():
    return pd.DataFrame(
        [
            {"strike": 80, "volume": 300, "openInterest": 800, "impliedVolatility": 0.40, "lastPrice": 0.3},
            {"strike": 95, "volume": 700, "openInterest": 1000, "impliedVolatility": 0.34, "lastPrice": 1.2},
            {"strike": 100, "volume": 1200, "openInterest": 2000, "impliedVolatility": 0.31, "lastPrice": 2.4},
            {"strike": 110, "volume": 200, "openInterest": 400, "impliedVolatility": 0.38, "lastPrice": 11.5},
        ]
    )


class OptionsFlowServiceTests(unittest.TestCase):
    def test_select_expiry_picks_nearest_at_least_seven_days_out(self):
        today = datetime.now(timezone.utc).date()
        tomorrow = (today + timedelta(days=1)).isoformat()
        next_week = (today + timedelta(days=8)).isoformat()
        next_month = (today + timedelta(days=30)).isoformat()
        chosen = _select_expiry([tomorrow, next_week, next_month])
        self.assertEqual(next_week, chosen)

    def test_select_expiry_falls_back_when_all_inside_buffer(self):
        today = datetime.now(timezone.utc).date()
        chosen = _select_expiry([(today + timedelta(days=2)).isoformat()])
        self.assertEqual((today + timedelta(days=2)).isoformat(), chosen)

    def test_get_options_flow_aggregates_volume_oi_and_atm_iv(self):
        service = OptionsFlowService()
        next_week = (datetime.now(timezone.utc).date() + timedelta(days=8)).isoformat()
        ticker = _ticker(
            expiries=[next_week],
            calls=_calls_frame(),
            puts=_puts_frame(),
            last_close=100.0,
        )
        with patch("app.options_flow_service.acquire_rate_limit", return_value=True), patch(
            "app.options_flow_service.yf.Ticker", return_value=ticker
        ):
            flow = service.get_options_flow("AAPL", asset_class="stock")

        # Total volume: calls 50+800+600+100 = 1550; puts 300+700+1200+200 = 2400
        self.assertEqual(1550, flow["totalCallVolume"])
        self.assertEqual(2400, flow["totalPutVolume"])
        self.assertAlmostEqual(2400 / 1550, flow["putCallVolumeRatio"], places=3)
        # ATM band [95, 105] picks up call strikes 100 + 105 (IV 0.30, 0.32) and
        # put strikes 95 + 100 (IV 0.34, 0.31) → mean ≈ 0.3175
        self.assertAlmostEqual(
            (0.30 + 0.32 + 0.34 + 0.31) / 4,
            flow["avgImpliedVolatilityAtm"],
            places=3,
        )
        # Top calls by volume desc → 800, 600, 100 → strikes 100, 105, 120
        self.assertEqual([100.0, 105.0, 120.0], [row["strike"] for row in flow["topCalls"]])
        # Volume P/C 2400/1550 ≈ 1.55 → bearish skew
        self.assertEqual("bearish_skew", flow["putCallSignal"])
        self.assertEqual(next_week, flow["expiry"])
        self.assertEqual(100.0, flow["lastClose"])

    def test_crypto_asset_class_returns_empty_payload(self):
        service = OptionsFlowService()
        with patch("app.options_flow_service.yf.Ticker") as ticker_mock:
            flow = service.get_options_flow("BTC/USD", asset_class="crypto")
        ticker_mock.assert_not_called()
        self.assertIsNone(flow["expiry"])
        self.assertEqual(0, flow["totalCallVolume"])

    def test_no_expiries_returns_empty_payload_and_caches(self):
        service = OptionsFlowService()
        ticker = _ticker(expiries=[], calls=pd.DataFrame(), puts=pd.DataFrame())
        with patch("app.options_flow_service.acquire_rate_limit", return_value=True), patch(
            "app.options_flow_service.yf.Ticker", return_value=ticker
        ) as ticker_mock:
            service.get_options_flow("UNKNOWN", asset_class="stock")
            service.get_options_flow("UNKNOWN", asset_class="stock")
        # Cache hits on the second call → only one Ticker construction
        self.assertEqual(1, ticker_mock.call_count)

    def test_chain_failure_returns_empty_payload(self):
        service = OptionsFlowService()
        next_week = (datetime.now(timezone.utc).date() + timedelta(days=8)).isoformat()
        ticker = _ticker(expiries=[next_week], calls=pd.DataFrame(), puts=pd.DataFrame())
        ticker.option_chain = MagicMock(side_effect=Exception("yfinance boom"))
        with patch("app.options_flow_service.acquire_rate_limit", return_value=True), patch(
            "app.options_flow_service.yf.Ticker", return_value=ticker
        ):
            flow = service.get_options_flow("AAPL", asset_class="stock")
        self.assertIsNone(flow["putCallVolumeRatio"])
        self.assertEqual(0, flow["totalCallVolume"])

    def test_rate_limit_skip_returns_empty(self):
        service = OptionsFlowService()
        with patch("app.options_flow_service.acquire_rate_limit", return_value=False), patch(
            "app.options_flow_service.yf.Ticker"
        ) as ticker_mock:
            flow = service.get_options_flow("AAPL", asset_class="stock")
        ticker_mock.assert_not_called()
        self.assertIsNone(flow["expiry"])

    def test_zero_call_volume_yields_none_ratio(self):
        service = OptionsFlowService()
        next_week = (datetime.now(timezone.utc).date() + timedelta(days=8)).isoformat()
        empty_calls = pd.DataFrame(
            [{"strike": 100, "volume": 0, "openInterest": 0, "impliedVolatility": 0.3, "lastPrice": 1.0}]
        )
        only_puts = pd.DataFrame(
            [{"strike": 100, "volume": 100, "openInterest": 200, "impliedVolatility": 0.3, "lastPrice": 1.0}]
        )
        ticker = _ticker(expiries=[next_week], calls=empty_calls, puts=only_puts, last_close=100.0)
        with patch("app.options_flow_service.acquire_rate_limit", return_value=True), patch(
            "app.options_flow_service.yf.Ticker", return_value=ticker
        ):
            flow = service.get_options_flow("AAPL", asset_class="stock")
        # Avoid divide-by-zero blow-up
        self.assertIsNone(flow["putCallVolumeRatio"])


if __name__ == "__main__":
    unittest.main()
