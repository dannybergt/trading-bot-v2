"""Verify Alembic-managed schema bring-up works for both fresh and pre-existing
databases.

Each scenario runs in its own subprocess so a single SQLAlchemy registry isn't
re-initialized inside the test runner (re-importing `app.*` from a single
process scrambles relationship resolution).

Two paths must be supported:

1. Fresh deployment: empty database -> `alembic upgrade head` creates all
   tables and populates `alembic_version` with the head revision.

2. Pre-Alembic deployment: legacy `Base.metadata.create_all` already created
   all tables but `alembic_version` does not yet exist. `init_db` must stamp
   at head without re-running the initial migration (which would fail because
   tables already exist).
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


def _find_backend_root() -> Path:
    """Locate the backend root in both layouts: repo (src/backend/) and
    container (/app/)."""
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / "src" / "backend", here.parent):
        if (candidate / "alembic.ini").exists():
            return candidate
    raise RuntimeError("Could not find backend root containing alembic.ini")


BACKEND_ROOT = _find_backend_root()


def _run_in_subprocess(script: str, db_path: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["PYTHONPATH"] = str(BACKEND_ROOT)
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(BACKEND_ROOT),
        timeout=60,
    )


class AlembicInitTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_fresh_database_runs_upgrade(self):
        script = textwrap.dedent(
            """
            import sqlite3, os
            from app import database
            database.init_db()
            con = sqlite3.connect(os.environ['DATABASE_URL'].removeprefix('sqlite:///'))
            tables = sorted(r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ))
            assert 'users' in tables, tables
            assert 'alert_rules' in tables, tables
            assert 'alembic_version' in tables, tables
            row = con.execute('SELECT version_num FROM alembic_version').fetchone()
            assert row and row[0], 'alembic_version should be populated'
            print('OK', row[0])
            """
        )
        result = _run_in_subprocess(script, self.db_path)
        self.assertEqual(0, result.returncode, msg=result.stderr or result.stdout)
        self.assertIn("OK ", result.stdout)

    def test_pre_alembic_full_schema_is_stamped_at_head(self):
        """All 10 tables present, no alembic_version: stamp at head only."""
        script = textwrap.dedent(
            """
            import sqlite3, os
            from app import database, models  # noqa: F401
            from app.database import Base, engine
            Base.metadata.create_all(bind=engine)
            db_path = os.environ['DATABASE_URL'].removeprefix('sqlite:///')
            con = sqlite3.connect(db_path)
            tables_before = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            assert 'alembic_version' not in tables_before, tables_before
            assert 'users' in tables_before, tables_before
            assert 'alert_rules' in tables_before, tables_before
            con.close()
            database.init_db()
            con = sqlite3.connect(db_path)
            row = con.execute('SELECT version_num FROM alembic_version').fetchone()
            assert row and row[0], 'should be stamped at head'
            database.init_db()  # idempotent
            print('OK', row[0])
            """
        )
        result = _run_in_subprocess(script, self.db_path)
        self.assertEqual(0, result.returncode, msg=result.stderr or result.stdout)
        self.assertIn("OK ", result.stdout)

    def test_drift_at_head_is_self_healed(self):
        """Schema drift seen on a legacy Codex volume: alembic_version is at
        HEAD but a couple of initial-schema tables (e.g. watchlist_alert_settings)
        are missing — typical of a stamp-on-existing-schema run that happened
        before those models had been added.

        init_db must self-heal by creating the missing tables idempotently.
        Without the safety net the dashboard 500s on every watchlist alert
        request because the table referenced by the ORM does not exist.
        """
        script = textwrap.dedent(
            """
            import sqlite3, os
            from app import database, models  # noqa: F401
            from app.database import Base, engine
            db_path = os.environ['DATABASE_URL'].removeprefix('sqlite:///')

            # Build the full schema, then surgically drop the two tables that
            # were missing on the real-world drifted DB. alembic_version stays
            # at HEAD to mimic an already-stamped deployment.
            database.init_db()
            con = sqlite3.connect(db_path)
            con.execute('DROP TABLE watchlist_alert_settings')
            con.execute('DROP TABLE watchlist_alert_deliveries')
            con.commit()
            tables_before = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            assert 'watchlist_alert_settings' not in tables_before
            assert 'watchlist_alert_deliveries' not in tables_before
            assert 'alembic_version' in tables_before
            con.close()

            database.init_db()

            con = sqlite3.connect(db_path)
            tables_after = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            assert 'watchlist_alert_settings' in tables_after, tables_after
            assert 'watchlist_alert_deliveries' in tables_after, tables_after
            print('OK drift_healed')
            """
        )
        result = _run_in_subprocess(script, self.db_path)
        self.assertEqual(0, result.returncode, msg=result.stderr or result.stdout)
        self.assertIn("OK drift_healed", result.stdout)

    def test_pre_alembic_baseline_schema_is_stamped_then_upgraded(self):
        """v2026.05.07-1 schema (8 tables) gets stamped at baseline, then
        migration 0002 applies to add alert_rules + alert_events."""
        script = textwrap.dedent(
            """
            import sqlite3, os
            from alembic import command
            from app import database
            db_path = os.environ['DATABASE_URL'].removeprefix('sqlite:///')

            # Apply 0001 only via alembic, then drop alembic_version to
            # simulate a deployment that ran create_all at the old release
            # (8 tables, no alembic_version).
            config = database._alembic_config()
            command.upgrade(config, database.BASELINE_REVISION)
            con = sqlite3.connect(db_path)
            con.execute('DROP TABLE alembic_version')
            con.commit()
            tables_before = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            assert 'alert_rules' not in tables_before, tables_before
            assert 'alert_events' not in tables_before, tables_before
            assert 'users' in tables_before, tables_before
            con.close()

            database.init_db()

            con = sqlite3.connect(db_path)
            tables_after = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            assert 'alert_rules' in tables_after, tables_after
            assert 'alert_events' in tables_after, tables_after
            row = con.execute('SELECT version_num FROM alembic_version').fetchone()
            assert row and row[0] != database.BASELINE_REVISION, (
                f'should be at HEAD, got {row}'
            )
            print('OK', row[0])
            """
        )
        result = _run_in_subprocess(script, self.db_path)
        self.assertEqual(0, result.returncode, msg=result.stderr or result.stdout)
        self.assertIn("OK ", result.stdout)


if __name__ == "__main__":
    unittest.main()
