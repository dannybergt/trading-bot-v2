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


def init_db():
    """Bring the schema to head via Alembic.

    For pre-Alembic deployments where the schema was bootstrapped via the legacy
    `Base.metadata.create_all` path, `users` already exists but `alembic_version`
    does not. In that case stamp at head so subsequent migrations have a clean
    starting point. Fresh databases run `upgrade head` normally.
    """
    # Ensure every model is registered on Base.metadata before alembic inspects.
    from app.models import (  # noqa: F401
        AlertEvent,
        AlertRule,
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

    config = _alembic_config()
    if has_users and not has_alembic_version:
        logger.info("alembic_stamp_pre_existing_schema")
        command.stamp(config, "head")
    else:
        logger.info("alembic_upgrade_head")
        command.upgrade(config, "head")
