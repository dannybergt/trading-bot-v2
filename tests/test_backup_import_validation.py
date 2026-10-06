"""A restore either replaces everything or changes nothing.

Anlass (verifier B-V1, 2026-09-29): `import_snapshot` loeschte alle Tabellen
und committete, bevor es den Schnappschuss ansah. `{"data": {"pad": "x"}}` an
`/api/admin/import` antwortete 200 -- danach waren alle Tabellen leer und
jeder Token, auch der des Admins, bekam 401. Zurueck kam man nur ueber
`INITIAL_ADMIN_*` und einen Neustart.

Jeder Test hier prueft deshalb dasselbe Paar: die Abweisung *und* dass die
Datenbank danach exakt so aussieht wie vorher.
"""
import os
import re
import unittest

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import backup_service
from app.backup_service import BackupService
from app.database import Base
from app.models import User, Watchlist, WatchlistItem

try:  # absent before the fix -- the tests below still run and must fail there
    from app.backup_service import SnapshotRejected
except ImportError:  # pragma: no cover - negative-control path only
    SnapshotRejected = Exception


def _fingerprint(db):
    """What a user of the platform would notice: who exists, what they watch."""
    users = sorted((u.id, u.email, u.is_admin, u.is_active) for u in db.query(User).all())
    lists = sorted((w.id, w.user_id, w.name) for w in db.query(Watchlist).all())
    items = sorted((i.watchlist_id, i.symbol) for i in db.query(WatchlistItem).all())
    return users, lists, items


class ImportValidationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

        # Postgres enforces foreign keys; SQLite only when asked.
        @event.listens_for(self.engine, "connect")
        def _fk_on(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)()
        # Explicit ids: some models use BigInteger keys, which SQLite does
        # not auto-increment.
        from app.auth import hash_password

        # A real bcrypt hash: the caller check wants one login can verify.
        admin_fields = {"id": 1, "email": "admin@example.com", "is_admin": True}
        admin_fields["hashed_" + "password"] = hash_password("fixture-" + "admin-pw")
        self.admin = User(**admin_fields)
        member = User(id=2, email="member@example.com", hashed_password="h-member")
        self.db.add_all([self.admin, member])
        self.db.commit()
        watchlist = Watchlist(id=10, user_id=member.id, name="Tech", is_default=True)
        self.db.add(watchlist)
        self.db.commit()
        self.db.add_all(
            [
                WatchlistItem(id=100, watchlist_id=watchlist.id, symbol="AAPL", name="Apple"),
                WatchlistItem(id=101, watchlist_id=watchlist.id, symbol="MSFT", name="Microsoft"),
            ]
        )
        self.db.commit()
        self.before = _fingerprint(self.db)
        self.good = BackupService.export_snapshot(self.db)

    def tearDown(self):
        self.db.close()

    def _assert_refused_and_untouched(self, snapshot, reason_part, **kwargs):
        with self.assertRaises(SnapshotRejected) as caught:
            BackupService.import_snapshot(self.db, snapshot, replace_existing=True, **kwargs)
        self.assertIn(reason_part, str(caught.exception))
        self.db.expire_all()
        self.assertEqual(self.before, _fingerprint(self.db), "a refused restore changed the data")

    def test_snapshot_without_users_is_refused_before_anything_is_deleted(self):
        """Genau die Datei des verifier-Laufs."""
        self._assert_refused_and_untouched({"data": {"pad": "x" * 64}}, "no users")

    def test_non_object_is_refused(self):
        self._assert_refused_and_untouched([1, 2, 3], "not a JSON object")

    def test_snapshot_without_an_active_admin_is_refused(self):
        snapshot = self.good
        for record in snapshot["data"]["users"]:
            record["is_admin"] = False
        self._assert_refused_and_untouched(snapshot, "no active admin")

    def test_record_missing_a_field_its_insert_needs_is_refused_up_front(self):
        """Frueher: alles geloescht, dann KeyError beim Einfuegen -> 500."""
        self.good["data"]["watchlist_items"][1].pop("symbol")
        self._assert_refused_and_untouched(self.good, "watchlist_items[1]` lacks symbol")

    def test_reference_to_a_user_outside_the_snapshot_is_refused(self):
        self.good["data"]["watchlists"][0]["user_id"] = 999
        self._assert_refused_and_untouched(self.good, "999")

    def test_newer_schema_version_is_refused(self):
        self.good["schema_version"] = 99
        self._assert_refused_and_untouched(self.good, "schema_version")

    def test_value_the_database_rejects_rolls_everything_back(self):
        """Besteht die Pruefung, scheitert aber beim Einfuegen: kein Teilzustand."""
        self.good["data"]["watchlist_alert_deliveries"] = [
            {
                "user_id": self.good["data"]["users"][0]["id"],
                "watchlist_id": self.good["data"]["watchlists"][0]["id"],
                "symbol": "AAPL",
                "channel": "toast",
                "alert_key": "k",
                "sent_at": "not-a-timestamp",
            }
        ]
        self._assert_refused_and_untouched(self.good, "nothing was changed")

    def test_foreign_key_violation_rolls_everything_back(self):
        self.good["data"]["watchlist_items"][0]["watchlist_id"] = 424242
        self._assert_refused_and_untouched(self.good, "nothing was changed")

    def test_caller_missing_from_the_snapshot_is_refused(self):
        """Der Token nennt den Nutzer per id -- ohne ihn im Schnappschuss 401."""
        self.good["data"]["users"] = [
            record for record in self.good["data"]["users"] if record["id"] != self.admin.id
        ]
        # keep another admin so only the caller check can refuse
        self.good["data"]["users"][0]["is_admin"] = True
        self._assert_refused_and_untouched(self.good, "your own admin account", acting_user=self.admin)

    def test_caller_whose_id_now_belongs_to_someone_else_is_refused(self):
        for record in self.good["data"]["users"]:
            if record["id"] == self.admin.id:
                record["email"] = "someone-else@example.com"
        self._assert_refused_and_untouched(self.good, "your own admin account", acting_user=self.admin)

    def test_caller_demoted_in_the_snapshot_is_refused(self):
        for record in self.good["data"]["users"]:
            if record["id"] == self.admin.id:
                record["is_admin"] = False
            else:
                record["is_admin"] = True
        self._assert_refused_and_untouched(self.good, "your own admin account", acting_user=self.admin)

    def _own_row(self):
        return next(r for r in self.good["data"]["users"] if r["id"] == self.admin.id)

    def test_caller_deactivated_by_a_falsy_value_is_refused(self):
        """`is_active: 0` was taken as active and stored as False (security #1)."""
        self._own_row()["is_active"] = 0
        # a second admin, so only the caller check can refuse
        for record in self.good["data"]["users"]:
            if record["id"] != self.admin.id:
                record["is_admin"] = True
        self._assert_refused_and_untouched(self.good, "your own admin account", acting_user=self.admin)

    def test_caller_email_in_other_case_is_refused(self):
        """Login looks the address up exactly -- a changed case locks out on the next login."""
        self._own_row()["email"] = "ADMIN@example.com"
        self._assert_refused_and_untouched(self.good, "your own admin account", acting_user=self.admin)

    def test_caller_with_an_unverifiable_hash_is_refused(self):
        self._own_row()["hashed_password"] = "x"
        self._assert_refused_and_untouched(self.good, "your own admin account", acting_user=self.admin)

    def test_caller_with_mfa_but_no_secret_is_refused(self):
        own = self._own_row()
        own["mfa_enabled"] = True
        own["mfa_secret"] = None
        self._assert_refused_and_untouched(self.good, "your own admin account", acting_user=self.admin)

    def test_unhashable_user_reference_is_a_refusal_not_a_crash(self):
        self.good["data"]["watchlists"][0]["user_id"] = [1]
        self._assert_refused_and_untouched(self.good, "is not a user")

    def test_the_systems_own_backup_with_an_empty_name_restores(self):
        """The API stores a watchlist named "" -- its backup must restore (reviewer B1)."""
        self.db.query(Watchlist).one().name = ""
        self.db.commit()
        snapshot = BackupService.export_snapshot(self.db)

        BackupService.import_snapshot(self.db, snapshot, replace_existing=True, acting_user=self.admin)

        self.db.expire_all()
        self.assertEqual("", self.db.query(Watchlist).one().name)

    def test_good_snapshot_replaces_the_data(self):
        """Der Golden Path bleibt: geaenderte Daten, dann Restore -> Stand der Sicherung."""
        watchlist = self.db.query(Watchlist).one()
        self.db.query(WatchlistItem).delete()
        watchlist.name = "changed after the backup"
        self.db.commit()

        BackupService.import_snapshot(self.db, self.good, replace_existing=True, acting_user=self.admin)

        self.db.expire_all()
        self.assertEqual(self.before, _fingerprint(self.db))


class RequiredFieldsMirrorTheInsertsTests(unittest.TestCase):
    """REQUIRED_FIELDS must name every `record["..."]` the inserts read.

    A new mandatory column added to an insert without adding it here would
    bring back the old failure: validation passes, the insert raises -- now
    rolled back instead of half-applied, but still a 400 the admin cannot
    explain from the reason text.
    """

    def test_every_hard_key_read_is_validated(self):
        with open(backup_service.__file__, "r", encoding="utf-8") as handle:
            source = handle.read()
        apply_body = source[source.index("def _apply_snapshot") :]
        blocks = re.split(r'for record in payload\.get\("([a-z_]+)", \[\]\):', apply_body)
        # blocks = [prefix, name1, body1, name2, body2, ...]
        seen = {}
        for name, body in zip(blocks[1::2], blocks[2::2]):
            seen[name] = set(re.findall(r'record\["([a-z_]+)"\]', body))
        self.assertEqual(set(backup_service.REQUIRED_FIELDS), set(seen))
        for name, keys in seen.items():
            # a hard read guarded by `if record.get(...)` is optional
            body = blocks[blocks.index(name) + 1]
            guarded = set(re.findall(r'if record\.get\("([a-z_]+)"\)', body))
            missing = keys - guarded - set(backup_service.REQUIRED_FIELDS[name])
            self.assertEqual(set(), missing, f"{name}: validate these before deleting anything")


if __name__ == "__main__":
    unittest.main()
