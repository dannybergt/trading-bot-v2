"""Die Anwendung muss auch nach der Start-Migration noch protokollieren.

Der Befund vom 2026-08-06: ein erfolgreicher Login und eine erfolgreiche
Suche erzeugten **null** Logzeilen. Ursache war nicht das Logging selbst,
sondern die Migration: `init_db()` faehrt Alembic im Anwendungsprozess, und
`alembic/env.py` rief `fileConfig(...)` — Default `disable_existing_loggers=True`.
Das schaltet jeden bereits bestehenden Logger (`app.*`, `uvicorn.*`) fuer die
restliche Lebensdauer des Prozesses ab und ersetzt die Root-Handler durch die
Konsole aus `alembic.ini` (Level WARN, Textformat statt JSON).

Sichtbar war der Schaden nur als Abwesenheit — genau die Sorte Fehler, die
keine gruene Kette findet. Deshalb stellt dieser Test den Zustand her
(Logging konfigurieren, dann wirklich migrieren) und prueft danach, dass eine
Logzeile noch ankommt, statt das zu unterstellen.

Laeuft in einem Subprozess wie `test_alembic_init.py`: eine echte Migration im
Testrunner wuerde dessen eigenes Logging veraendern.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


def _find_backend_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / "src" / "backend", here.parent):
        if (candidate / "alembic.ini").exists():
            return candidate
    raise RuntimeError("Could not find backend root containing alembic.ini")


BACKEND_ROOT = _find_backend_root()

PROBE = textwrap.dedent(
    """
    import json
    import logging

    from app.logging_config import configure_logging

    configure_logging()

    root = logging.getLogger()
    handlers_before = len(root.handlers)
    level_before = root.level

    # Die Migration im selben Prozess — genau das, was beim Start passiert.
    from app import database
    database.init_db()

    app_logger = logging.getLogger("app.probe")
    uvicorn_logger = logging.getLogger("uvicorn.error")

    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    capture = Capture()
    logging.getLogger().addHandler(capture)

    app_logger.info("probe_after_migration")
    uvicorn_logger.info("uvicorn_after_migration")

    print(json.dumps({
        "handlersBefore": handlers_before,
        "levelBefore": level_before,
        "handlersAfter": len(logging.getLogger().handlers),
        "levelAfter": logging.getLogger().level,
        "appLoggerDisabled": app_logger.disabled,
        "uvicornLoggerDisabled": uvicorn_logger.disabled,
        "captured": records,
    }))
    """
)


class RuntimeLoggingSurvivesMigrationTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "logging.db"

    def tearDown(self):
        self._tmpdir.cleanup()

    def _run_probe(self):
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        env["PYTHONPATH"] = str(BACKEND_ROOT)
        env.setdefault("JWT_SECRET", "12345678901234567890123456789012")
        env.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")
        result = subprocess.run(
            [sys.executable, "-c", PROBE],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(BACKEND_ROOT),
            timeout=120,
        )
        self.assertEqual(0, result.returncode, msg=result.stderr or result.stdout)
        payload = result.stdout.strip().splitlines()[-1]
        import json

        return json.loads(payload)

    def test_application_loggers_are_not_disabled_by_the_migration(self):
        state = self._run_probe()
        self.assertFalse(
            state["appLoggerDisabled"],
            "Die Start-Migration hat die Anwendungs-Logger abgeschaltet — ab hier "
            "protokolliert der Prozess nichts mehr.",
        )
        self.assertFalse(
            state["uvicornLoggerDisabled"],
            "Die Start-Migration hat die uvicorn-Logger abgeschaltet — keine "
            "Request-Logs mehr.",
        )

    def test_a_log_line_still_arrives_after_the_migration(self):
        # Der eigentliche Nachweis: nicht "der Logger existiert", sondern
        # "eine Zeile kommt an".
        state = self._run_probe()
        self.assertIn("probe_after_migration", state["captured"])
        self.assertIn("uvicorn_after_migration", state["captured"])

    def test_the_migration_does_not_take_over_the_root_handler(self):
        state = self._run_probe()
        self.assertEqual(
            state["handlersBefore"],
            state["handlersAfter"] - 1,  # der Capture-Handler des Tests
            "Die Migration hat die Root-Handler ersetzt — das JSON-Format der "
            "Anwendung ist damit weg.",
        )
        self.assertEqual(
            state["levelBefore"],
            state["levelAfter"],
            "Die Migration hat den Root-Level veraendert (alembic.ini setzt WARN).",
        )


if __name__ == "__main__":
    unittest.main()
