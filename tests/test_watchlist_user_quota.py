"""Ein Deckel auf Watchlist-Zeilen und -Listen je Konto, nicht je Prozess.

Jede gespeicherte Zeile kostet die Hintergrundschleifen (Alarm-Dispatcher,
Scanner) je Zyklus Anbieteraufrufe — ein Member kann mit wohlgeformten
Symbolen beliebig viele davon anlegen (security-reviewer 2026-09-18 #2).
Dieselbe Mechanik wie der Nutzer-Anteil an der Backtest-Warteschlange.

Gegen eine echte Datenbank, weil die Zaehlung ueber die Listen eines Nutzers
hinweg (JOIN auf `watchlists.user_id`) genau das ist, was hier entscheidet;
ein Mock wuerde jede Zaehlung durchwinken.

Geprueft wird:
  1. am Deckel endet eine neue Zeile mit 409, nennt den Deckel, und es
     entsteht keine Zeile,
  2. Zeilen zaehlen ueber alle Listen des Nutzers zusammen,
  3. der Deckel gilt je Konto — ein zweiter Nutzer legt weiter an,
  4. Umbenennen/Umtaggen einer bestehenden Zeile bleibt am Deckel moeglich,
  5. die Symbolform wird vor dem Deckel geprueft (400 vor 409),
  6. Listen haben denselben Deckel je Konto,
  7. eine Abweisung steht im Log (`watchlist_user_quota_full`, User-ID,
     kein weiteres Datum) — sonst sieht der Betreiber weder das zu grosse
     Portfolio noch den Missbrauch.
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


ITEM_CAP = 3
LIST_CAP = 2


class WatchlistUserQuotaTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.database import Base
        from app.models import Watchlist, WatchlistItem

        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)()
        # Nutzer 1: zwei Listen, ITEM_CAP Zeilen ueber beide verteilt — am Deckel.
        self.db.add(Watchlist(id="u1a", user_id=1, name="Erste", is_default=True))
        self.db.add(Watchlist(id="u1b", user_id=1, name="Zweite"))
        self.db.add(WatchlistItem(watchlist_id="u1a", symbol="AAPL", name="Apple"))
        self.db.add(WatchlistItem(watchlist_id="u1a", symbol="MSFT", name="Microsoft"))
        self.db.add(WatchlistItem(watchlist_id="u1b", symbol="VOO", name="Vanguard"))
        # Nutzer 2: eine Liste, eine Zeile — weit unter dem Deckel.
        self.db.add(Watchlist(id="u2a", user_id=2, name="Fremd", is_default=True))
        self.db.add(WatchlistItem(watchlist_id="u2a", symbol="AAPL", name="Apple"))
        self.db.commit()
        self.user1 = MagicMock(id=1)
        self.user2 = MagicMock(id=2)
        self._caps = patch.multiple(
            app_main,
            WATCHLIST_MAX_ITEMS_PER_USER=ITEM_CAP,
            WATCHLIST_MAX_LISTS_PER_USER=LIST_CAP,
        )
        self._caps.start()

    def tearDown(self):
        self._caps.stop()
        self.db.close()

    def _items(self, user_id: int) -> list[tuple[str, str, str]]:
        from app.models import Watchlist, WatchlistItem

        rows = (
            self.db.query(WatchlistItem)
            .join(Watchlist, WatchlistItem.watchlist_id == Watchlist.id)
            .filter(Watchlist.user_id == user_id)
            .all()
        )
        return sorted((row.watchlist_id, row.symbol, row.name) for row in rows)

    def _add(self, user, watchlist_id: str, symbol: str, **fields):
        return app_main.add_item(
            watchlist_id,
            app_main.WatchlistItemRequest(symbol=symbol, **fields),
            current_user=user,
            db=self.db,
        )

    def test_a_new_row_at_the_cap_is_refused_and_names_the_cap(self):
        before = self._items(1)
        with self.assertRaises(HTTPException) as caught:
            self._add(self.user1, "u1b", "NVDA")
        self.assertEqual(409, caught.exception.status_code)
        self.assertIn(str(ITEM_CAP), caught.exception.detail)
        self.assertIn("items", caught.exception.detail)
        self.assertEqual(before, self._items(1), "eine abgewiesene Zeile darf nicht entstehen")

    def test_a_refusal_is_logged_with_the_account(self):
        with self.assertLogs(app_main.logger, level="WARNING") as logs, \
             self.assertRaises(HTTPException):
            self._add(self.user1, "u1a", "NVDA")
        self.assertEqual(1, len(logs.records))
        record = logs.records[0]
        self.assertEqual("watchlist_user_quota_full", record.getMessage())
        self.assertEqual((1, "items", ITEM_CAP, ITEM_CAP), (record.user, record.unit, record.current, record.limit))

    def test_rows_count_across_all_lists_of_the_user(self):
        # Die Liste `u1b` hat nur eine Zeile; wuerde je Liste gezaehlt, ginge
        # NVDA dort durch. Gezaehlt wird je Konto.
        with self.assertRaises(HTTPException) as caught:
            self._add(self.user1, "u1b", "NVDA")
        self.assertEqual(409, caught.exception.status_code)

    def test_the_cap_is_per_account_not_per_process(self):
        payload = self._add(self.user2, "u2a", "NVDA", name="Nvidia")
        self.assertIn("NVDA", [item.symbol for item in payload.items])
        self.assertEqual(
            [("u2a", "AAPL", "Apple"), ("u2a", "NVDA", "Nvidia")], self._items(2)
        )

    def test_below_the_cap_a_row_is_stored(self):
        self.db.delete(
            next(row for row in self.db.query(app_main.WatchlistItemRecord) if row.symbol == "VOO")
        )
        self.db.commit()
        self._add(self.user1, "u1b", "NVDA", name="Nvidia")
        self.assertIn(("u1b", "NVDA", "Nvidia"), self._items(1))

    def test_an_existing_row_can_still_be_renamed_at_the_cap(self):
        payload = self._add(self.user1, "u1a", "aapl", name="Apple Inc.", tags=["core"])
        apple = next(item for item in payload.items if item.symbol == "AAPL")
        self.assertEqual("Apple Inc.", apple.name)
        self.assertEqual(["core"], apple.tags)
        self.assertEqual(ITEM_CAP, len(self._items(1)), "Umbenennen darf keine Zeile anlegen")

    def test_the_symbol_form_is_checked_before_the_cap(self):
        with self.assertRaises(HTTPException) as caught:
            self._add(self.user1, "u1a", "AMAZON INC")
        self.assertEqual(400, caught.exception.status_code)
        self.assertIn("AMAZON INC", caught.exception.detail)

    def test_a_new_list_at_the_cap_is_refused_and_no_row_exists(self):
        from app.models import Watchlist

        with self.assertRaises(HTTPException) as caught:
            app_main.create_watchlist(
                app_main.CreateWatchlistRequest(name="Dritte"), current_user=self.user1, db=self.db
            )
        self.assertEqual(409, caught.exception.status_code)
        self.assertIn(str(LIST_CAP), caught.exception.detail)
        self.assertIn("lists", caught.exception.detail)
        self.assertEqual(
            LIST_CAP, self.db.query(Watchlist).filter(Watchlist.user_id == 1).count()
        )

    def test_lists_are_capped_per_account(self):
        from app.models import Watchlist

        payload = app_main.create_watchlist(
            app_main.CreateWatchlistRequest(name="Zweite fremde"), current_user=self.user2, db=self.db
        )
        self.assertEqual("Zweite fremde", payload.name)
        self.assertEqual(2, self.db.query(Watchlist).filter(Watchlist.user_id == 2).count())


if __name__ == "__main__":
    unittest.main()
