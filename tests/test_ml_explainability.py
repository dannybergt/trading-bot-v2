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


class _UserStub:
    def __init__(
        self,
        *,
        trade_fee_percent=0,
        trade_fee_absolute=0,
        capital_gains_tax_bps=0,
        income_tax_bps=0,
        min_target_yield=0,
    ):
        self.trade_fee_percent = trade_fee_percent
        self.trade_fee_absolute = trade_fee_absolute
        self.capital_gains_tax_bps = capital_gains_tax_bps
        self.income_tax_bps = income_tax_bps
        self.min_target_yield = min_target_yield


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

    def test_yield_model_subtracts_fees_and_taxes_from_target(self):
        zones = {
            "direction": "UP",
            "currentPrice": 100.0,
            "atr": 2.0,
            "entryLow": 99.0,
            "entryHigh": 100.0,
            "stopLoss": 97.0,
            "target": 110.0,
            "riskReward": 3.33,
        }
        user = _UserStub(
            trade_fee_percent=0,
            trade_fee_absolute=1,  # 1 EUR per leg, on a 100 EUR price -> 1% per leg, 2% round trip
            capital_gains_tax_bps=2500,  # 25%
            min_target_yield=5,  # 5% net floor
        )
        enriched = PricePredictor._enrich_with_yield_model(zones, user)
        self.assertIsNotNone(enriched)
        assert enriched is not None
        # Gross target = (110 - 100)/100 * 100 = 10%
        self.assertAlmostEqual(10.0, enriched["grossTargetPct"], places=2)
        # Round-trip fee = 2%
        self.assertAlmostEqual(2.0, enriched["feeRoundTripPct"], places=2)
        # After fees: 8%; tax 25% of 8% = 2%; net = 6%
        self.assertAlmostEqual(6.0, enriched["netTargetPct"], places=2)
        # 6% net beats 5% min -> meetsMinimum True
        self.assertTrue(enriched["meetsMinimum"])

    def test_yield_model_flags_when_below_minimum(self):
        zones = {
            "direction": "UP",
            "currentPrice": 100.0,
            "atr": 1.0,
            "entryLow": 99.0,
            "entryHigh": 100.0,
            "stopLoss": 98.5,
            "target": 102.0,  # only 2% gross
        }
        user = _UserStub(
            trade_fee_percent=0,
            trade_fee_absolute=1,  # 1% per leg, 2% round trip
            capital_gains_tax_bps=0,
            min_target_yield=5,
        )
        enriched = PricePredictor._enrich_with_yield_model(zones, user)
        # 2% gross - 2% fees - 0% tax = 0% net, way under 5% threshold
        self.assertAlmostEqual(0.0, enriched["netTargetPct"], places=2)
        self.assertFalse(enriched["meetsMinimum"])

    def test_yield_model_short_uses_absolute_target_distance(self):
        zones = {
            "direction": "DOWN",
            "currentPrice": 100.0,
            "atr": 2.0,
            "entryLow": 100.0,
            "entryHigh": 101.0,
            "stopLoss": 103.0,
            "target": 90.0,
        }
        user = _UserStub(min_target_yield=5)
        enriched = PricePredictor._enrich_with_yield_model(zones, user)
        # For DOWN, the target distance is abs(target - current)/current.
        self.assertAlmostEqual(10.0, enriched["grossTargetPct"], places=2)

    def test_zones_skip_when_atr_unavailable(self):
        # Direct call into the static zone helper with no ATR set.
        latest = pd.DataFrame({"Close": [100.0], "ATR": [0.0]})
        zones = PricePredictor._compute_zones(latest, direction="UP", confidence=0.7)
        self.assertIsNone(zones)


if __name__ == "__main__":
    unittest.main()
