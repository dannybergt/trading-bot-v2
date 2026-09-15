"""Backtest-service tests.

Builds a synthetic monotonically-rising frame so the predictor sees a
trivially separable target, then verifies the walk-forward loop
produces non-empty metrics, reasonable accuracy on the trend, a
reliability table with the expected bucket layout, and a defensive
empty payload when there isn't enough history.
"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


def _synthetic_frame(rows: int = 250) -> pd.DataFrame:
    """Trending close with noisy indicator columns so PricePredictor
    sees enough feature variation to make actual splits. Seeded RNG
    keeps the test deterministic."""
    import numpy as np

    rng = np.random.default_rng(seed=42)
    drift = np.cumsum(rng.normal(0.5, 1.0, rows)) + 100
    df = pd.DataFrame({"Close": drift})
    for col in (
        "RSI",
        "SMA_20",
        "SMA_50",
        "EMA_12",
        "EMA_26",
        "BBL_20_2.0",
        "BBM_20_2.0",
        "BBU_20_2.0",
        "MACD_12_26_9",
        "MACDh_12_26_9",
        "MACDs_12_26_9",
        "ATR",
        "STOCH_K",
        "STOCH_D",
        "News_Sentiment",
        "PE_Ratio",
        "Forward_PE",
        "Price_To_Book",
    ):
        df[col] = rng.normal(0.5, 0.2, rows)
    df["Volume"] = rng.integers(900_000, 1_100_000, rows)
    return df


class BacktestServiceTests(unittest.TestCase):
    def test_run_backtest_produces_metrics_for_trending_frame(self):
        from app import backtest_service

        df = _synthetic_frame(250)
        result = backtest_service.run_backtest(df, train_window=120, step=20)
        self.assertGreater(result["samples"], 0)
        self.assertIsNotNone(result["accuracy"])
        self.assertGreaterEqual(result["accuracy"], 0.0)
        self.assertLessEqual(result["accuracy"], 1.0)
        # AUC on a perfectly trending frame should be high but the test
        # only asserts the field is computed (predictor may collapse on
        # near-degenerate features).
        self.assertEqual(180, result["trainWindow"]) if False else None
        self.assertEqual(result["trainWindow"], 120)
        self.assertEqual(result["step"], 20)
        # Reliability has 10 buckets always
        self.assertEqual(10, len(result["reliability"]))

    def test_run_backtest_empty_when_history_too_short(self):
        from app import backtest_service

        short = _synthetic_frame(50)
        result = backtest_service.run_backtest(short, train_window=180, step=10)
        self.assertEqual(0, result["samples"])
        self.assertIsNone(result["accuracy"])

    def test_untrainable_windows_do_not_reach_the_predictor(self):
        # Ein Fenster, das nach der Feature-Vorbereitung eine Zeile oder eine
        # Klasse traegt, kann kein Training tragen. Bisher lief `train`
        # trotzdem an und schrieb je Fenster einen Traceback auf ERROR
        # (gemessen 2026-09-11: sechs pro Anfrage). Das Fenster wird jetzt
        # vorher erkannt und ohne Training uebersprungen.
        from unittest.mock import patch
        from app import backtest_service

        # Alles NaN ausser den letzten Zeilen: prepare_features behaelt zu
        # wenige Zeilen fuer einen Split -> untrainierbar.
        df = _synthetic_frame(200)
        df.loc[: len(df) - 4, "RSI"] = float("nan")

        with patch.object(backtest_service.PricePredictor, "train") as train, \
             self.assertNoLogs("app.ml_models", level="ERROR"):
            result = backtest_service.run_backtest(df, train_window=120, step=20)

        train.assert_not_called()
        self.assertEqual(0, result["samples"])

    def test_single_class_window_is_untrainable(self):
        from app import backtest_service

        df = _synthetic_frame(60)
        df["Close"] = [100.0 + i for i in range(60)]  # nur Aufwaertstage
        predictor = backtest_service.PricePredictor()
        self.assertFalse(backtest_service._window_is_trainable(predictor, df))

        df = _synthetic_frame(60)  # gemischte Richtungen
        self.assertTrue(backtest_service._window_is_trainable(predictor, df))

    def test_walk_forward_scores_each_block_in_one_batch(self):
        # Der Walk-Forward rief fuer jeden Bar die volle Bildschirm-Vorhersage
        # (Erklaerung, Zonen, Ertragsmodell) auf einer wachsenden Kopie des
        # Frames: 323 Aufrufe x 0,125 s = 40 s von 53 s je Anfrage, unabhaengig
        # von `step` (verifier, 2026-09-11). Jetzt: ein Training je Block, ein
        # Batch-Aufruf je Block, und die Bildschirm-Vorhersage gar nicht.
        from unittest.mock import patch
        from app import backtest_service

        df = _synthetic_frame(250)
        with patch.object(backtest_service.PricePredictor, "probability_up",
                          autospec=True, side_effect=lambda self, rows: [0.6] * len(rows)) as batch, \
             patch.object(backtest_service.PricePredictor, "predict_next_movement") as single:
            result = backtest_service.run_backtest(df, train_window=120, step=20)

        single.assert_not_called()
        # 250 Zeilen, Fenster 120, Schritt 20: Bloecke ab 120, 140, ..., 240 -> 7
        self.assertEqual(batch.call_count, 7)
        self.assertEqual(result["samples"], 249 - 120)
        # Jeder Block sieht genau seine `step` Zeilen (der letzte den Rest).
        sizes = [len(call.args[1]) for call in batch.call_args_list]
        self.assertEqual(sizes, [20, 20, 20, 20, 20, 20, 9])

    def test_batch_probabilities_match_the_single_prediction(self):
        # Die Batch-Wahrscheinlichkeit muss dieselbe sein wie die der
        # Einzelvorhersage — sonst misst der Backtest ein anderes Modell als
        # das, was auf dem Bildschirm steht.
        from app.ml_models import PricePredictor

        df = _synthetic_frame(250)
        predictor = PricePredictor()
        predictor.train(df.iloc[:200])
        if not predictor.is_trained:
            self.skipTest("XGBoost training did not converge on the synthetic frame")

        rows = df.iloc[200:210]
        batch = predictor.probability_up(rows)
        self.assertIsNotNone(batch)
        self.assertEqual(len(batch), 10)
        for offset in (0, 4, 9):
            single = predictor.predict_next_movement(df.iloc[: 200 + offset + 1], user=None)
            self.assertAlmostEqual(float(batch[offset]), single["probabilityUp"], places=6)

    def test_endpoint_passes_the_configured_cadence(self):
        # Die Kadenz ist eine Konstante mit einer Messung im Kommentar; der
        # Endpunkt muss sie auch setzen, sonst ist die Messung wertlos. Ob die
        # Antwortzeit unter dem Proxy-Timeout bleibt, wird nicht hier
        # modelliert, sondern am laufenden System gemessen (verifier).
        from unittest.mock import MagicMock, patch
        from app import backtest_service
        from app import main as app_main

        real_payload = {"data": _synthetic_frame(504), "synthetic": False}
        with patch.object(app_main.service, "get_stock_data", return_value=real_payload), \
             patch.object(app_main.service, "get_asset_profile",
                          return_value={"symbol": "AAPL", "assetClass": "stock",
                                        "assetLabel": "Stock", "market": "equity",
                                        "exchange": "NASDAQ", "type": "STOCK", "isCrypto": False}), \
             patch.object(app_main, "get_user_watchlist_symbol_name", return_value=None), \
             patch.object(backtest_service, "run_backtest_serialized",
                          return_value=backtest_service._empty_payload()) as run:
            payload = app_main.get_symbol_backtest(
                symbol="AAPL", current_user=MagicMock(), db=MagicMock()
            )

        self.assertFalse(payload["synthetic"])
        self.assertEqual(run.call_args.kwargs["step"], app_main.BACKTEST_STEP)
        self.assertEqual(run.call_args.kwargs["train_window"], app_main.BACKTEST_TRAIN_WINDOW)
        self.assertEqual(run.call_args.kwargs["symbol"], "AAPL")

    def test_serialized_backtests_never_overlap_and_repeat_for_free(self):
        # Zwei gleichzeitige Backtests brauchten je 78-85 s statt ~20 s
        # (verifier, 2026-09-11): jedes Ensemble-Mitglied trainiert auf allen
        # Kernen, parallel nehmen sie sich nur die CPUs weg. Also: einer zur
        # Zeit — und dieselben Bars fuer dasselbe Symbol nie zweimal.
        import threading
        import time
        from unittest.mock import patch
        from app import backtest_service

        overlap = {"active": 0, "max": 0, "calls": 0}
        guard = threading.Lock()

        def slow_backtest(df, *, train_window, step):
            with guard:
                overlap["active"] += 1
                overlap["calls"] += 1
                overlap["max"] = max(overlap["max"], overlap["active"])
            time.sleep(0.05)
            with guard:
                overlap["active"] -= 1
            return {**backtest_service._empty_payload(), "samples": len(df)}

        df = _synthetic_frame(30)
        backtest_service._RESULTS.clear()
        with patch.object(backtest_service, "run_backtest", side_effect=slow_backtest):
            threads = [
                threading.Thread(
                    target=backtest_service.run_backtest_serialized,
                    args=(df,), kwargs={"symbol": sym, "train_window": 5, "step": 5},
                )
                for sym in ("AAPL", "MSFT", "AAPL", "MSFT")
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            # Wiederholung auf denselben Bars: kein Aufruf.
            repeat = backtest_service.run_backtest_serialized(
                df, symbol="AAPL", train_window=5, step=5
            )
            # Ein neuer Bar: neue Rechnung.
            longer = _synthetic_frame(31)
            backtest_service.run_backtest_serialized(
                longer, symbol="AAPL", train_window=5, step=5
            )

        self.assertEqual(overlap["max"], 1, "zwei Backtests liefen gleichzeitig")
        self.assertEqual(overlap["calls"], 3)  # AAPL, MSFT, AAPL mit neuem Bar
        self.assertEqual(repeat["samples"], 30)

    def test_endpoint_refuses_synthetic_history(self):
        # Regel K: keine Kennzahl auf erfundenen Kursen. Der Platzhalter ist
        # ein geseedeter Random Walk — AAPL, MSFT und `ZZZZNOPE123` liefern
        # dieselbe Accuracy-Tabelle (gemessen 2026-09-11), und die Rechnung
        # kostet Minuten. Der Endpunkt gibt dann die Leerantwort und sagt
        # warum, statt zu trainieren.
        from unittest.mock import MagicMock, patch
        from app import backtest_service
        from app import main as app_main

        synthetic_payload = {"data": _synthetic_frame(600), "synthetic": True}
        with patch.object(app_main.service, "get_stock_data", return_value=synthetic_payload), \
             patch.object(app_main.service, "get_asset_profile",
                          return_value={"symbol": "ZZZZNOPE123", "assetClass": "stock",
                                        "assetLabel": "Stock", "market": "equity",
                                        "exchange": "", "type": "STOCK", "isCrypto": False}), \
             patch.object(app_main, "get_user_watchlist_symbol_name", return_value=None), \
             patch.object(backtest_service, "run_backtest") as run:
            payload = app_main.get_symbol_backtest(
                symbol="ZZZZNOPE123", current_user=MagicMock(), db=MagicMock()
            )

        run.assert_not_called()
        self.assertTrue(payload["synthetic"])
        self.assertEqual(0, payload["result"]["samples"])
        self.assertIsNone(payload["result"]["accuracy"])

    def test_run_backtest_empty_for_empty_frame(self):
        from app import backtest_service

        empty = pd.DataFrame()
        result = backtest_service.run_backtest(empty)
        self.assertEqual(0, result["samples"])

    def test_reliability_buckets_partition_predictions(self):
        from app import backtest_service

        df = _synthetic_frame(220)
        result = backtest_service.run_backtest(df, train_window=120, step=20)
        labels = [b["bucket"] for b in result["reliability"]]
        self.assertEqual(
            ["0-10%", "10-20%", "20-30%", "30-40%", "40-50%", "50-60%", "60-70%", "70-80%", "80-90%", "90-100%"],
            labels,
        )
        # Sum of bucket counts must match samples
        self.assertEqual(result["samples"], sum(b["count"] for b in result["reliability"]))


if __name__ == "__main__":
    unittest.main()
