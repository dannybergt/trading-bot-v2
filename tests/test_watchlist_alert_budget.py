"""Gesamtbudget fuer die Anbieterarbeit einer Alarm-Anfrage.

Hintergrund: `net_timeout` begrenzt den einzelnen Anbieteraufruf, `rate_limit`
wartet je Aufruf auf ein Token — beides *pro Aufruf*. Der Alarm-Payload laeuft
pro Symbol durch zwei anbieterlastige Aufrufe, und `get_stock_data` macht intern
noch einmal mehrere. Unter Drosselung summiert sich das; am 2026-08-07 wurden
22,5 s fuer `/api/watchlists/<id>/alerts` gemessen (yfinance `429`).

Geprueft wird deshalb dreierlei, und zwar getrennt:
  1. das Budget greift und schneidet die Anbieterarbeit ab,
  2. der abgeschnittene Teil wird als solcher *ausgewiesen* (sonst ist ein
     uebersprungenes Symbol von einem stillen Anbieter nicht zu unterscheiden),
  3. der Endpunkt reicht das Budget ueberhaupt durch — ohne (3) waeren (1) und
     (2) gruen und trotzdem wirkungslos.
"""
import os
import sys
from pathlib import Path
from time import monotonic, sleep
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


SYMBOLS = ("AAA", "BBB", "CCC", "DDD")
PROVIDER_SECONDS = 0.25


def _build(*, budget, sleep_seconds=PROVIDER_SECONDS):
    from app import main as app_main

    record = MagicMock()
    record.id = "wl_budget"
    record.name = "Tech Giants"
    items = []
    for index, _symbol in enumerate(SYMBOLS):
        item = MagicMock()
        item.id = index
        items.append(item)
    record.items = items

    user = MagicMock()
    user.id = 7
    db = MagicMock()

    asked: list[str] = []

    def slow_stock(symbol, **_kwargs):
        asked.append(symbol)
        sleep(sleep_seconds)
        return {}

    def slow_news(symbol, **_kwargs):
        sleep(sleep_seconds)
        return {}

    def fake_serialize(item, **_kwargs):
        # `**_kwargs` schluckt die gespeicherte Anlageklasse, die der Aufrufer
        # seit dem 2026-08-11 mitgibt. Die Zusicherungen dieses Falls betreffen
        # das Budget, nicht die Einstufung.
        symbol = SYMBOLS[items.index(item)]
        return {"symbol": symbol, "name": symbol, "tags": [], "provider": {}}

    with patch.object(app_main, "get_or_create_watchlist_alert_setting", return_value=MagicMock()), \
         patch.object(app_main, "serialize_tracked_watchlist_item", side_effect=fake_serialize), \
         patch.object(app_main, "apply_alert_notifications", return_value={"popupCount": 0, "pushCount": 0}), \
         patch.object(app_main.service, "get_stock_data", side_effect=slow_stock), \
         patch.object(app_main.service, "get_market_news", side_effect=slow_news):
        started = monotonic()
        payload = app_main.build_watchlist_alert_payload(db, user, record, budget_seconds=budget)
        elapsed = monotonic() - started

    return payload, elapsed, asked


class WatchlistAlertRequestBudgetTests(unittest.TestCase):
    def test_budget_stops_provider_work_after_the_deadline(self):
        # Ein Symbol kostet zwei Aufrufe (0,5 s). Nach dem ersten ist das Budget
        # von 0,3 s ueberschritten, die restlichen drei duerfen keinen Anbieter
        # mehr sehen.
        payload, elapsed, asked = _build(budget=0.3)

        self.assertEqual(asked, ["AAA"], "nach dem Budget wurde weiter befragt")
        self.assertLess(
            elapsed,
            1.2,
            f"Budget hat nicht gegriffen: {elapsed:.2f}s (ungebremst waeren es ~2.0s)",
        )

    def test_skipped_symbols_are_declared_not_silently_empty(self):
        payload, _elapsed, _asked = _build(budget=0.3)

        summary = payload["summary"]
        # Erst die Existenz, dann der Wert: ein fehlender Schluessel soll sagen,
        # dass die Kennzeichnung fehlt, und nicht als nackter KeyError auffallen.
        self.assertIn(
            "degraded",
            summary,
            "uebersprungene Symbole werden nicht gekennzeichnet — der Payload sieht aus wie ein vollstaendiger",
        )
        self.assertTrue(summary["degraded"])
        self.assertEqual(summary["degradedReason"], "provider_budget_exhausted")
        self.assertIn("staleSymbols", summary, "die uebersprungenen Symbole werden nicht genannt")
        # Die Symbole werden genannt. "Einige Werte fehlen" ohne zu sagen welche
        # waere keine Auskunft.
        self.assertEqual(summary["staleSymbols"], ["BBB", "CCC", "DDD"])
        self.assertEqual(summary["trackedSymbols"], len(SYMBOLS))

        by_symbol = {item["symbol"]: item for item in payload["items"]}
        self.assertTrue(by_symbol["AAA"]["dataFresh"])
        for symbol in ("BBB", "CCC", "DDD"):
            self.assertFalse(
                by_symbol[symbol]["dataFresh"],
                f"{symbol} wurde uebersprungen, gibt sich aber als frisch aus",
            )

    def test_without_a_budget_every_symbol_is_asked(self):
        # Gegenprobe und zugleich die Zusage fuer die Hintergrundschleifen: ohne
        # Budget wird nichts abgeschnitten, sonst wuerden Alarme verschluckt.
        payload, _elapsed, asked = _build(budget=None)

        self.assertEqual(asked, list(SYMBOLS))
        self.assertNotIn("degraded", payload["summary"])
        self.assertTrue(all(item["dataFresh"] for item in payload["items"]))

    def test_endpoint_passes_the_request_budget(self):
        # Ohne diese Zusage waere die ganze Aenderung wirkungslos und trotzdem
        # gruen: das Budget ist ein Default-Argument, das nur greift, wenn der
        # Anfragepfad es auch setzt.
        from app import main as app_main

        record = MagicMock()
        record.id = "wl_budget"
        record.name = "Tech Giants"
        record.items = []

        with patch.object(app_main, "get_watchlist_record_or_404", return_value=record), \
             patch.object(app_main, "build_watchlist_alert_payload", return_value={}) as builder:
            app_main.get_watchlist_alerts(
                id="wl_budget",
                limit=10,
                news_limit=2,
                current_user=MagicMock(),
                db=MagicMock(),
            )

        self.assertEqual(
            builder.call_args.kwargs.get("budget_seconds"),
            app_main.WATCHLIST_ALERT_REQUEST_BUDGET_SECONDS,
        )
        self.assertGreater(app_main.WATCHLIST_ALERT_REQUEST_BUDGET_SECONDS, 0)

    def test_background_callers_stay_unbudgeted(self):
        # Die Regelauswertung und der Push-Dispatcher rufen denselben Payload.
        # Ein Budget waere dort falsch: niemand wartet vor einem Bildschirm, und
        # ein abgeschnittener Lauf wuerde Alarme verschlucken. Gelesen wird die
        # Quelle, weil ein Lauf beider Schleifen hier zu teuer waere.
        import inspect
        from app import main as app_main

        for func in (app_main.evaluate_alert_rules, app_main.dispatch_watchlist_push_alerts):
            source = inspect.getsource(func)
            self.assertNotIn(
                "budget_seconds",
                source,
                f"{func.__name__} setzt ein Budget — Hintergrundarbeit darf nicht abgeschnitten werden",
            )


if __name__ == "__main__":
    unittest.main()
