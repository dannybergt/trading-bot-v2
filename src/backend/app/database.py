"""
Database setup for user management.

Schema lifecycle is managed via Alembic. `init_db` runs migrations on startup;
deployments that pre-date Alembic (tables exist but no `alembic_version` yet)
are stamped at head so subsequent migrations apply cleanly.
"""
import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SQLITE_URL = f"sqlite:///{DATA_DIR}/users.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)

# alembic.ini lives at the backend package root (one level above app/)
ALEMBIC_INI_PATH = Path(__file__).resolve().parent.parent / "alembic.ini"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _alembic_config():
    from alembic.config import Config

    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    return config


BASELINE_REVISION = "b97b927c8690"  # 0001_initial_schema (matches v2026.05.07-1)


def init_db():
    """Bring the schema to head via Alembic.

    Three startup paths are supported:

    1. Fresh database (`users` does not exist): run `upgrade head`. Alembic
       applies all migrations from scratch.
    2. Pre-Alembic deployment at the v2026.05.07-1 schema (`users` exists,
       no `alembic_version`, no `alert_rules`): stamp at the BASELINE
       revision and run `upgrade head` so migration 0002+ apply on top.
    3. Pre-Alembic deployment that was already at the new schema (`users`
       and `alert_rules` exist, no `alembic_version`): stamp at head and
       skip pending upgrades. This catches the rare case where Codex's
       earlier in-place create_all run produced the 10-table schema before
       Alembic was wired in.

    All other shapes hit the default `upgrade head` path which fails fast
    if the schema diverges in unexpected ways.

    After the alembic decision, a final `Base.metadata.create_all` runs as a
    self-healing safety net. It is idempotent (CREATE TABLE IF NOT EXISTS)
    and only adds tables that are present in the model registry but missing
    from the database. This repairs DBs that were stamped on head without
    actually owning every initial-schema table — a real drift seen on legacy
    Codex volumes where path 3 stamped head while a few model tables were
    still absent.
    """
    # Ensure every model is registered on Base.metadata before alembic inspects.
    from app.models import (  # noqa: F401
        AlertEvent,
        AlertRule,
        AuditEvent,
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

    from alembic import command

    inspector = inspect(engine)
    has_users = inspector.has_table("users")
    has_alembic_version = inspector.has_table("alembic_version")
    has_alert_rules = inspector.has_table("alert_rules")

    config = _alembic_config()
    if has_alembic_version:
        logger.info("alembic_upgrade_head")
        command.upgrade(config, "head")
    elif has_users and has_alert_rules:
        logger.info("alembic_stamp_head_pre_existing_full_schema")
        command.stamp(config, "head")
    elif has_users:
        logger.info("alembic_stamp_baseline_then_upgrade revision=%s", BASELINE_REVISION)
        command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")
    else:
        logger.info("alembic_upgrade_head_fresh")
        command.upgrade(config, "head")

    # Self-heal model/db drift: only adds missing tables, never alters existing ones.
    inspector_after = inspect(engine)
    expected = set(Base.metadata.tables.keys())
    present = set(inspector_after.get_table_names())
    missing = sorted(expected - present)
    if missing:
        logger.warning("schema_drift_detected creating_missing_tables=%s", ",".join(missing))
        Base.metadata.create_all(bind=engine)
