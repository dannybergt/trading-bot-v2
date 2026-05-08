"""Per-symbol PricePredictor persistence tests.

Trains a tiny XGBoost model on a synthetic linearly-separable frame,
persists it, reloads it, and verifies the on-disk model produces the
same predictions and that staleness math respects the TTL.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

import tempfile

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


class MLPersistenceTests(unittest.TestCase):
    def setUp(self):
        # Redirect MODEL_DIR to a temp folder so we don't pollute the
        # backend container's volume.
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["ML_MODEL_DIR"] = self._tmp.name
        # Force a re-import so the module-level MODEL_DIR picks up the env
        for module_name in list(sys.modules):
            if module_name.startswith("app.ml_persistence"):
                del sys.modules[module_name]
        from app import ml_persistence  # noqa: WPS433

        self.ml_persistence = ml_persistence

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("ML_MODEL_DIR", None)

    def _build_synthetic_predictor(self):
        from app.ml_models import PricePredictor
        import pandas as pd

        # 200 bars with a clear linear trend so the model can fit.
        rows = 200
        closes = [100 + i * 0.5 for i in range(rows)]
        df = pd.DataFrame({"Close": closes})
        for col in (
            "RSI", "SMA_20", "SMA_50", "EMA_12", "EMA_26",
            "BBL_20_2.0", "BBM_20_2.0", "BBU_20_2.0",
            "MACD_12_26_9", "MACDh_12_26_9", "MACDs_12_26_9",
            "Volume", "ATR", "STOCH_K", "STOCH_D",
            "News_Sentiment", "PE_Ratio", "Forward_PE", "Price_To_Book",
        ):
            df[col] = 0.5
        # Make Volume a proper int
        df["Volume"] = 1_000_000
        predictor = PricePredictor()
        metrics = predictor.train(df)
        return predictor, metrics, df

    def test_save_load_roundtrip_recovers_predictor(self):
        from app.ml_models import PricePredictor

        predictor, metrics, df = self._build_synthetic_predictor()
        if not predictor.is_trained:
            self.skipTest("XGBoost training did not converge on the synthetic frame")

        metadata = self.ml_persistence.save_predictor(
            "AAPL",
            predictor,
            accuracy=metrics.get("accuracy", 0.0),
            features=metrics.get("features", []),
            n_samples=len(df.index),
        )
        self.assertIsNotNone(metadata)
        self.assertEqual("AAPL", metadata["symbol"])
        self.assertEqual(len(df.index), metadata["nSamples"])

        loaded = self.ml_persistence.load_predictor("AAPL", PricePredictor)
        self.assertIsNotNone(loaded)
        loaded_predictor, loaded_meta = loaded
        self.assertTrue(loaded_predictor.is_trained)
        self.assertEqual(metadata["accuracy"], loaded_meta["accuracy"])

        # Same input → same prediction
        original_pred = predictor.predict_next_movement(df, user=None)
        recovered_pred = loaded_predictor.predict_next_movement(df, user=None)
        self.assertEqual(original_pred["direction"], recovered_pred["direction"])
        self.assertAlmostEqual(
            original_pred["probabilityUp"], recovered_pred["probabilityUp"], places=6
        )

    def test_load_returns_none_when_no_model_exists(self):
        from app.ml_models import PricePredictor

        loaded = self.ml_persistence.load_predictor("UNSEEN", PricePredictor)
        self.assertIsNone(loaded)

    def test_is_stale_true_for_old_metadata(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        self.assertTrue(self.ml_persistence.is_stale({"trainedAt": old}, ttl_hours=24))

    def test_is_stale_false_for_fresh_metadata(self):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        self.assertFalse(
            self.ml_persistence.is_stale({"trainedAt": recent}, ttl_hours=24)
        )

    def test_is_stale_true_for_missing_metadata(self):
        self.assertTrue(self.ml_persistence.is_stale(None))
        self.assertTrue(self.ml_persistence.is_stale({}))

    def test_unsafe_symbol_is_rejected(self):
        from app.ml_models import PricePredictor

        with self.assertRaises(ValueError):
            self.ml_persistence._safe_symbol("..")
        with self.assertRaises(ValueError):
            self.ml_persistence._safe_symbol("")


if __name__ == "__main__":
    unittest.main()
