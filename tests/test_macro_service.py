"""Tests for the macro context adapter.

Stubs the yfinance Ticker so no real network traffic happens. Verifies the
shape of the snapshot, change-percent math, and the in-process cache.
"""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import pandas as pd

from app.macro_service import MacroService  # noqa: E402


def _history_frame(closes: list[float]):
    index = pd.date_range(end=datetime(2026, 5, 8), periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=index)


class MacroServiceTests(unittest.TestCase):
    def _ticker_mock(self, frame_by_symbol: dict[str, pd.DataFrame]):
        def _factory(symbol):
            ticker = MagicMock()
            ticker.history = MagicMock(return_value=frame_by_symbol.get(symbol, pd.DataFrame()))
            return ticker

        return _factory

    def test_snapshot_returns_value_and_change_for_each_instrument(self):
        frames = {
            "^VIX": _history_frame([14.5, 15.0]),
            "^TNX": _history_frame([4.10, 4.15]),
            "DX-Y.NYB": _history_frame([105.20, 104.80]),
        }
        service = MacroService()
        with patch("app.macro_service.acquire_rate_limit", return_value=True), patch(
            "app.macro_service.yf.Ticker", side_effect=self._ticker_mock(frames)
        ):
            snapshot = service.get_context()

        self.assertEqual({"vix", "yield10y", "dxy"}, set(snapshot.keys()))
        self.assertAlmostEqual(15.0, snapshot["vix"]["value"])
        # changePct = (15.0 - 14.5) / 14.5 * 100 ≈ 3.448
        self.assertAlmostEqual(3.4483, snapshot["vix"]["changePct"], places=3)
        self.assertEqual("^VIX", snapshot["vix"]["symbol"])
        self.assertEqual("2026-05-08", snapshot["vix"]["asOf"])
        self.assertAlmostEqual(4.15, snapshot["yield10y"]["value"])
        self.assertAlmostEqual(104.80, snapshot["dxy"]["value"])

    def test_empty_frame_yields_none_values_without_failure(self):
        frames = {
            "^VIX": pd.DataFrame(),
            "^TNX": pd.DataFrame(),
            "DX-Y.NYB": pd.DataFrame(),
        }
        service = MacroService()
        with patch("app.macro_service.acquire_rate_limit", return_value=True), patch(
            "app.macro_service.yf.Ticker", side_effect=self._ticker_mock(frames)
        ):
            snapshot = service.get_context()

        for key in ("vix", "yield10y", "dxy"):
            self.assertIsNone(snapshot[key]["value"])
            self.assertIsNone(snapshot[key]["changePct"])

    def test_rate_limit_skip_returns_empty_payload_without_yfinance_call(self):
        service = MacroService()
        with patch("app.macro_service.acquire_rate_limit", return_value=False), patch(
            "app.macro_service.yf.Ticker"
        ) as ticker_mock:
            snapshot = service.get_context()
        ticker_mock.assert_not_called()
        for key in ("vix", "yield10y", "dxy"):
            self.assertIsNone(snapshot[key]["value"])

    def test_cache_avoids_second_yfinance_call(self):
        frames = {
            "^VIX": _history_frame([14.5, 15.0]),
            "^TNX": _history_frame([4.10, 4.15]),
            "DX-Y.NYB": _history_frame([105.20, 104.80]),
        }
        ticker_factory = MagicMock(side_effect=self._ticker_mock(frames))
        service = MacroService()
        with patch("app.macro_service.acquire_rate_limit", return_value=True), patch(
            "app.macro_service.yf.Ticker", ticker_factory
        ):
            service.get_context()
            calls_after_first = ticker_factory.call_count
            service.get_context()
            calls_after_second = ticker_factory.call_count

        self.assertEqual(calls_after_first, calls_after_second)


if __name__ == "__main__":
    unittest.main()
