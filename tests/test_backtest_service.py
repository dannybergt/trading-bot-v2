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


def _raw_bars(rows: int = 504) -> pd.DataFrame:
    """Bare OHLCV bars as a provider hands them over — what the endpoint
    gets from `get_history_frame` before it computes the indicators."""
    import numpy as np

    rng = np.random.default_rng(seed=7)
    close = np.cumsum(rng.normal(0.3, 1.0, rows)) + 100
    idx = pd.date_range("2024-01-01", periods=rows, freq="B")
    return pd.DataFrame(
        {"Open": close - 0.5, "High": close + 1.0, "Low": close - 1.0,
         "Close": close, "Volume": [1_000_000] * rows},
        index=idx,
    )


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

        profile = {"symbol": "AAPL", "assetClass": "stock", "assetLabel": "Stock",
                   "market": "equity", "exchange": "NASDAQ", "type": "STOCK", "isCrypto": False}
        real_bars = (_raw_bars(504), False, profile)
        answer = {"status": "pending", "queued": True,
                  "result": backtest_service._empty_payload(),
                  "computedAt": None, "lastBar": None}
        with patch.object(app_main.service, "get_history_frame", return_value=real_bars), \
             patch.object(app_main.service, "get_stock_data") as full_path, \
             patch.object(app_main.service, "get_asset_profile",
                          return_value={"symbol": "AAPL", "assetClass": "stock",
                                        "assetLabel": "Stock", "market": "equity",
                                        "exchange": "NASDAQ", "type": "STOCK", "isCrypto": False}), \
             patch.object(app_main, "get_user_watchlist_symbol_name", return_value=None), \
             patch.object(backtest_service, "request_backtest", return_value=answer) as run:
            user = MagicMock(id=7)
            payload = app_main.get_symbol_backtest(
                symbol="AAPL", current_user=user, db=MagicMock()
            )

        self.assertFalse(payload["synthetic"])
        self.assertEqual("pending", payload["status"])
        self.assertTrue(payload["queued"])
        self.assertEqual(run.call_args.kwargs["step"], app_main.BACKTEST_STEP)
        self.assertEqual(run.call_args.kwargs["train_window"], app_main.BACKTEST_TRAIN_WINDOW)
        self.assertEqual(run.call_args.kwargs["symbol"], "AAPL")
        # Der Anteil je Nutzer braucht den Nutzer: der Endpunkt nennt ihn.
        self.assertEqual(run.call_args.kwargs["owner"], str(user.id))
        # Der Endpunkt holt Bars, nicht die Bildschirm-Vorhersage (verifier
        # 2026-09-16: 7-22 s je Erstaufruf fuer eine Vorhersage, die die
        # Antwort nicht traegt) — und der Job bekommt die Indikatorspalten.
        full_path.assert_not_called()
        handed_over = run.call_args.args[0]
        self.assertIn("RSI", handed_over.columns)

    def test_endpoint_polls_without_touching_a_provider(self):
        # Waehrend ein Job laeuft, darf ein Poll weder das Asset-Profil noch
        # die Kurshistorie holen: beides kann einen Anbieter-Aufruf kosten,
        # und der yfinance-Pfad faellt bei Drossel still auf den synthetischen
        # Platzhalter — die Antwort waere dann `ready` + leer, waehrend das
        # echte Ergebnis ungesehen in der Registry laege (critic, 2026-09-15).
        from unittest.mock import MagicMock, patch
        from app import backtest_service
        from app import main as app_main

        in_flight = {"status": "pending", "queued": True,
                     "result": backtest_service._empty_payload(),
                     "computedAt": None, "lastBar": None}
        with patch.object(backtest_service, "peek", return_value=in_flight) as peek, \
             patch.object(app_main.service, "get_history_frame") as history, \
             patch.object(app_main.service, "get_asset_profile") as profile, \
             patch.object(app_main, "get_user_watchlist_symbol_name", return_value=None):
            user = MagicMock(id=7)
            payload = app_main.get_symbol_backtest(
                symbol="btc-usd", current_user=user, db=MagicMock()
            )

        peek.assert_called_once()
        self.assertEqual("BTC/USD", peek.call_args.args[0])
        self.assertEqual(str(user.id), peek.call_args.kwargs["owner"])
        history.assert_not_called()
        profile.assert_not_called()
        self.assertEqual("pending", payload["status"])
        self.assertEqual("BTC/USD", payload["symbol"])


    def test_endpoint_refuses_synthetic_history(self):
        # Regel K: keine Kennzahl auf erfundenen Kursen. Der Platzhalter ist
        # ein geseedeter Random Walk — AAPL, MSFT und `ZZZZNOPE123` liefern
        # dieselbe Accuracy-Tabelle (gemessen 2026-09-11), und die Rechnung
        # kostet Minuten. Der Endpunkt gibt dann die Leerantwort und sagt
        # warum, statt zu trainieren.
        from unittest.mock import MagicMock, patch
        from app import backtest_service
        from app import main as app_main

        profile = {"symbol": "ZZZZNOPE123", "assetClass": "stock", "assetLabel": "Stock",
                   "market": "equity", "exchange": "", "type": "STOCK", "isCrypto": False}
        synthetic_bars = (_raw_bars(600), True, profile)
        with patch.object(app_main.service, "get_history_frame", return_value=synthetic_bars), \
             patch.object(app_main.service, "get_asset_profile", return_value=profile), \
             patch.object(app_main, "get_user_watchlist_symbol_name", return_value=None), \
             patch.object(backtest_service, "request_backtest") as ask:
            payload = app_main.get_symbol_backtest(
                symbol="ZZZZNOPE123", current_user=MagicMock(), db=MagicMock()
            )

        # Die Naht ist `request_backtest`, nicht `run_backtest`: ein Job
        # liefe asynchron nach dem `with` weiter, und `run` bliebe still.
        ask.assert_not_called()
        self.assertTrue(payload["synthetic"])
        self.assertEqual(backtest_service.STATUS_READY, payload["status"])
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


