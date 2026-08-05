"""Guard the restore path against unvollstaendige Loeschlisten.

Der Anlass (2026-08-05): `import_snapshot(replace_existing=True)` leert die
Tabellen, bevor es den Schnappschuss einspielt. `auto_execution_limits` und
`auto_execution_events` fehlten in dieser Liste, haengen aber per
Fremdschluessel an `users.id`. Sobald ueberhaupt ein Nutzer Auto-Execution-
Limits hatte, lief `db.query(User).delete()` in eine Fremdschluesselverletzung
und der komplette Restore antwortete mit 500.

Warum es niemandem auffiel: die API-Regression hat diese beiden Tabellen nie
befuellt. Der Import lief also immer gegen eine Datenbank, in der die fehlenden
Loeschungen folgenlos blieben — gruen, aber nicht nachgewiesen. Erst ein
Regressionsschritt, der die Limits tatsaechlich setzt, hat es sichtbar gemacht.

Der erste Test prueft deshalb nicht die zwei Tabellen von damals, sondern die
**Regel**: jedes Modell mit einem Fremdschluessel auf `users.id` muss vor den
Nutzern geleert werden. Ein neues Modell mit User-Bezug laesst ihn rot werden,
bevor es den Restore in Produktion zerlegt.
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import backup_service
from app.backup_service import BackupService
from app.database import Base
from app.models import AutoExecutionEvent, AutoExecutionLimits, User


def _models_blocking_user_deletion() -> list[type]:
    """Modelle, deren Fremdschluessel das Loeschen eines Nutzers verhindert.

    Nicht jeder Verweis auf `users.id` ist ein Problem. `PlatformConfiguration`
    und `CompositeWeightConfiguration` halten ein nullable
    `updated_by_user_id` mit `ondelete="SET NULL"` — die Datenbank raeumt den
    Verweis beim Loeschen selbst auf, und beide Tabellen gehoeren bewusst nicht
    in den Schnappschuss (die eine haelt verschluesselte Zugangsdaten, die
    andere Betreiber-Konfiguration).

    Es bleibt also genau der Fall uebrig, der 2026-08-05 den Restore zerlegt
    hat: ein Verweis, den die Datenbank nicht selbst aufloesen kann. Postgres
    setzt das durch; SQLite prueft Fremdschluessel per Default gar nicht,
    weshalb ein reiner SQLite-Test hier nichts gemerkt haette.
    """
    resolved_by_db = {"CASCADE", "SET NULL", "SET DEFAULT"}
    found = []
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if model is User:
            continue
        for column in mapper.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name != "users":
                    continue
                ondelete = (fk.ondelete or "").upper()
                if ondelete in resolved_by_db:
                    continue
                found.append(model)
                break
            else:
                continue
            break
    return found


class RestoreDeleteListTests(unittest.TestCase):
    def test_every_user_owned_table_is_cleared_before_users(self):
        """Die Loeschliste muss jedes user-gebundene Modell enthalten."""
        source = backup_service.__file__
        with open(source, "r", encoding="utf-8") as handle:
            text = handle.read()

        start = text.index("if replace_existing:")
        end = text.index("db.query(User).delete()", start)
        replace_block = text[start:end]

        missing = [
            model.__name__
            for model in _models_blocking_user_deletion()
            if f"db.query({model.__name__}).delete()" not in replace_block
        ]
        self.assertEqual(
            [],
            missing,
            "Diese Modelle haengen per Fremdschluessel an users.id, werden vom "
            "Restore aber nicht geleert, bevor die Nutzer geloescht werden. "
            "Der Import bricht damit mit einer Fremdschluesselverletzung ab, "
            "sobald ein Nutzer solche Zeilen besitzt: " + ", ".join(missing),
        )


class RestoreRoundTripTests(unittest.TestCase):
    """Der echte Round-Trip gegen SQLite -- Export rein, Import raus."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()

    def _seed_user_with_auto_execution(self) -> int:
        user = User(email="alice@example.com", hashed_password="x")
        self.db.add(user)
        self.db.commit()
        self.db.add(
            AutoExecutionLimits(
                user_id=user.id,
                enabled=True,
                mode="paper",
                max_position_size_usd=500.0,
            )
        )
        self.db.add(
            AutoExecutionEvent(
                user_id=user.id,
                status="halted",
                reason="manual_user_halt",
                payload_json="{}",
            )
        )
        self.db.commit()
        return user.id

    def test_import_survives_existing_auto_execution_rows(self):
        """Genau der Fall, der live 500 geliefert hat."""
        self._seed_user_with_auto_execution()
        snapshot = BackupService.export_snapshot(self.db)

        # Ohne die Loeschungen wirft das hier eine IntegrityError.
        BackupService.import_snapshot(self.db, snapshot, replace_existing=True)

        self.assertEqual(1, self.db.query(User).count())
        self.assertEqual(1, self.db.query(AutoExecutionLimits).count())

    def test_mode_survives_the_round_trip(self):
        """mode fehlte im Export -- ein Restore setzte ihn still zurueck."""
        user_id = self._seed_user_with_auto_execution()
        limits = (
            self.db.query(AutoExecutionLimits).filter_by(user_id=user_id).one()
        )
        limits.mode = "live"
        self.db.commit()

        snapshot = BackupService.export_snapshot(self.db)
        BackupService.import_snapshot(self.db, snapshot, replace_existing=True)

        restored = self.db.query(AutoExecutionLimits).one()
        self.assertEqual(
            "live",
            restored.mode,
            "Der Modus hat den Export/Import nicht ueberlebt -- ein Restore "
            "aendert damit stillschweigend das Handelsverhalten",
        )

    def test_older_snapshots_without_mode_default_to_paper(self):
        """Rueckwaertskompatibel, und zwar konservativ."""
        self._seed_user_with_auto_execution()
        snapshot = BackupService.export_snapshot(self.db)
        for record in snapshot["data"]["auto_execution_limits"]:
            record.pop("mode", None)

        BackupService.import_snapshot(self.db, snapshot, replace_existing=True)

        self.assertEqual("paper", self.db.query(AutoExecutionLimits).one().mode)


if __name__ == "__main__":
    unittest.main()
