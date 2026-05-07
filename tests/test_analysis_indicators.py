"""Verify the indicator surface that the chart layer depends on.

Phase 2 calls out MAs/EMAs/VWAP/RSI/MACD/Bollinger/ATR as the toggleable
overlays. We don't reimplement the indicators (they're delegated to the `ta`
library); we just verify the columns are present and finite for a normal
input series so the frontend chart never gets a missing-column surprise.
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.analysis import (  # noqa: E402
    calculate_indicators,
    compute_volume_profile,
    detect_support_resistance,
)


def _synthetic_ohlcv(n: int = 250) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    base = 100.0
    closes = base + np.cumsum(rng.normal(0, 1.0, n))
    highs = closes + np.abs(rng.normal(0, 0.5, n))
    lows = closes - np.abs(rng.normal(0, 0.5, n))
    opens = closes + rng.normal(0, 0.3, n)
    volumes = rng.integers(100_000, 5_000_000, n).astype(float)
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=pd.date_range("2025-01-01", periods=n, freq="D"),
    )


class IndicatorTests(unittest.TestCase):
    def test_calculate_indicators_includes_phase2_overlays(self):
        df = calculate_indicators(_synthetic_ohlcv())

        required = {
            "RSI",
            "MACD_12_26_9",
            "MACDs_12_26_9",
            "MACDh_12_26_9",
            "BBU_20_2.0",
            "BBL_20_2.0",
            "BBM_20_2.0",
            "SMA_20",
            "SMA_50",
            "SMA_100",
            "SMA_200",
            "EMA_12",
            "EMA_26",
            "ATR",
            "STOCH_K",
            "STOCH_D",
            "VWAP",
        }
        missing = required - set(df.columns)
        self.assertFalse(missing, msg=f"Missing indicator columns: {missing}")

    def test_vwap_monotonically_anchored_to_typical_price(self):
        df = calculate_indicators(_synthetic_ohlcv())
        # VWAP should be finite once volume has accumulated.
        self.assertFalse(df["VWAP"].iloc[10:].isna().any())
        # Within the price range of the series (cumulative volume-weighted avg
        # cannot escape the convex hull of typical prices).
        typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
        self.assertGreaterEqual(df["VWAP"].iloc[-1], typical.min())
        self.assertLessEqual(df["VWAP"].iloc[-1], typical.max())

    def test_vwap_handles_zero_initial_volume(self):
        df = _synthetic_ohlcv(50)
        # First few rows have zero volume -> VWAP must not raise / blow up.
        df.loc[df.index[0], "Volume"] = 0
        df.loc[df.index[1], "Volume"] = 0
        result = calculate_indicators(df)
        self.assertIn("VWAP", result.columns)
        # Tail should still be finite.
        self.assertFalse(np.isinf(result["VWAP"].iloc[-1]))


class VolumeProfileTests(unittest.TestCase):
    def test_bins_sum_to_total_volume(self):
        df = _synthetic_ohlcv(120)
        profile = compute_volume_profile(df, bins=20)
        self.assertEqual(20, len(profile["bins"]))
        bin_sum = sum(b["volume"] for b in profile["bins"])
        self.assertAlmostEqual(profile["totalVolume"], bin_sum, places=2)
        self.assertAlmostEqual(df["Volume"].sum(), profile["totalVolume"], places=2)

    def test_point_of_control_falls_inside_price_range(self):
        df = _synthetic_ohlcv(120)
        profile = compute_volume_profile(df)
        self.assertIsNotNone(profile["pointOfControl"])
        self.assertGreaterEqual(profile["pointOfControl"], profile["minPrice"])
        self.assertLessEqual(profile["pointOfControl"], profile["maxPrice"])

    def test_handles_flat_price_series(self):
        # All closes equal -> max <= min path; should not crash.
        df = pd.DataFrame({
            "Open": [100.0] * 5,
            "High": [100.0] * 5,
            "Low": [100.0] * 5,
            "Close": [100.0] * 5,
            "Volume": [1000.0] * 5,
        }, index=pd.date_range("2025-01-01", periods=5, freq="D"))
        profile = compute_volume_profile(df)
        self.assertEqual([], profile["bins"])
        self.assertEqual(5000.0, profile["totalVolume"])


class SupportResistanceTests(unittest.TestCase):
    def _double_top_series(self) -> pd.DataFrame:
        # Construct a synthetic series with two clear swing highs near 110
        # and two swing lows near 90 so the detector should produce one
        # resistance cluster around 110 and one support cluster around 90.
        base = np.array(
            [100, 102, 104, 105, 108, 110, 108, 105, 100, 95, 92, 90, 92, 95, 100,
             103, 106, 108, 110, 109, 105, 100, 97, 92, 90, 91, 93, 96, 99, 102]
        ).astype(float)
        df = pd.DataFrame(
            {
                "Open": base,
                "High": base + 1.0,
                "Low": base - 1.0,
                "Close": base,
                "Volume": np.full(len(base), 1_000_000.0),
            },
            index=pd.date_range("2025-01-01", periods=len(base), freq="D"),
        )
        return df

    def test_detects_resistance_and_support_clusters(self):
        df = self._double_top_series()
        levels = detect_support_resistance(df, lookback=2, tolerance_pct=2.0)

        kinds = {level["kind"] for level in levels}
        self.assertIn("resistance", kinds)
        self.assertIn("support", kinds)

        resistance_prices = [lvl["price"] for lvl in levels if lvl["kind"] == "resistance"]
        support_prices = [lvl["price"] for lvl in levels if lvl["kind"] == "support"]
        self.assertTrue(any(108.0 <= p <= 113.0 for p in resistance_prices))
        self.assertTrue(any(87.0 <= p <= 92.0 for p in support_prices))

    def test_strength_increases_with_touches(self):
        df = self._double_top_series()
        levels = detect_support_resistance(df, lookback=2, tolerance_pct=2.0)
        # The double-top resistance cluster should aggregate >= 2 touches.
        for lvl in levels:
            if lvl["kind"] == "resistance" and 108.0 <= lvl["price"] <= 113.0:
                self.assertGreaterEqual(lvl["strength"], 2)
                return
        self.fail("No clustered resistance level found")

    def test_returns_empty_for_short_series(self):
        df = pd.DataFrame({"High": [100.0, 101.0], "Low": [99.0, 100.0]})
        self.assertEqual([], detect_support_resistance(df))


if __name__ == "__main__":
    unittest.main()
