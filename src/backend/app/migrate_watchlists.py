import json
import logging
import os
import sqlite3
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DB_PATH = DATA_DIR / "users.db"
WATCHLIST_FILE = DATA_DIR / "watchlists.json"
DATABASE_URL = os.getenv("DATABASE_URL", "")


DEFAULT_WATCHLIST_NAMES = {"Tech Giants", "Crypto Proxies"}


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _column_names(cursor: sqlite3.Cursor, table_name: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [info[1] for info in cursor.fetchall()]


def _create_watchlist_tables(cursor: sqlite3.Cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlists (
            id VARCHAR PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name VARCHAR NOT NULL,
            is_default BOOLEAN NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watchlist_id VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            name VARCHAR NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(watchlist_id) REFERENCES watchlists(id)
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_watchlists_id ON watchlists (id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_watchlists_user_id ON watchlists (user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_watchlist_items_id ON watchlist_items (id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_watchlist_items_watchlist_id ON watchlist_items (watchlist_id)")


def _ensure_watchlist_schema(cursor: sqlite3.Cursor):
    _create_watchlist_tables(cursor)
    columns = _column_names(cursor, "watchlists")
    if "is_default" not in columns:
        cursor.execute("ALTER TABLE watchlists ADD COLUMN is_default BOOLEAN NOT NULL DEFAULT 0")


def _load_legacy_watchlists() -> list[dict]:
    if not WATCHLIST_FILE.exists():
        return []
    try:
        return json.loads(WATCHLIST_FILE.read_text())
    except Exception:
        logger.exception("legacy_watchlists_load_failed path=%s", WATCHLIST_FILE)
        return []


def _user_has_watchlists(cursor: sqlite3.Cursor, user_id: int) -> bool:
    cursor.execute("SELECT 1 FROM watchlists WHERE user_id = ? LIMIT 1", (user_id,))
    return cursor.fetchone() is not None


def _import_legacy_watchlists(cursor: sqlite3.Cursor, legacy_watchlists: list[dict]):
    if not legacy_watchlists:
        return 0
    if not _table_exists(cursor, "users"):
        return 0

    cursor.execute("SELECT id FROM users")
    user_ids = [row[0] for row in cursor.fetchall()]

    imported_for_users = 0
    for user_id in user_ids:
        if _user_has_watchlists(cursor, user_id):
            continue

        for legacy_watchlist in legacy_watchlists:
            watchlist_id = str(uuid.uuid4())[:8]
            watchlist_name = str(legacy_watchlist.get("name", "Imported Watchlist"))
            is_default = 1 if watchlist_name in DEFAULT_WATCHLIST_NAMES else 0

            cursor.execute(
                """
                INSERT INTO watchlists (id, user_id, name, is_default)
                VALUES (?, ?, ?, ?)
                """,
                (watchlist_id, user_id, watchlist_name, is_default),
            )

            for item in legacy_watchlist.get("items", []):
                cursor.execute(
                    """
                    INSERT INTO watchlist_items (watchlist_id, symbol, name)
                    VALUES (?, ?, ?)
                    """,
                    (
                        watchlist_id,
                        str(item.get("symbol", "")).upper(),
                        str(item.get("name", "")),
                    ),
                )
        imported_for_users += 1

    return imported_for_users


def migrate():
    logger.info("watchlist_migration_start db_path=%s", DB_PATH)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if DATABASE_URL and not DATABASE_URL.startswith("sqlite"):
        logger.info("watchlist_migration_skipped_non_sqlite database_url=%s", DATABASE_URL.split(":", 1)[0])
        return

    if not DB_PATH.exists():
        logger.info("watchlist_migration_skipped_missing_sqlite_db path=%s", DB_PATH)
        return

    try:
        conn = sqlite3.connect(str(DB_PATH))
    except sqlite3.Error:
        logger.exception("watchlist_migration_sqlite_open_failed path=%s", DB_PATH)
        return

    try:
        cursor = conn.cursor()
        _ensure_watchlist_schema(cursor)
        imported_users = _import_legacy_watchlists(cursor, _load_legacy_watchlists())
        conn.commit()

        if imported_users:
            logger.info("watchlist_migration_imported users=%s", imported_users)
        else:
            logger.info("watchlist_migration_noop")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
