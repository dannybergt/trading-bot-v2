"""Operator-managed platform configuration (provider API keys, etc.).

Keeps a small allow-list of operational settings that the admin UI can
edit at runtime. Values are encrypted at rest with the same Fernet wrapper
that already protects per-user secrets (`encrypt_secret`/`decrypt_secret`
in `auth.py`).

Read path: DB-row (when present) > os.environ > None. A 60-second
in-memory cache keeps the hot path off the database; explicit
`invalidate(key)` is called whenever a row is written so the next provider
call sees the new value immediately.

The allow-list deliberately excludes bootstrap secrets (JWT, encryption
key, postgres, VAPID, SMTP, initial-admin) — those stay env-only and can
never be set through the admin UI.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.auth import decrypt_secret, encrypt_secret
from app.models import PlatformConfiguration

logger = logging.getLogger(__name__)


# Keys the admin UI may set/unset. Anything outside this set is rejected
# with HTTP 400 in the API layer and ignored by the read path.
MANAGED_KEYS: frozenset[str] = frozenset(
    {
        "ALPHA_VANTAGE_API_KEY",
        "FMP_API_KEY",
        "TWELVE_DATA_API_KEY",
        "COINGECKO_API_KEY",
        "FRED_API_KEY",
        "RSS_NEWS_FEEDS",
        "SENTIMENT_PROVIDER",
    }
)


# Cache TTL in seconds. Provider adapters resolve `api_key` on each call
# (see e.g. `AlphaVantageService.api_key`), so the cache avoids hitting
# the DB on every Alpha-Vantage request. 60s keeps it fresh enough that
# even without explicit invalidation a key rotation propagates within a
# minute; explicit `invalidate(key)` makes the propagation immediate.
_CACHE_TTL_SECONDS = 60.0

# (timestamp, value)
_cache: dict[str, tuple[float, Optional[str]]] = {}


def _now() -> float:
    return time.monotonic()


def is_managed(key: str) -> bool:
    return key in MANAGED_KEYS


def invalidate(key: Optional[str] = None) -> None:
    """Drop a single key from the cache, or all keys if `key` is None."""
    if key is None:
        _cache.clear()
        return
    _cache.pop(key, None)


def _read_from_db(db: Session, key: str) -> Optional[str]:
    row = (
        db.query(PlatformConfiguration)
        .filter(PlatformConfiguration.key == key)
        .one_or_none()
    )
    if row is None:
        return None
    try:
        return decrypt_secret(row.encrypted_value)
    except Exception:  # noqa: BLE001 — defensive log + env fallback
        logger.exception(
            "platform_config_decrypt_failed key=%s", key
        )
        return None


def get_value(db: Session, key: str) -> Optional[str]:
    """Resolve the active value for `key`.

    Order:
      1. cache (60s TTL)
      2. platform_configuration row (decrypted)
      3. os.environ
      4. None
    """
    now = _now()
    cached = _cache.get(key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    value: Optional[str] = None
    if key in MANAGED_KEYS:
        value = _read_from_db(db, key)
    if value is None:
        value = os.environ.get(key) or None
    if value == "":
        value = None
    _cache[key] = (now, value)
    return value


def get_value_with_short_session(key: str) -> Optional[str]:
    """Same as `get_value` but opens a short-lived DB session itself.

    Used by provider adapters that are module-level singletons and have
    no per-request `Session`. Falls back to env-only lookup if the DB
    is unreachable (so a misconfigured database does not break the
    provider chain on startup).
    """
    now = _now()
    cached = _cache.get(key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        from app.database import SessionLocal

        with SessionLocal() as db:
            return get_value(db, key)
    except Exception:  # noqa: BLE001
        logger.exception(
            "platform_config_session_open_failed key=%s — falling back to env",
            key,
        )
        value = os.environ.get(key) or None
        if value == "":
            value = None
        _cache[key] = (now, value)
        return value


def set_value(
    db: Session,
    key: str,
    value: str,
    *,
    updated_by_user_id: Optional[int],
) -> None:
    """Upsert + encrypt + cache-invalidate. Caller commits."""
    if key not in MANAGED_KEYS:
        raise ValueError(f"key {key!r} is not managed")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("value must be a non-empty string")
    encrypted = encrypt_secret(value)
    row = (
        db.query(PlatformConfiguration)
        .filter(PlatformConfiguration.key == key)
        .one_or_none()
    )
    if row is None:
        row = PlatformConfiguration(
            key=key,
            encrypted_value=encrypted,
            updated_by_user_id=updated_by_user_id,
        )
        db.add(row)
    else:
        row.encrypted_value = encrypted
        row.updated_by_user_id = updated_by_user_id
        # `server_default=func.now()` only applies on INSERT — explicitly
        # refresh on UPDATE so the "last updated" hint in the UI stays
        # honest. Using a Python-side datetime keeps the path simple and
        # works across SQLite + PostgreSQL.
        from datetime import datetime, timezone

        row.updated_at = datetime.now(timezone.utc)
    db.flush()
    invalidate(key)


def delete_value(db: Session, key: str) -> bool:
    """Remove a managed key. Reads fall back to env on the next lookup."""
    if key not in MANAGED_KEYS:
        raise ValueError(f"key {key!r} is not managed")
    row = (
        db.query(PlatformConfiguration)
        .filter(PlatformConfiguration.key == key)
        .one_or_none()
    )
    if row is None:
        return False
    db.delete(row)
    db.flush()
    invalidate(key)
    return True


@dataclass(frozen=True)
class ManagedKeyStatus:
    key: str
    source: str  # "db" | "env" | "unconfigured"
    configured: bool
    last_updated_at: Optional[str]  # ISO-8601 UTC string
    last_updated_by_user_id: Optional[int]


def list_status(db: Session) -> list[ManagedKeyStatus]:
    """Diagnostic listing for the admin UI. Never returns the value itself."""
    rows = {
        row.key: row
        for row in db.query(PlatformConfiguration)
        .filter(PlatformConfiguration.key.in_(MANAGED_KEYS))
        .all()
    }
    out: list[ManagedKeyStatus] = []
    for key in sorted(MANAGED_KEYS):
        row = rows.get(key)
        env_value = (os.environ.get(key) or "").strip()
        if row is not None:
            source = "db"
            configured = True
            last_updated_at = (
                row.updated_at.isoformat() if row.updated_at is not None else None
            )
            last_updated_by_user_id = row.updated_by_user_id
        elif env_value:
            source = "env"
            configured = True
            last_updated_at = None
            last_updated_by_user_id = None
        else:
            source = "unconfigured"
            configured = False
            last_updated_at = None
            last_updated_by_user_id = None
        out.append(
            ManagedKeyStatus(
                key=key,
                source=source,
                configured=configured,
                last_updated_at=last_updated_at,
                last_updated_by_user_id=last_updated_by_user_id,
            )
        )
    return out
