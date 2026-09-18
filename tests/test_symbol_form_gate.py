"""Die Symbolform wird geprueft, bevor ein Anbieter gefragt wird.

Jeder Lese-Endpunkt je Symbol laeuft fuer das, was im Pfad steht, bis zu
drei Anbieter und den Platzhalter ab — auch fuer `AMAZON INC`, `<b>AAPL</b>` oder
eine 120 Zeichen lange Zeichenkette. Jeder Versuch kostet das Kontingent
des Betreibers fuer eine Zeichenkette, die kein Markt fuehrt
(security-reviewer 2026-09-16; `place_order` prueft die Form seit #33).

Geprueft wird je Endpunkt:
  1. eine Zeichenkette ohne Tickerform endet mit 404 und nennt sie,
  2. dabei wird kein Dienst aufgerufen — die Pruefung steht VOR dem
     ersten Aufruf, nicht dahinter,
  3. eine wohlgeformte, aber unbekannte Zeichenkette geht weiter zum
     Anbieter: die Form ist kein Gueltigkeitsurteil.
"""
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import HTTPException  # noqa: E402

from app import main as app_main  # noqa: E402


MALFORMED = ("AMAZON INC", "A" * 25, "AAPL;DROP", "<b>AAPL</b>", "", "A/../../V4/X", "//X", "A/B/C")

# Alle Dienstmethoden, die einer der Endpunkte als erstes ruft. Wird eine
# davon bei einer Zeichenkette ohne Tickerform gerufen, steht die Pruefung
# an der falschen Stelle.
SERVICE_ENTRY_POINTS = (
    "get_asset_profile",
    "get_stock_data",
    "get_history_frame",
    "get_market_news",
    "get_provider_snapshot",
    "get_ticker_info",
)


def _endpoints():
    user = MagicMock(id=7, alpaca_api_key=None, alpaca_secret_key=None)
    db = MagicMock()
    return {
        "stock": lambda s: app_main.get_stock_analysis(s, current_user=user, db=db),
        "research": lambda s: app_main.get_symbol_research(s, current_user=user, db=db),
        "data_quality": lambda s: app_main.get_symbol_data_quality(s, current_user=user, db=db),
        "backtest": lambda s: app_main.get_symbol_backtest(s, current_user=user, db=db),
        "events": lambda s: app_main.get_symbol_events(s, current_user=user, db=db),
        "news": lambda s: app_main.get_stock_news(s, current_user=user),
        "alpaca_bars": lambda s: app_main.get_alpaca_bars(s, current_user=user),
    }


