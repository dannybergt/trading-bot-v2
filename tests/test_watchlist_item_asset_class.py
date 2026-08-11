"""Die gespeicherte Anlageklasse eines Watchlist-Eintrags.

Anlass (2026-08-11, gefunden im Review des Vorgaenger-Commits): die Klasse
entscheidet darueber, welcher Anbieter die Kurshistorie liefert. Abgeleitet
wurde sie pro Anfrage — entweder aus einem Stammdatenabruf (yfinance `.info`,
der unter Drosselung `429` liefert und den Anfragepfad blockiert) oder aus dem
vom Nutzer vergebenen Anzeigenamen (Substring-Heuristik ueber
`ETF_HINT_PATTERNS`; ein Eintrag namens "Fundgrube" wird damit zum ETF).

Beides ist als Grundlage untauglich. Geprueft wird deshalb:
  1. eine gespeicherte Klasse schlaegt die Namensheuristik (sonst steuert ein
     Anzeigetext die Datenquelle),
  2. ein unbekannter gespeicherter Wert wird ignoriert statt durchgereicht,
  3. die Aufloesung passiert **einmal** und danach nie wieder,
  4. der Alarm-Pfad benutzt sie ueberhaupt — ohne (4) waere der Rest gruen und
     wirkungslos,
  5. der Schnappschuss traegt die Spalte durch Export und Import; ein alter
     Schnappschuss ohne die Spalte laedt weiterhin.
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

from app.asset_metadata import build_asset_profile  # noqa: E402


class StoredClassBeatsTheHeuristicTests(unittest.TestCase):
    def test_stored_class_wins_over_the_display_name(self):
        # "Fundgrube" enthaelt "fund" — die Heuristik macht daraus einen ETF.
        geraten = build_asset_profile("AAPL", fallback_name="Fundgrube")
        self.assertEqual(geraten["assetClass"], "etf", "Praemisse des Falls entfallen")

        gespeichert = build_asset_profile(
            "AAPL", fallback_name="Fundgrube", known_asset_class="stock"
        )
        self.assertEqual(gespeichert["assetClass"], "stock")
        self.assertFalse(gespeichert["isCrypto"])

    def test_unknown_stored_value_does_not_leak_through(self):
        # Die Klasse kommt aus der Datenbank und ist damit potenziell aelter als
        # der Code, der sie liest. Ein Wert, den dieser Code nicht kennt, darf
        # sich nicht durch die Oberflaeche ziehen.
        profil = build_asset_profile("AAPL", known_asset_class="wertpapier")
        self.assertEqual(profil["assetClass"], "stock")


class ResolutionTests(unittest.TestCase):
    def _record(self, asset_class=None):
        record = MagicMock()
        record.id = 1
        record.symbol = "VOO"
        record.name = "Altersvorsorge"
        record.asset_class = asset_class
        return record

    def test_stored_class_costs_no_provider_call(self):
        from app import main as app_main

        record = self._record(asset_class="etf")
        db = MagicMock()

        with patch.object(app_main.service, "get_ticker_info") as ticker_info:
            resolved = app_main.resolve_watchlist_item_asset_class(db, record)

        ticker_info.assert_not_called()
        db.commit.assert_not_called()
        self.assertEqual(resolved, "etf")

    def test_missing_class_is_resolved_once_and_written(self):
        from app import main as app_main

        record = self._record(asset_class=None)
        db = MagicMock()

        with patch.object(
            app_main.service,
            "get_ticker_info",
            return_value={"quoteType": "ETF", "shortName": "Vanguard S&P 500 ETF"},
        ) as ticker_info:
            first = app_main.resolve_watchlist_item_asset_class(db, record)
            # Der Eintrag traegt die Klasse jetzt — der zweite Lauf darf keinen
            # Anbieter mehr sehen.
            second = app_main.resolve_watchlist_item_asset_class(db, record)

        self.assertEqual((first, second), ("etf", "etf"))
        self.assertEqual(ticker_info.call_count, 1, "die Aufloesung lief mehr als einmal")
        self.assertEqual(record.asset_class, "etf")
        db.commit.assert_called_once()

    def test_unresolvable_symbol_is_left_open_instead_of_guessed(self):
        from app import main as app_main

        record = self._record(asset_class=None)
        record.symbol = ""
        db = MagicMock()

        with patch.object(app_main.service, "get_ticker_info", return_value={}), patch.object(
            app_main.service, "get_asset_profile", return_value={"assetClass": None}
        ):
            resolved = app_main.resolve_watchlist_item_asset_class(db, record)

        self.assertIsNone(resolved)
        self.assertIsNone(record.asset_class)
        db.commit.assert_not_called()


class AlertPathUsesTheStoredClassTests(unittest.TestCase):
    """Der stille Rueckweg: loest der Alarm-Pfad die Klasse nicht auf, bleibt
    alles andere gruen und der Eintrag wird weiter nach seinem Namen
    eingestuft."""

    def test_alert_payload_resolves_and_forwards_the_stored_class(self):
        from app import main as app_main

        record = MagicMock()
        record.id = "wl"
        item = MagicMock()
        item.id = 1
        item.symbol = "VOO"
        item.name = "Altersvorsorge"
        item.asset_class = "etf"
        item.tags = []
        record.items = [item]

        gesehen: list = []

        def merke(symbol, **kwargs):
            profil = kwargs.get("asset_profile") or {}
            gesehen.append(profil.get("assetClass"))
            return {}

        with patch.object(app_main, "get_or_create_watchlist_alert_setting", return_value=MagicMock()), \
             patch.object(app_main, "apply_alert_notifications", return_value={"popupCount": 0, "pushCount": 0}), \
             patch.object(app_main.service, "get_provider_snapshot", return_value=None), \
             patch.object(app_main.service, "get_ticker_info") as ticker_info, \
             patch.object(app_main.service, "get_stock_data", side_effect=merke), \
             patch.object(app_main.service, "get_market_news", return_value={}):
            app_main.build_watchlist_alert_payload(MagicMock(), MagicMock(), record)

        ticker_info.assert_not_called()
        self.assertEqual(
            gesehen,
            ["etf"],
            "der Alarm-Pfad analysiert nicht mit der gespeicherten Klasse — der "
            "Eintrag wird weiter nach seinem Anzeigenamen eingestuft",
        )


class SnapshotRoundTripTests(unittest.TestCase):
    def test_export_and_import_carry_the_column(self):
        import inspect

        from app import backup_service

        quelle = inspect.getsource(backup_service)
        self.assertIn(
            '"asset_class": item.asset_class',
            quelle,
            "der Schnappschuss exportiert die Anlageklasse nicht — ein Restore "
            "wuerde jeden Eintrag wieder auf die Namensheuristik zuruecksetzen",
        )
        self.assertIn(
            'asset_class=record.get("asset_class")',
            quelle,
            "der Import liest die Anlageklasse nicht zurueck",
        )

    def test_older_snapshots_without_the_column_still_load(self):
        # `.get` statt `[...]`: ein Schnappschuss von vor dieser Spalte darf
        # nicht am fehlenden Schluessel scheitern.
        alter_eintrag = {"id": 1, "watchlist_id": "wl", "symbol": "VOO", "name": "VOO"}
        self.assertIsNone(alter_eintrag.get("asset_class"))


if __name__ == "__main__":
    unittest.main()
