import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import PasswordResetToken, PushSubscription, User, Watchlist, WatchlistItem, WatchlistItemTag


BACKUP_DIR = Path(os.getenv("BACKUP_DIR", Path(__file__).parent.parent / "data" / "backups"))
BACKUP_INTERVAL_SECONDS = int(os.getenv("BACKUP_INTERVAL_SECONDS", "3600"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_SCHEMA_VERSION = 1
logger = logging.getLogger(__name__)


class BackupService:
    @staticmethod
    def _snapshot_timestamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def export_snapshot(db: Session) -> dict[str, Any]:
        users = db.query(User).all()
        watchlists = db.query(Watchlist).all()
        watchlist_items = db.query(WatchlistItem).all()
        watchlist_item_tags = db.query(WatchlistItemTag).all()
        push_subscriptions = db.query(PushSubscription).all()
        reset_tokens = db.query(PasswordResetToken).all()

        return {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data": {
                "users": [
                    {
                        "id": user.id,
                        "email": user.email,
                        "hashed_password": user.hashed_password,
                        "is_active": user.is_active,
                        "is_admin": user.is_admin,
                        "mfa_secret": user.mfa_secret,
                        "mfa_enabled": user.mfa_enabled,
                        "alpaca_api_key": user.alpaca_api_key,
                        "alpaca_secret_key": user.alpaca_secret_key,
                        "alpaca_paper": user.alpaca_paper,
                        "trade_fee_absolute": user.trade_fee_absolute,
                        "trade_fee_percent": user.trade_fee_percent,
                        "min_target_yield": user.min_target_yield,
                        "created_at": user.created_at.isoformat() if user.created_at else None,
                    }
                    for user in users
                ],
                "watchlists": [
                    {
                        "id": watchlist.id,
                        "user_id": watchlist.user_id,
                        "name": watchlist.name,
                        "is_default": watchlist.is_default,
                        "created_at": watchlist.created_at.isoformat() if watchlist.created_at else None,
                    }
                    for watchlist in watchlists
                ],
                "watchlist_items": [
                    {
                        "id": item.id,
                        "watchlist_id": item.watchlist_id,
                        "symbol": item.symbol,
                        "name": item.name,
                        "created_at": item.created_at.isoformat() if item.created_at else None,
                    }
                    for item in watchlist_items
                ],
                "watchlist_item_tags": [
                    {
                        "id": tag.id,
                        "watchlist_item_id": tag.watchlist_item_id,
                        "tag": tag.tag,
                        "created_at": tag.created_at.isoformat() if tag.created_at else None,
                    }
                    for tag in watchlist_item_tags
                ],
                "push_subscriptions": [
                    {
                        "id": subscription.id,
                        "user_id": subscription.user_id,
                        "endpoint": subscription.endpoint,
                        "p256dh": subscription.p256dh,
                        "auth": subscription.auth,
                        "created_at": subscription.created_at.isoformat() if subscription.created_at else None,
                    }
                    for subscription in push_subscriptions
                ],
                "password_reset_tokens": [
                    {
                        "id": token.id,
                        "user_id": token.user_id,
                        "token": token.token,
                        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
                        "used": token.used,
                        "created_at": token.created_at.isoformat() if token.created_at else None,
                    }
                    for token in reset_tokens
                ],
            },
        }

    @staticmethod
    def create_backup(db: Session, label: str | None = None) -> Path:
        snapshot = BackupService.export_snapshot(db)
        safe_label = f"-{label}" if label else ""
        filename = f"backup-{BackupService._snapshot_timestamp()}{safe_label}.json"
        path = BACKUP_DIR / filename
        path.write_text(json.dumps(snapshot, indent=2))
        return path

    @staticmethod
    def list_backups() -> list[dict[str, Any]]:
        backups = []
        for path in sorted(BACKUP_DIR.glob("backup-*.json"), reverse=True):
            stat = path.stat()
            backups.append(
                {
                    "filename": path.name,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                }
            )
        return backups

    @staticmethod
    def backup_path(filename: str) -> Path:
        if "/" in filename or ".." in filename:
            raise ValueError("Invalid backup filename")
        path = BACKUP_DIR / filename
        if not path.exists():
            raise FileNotFoundError(filename)
        return path

    @staticmethod
    def import_snapshot(db: Session, snapshot: dict[str, Any], replace_existing: bool = True):
        payload = snapshot.get("data", snapshot)

        if replace_existing:
            db.query(WatchlistItemTag).delete()
            db.query(WatchlistItem).delete()
            db.query(Watchlist).delete()
            db.query(PushSubscription).delete()
            db.query(PasswordResetToken).delete()
            db.query(User).delete()
            db.commit()

        for record in payload.get("users", []):
            db.add(
                User(
                    id=record["id"],
                    email=record["email"],
                    hashed_password=record["hashed_password"],
                    is_active=record.get("is_active", True),
                    is_admin=record.get("is_admin", False),
                    mfa_secret=record.get("mfa_secret"),
                    mfa_enabled=record.get("mfa_enabled", False),
                    alpaca_api_key=record.get("alpaca_api_key"),
                    alpaca_secret_key=record.get("alpaca_secret_key"),
                    alpaca_paper=record.get("alpaca_paper", True),
                    trade_fee_absolute=record.get("trade_fee_absolute", 1),
                    trade_fee_percent=record.get("trade_fee_percent", 0),
                    min_target_yield=record.get("min_target_yield", 1),
                )
            )

        # Flush parent tables before inserting dependent rows to keep PostgreSQL
        # foreign-key checks deterministic during full snapshot imports.
        db.flush()

        for record in payload.get("watchlists", []):
            db.add(
                Watchlist(
                    id=record["id"],
                    user_id=record["user_id"],
                    name=record["name"],
                    is_default=record.get("is_default", False),
                )
            )

        db.flush()

        for record in payload.get("watchlist_items", []):
            db.add(
                WatchlistItem(
                    id=record.get("id"),
                    watchlist_id=record["watchlist_id"],
                    symbol=record["symbol"],
                    name=record.get("name", ""),
                )
            )

        db.flush()

        for record in payload.get("watchlist_item_tags", []):
            db.add(
                WatchlistItemTag(
                    id=record.get("id"),
                    watchlist_item_id=record["watchlist_item_id"],
                    tag=record["tag"],
                )
            )

        for record in payload.get("push_subscriptions", []):
            db.add(
                PushSubscription(
                    id=record.get("id"),
                    user_id=record["user_id"],
                    endpoint=record["endpoint"],
                    p256dh=record["p256dh"],
                    auth=record["auth"],
                )
            )

        for record in payload.get("password_reset_tokens", []):
            db.add(
                PasswordResetToken(
                    id=record.get("id"),
                    user_id=record["user_id"],
                    token=record["token"],
                    expires_at=datetime.fromisoformat(record["expires_at"]) if record.get("expires_at") else None,
                    used=record.get("used", False),
                )
            )

        db.commit()


async def backup_scheduler_task():
    if BACKUP_INTERVAL_SECONDS <= 0:
        return

    while True:
        await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
            BackupService.create_backup(db, label="scheduled")
        except Exception:
            logger.exception("Scheduled backup failed")
        finally:
            db.close()
