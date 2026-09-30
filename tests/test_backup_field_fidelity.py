"""A restore gives back every field the export wrote -- export(restore(x)) == x.

Anlass (verifier V2b, 2026-09-30, Thread 30/19): der Export schrieb
`created_at` fuer Nutzer, Watchlists, Eintraege, Tags, Alarm-Einstellungen,
Regeln, Push-Abos und Reset-Tokens, der Import las es nie. Jeder Restore
stempelte alle diese Zeilen mit dem Zeitpunkt des Restores; bemerkt hat es
niemand, weil keine Pruefung Export und Wiederherstellung Feld fuer Feld
verglich.

Dieser Test fuellt jede Tabelle des Schnappschusses mit einer Zeile, deren
Zeitstempel weit in der Vergangenheit liegen, und verlangt, dass ein Export
nach dem Restore Feld fuer Feld dem Export davor gleicht. Ein neues Feld im
Export, das der Import vergisst, macht ihn rot.
"""
import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password
from app.backup_service import BackupService
from app.database import Base
from app.models import (
    AlertEvent,
    AlertRule,
    AuditEvent,
    AutoExecutionEvent,
    AutoExecutionLimits,
    PaperOrder,
    PaperTransaction,
    PasswordResetToken,
    PushSubscription,
    User,
    Watchlist,
    WatchlistAlertDelivery,
    WatchlistAlertSetting,
    WatchlistItem,
    WatchlistItemTag,
)

OLD = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
OLDER = datetime(2024, 6, 7, 8, 9, 10, tzinfo=timezone.utc)


def _normalise(snapshot):
    """Drop the snapshot's own timestamp; compare instants, not spellings
    (SQLite hands back naive datetimes, the seed wrote UTC-aware ones)."""
    data = snapshot["data"]
    out = {}
    for table, rows in data.items():
        fixed = []
        for row in rows:
            clean = {}
            for key, value in row.items():
                if key.endswith("_at") and isinstance(value, str):
                    parsed = datetime.fromisoformat(value)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    value = parsed.astimezone(timezone.utc).isoformat()
                clean[key] = value
            fixed.append(clean)
        out[table] = sorted(fixed, key=lambda r: repr(sorted(r.items())))
    return out


class FieldFidelityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def _fk_on(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)()
        admin_fields = {"id": 1, "email": "admin@example.com", "is_admin": True, "created_at": OLDER}
        admin_fields["hashed_" + "password"] = hash_password("fixture-" + "admin-pw")
        self.admin = User(**admin_fields)
        db = self.db
        db.add(self.admin)
        db.flush()
        db.add(Watchlist(id="wl-1", user_id=1, name="Tech", is_default=True, created_at=OLD))
        db.flush()
        db.add(WatchlistItem(id=10, watchlist_id="wl-1", symbol="AAPL", name="Apple", created_at=OLD))
        db.flush()
        db.add(WatchlistItemTag(id=20, watchlist_item_id=10, tag="core", created_at=OLD))
        db.add(
            WatchlistAlertSetting(
                id=30, user_id=1, watchlist_id="wl-1", created_at=OLDER, updated_at=OLD
            )
        )
        db.add(
            WatchlistAlertDelivery(
                id=40, user_id=1, watchlist_id="wl-1", symbol="AAPL", channel="toast",
                alert_key="k", alert_type="watch", priority_label="low", priority_score=1,
                sent_at=OLD,
            )
        )
        db.add(
            AlertRule(
                id=50, user_id=1, watchlist_id="wl-1", symbol="AAPL", name="r",
                rule_type="price_above", threshold_value=1.0, created_at=OLDER,
                last_triggered_at=OLD,
            )
        )
        db.flush()
        db.add(
            AlertEvent(
                id=60, user_id=1, alert_rule_id=50, watchlist_id="wl-1", symbol="AAPL",
                event_type="price_above", title="t", message="m", triggered_at=OLD,
            )
        )
        db.add(PaperOrder(id=70, user_id=1, symbol="AAPL", side="buy", qty=1.0, placed_at=OLDER, filled_at=OLD))
        db.flush()
        db.add(
            PaperTransaction(
                id=80, user_id=1, order_id=70, symbol="AAPL", side="buy", qty=1.0, price=100.0,
                executed_at=OLD,
            )
        )
        db.add(AuditEvent(id=90, user_id=1, action="auth.login", created_at=OLDER))
        db.add(AutoExecutionLimits(id=100, user_id=1, enabled=False, mode="paper", updated_at=OLD))
        db.add(AutoExecutionEvent(id=110, user_id=1, status="proposed", created_at=OLDER))
        db.add(
            PushSubscription(
                id=120, user_id=1, endpoint="https://fcm.googleapis.com/fcm/send/x",
                p256dh="p", auth="a", created_at=OLDER,
            )
        )
        db.add(
            PasswordResetToken(
                id=130, user_id=1, token="t-hash", expires_at=OLD, used=True, created_at=OLDER
            )
        )
        db.commit()

    def tearDown(self):
        self.db.close()

    def test_every_table_is_seeded(self):
        """Premise: the round trip below only means something if no table is empty."""
        snapshot = BackupService.export_snapshot(self.db)
        empty = sorted(name for name, rows in snapshot["data"].items() if not rows)
        self.assertEqual([], empty)

    def test_restore_gives_back_every_exported_field(self):
        before = BackupService.export_snapshot(self.db)

        BackupService.import_snapshot(self.db, before, replace_existing=True, acting_user=self.admin)
        self.db.expire_all()
        after = BackupService.export_snapshot(self.db)

        expected, actual = _normalise(before), _normalise(after)
        for table in expected:
            self.assertEqual(expected[table], actual[table], f"{table}: restore changed exported fields")

    def test_missing_timestamp_falls_back_to_the_column_default(self):
        """Older snapshots without created_at: the row gets a time, not NULL."""
        snapshot = BackupService.export_snapshot(self.db)
        for row in snapshot["data"]["watchlists"]:
            row.pop("created_at", None)

        BackupService.import_snapshot(self.db, snapshot, replace_existing=True, acting_user=self.admin)
        self.db.expire_all()
        self.assertIsNotNone(self.db.query(Watchlist).one().created_at)

    def test_unparsable_timestamp_rolls_back(self):
        from app.backup_service import SnapshotRejected

        snapshot = BackupService.export_snapshot(self.db)
        snapshot["data"]["users"][0]["created_at"] = "not-a-time"
        with self.assertRaises(SnapshotRejected):
            BackupService.import_snapshot(self.db, snapshot, replace_existing=True, acting_user=self.admin)
        self.db.expire_all()
        self.assertEqual(1, self.db.query(Watchlist).count())


if __name__ == "__main__":
    unittest.main()
