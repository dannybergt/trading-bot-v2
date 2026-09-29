"""Training uses every row the model's features allow -- and no made-up label.

Anlass (verifier N1, 2026-09-29, lokal bestaetigt 2026-09-30):
`prepare_features` rief `dropna()` ueber *alle* Spalten. `calculate_indicators`
legt auch SMA_100/SMA_200 an, die das Modell gar nicht liest; SMA_200 braucht
200 Bars. Gemessen mit echten Indikatoren:

    Bars   Zeilen vorher   Zeilen nur nach Features   trainiert vorher
     126         0               ~77                   nein
     181         0               132                   nein  (Platzhalter 6M)
     260        61               211                   ja, auf 61
     366       167               317                   ja

Die Standardansicht (6M: ~126 Handelstage ueber yfinance, 181 im Platzhalter)
trainierte damit nie, und der Retrain-Zyklus (`period="6mo"`) ebenso.

Dazu: die letzte Zeile hat keinen naechsten Schlusskurs; `NaN > x` ist False,
sie ging also als erfundenes DOWN ins Training.
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

import numpy as np
import pandas as pd

from app.analysis import calculate_indicators
from app.ml_models import MODEL_FEATURE_COLS, PricePredictor


def _bars(n: int, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    frame = pd.DataFrame(
        {
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": rng.integers(100_000, 1_000_000, n),
        },
        index=idx,
    )
    return calculate_indicators(frame)


class TrainingRowsTests(unittest.TestCase):
    def test_six_months_of_bars_leave_rows_to_train_on(self):
        """126 Handelstage = die 6M-Ansicht ueber yfinance."""
        df = _bars(126)
        self.assertTrue(df["SMA_200"].isna().all(), "premise: SMA_200 not warm yet")
        data, cols = PricePredictor().prepare_features(df)
        self.assertGreaterEqual(len(data), 60, "a 6-month history must leave rows to learn from")
        self.assertFalse(data[cols].isna().any().any())

    def test_placeholder_six_months_trains(self):
        predictor = PricePredictor()
        predictor.train(_bars(181))
        self.assertTrue(predictor.is_trained, "the 181-bar 6M frame must train")

    def test_columns_the_model_never_reads_do_not_cost_rows(self):
        df = _bars(260)
        with_sma = PricePredictor().prepare_features(df)[0]
        without_sma = PricePredictor().prepare_features(df.drop(columns=["SMA_100", "SMA_200"]))[0]
        self.assertEqual(len(without_sma), len(with_sma))

    def test_last_row_has_no_invented_label(self):
        df = _bars(150)
        data, _ = PricePredictor().prepare_features(df)
        self.assertLess(data.index[-1], df.index[-1], "the last bar has no next close to label from")
        # every label matches the real next close
        closes = df["Close"]
        for ts, label in data["Target"].items():
            pos = closes.index.get_loc(ts)
            self.assertEqual(int(closes.iloc[pos + 1] > closes.iloc[pos]), int(label))

    def test_feature_list_is_the_models(self):
        """Premise of the fix: SMA_100/SMA_200 are not model features."""
        self.assertNotIn("SMA_200", MODEL_FEATURE_COLS)
        self.assertNotIn("SMA_100", MODEL_FEATURE_COLS)


if __name__ == "__main__":
    unittest.main()