class SymbolFormGateTests(unittest.TestCase):
    def test_malformed_symbol_is_refused_before_any_provider(self):
        for name, call in _endpoints().items():
            for raw in MALFORMED:
                with self.subTest(endpoint=name, symbol=raw), \
                     patch.multiple(app_main.service, **{m: MagicMock() for m in SERVICE_ENTRY_POINTS}) as mocks, \
                     patch.object(app_main, "get_user_watchlist_symbol_name") as watchlist_name, \
                     patch.object(app_main.backtest_service, "peek") as peek:
                    with self.assertRaises(HTTPException) as caught:
                        call(raw)
                    self.assertEqual(404, caught.exception.status_code)
                    # Der Grund nennt die Zeichenkette (Regel K), gekuerzt.
                    self.assertIn("form", caught.exception.detail)
                    self.assertIn(raw[:40].upper().strip(), caught.exception.detail)
                    for method, mock in mocks.items():
                        mock.assert_not_called()
                    watchlist_name.assert_not_called()
                    peek.assert_not_called()

    def test_well_formed_unknown_symbol_still_reaches_the_provider(self):
        # Die Form ist kein Gueltigkeitsurteil: ob `ZZZZNOPE123` existiert,
        # weiss nur der Anbieter — und nur er kann "unbekannt" von "gerade
        # nicht erreichbar" unterscheiden.
        self.assertEqual("ZZZZNOPE123", app_main.require_symbol_form("zzzznope123"))
        self.assertEqual("BTC/USD", app_main.require_symbol_form("btc-usd"))
        self.assertEqual("BRK.B", app_main.require_symbol_form("BRK.B"))

    def test_watchlist_add_refuses_a_malformed_symbol_before_writing(self):
        # Ein gespeicherter Nicht-Ticker ist nicht harmlos: Alarm-Dispatcher
        # und Scanner fragen fuer jeden Eintrag je Zyklus die Anbieter, und die
        # Analyse-Seite antwortet dafuer seit #35 mit 404. Deshalb 400 beim
        # Anlegen — ein Schreibfehler des Aufrufers, keine fehlende Ressource.
        user = MagicMock(id=7)
        for raw in ("AMAZON INC", "A/../../V4/X", "<b>AAPL</b>"):
            with self.subTest(symbol=raw):
                db = MagicMock()
                record = MagicMock(items=[])
                with patch.object(app_main, "get_watchlist_record_or_404", return_value=record):
                    with self.assertRaises(HTTPException) as caught:
                        app_main.add_item("w1", app_main.WatchlistItemRequest(symbol=raw), current_user=user, db=db)
                self.assertEqual(400, caught.exception.status_code)
                self.assertIn(raw.upper(), caught.exception.detail)
                db.add.assert_not_called()
                db.commit.assert_not_called()
        # Wohlgeformt wird geschrieben — kanonisch.
        db = MagicMock()
        record = MagicMock(items=[])
        with patch.object(app_main, "get_watchlist_record_or_404", return_value=record), \
             patch.object(app_main, "serialize_watchlist", return_value={}):
            app_main.add_item("w1", app_main.WatchlistItemRequest(symbol="btc-usd"), current_user=user, db=db)
        self.assertEqual("BTC/USD", db.add.call_args.args[0].symbol)
        db.commit.assert_called_once()

    def _item(self, item_id, symbol):
        item = MagicMock()
        item.id = item_id
        item.watchlist_id = "w1"
        item.symbol = symbol
        item.name = ""
        item.asset_class = None
        item.tags = []
        return item

    def test_background_loops_skip_a_stored_symbol_without_ticker_form(self):
        # Bestandszeilen (vor der Form-Grenze angelegt oder aus einer
        # Sicherung) kosteten je Zyklus bis zu drei Anbieteraufrufe — die
        # Schleifen ueberspringen sie jetzt und sagen es einmal je Zyklus.
        record = MagicMock()
        record.items = [self._item(1, "AMAZON INC"), self._item(2, "VOO")]
        asked: list = []

        def remember(symbol, **kwargs):
            asked.append(symbol)
            return {}

        def tracked(item, **_kwargs):
            return {"symbol": item.symbol, "name": "", "tags": [], "assetClass": "etf",
                    "assetLabel": "ETF", "market": "equity", "exchange": "", "type": "ETF",
                    "isCrypto": False, "provider": {}}

        with patch.object(app_main, "get_or_create_watchlist_alert_setting", return_value=MagicMock()), \
             patch.object(app_main, "apply_alert_notifications", return_value={"popupCount": 0, "pushCount": 0}), \
             patch.object(app_main, "serialize_tracked_watchlist_item", side_effect=tracked) as serialize, \
             patch.object(app_main.service, "get_stock_data", side_effect=remember), \
             patch.object(app_main.service, "get_market_news", return_value={}), \
             self.assertLogs("app.main", level="WARNING") as logs:
            app_main.build_watchlist_alert_payload(MagicMock(), MagicMock(), record)
        self.assertEqual(["VOO"], asked)
        # Auch das Profil des toten Eintrags wird nicht mehr geholt.
        self.assertEqual(["VOO"], [call.args[0].symbol for call in serialize.call_args_list])
        self.assertTrue(any("watchlist_item_malformed_skipped" in line for line in logs.output))

        # Scanner: dieselbe Sammelstelle.
        asked.clear()
        user = MagicMock(is_active=True)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [user]
        watchlist = MagicMock(items=[self._item(1, "AMAZON INC"), self._item(2, "AAPL")])
        with patch.object(app_main, "SessionLocal", return_value=db), \
             patch.object(app_main, "get_user_watchlist_records", return_value=[watchlist]), \
             patch.object(app_main.service, "get_stock_data", side_effect=remember), \
             patch.object(app_main, "backfill_watchlist_item_asset_classes", return_value=0), \
             self.assertLogs("app.main", level="WARNING"):
            app_main._auto_scanner_cycle()
        self.assertEqual(["AAPL"], asked)

    def test_watchlist_names_are_bounded_on_every_write_path(self):
        from pydantic import ValidationError
        too_long = "n" * (app_main.WATCHLIST_NAME_MAX + 1)
        with self.assertRaises(ValidationError):
            app_main.WatchlistItemRequest(symbol="AAPL", name=too_long)
        with self.assertRaises(ValidationError):
            app_main.UpdateWatchlistItemRequest(name=too_long)
        with self.assertRaises(ValidationError):
            app_main.CreateWatchlistRequest(name=too_long)
        with self.assertRaises(ValidationError):
            app_main.RenameWatchlistRequest(name=too_long)
        app_main.UpdateWatchlistItemRequest(name="n" * app_main.WATCHLIST_NAME_MAX)

    def test_detail_is_bounded(self):
        with self.assertRaises(HTTPException) as caught:
            app_main.require_symbol_form("X Y" * 100)
        self.assertLess(len(caught.exception.detail), 120)


if __name__ == "__main__":
    unittest.main()
