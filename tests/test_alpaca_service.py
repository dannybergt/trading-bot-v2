"""Alpaca REST/stream adapter tests — the shapes the SDK really returns.

No network: the SDK client is replaced by a recorder. What is tested is
the contract between our adapter and the data API, which no unit test
held before — the deployed instance served charts ending five months in
the past for as long as Alpaca was configured (found 2026-09-16).
"""
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.alpaca_service import AlpacaService  # noqa: E402
from app.alpaca_stream import _iso_timestamp  # noqa: E402


class _Bars:
    def __init__(self, df):
        self.df = df


class _RecordingApi:
    """Behaves like the data API: pages ascending from `start` unless
    `sort=desc`, and `limit` cuts the page."""

    def __init__(self, days: int = 400):
        end = pd.Timestamp("2026-09-16", tz="America/New_York")
        self.all_bars = pd.DataFrame(
            {"open": 1.0, "high": 2.0, "low": 0.5, "close": [float(i) for i in range(days)],
             "volume": 10, "trade_count": 1, "vwap": 1.0},
            index=pd.bdate_range(end=end, periods=days, name="timestamp"),
        )
        self.calls = []

    def get_bars(self, symbol, timeframe, start=None, end=None, adjustment="raw", limit=None, feed=None, asof=None, sort=None):
        self.calls.append({"symbol": symbol, "start": start, "limit": limit, "sort": sort})
        window = self.all_bars[self.all_bars.index >= pd.Timestamp(start, tz="America/New_York")]
        if sort is not None and str(getattr(sort, "value", sort)) == "desc":
            window = window.iloc[::-1]
        if limit:
            window = window.iloc[:limit]
        return _Bars(window)

    get_crypto_bars = get_bars


class AlpacaBarsTests(unittest.TestCase):
    def _service(self, api):
        svc = AlpacaService(api_key="k", secret_key="s")
        svc.api = api
        return svc

    def test_get_bars_df_returns_the_newest_bars_ascending(self):
        # Vorher: `start` = heute - 2*limit Tage und `limit` = 260 -> die
        # API lieferte die AELTESTEN 260 Bars des Fensters, der Chart endete
        # Monate vor heute (AAPL/AMZN/SPY: 2026-04-27, BTC/USD: 2025-12-29).
        api = _RecordingApi(days=400)
        df = self._service(api).get_bars_df("AAPL", timeframe="1Day", limit=260)

        self.assertEqual(len(df), 260)
        self.assertTrue(df.index.is_monotonic_increasing)
        self.assertEqual(df.index[-1].date().isoformat(), "2026-09-16")
        self.assertEqual(float(df["Close"].iloc[-1]), 399.0)  # der juengste Bar
        self.assertEqual(str(getattr(api.calls[0]["sort"], "value", api.calls[0]["sort"])), "desc")

    def test_get_bars_df_without_desc_would_end_in_the_past(self):
        # Negativkontrolle am Fake: ohne `sort=desc` verhaelt sich die API
        # genau so, wie der Bug aussah — der Fake bildet das ab.
        api = _RecordingApi(days=400)
        window = api.get_bars("AAPL", "1Day", start="2025-04-15", limit=260).df
        self.assertLess(window.index[-1], pd.Timestamp("2026-06-01", tz="America/New_York"))


class StreamTimestampTests(unittest.TestCase):
    def test_nanosecond_int_becomes_iso_utc(self):
        # Stream-Bars tragen den Zeitstempel als Nanosekunden-Int;
        # `.isoformat()` darauf warf je Symbol und Minute einen Fehler.
        ns = 1_758_049_920_000_000_000
        self.assertEqual(_iso_timestamp(ns), datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).isoformat())

    def test_pandas_timestamp_and_none_pass_through(self):
        self.assertEqual(_iso_timestamp(pd.Timestamp("2026-09-16T15:12:00Z")), "2026-09-16T15:12:00+00:00")
        self.assertIsNone(_iso_timestamp(None))
        self.assertIsNone(_iso_timestamp(""))


if __name__ == "__main__":
    unittest.main()
