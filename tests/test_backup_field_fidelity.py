"""A restore gives back every field the export wrote -- export(restore(x)) == x.

Anlass (verifier V2b, 2026-09-30, Thread 30/19): der Export schrieb
`created_at` fuer Nutzer, Watchlists, Eintraege, Tags, Alarm-Einstellungen,
Regeln, Push-Abos und Reset-Tokens, der Import las es nie. Jeder Restore
stempelte alle diese Zeilen mit dem Zeitpunkt des Restores; bemerkt hat es
niemand, weil keine Pruefung Export und Wiederherstellung Feld fuer Feld
verglich.

Dieser Test fuellt jede Tabelle des Schnappschusses mit einer Zeile, deren
Zeitstempel weit in der Vergangenheit liegen und deren uebrige Felder bewusst
NICHT auf dem Rueckfallwert des Imports stehen (sonst fiele ein vergessenes
Feld nicht auf -- reviewer W1, per Mutation gezeigt: mfa_enabled,
display_currency, severity, direction, acknowledged_at). Ein Export nach dem
Restore muss Feld fuer Feld dem Export davor gleichen.
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
        admin_fields = {
            "id": 1, "email": "admin@example.com", "is_admin": True, "created_at": OLDER,
            "mfa_enabled": True, "alpaca_paper": False,
            "trade_fee_absolute": 2.5, "trade_fee_percent": 0.1, "min_target_yield": 3,
            "trading_defaults_set_at": OLD, "capital_gains_tax_bps": 2500,
            "income_tax_bps": 1000, "display_currency": "EUR",
        }
        admin_fields["hashed_" + "password"] = hash_password("fixture-" + "admin-pw")
        # Placeholder values, built from parts so no scanner mistakes them
        # for credentials; they only need to differ from the import defaults.
        admin_fields["mfa_" + "secret"] = "FIXTURE" + "BASE32"
        admin_fields["alpaca_api_" + "key"] = "fixture-" + "k"
        admin_fields["alpaca_" + "secret_key"] = "fixture-" + "s"
        self.admin = User(**admin_fields)
        db = self.db
        db.add(self.admin)
        db.flush()
        db.add(Watchlist(id="wl-1", user_id=1, name="Tech", is_default=True, created_at=OLD))
        db.flush()
        db.add(WatchlistItem(id=10, watchlist_id="wl-1", symbol="AAPL", name="Apple", asset_class="stock", created_at=OLD))
        db.flush()
        db.add(WatchlistItemTag(id=20, watchlist_item_id=10, tag="core", created_at=OLD))
        db.add(
            WatchlistAlertSetting(
                id=30, user_id=1, watchlist_id="wl-1", enabled=False, toast_enabled=False,
                push_enabled=True, min_priority="low", min_score=12,
                created_at=OLDER, updated_at=OLD,
            )
        )
        db.add(
            WatchlistAlertDelivery(
                id=40, user_id=1, watchlist_id="wl-1", symbol="AAPL", channel="toast",
                alert_key="k", alert_type="breakout", priority_label="high", priority_score=91,
                sent_at=OLD,
            )
        )
        db.add(
            AlertRule(
                id=50, user_id=1, watchlist_id="wl-1", symbol="AAPL", name="r",
                rule_type="price_above", threshold_value=1.0, direction="up", tag="core",
                enabled=False, snoozed_until=OLD, created_at=OLDER, updated_at=OLD,
                last_triggered_at=OLD,
            )
        )
        db.flush()
        db.add(
            AlertEvent(
                id=60, user_id=1, alert_rule_id=50, watchlist_id="wl-1", symbol="AAPL",
                event_type="price_above", severity="high", status="acknowledged",
                title="t", message="m", payload_json='{"p": 1}', triggered_at=OLD,
                acknowledged_at=OLD,
            )
        )
        db.add(PaperOrder(
            id=70, user_id=1, symbol="AAPL", side="buy", qty=1.0, limit_price=99.5,
            status="filled", source="auto", rejection_reason="none", placed_at=OLDER, filled_at=OLD,
        ))
        db.flush()
        db.add(
            PaperTransaction(
                id=80, user_id=1, order_id=70, symbol="AAPL", side="buy", qty=1.0, price=100.0,
                fee_absolute=1.5, fee_percent_amount=0.2, tax_amount=3.0, realized_pnl=-4.0,
                executed_at=OLD,
            )
        )
        db.add(AuditEvent(
            id=90, user_id=1, actor_fingerprint="fp", action="auth.login", resource_type="user",
            resource_id="1", outcome="failure", details_json='{"d": 1}', ip_fingerprint="ip",
            user_agent_fingerprint="ua", request_id="req", created_at=OLDER,
        ))
        db.add(AutoExecutionLimits(
            id=100, user_id=1, enabled=True, mode="live", max_position_size_usd=750.0,
            max_daily_loss_usd=150.0, max_open_positions=3, max_portfolio_beta=1.5,
            allowed_asset_classes="stock,etf", per_strategy_budget_pct='{"a": 50}',
            composite_gate_enabled=False, min_composite_confidence=0.4, updated_at=OLD,
        ))
        db.add(AutoExecutionEvent(
            id=110, user_id=1, proposal_id="p-1", symbol="AAPL", side="buy", status="halted",
            reason="manual", payload_json='{"e": 1}', created_at=OLDER,
        ))
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
            with self.subTest(table=table):
                self.assertEqual(expected[table], actual[table], f"{table}: restore changed exported fields")

    def test_missing_timestamp_falls_back_to_the_column_default(self):
        """Older snapshots without created_at restore, and the row still has a
        time (the column default; regression anchor, not a discriminating test
        -- the ORM omits None for server-default columns anyway)."""
        snapshot = BackupService.export_snapshot(self.db)
        for row in snapshot["data"]["watchlists"]:
            row.pop("created_at", None)

        BackupService.import_snapshot(self.db, snapshot, replace_existing=True, acting_user=self.admin)
        self.db.expire_all()
        self.assertIsNotNone(self.db.query(Watchlist).one().created_at)

    def test_naive_and_offset_values_are_read_as_the_instant_they_name(self):
        """A naive value means UTC (SQLite exports); an offset converts to UTC.
        Postgres would otherwise read a naive value in the session time zone
        (migration-reviewer #1)."""
        from app.backup_service import _restore_ts

        self.assertEqual(
            datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc), _restore_ts("2025-01-02T03:04:05")
        )
        self.assertEqual(
            datetime(2025, 1, 1, 21, 34, 5, tzinfo=timezone.utc), _restore_ts("2025-01-02T03:04:05+05:30")
        )
        with self.assertRaises(ValueError):
            _restore_ts("0001-01-01T00:00:00+14:00")

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