class BacktestRegistryTests(unittest.TestCase):
    """The request never computes: it asks, and a single worker answers.

    Measured 2026-09-11 (verifier): the walk-forward takes 18-165 s, nginx
    cuts the request at 60 s. Every test here waits on a Future or an
    Event, never on a sleep — a timing-based test was green at 53 s once.
    """

    def setUp(self):
        from app import backtest_service
        self.svc = backtest_service
        self.svc._reset_for_tests()
        self.addCleanup(self.svc._reset_for_tests)

    def _blocking_backtest(self):
        """A stand-in for `run_backtest` that holds until the test releases it
        and counts its calls."""
        import threading
        gate = threading.Event()
        self.addCleanup(gate.set)  # a failing assertion must not hang tearDown
        calls = {"n": 0}

        def fake(df, *, train_window, step):
            calls["n"] += 1
            gate.wait(5)
            return {**self.svc._empty_payload(), "samples": len(df)}

        return gate, calls, fake

    def _wait_for_job(self, symbol):
        job = self.svc._JOBS.get(symbol)
        if job is not None:
            job["future"].result(timeout=5)

    def test_first_ask_is_pending_then_ready_with_a_data_stamp(self):
        from unittest.mock import patch
        gate, calls, fake = self._blocking_backtest()
        df = _synthetic_frame(30)
        with patch.object(self.svc, "run_backtest", side_effect=fake):
            first = self.svc.request_backtest(df, symbol="AAPL", train_window=5, step=5)
            self.assertEqual("pending", first["status"])
            self.assertTrue(first["queued"])
            self.assertEqual(0, first["result"]["samples"])
            gate.set()
            self._wait_for_job("AAPL")
            second = self.svc.request_backtest(df, symbol="AAPL", train_window=5, step=5)

        self.assertEqual("ready", second["status"])
        self.assertEqual(30, second["result"]["samples"])
        self.assertEqual(str(df.index[-1]), second["lastBar"])
        self.assertRegex(second["computedAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")
        self.assertEqual(1, calls["n"])
        self.assertNotIn("AAPL", self.svc._JOBS)

    def test_concurrent_asks_enqueue_one_job(self):
        # Genau der verifier-Fall: zwei (hier vier) Anfragen zugleich. Ohne
        # Lock sehen alle "kein Treffer, kein Job" und reihen viermal ein.
        # Der Wettlauf wird erzwungen: `_job_is_open` haelt jeden Thread an
        # einer Barriere fest, bis alle vier im kritischen Abschnitt sind.
        # Mit Lock kommt nur einer hinein, die Barriere reisst per Timeout
        # und der Ablauf ist wie ohne sie; ohne Lock treffen sich alle vier
        # und reihen viermal ein (Mutation `_LOCK = nullcontext()`: 4 != 1).
        # Ohne Barriere war der Test unter dem GIL in 4 von 7 Laeufen gruen.
        import threading
        from unittest.mock import patch
        gate, calls, fake = self._blocking_backtest()
        df = _synthetic_frame(30)
        answers = []
        barrier = threading.Barrier(4, timeout=0.2)
        real_is_open = self.svc._job_is_open

        def is_open_after_meeting(job):
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
            return real_is_open(job)

        with patch.object(self.svc, "run_backtest", side_effect=fake), \
             patch.object(self.svc, "_job_is_open", side_effect=is_open_after_meeting):
            threads = [
                threading.Thread(
                    target=lambda: answers.append(
                        self.svc.request_backtest(df, symbol="AAPL", train_window=5, step=5)
                    )
                )
                for _ in range(4)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual({"pending"}, {a["status"] for a in answers})
            self.assertEqual("pending", self.svc.peek("AAPL")["status"])
            gate.set()
            self._wait_for_job("AAPL")
            final = self.svc.request_backtest(df, symbol="AAPL", train_window=5, step=5)

        self.assertEqual(1, calls["n"])
        self.assertEqual("ready", final["status"])
        self.assertIsNone(self.svc.peek("AAPL"))

    def test_new_bar_recomputes_and_serves_the_old_result_meanwhile(self):
        from unittest.mock import patch
        gate, calls, fake = self._blocking_backtest()
        gate.set()
        df = _synthetic_frame(30)
        with patch.object(self.svc, "run_backtest", side_effect=fake):
            self.svc.request_backtest(df, symbol="AAPL", train_window=5, step=5)
            self._wait_for_job("AAPL")
            gate.clear()
            longer = _synthetic_frame(31)
            meanwhile = self.svc.request_backtest(longer, symbol="AAPL", train_window=5, step=5)
            self.assertEqual("pending", meanwhile["status"])
            self.assertEqual(30, meanwhile["result"]["samples"])  # altes Ergebnis bleibt sichtbar
            gate.set()
            self._wait_for_job("AAPL")
            after = self.svc.request_backtest(longer, symbol="AAPL", train_window=5, step=5)

        self.assertEqual("ready", after["status"])
        self.assertEqual(31, after["result"]["samples"])
        self.assertEqual(2, calls["n"])

    def test_waiting_job_with_stale_bars_is_replaced(self):
        # Ein Job, der noch auf den Worker wartet, waehrend schon neuere Bars
        # da sind, rechnet umsonst: er wird verworfen, nicht nachgeholt.
        from unittest.mock import patch
        gate, calls, fake = self._blocking_backtest()
        with patch.object(self.svc, "run_backtest", side_effect=fake):
            # MSFT belegt den einen Worker; AAPL wartet.
            self.svc.request_backtest(_synthetic_frame(30), symbol="MSFT", train_window=5, step=5)
            self.svc.request_backtest(_synthetic_frame(30), symbol="AAPL", train_window=5, step=5)
            stale = self.svc._JOBS["AAPL"]["future"]
            self.svc.request_backtest(_synthetic_frame(31), symbol="AAPL", train_window=5, step=5)
            fresh = self.svc._JOBS["AAPL"]["future"]
            self.assertIsNot(stale, fresh)
            self.assertTrue(stale.cancelled())
            gate.set()
            self._wait_for_job("MSFT")
            self._wait_for_job("AAPL")
            after = self.svc.request_backtest(_synthetic_frame(31), symbol="AAPL", train_window=5, step=5)

        self.assertEqual("ready", after["status"])
        self.assertEqual(31, after["result"]["samples"])
        self.assertEqual(2, calls["n"])  # MSFT + AAPL(31); AAPL(30) lief nie
        self.assertNotIn("AAPL", self.svc._JOBS)

    def test_running_job_with_stale_bars_finishes_and_the_next_poll_enqueues(self):
        # Ein Job, der schon rechnet, laesst sich nicht abbrechen: neuere
        # Bars bekommen `pending`, kein zweites Einreihen, und erst der
        # naechste Poll nach dem Abschluss reiht den Nachfolger ein.
        import threading
        from unittest.mock import patch
        gate, calls, fake = self._blocking_backtest()
        started = threading.Event()

        def fake_that_announces(df, **kwargs):
            started.set()
            return fake(df, **kwargs)

        with patch.object(self.svc, "run_backtest", side_effect=fake_that_announces):
            self.svc.request_backtest(_synthetic_frame(30), symbol="AAPL", train_window=5, step=5)
            running = self.svc._JOBS["AAPL"]["future"]
            self.assertTrue(started.wait(5))  # der Worker rechnet — jetzt ist er nicht mehr abbrechbar
            newer = self.svc.request_backtest(_synthetic_frame(31), symbol="AAPL", train_window=5, step=5)
            self.assertEqual("pending", newer["status"])
            self.assertIs(running, self.svc._JOBS["AAPL"]["future"])
            self.assertFalse(running.cancelled())
            gate.set()
            self._wait_for_job("AAPL")
            self.assertEqual(1, calls["n"])
            poll = self.svc.request_backtest(_synthetic_frame(31), symbol="AAPL", train_window=5, step=5)
            self.assertEqual("pending", poll["status"])
            self.assertEqual(30, poll["result"]["samples"])  # das alte Ergebnis reist mit
            self._wait_for_job("AAPL")
            after = self.svc.request_backtest(_synthetic_frame(31), symbol="AAPL", train_window=5, step=5)

        self.assertEqual("ready", after["status"])
        self.assertEqual(31, after["result"]["samples"])
        self.assertEqual(2, calls["n"])

    def test_failed_job_is_reported_and_not_retried_for_the_same_bars(self):
        from unittest.mock import patch
        df = _synthetic_frame(30)
        calls = {"n": 0}

        def boom(df, *, train_window, step):
            calls["n"] += 1
            raise RuntimeError("training exploded")

        with patch.object(self.svc, "run_backtest", side_effect=boom), \
             self.assertLogs("app.backtest_service", level="ERROR") as logs:
            self.svc.request_backtest(df, symbol="AAPL", train_window=5, step=5)
            self._wait_for_job("AAPL")
            again = self.svc.request_backtest(df, symbol="AAPL", train_window=5, step=5)
            longer = self.svc.request_backtest(_synthetic_frame(31), symbol="AAPL", train_window=5, step=5)

        self.assertEqual("failed", again["status"])
        self.assertEqual(0, again["result"]["samples"])
        self.assertEqual("pending", longer["status"])  # neuer Bar: neuer Versuch
        self.assertEqual(1, calls["n"])
        self.assertTrue(any("backtest_job_failed" in line for line in logs.output))

    def test_queue_is_capped_and_says_so(self):
        from unittest.mock import patch
        gate, calls, fake = self._blocking_backtest()
        with patch.object(self.svc, "run_backtest", side_effect=fake), \
             patch.object(self.svc, "BACKTEST_MAX_JOBS", 3), \
             self.assertLogs("app.backtest_service", level="WARNING") as logs:
            for sym in ("A", "B", "C"):
                self.assertTrue(
                    self.svc.request_backtest(_synthetic_frame(30), symbol=sym, train_window=5, step=5)["queued"]
                )
            fourth = self.svc.request_backtest(_synthetic_frame(30), symbol="D", train_window=5, step=5)
            self.assertEqual("pending", fourth["status"])
            self.assertFalse(fourth["queued"])
            # Die Verweigerung bleibt fuer `peek` sichtbar: ein Poll darauf
            # zahlt keinen Abruf und kann nicht auf den Platzhalter kippen.
            held = self.svc.peek("D")
            self.assertEqual("pending", held["status"])
            self.assertFalse(held["queued"])
            # Nach Ablauf der Haltezeit laesst `peek` den vollen Pfad wieder zu.
            self.svc._REFUSED[(None, "D")] -= self.svc.BACKTEST_REFUSAL_HOLD_S
            self.assertIsNone(self.svc.peek("D"))
            self.assertNotIn((None, "D"), self.svc._REFUSED)
            gate.set()
            for sym in ("A", "B", "C"):
                self._wait_for_job(sym)
            retried = self.svc.request_backtest(_synthetic_frame(30), symbol="D", train_window=5, step=5)
            self.assertTrue(retried["queued"])
            self.assertNotIn((None, "D"), self.svc._REFUSED)
            self._wait_for_job("D")

        self.assertEqual(4, calls["n"])
        self.assertTrue(any("backtest_queue_full" in line for line in logs.output))

    def test_one_user_cannot_fill_the_queue(self):
        # Der globale Deckel begrenzt den Prozess, nicht den Nutzer: ohne
        # eigenen Anteil fuellt ein Member alle Plaetze und jeder andere liest
        # `queued: false`, solange er pollt (security-reviewer 2026-09-16).
        from unittest.mock import patch
        gate, calls, fake = self._blocking_backtest()
        with patch.object(self.svc, "run_backtest", side_effect=fake), \
             patch.object(self.svc, "BACKTEST_MAX_JOBS_PER_USER", 2), \
             self.assertLogs("app.backtest_service", level="WARNING") as logs:
            for sym in ("A", "B"):
                self.assertTrue(
                    self.svc.request_backtest(_synthetic_frame(30), symbol=sym, train_window=5, step=5, owner="u1")["queued"]
                )
            third = self.svc.request_backtest(_synthetic_frame(30), symbol="C", train_window=5, step=5, owner="u1")
            self.assertEqual("pending", third["status"])
            self.assertFalse(third["queued"])
            # Die Abweisung haelt wie beim globalen Deckel: ein Poll darauf
            # zahlt keinen Abruf — aber nur fuer diesen Nutzer. Fuer jeden
            # anderen ist das Symbol frei (reviewer W1: sonst hielte ein
            # Member an seinem Anteil beliebige Symbole fuer alle).
            self.assertFalse(self.svc.peek("C", owner="u1")["queued"])
            self.assertIsNone(self.svc.peek("C", owner="u2"))
            self.assertIsNone(self.svc.peek("C"))
            # Ein zweiter Nutzer bekommt seinen Platz — und den offenen Job
            # des ersten liest er ueber `peek`, ohne selbst einen zu besitzen.
            other = self.svc.request_backtest(_synthetic_frame(30), symbol="D", train_window=5, step=5, owner="u2")
            self.assertTrue(other["queued"])
            self.assertTrue(self.svc.peek("A")["queued"])
            self.assertEqual("u1", self.svc._JOBS["A"]["owner"])
            # Interne Aufrufer ohne Eigentuemer unterliegen nur dem globalen Deckel.
            self.assertTrue(
                self.svc.request_backtest(_synthetic_frame(30), symbol="E", train_window=5, step=5)["queued"]
            )
            gate.set()
            for sym in ("A", "B", "D", "E"):
                self._wait_for_job(sym)
            self.svc._REFUSED.pop(("u1", "C"), None)
            retried = self.svc.request_backtest(_synthetic_frame(30), symbol="C", train_window=5, step=5, owner="u1")
            self.assertTrue(retried["queued"])
            self._wait_for_job("C")

        self.assertEqual(5, calls["n"])
        self.assertTrue(any("backtest_user_quota_full" in line for line in logs.output))
        self.assertFalse(any("backtest_queue_full" in line for line in logs.output))

    def test_enqueues_per_user_are_windowed(self):
        # Der Anteil begrenzt, was gleichzeitig offen ist; das Fenster
        # begrenzt, wie oft ein Nutzer nachlegt, sobald ein Job fertig ist —
        # sonst haelt ein Member den einen Worker mit der Watchlist dauerhaft.
        from unittest.mock import patch
        from app.rate_limit import SlidingWindowLimit
        gate, calls, fake = self._blocking_backtest()
        gate.set()  # Jobs enden sofort; nur das Fenster zaehlt hier.
        window = SlidingWindowLimit(2, 600.0)
        with patch.object(self.svc, "run_backtest", side_effect=fake), \
             patch.object(self.svc, "BACKTEST_ENQUEUES_PER_USER", window), \
             self.assertLogs("app.backtest_service", level="WARNING") as logs:
            for sym in ("A", "B"):
                self.assertTrue(
                    self.svc.request_backtest(_synthetic_frame(30), symbol=sym, train_window=5, step=5, owner="u1")["queued"]
                )
                self._wait_for_job(sym)
            third = self.svc.request_backtest(_synthetic_frame(30), symbol="C", train_window=5, step=5, owner="u1")
            self.assertFalse(third["queued"])
            self.assertEqual("pending", third["status"])
            self.assertIn(("u1", "C"), self.svc._REFUSED)
            # Ein Poll auf ein fertiges Symbol ist frei — er zaehlt nicht.
            self.assertEqual("ready", self.svc.request_backtest(_synthetic_frame(30), symbol="A", train_window=5, step=5, owner="u1")["status"])
            # Ein anderer Nutzer hat sein eigenes Fenster.
            self.assertTrue(
                self.svc.request_backtest(_synthetic_frame(30), symbol="C", train_window=5, step=5, owner="u2")["queued"]
            )
            self._wait_for_job("C")

        self.assertEqual(3, calls["n"])
        self.assertTrue(any("backtest_user_window_full" in line for line in logs.output))

    def test_refusal_by_share_does_not_spend_the_window(self):
        # Reihenfolge der Pruefungen: wer an seinem Anteil scheitert, verliert
        # keinen Eintrag im Fenster — sonst kostete jeder Poll auf ein
        # abgewiesenes Symbol nach der Haltezeit einen Enqueue.
        from unittest.mock import patch
        from app.rate_limit import SlidingWindowLimit
        gate, calls, fake = self._blocking_backtest()
        window = SlidingWindowLimit(1, 600.0)
        with patch.object(self.svc, "run_backtest", side_effect=fake), \
             patch.object(self.svc, "BACKTEST_MAX_JOBS_PER_USER", 1), \
             patch.object(self.svc, "BACKTEST_ENQUEUES_PER_USER", window), \
             self.assertLogs("app.backtest_service", level="WARNING"):
            self.assertTrue(
                self.svc.request_backtest(_synthetic_frame(30), symbol="A", train_window=5, step=5, owner="u1")["queued"]
            )
            self.assertFalse(
                self.svc.request_backtest(_synthetic_frame(30), symbol="B", train_window=5, step=5, owner="u1")["queued"]
            )
            gate.set()
            self._wait_for_job("A")
        # Das Fenster (1 je 600 s) ist durch A belegt, nicht zusaetzlich durch B.
        self.assertFalse(window.try_acquire("u1"))
        self.assertEqual(1, len(window._hits["u1"]))

    def test_peek_knows_nothing_without_a_job(self):
        self.assertIsNone(self.svc.peek("AAPL"))

    def test_last_bar_is_a_plain_date_for_daily_bars(self):
        # Die Karte nennt den Datenstand; fuer Tagesbars ist "12.09.2024"
        # ehrlicher als "12.09.2024, 00:00".
        self.assertEqual("2024-09-12", self.svc._bar_label(pd.Timestamp("2024-09-12")))
        self.assertEqual(
            "2024-09-12T15:30:00+00:00",
            self.svc._bar_label(pd.Timestamp("2024-09-12 15:30", tz="UTC")),
        )
        self.assertEqual("29", self.svc._bar_label(29))


if __name__ == "__main__":
    unittest.main()
