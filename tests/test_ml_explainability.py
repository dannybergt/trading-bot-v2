"""Smoke tests for the ML predictor's explainability and zone-derivation paths.

The XGBoost training path needs a non-trivial dataset; we synthesize one with
clear separability so the model converges quickly and the contribution
extraction has signal.
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

from app.ml_models import PricePredictor, ML_AVAILABLE  # noqa: E402
from app.analysis import calculate_indicators  # noqa: E402


def _trending_ohlcv(n: int = 320) -> pd.DataFrame:
    """A series with a clear up-trend so the XGBoost classifier learns
    something other than random noise; allows feature attributions to be
    meaningful."""
    rng = np.random.default_rng(7)
    drift = np.linspace(0, 30, n)
    noise = rng.normal(0, 0.6, n)
    closes = 100.0 + drift + np.cumsum(noise) * 0.05
    highs = closes + np.abs(rng.normal(0, 0.4, n))
    lows = closes - np.abs(rng.normal(0, 0.4, n))
    opens = closes + rng.normal(0, 0.2, n)
    volumes = rng.integers(500_000, 5_000_000, n).astype(float)
    df = pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=pd.date_range("2025-01-01", periods=n, freq="D"),
    )
    df = calculate_indicators(df)
    # Add the fundamentals/sentiment columns the predictor expects.
    df["News_Sentiment"] = 0.1
    df["PE_Ratio"] = 25.0
    df["Forward_PE"] = 22.0
    df["Price_To_Book"] = 8.0
    return df


@unittest.skipUnless(ML_AVAILABLE, "ML deps missing")
class PricePredictorExplainabilityTests(unittest.TestCase):
    def test_prediction_carries_explanation_and_zones(self):
        df = _trending_ohlcv()
        predictor = PricePredictor()
        train_result = predictor.train(df)
        self.assertIn("accuracy", train_result)

        prediction = predictor.predict_next_movement(df)
        self.assertIsNotNone(prediction)
        assert prediction is not None  # for type narrowing

        self.assertIn(prediction["direction"], {"UP", "DOWN"})
        self.assertIsInstance(prediction["confidence"], float)

        explanation = prediction["explanation"]
        self.assertIsNotNone(explanation)
        assert explanation is not None
        self.assertEqual("xgboost_pred_contribs", explanation["method"])
        self.assertGreaterEqual(len(explanation["topFeatures"]), 1)
        for feature in explanation["topFeatures"]:
            self.assertIn(feature["direction"], {"up", "down"})
            self.assertIn("contribution", feature)
            self.assertIn("value", feature)
            self.assertIn("category", feature)
            self.assertIn(
                feature["category"],
                {"trend", "technical", "volume", "news", "fundamentals", "other"},
            )

        # Category roll-up shows up alongside per-feature contributions.
        self.assertIn("categories", explanation)
        self.assertGreaterEqual(len(explanation["categories"]), 1)
        for cat in explanation["categories"]:
            self.assertIn("category", cat)
            self.assertIn("label", cat)
            self.assertIn("contribution", cat)

        # Probabilities are explicit and sum to ~1.
        self.assertAlmostEqual(
            prediction["probabilityUp"] + prediction["probabilityDown"], 1.0, places=4
        )

        # Reasoning is a non-empty narrative referencing the top category.
        self.assertIsNotNone(prediction["reasoning"])
        self.assertGreater(len(prediction["reasoning"]), 0)

        zones = prediction["zones"]
        self.assertIsNotNone(zones)
        assert zones is not None
        self.assertEqual(prediction["direction"], zones["direction"])
        self.assertGreater(zones["currentPrice"], 0)
        self.assertGreater(zones["atr"], 0)

        if zones["direction"] == "UP":
            self.assertLess(zones["stopLoss"], zones["currentPrice"])
            self.assertGreater(zones["target"], zones["currentPrice"])
        else:
            self.assertGreater(zones["stopLoss"], zones["currentPrice"])
            self.assertLess(zones["target"], zones["currentPrice"])

        # Risk/reward ratio is positive (target distance > 0, stop distance > 0)
        self.assertIsNotNone(zones["riskReward"])
        self.assertGreater(zones["riskReward"], 0.0)

    def test_zones_skip_when_atr_unavailable(self):
        # Direct call into the static zone helper with no ATR set.
        latest = pd.DataFrame({"Close": [100.0], "ATR": [0.0]})
        zones = PricePredictor._compute_zones(latest, direction="UP", confidence=0.7)
        self.assertIsNone(zones)


if __name__ == "__main__":
    unittest.main()
