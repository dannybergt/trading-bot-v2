"""Alembic environment for trading-bot-v2.

Reads `DATABASE_URL` from the same env that the app uses, so migrations always
run against the active database.
"""
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database import Base, DATABASE_URL
# Importing models here ensures every table is registered on Base.metadata
# before autogenerate inspects it.
from app import models  # noqa: F401


config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Logging nur konfigurieren, wenn Alembic eigenstaendig laeuft (CLI).
#
# `init_db()` fuehrt die Migration **im Anwendungsprozess** aus. `fileConfig`
# setzt dort per Default `disable_existing_loggers=True` und ersetzt zusaetzlich
# die Root-Handler durch die Konsole aus `alembic.ini` (Level WARN, Textformat).
# Ergebnis war: ab dem Ende des Starts protokollierte die Anwendung **gar
# nichts** mehr — keine Request-IDs, keine Warnungen, kein JSON. Nur Bibliotheken
# mit eigenem Logger (yfinance) waren noch zu sehen, weil sie erst nach diesem
# Aufruf entstanden. Gemessen am 2026-08-06: ein erfolgreicher Login und eine
# erfolgreiche Suche erzeugten null Logzeilen.
#
# Hat die Anwendung ihr Logging schon eingerichtet (Root hat Handler), bleibt es
# unangetastet; im CLI-Fall (keine Handler) gilt weiter `alembic.ini`.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
