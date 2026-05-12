import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    AlertEvent,
    AlertRule,
    AuditEvent,
    AutoExecutionEvent,
    AutoExecutionLimits,
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
        watchlist_alert_settings = db.query(WatchlistAlertSetting).all()
        watchlist_alert_deliveries = db.query(WatchlistAlertDelivery).all()
        alert_rules = db.query(AlertRule).all()
        alert_events = db.query(AlertEvent).all()
        paper_orders = db.query(PaperOrder).all()
        paper_transactions = db.query(PaperTransaction).all()
        audit_events = db.query(AuditEvent).all()
        auto_execution_limits = db.query(AutoExecutionLimits).all()
        auto_execution_events = db.query(AutoExecutionEvent).all()
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
                        "capital_gains_tax_bps": user.capital_gains_tax_bps or 0,
                        "income_tax_bps": user.income_tax_bps or 0,
                        "display_currency": user.display_currency or "USD",
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
                "watchlist_alert_settings": [
                    {
                        "id": setting.id,
                        "user_id": setting.user_id,
                        "watchlist_id": setting.watchlist_id,
                        "enabled": setting.enabled,
                        "toast_enabled": setting.toast_enabled,
                        "push_enabled": setting.push_enabled,
                        "min_priority": setting.min_priority,
                        "min_score": setting.min_score,
                        "created_at": setting.created_at.isoformat() if setting.created_at else None,
                        "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
                    }
                    for setting in watchlist_alert_settings
                ],
                "watchlist_alert_deliveries": [
                    {
                        "id": delivery.id,
                        "user_id": delivery.user_id,
                        "watchlist_id": delivery.watchlist_id,
                        "symbol": delivery.symbol,
                        "channel": delivery.channel,
                        "alert_key": delivery.alert_key,
                        "alert_type": delivery.alert_type,
                        "priority_label": delivery.priority_label,
                        "priority_score": delivery.priority_score,
                        "sent_at": delivery.sent_at.isoformat() if delivery.sent_at else None,
                    }
                    for delivery in watchlist_alert_deliveries
                ],
                "alert_rules": [
                    {
                        "id": rule.id,
                        "user_id": rule.user_id,
                        "watchlist_id": rule.watchlist_id,
                        "symbol": rule.symbol,
                        "name": rule.name,
                        "rule_type": rule.rule_type,
                        "threshold_value": rule.threshold_value,
                        "direction": rule.direction,
                        "tag": rule.tag,
                        "enabled": rule.enabled,
                        "snoozed_until": rule.snoozed_until.isoformat() if rule.snoozed_until else None,
                        "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
                        "created_at": rule.created_at.isoformat() if rule.created_at else None,
                    }
                    for rule in alert_rules
                ],
                "alert_events": [
                    {
                        "id": event.id,
                        "user_id": event.user_id,
                        "alert_rule_id": event.alert_rule_id,
                        "watchlist_id": event.watchlist_id,
                        "symbol": event.symbol,
                        "event_type": event.event_type,
                        "severity": event.severity,
                        "status": event.status,
                        "title": event.title,
                        "message": event.message,
                        "payload_json": event.payload_json,
                        "triggered_at": event.triggered_at.isoformat() if event.triggered_at else None,
                        "acknowledged_at": event.acknowledged_at.isoformat() if event.acknowledged_at else None,
                    }
                    for event in alert_events
                ],
                "paper_orders": [
                    {
                        "id": order.id,
                        "user_id": order.user_id,
                        "symbol": order.symbol,
                        "side": order.side,
                        "qty": float(order.qty),
                        "limit_price": float(order.limit_price) if order.limit_price is not None else None,
                        "status": order.status,
                        "source": order.source,
                        "rejection_reason": order.rejection_reason,
                        "placed_at": order.placed_at.isoformat() if order.placed_at else None,
                        "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                    }
                    for order in paper_orders
                ],
                "audit_events": [
                    {
                        "id": event.id,
                        "user_id": event.user_id,
                        "actor_fingerprint": event.actor_fingerprint,
                        "action": event.action,
                        "resource_type": event.resource_type,
                        "resource_id": event.resource_id,
                        "outcome": event.outcome,
                        "details_json": event.details_json,
                        "ip_fingerprint": event.ip_fingerprint,
                        "user_agent_fingerprint": event.user_agent_fingerprint,
                        "request_id": event.request_id,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                    }
                    for event in audit_events
                ],
                "paper_transactions": [
                    {
                        "id": tx.id,
                        "user_id": tx.user_id,
                        "order_id": tx.order_id,
                        "symbol": tx.symbol,
                        "side": tx.side,
                        "qty": float(tx.qty),
                        "price": float(tx.price),
                        "fee_absolute": float(tx.fee_absolute),
                        "fee_percent_amount": float(tx.fee_percent_amount),
                        "tax_amount": float(tx.tax_amount),
                        "realized_pnl": float(tx.realized_pnl),
                        "executed_at": tx.executed_at.isoformat() if tx.executed_at else None,
                    }
                    for tx in paper_transactions
                ],
                "auto_execution_limits": [
                    {
                        "id": row.id,
                        "user_id": row.user_id,
                        "enabled": bool(row.enabled),
                        "max_position_size_usd": float(row.max_position_size_usd or 0),
                        "max_daily_loss_usd": float(row.max_daily_loss_usd or 0),
                        "max_open_positions": int(row.max_open_positions or 0),
                        "max_portfolio_beta": float(row.max_portfolio_beta or 0),
                        "allowed_asset_classes": row.allowed_asset_classes or "",
                        "per_strategy_budget_pct": row.per_strategy_budget_pct or "{}",
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    }
                    for row in auto_execution_limits
                ],
                "auto_execution_events": [
                    {
                        "id": event.id,
                        "user_id": event.user_id,
                        "proposal_id": event.proposal_id,
                        "symbol": event.symbol,
                        "side": event.side,
                        "status": event.status,
                        "reason": event.reason,
                        "payload_json": event.payload_json,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                    }
                    for event in auto_execution_events
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
            db.query(AuditEvent).delete()
            db.query(AlertEvent).delete()
            db.query(AlertRule).delete()
            db.query(PaperTransaction).delete()
            db.query(PaperOrder).delete()
            db.query(WatchlistItemTag).delete()
            db.query(WatchlistAlertDelivery).delete()
            db.query(WatchlistAlertSetting).delete()
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
                    capital_gains_tax_bps=record.get("capital_gains_tax_bps", 0),
                    income_tax_bps=record.get("income_tax_bps", 0),
                    display_currency=record.get("display_currency") or "USD",
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

        for record in payload.get("watchlist_alert_settings", []):
            db.add(
                WatchlistAlertSetting(
                    id=record.get("id"),
                    user_id=record["user_id"],
                    watchlist_id=record["watchlist_id"],
                    enabled=record.get("enabled", True),
                    toast_enabled=record.get("toast_enabled", True),
                    push_enabled=record.get("push_enabled", False),
                    min_priority=record.get("min_priority", "high"),
                    min_score=record.get("min_score", 70),
                )
            )

        db.flush()

        for record in payload.get("watchlist_alert_deliveries", []):
            db.add(
                WatchlistAlertDelivery(
                    id=record.get("id"),
                    user_id=record["user_id"],
                    watchlist_id=record["watchlist_id"],
                    symbol=record["symbol"],
                    channel=record["channel"],
                    alert_key=record["alert_key"],
                    alert_type=record.get("alert_type", "watch"),
                    priority_label=record.get("priority_label", "low"),
                    priority_score=record.get("priority_score", 0),
                    sent_at=datetime.fromisoformat(record["sent_at"]) if record.get("sent_at") else None,
                )
            )

        db.flush()

        for record in payload.get("alert_rules", []):
            db.add(
                AlertRule(
                    id=record.get("id"),
                    user_id=record["user_id"],
                    watchlist_id=record["watchlist_id"],
                    symbol=record["symbol"],
                    name=record.get("name", ""),
                    rule_type=record["rule_type"],
                    threshold_value=record.get("threshold_value"),
                    direction=record.get("direction"),
                    tag=record.get("tag"),
                    enabled=record.get("enabled", True),
                    snoozed_until=(
                        datetime.fromisoformat(record["snoozed_until"])
                        if record.get("snoozed_until")
                        else None
                    ),
                    last_triggered_at=(
                        datetime.fromisoformat(record["last_triggered_at"])
                        if record.get("last_triggered_at")
                        else None
                    ),
                )
            )

        db.flush()

        for record in payload.get("alert_events", []):
            db.add(
                AlertEvent(
                    id=record.get("id"),
                    user_id=record["user_id"],
                    alert_rule_id=record["alert_rule_id"],
                    watchlist_id=record["watchlist_id"],
                    symbol=record["symbol"],
                    event_type=record["event_type"],
                    severity=record.get("severity", "medium"),
                    status=record.get("status", "open"),
                    title=record["title"],
                    message=record["message"],
                    payload_json=record.get("payload_json") or "{}",
                    triggered_at=(
                        datetime.fromisoformat(record["triggered_at"])
                        if record.get("triggered_at")
                        else None
                    ),
                    acknowledged_at=(
                        datetime.fromisoformat(record["acknowledged_at"])
                        if record.get("acknowledged_at")
                        else None
                    ),
                )
            )

        for record in payload.get("paper_orders", []):
            db.add(
                PaperOrder(
                    id=record.get("id"),
                    user_id=record["user_id"],
                    symbol=record["symbol"],
                    side=record["side"],
                    qty=record["qty"],
                    limit_price=record.get("limit_price"),
                    status=record.get("status", "pending"),
                    source=record.get("source", "manual"),
                    rejection_reason=record.get("rejection_reason"),
                    placed_at=(
                        datetime.fromisoformat(record["placed_at"])
                        if record.get("placed_at")
                        else None
                    ),
                    filled_at=(
                        datetime.fromisoformat(record["filled_at"])
                        if record.get("filled_at")
                        else None
                    ),
                )
            )

        db.flush()

        for record in payload.get("audit_events", []):
            db.add(
                AuditEvent(
                    id=record.get("id"),
                    user_id=record.get("user_id"),
                    actor_fingerprint=record.get("actor_fingerprint"),
                    action=record["action"],
                    resource_type=record.get("resource_type"),
                    resource_id=record.get("resource_id"),
                    outcome=record.get("outcome", "success"),
                    details_json=record.get("details_json") or "{}",
                    ip_fingerprint=record.get("ip_fingerprint"),
                    user_agent_fingerprint=record.get("user_agent_fingerprint"),
                    request_id=record.get("request_id"),
                    created_at=(
                        datetime.fromisoformat(record["created_at"])
                        if record.get("created_at")
                        else None
                    ),
                )
            )

        for record in payload.get("paper_transactions", []):
            db.add(
                PaperTransaction(
                    id=record.get("id"),
                    user_id=record["user_id"],
                    order_id=record["order_id"],
                    symbol=record["symbol"],
                    side=record["side"],
                    qty=record["qty"],
                    price=record["price"],
                    fee_absolute=record.get("fee_absolute", 0.0),
                    fee_percent_amount=record.get("fee_percent_amount", 0.0),
                    tax_amount=record.get("tax_amount", 0.0),
                    realized_pnl=record.get("realized_pnl", 0.0),
                    executed_at=(
                        datetime.fromisoformat(record["executed_at"])
                        if record.get("executed_at")
                        else None
                    ),
                )
            )

        for record in payload.get("auto_execution_limits", []):
            db.add(
                AutoExecutionLimits(
                    id=record.get("id"),
                    user_id=record["user_id"],
                    enabled=bool(record.get("enabled", False)),
                    max_position_size_usd=float(record.get("max_position_size_usd") or 0),
                    max_daily_loss_usd=float(record.get("max_daily_loss_usd") or 0),
                    max_open_positions=int(record.get("max_open_positions") or 0),
                    max_portfolio_beta=float(record.get("max_portfolio_beta") or 0),
                    allowed_asset_classes=record.get("allowed_asset_classes") or "",
                    per_strategy_budget_pct=record.get("per_strategy_budget_pct") or "{}",
                    updated_at=(
                        datetime.fromisoformat(record["updated_at"])
                        if record.get("updated_at")
                        else None
                    ),
                )
            )

        for record in payload.get("auto_execution_events", []):
            db.add(
                AutoExecutionEvent(
                    id=record.get("id"),
                    user_id=record["user_id"],
                    proposal_id=record.get("proposal_id"),
                    symbol=record.get("symbol"),
                    side=record.get("side"),
                    status=record.get("status") or "proposed",
                    reason=record.get("reason"),
                    payload_json=record.get("payload_json") or "{}",
                    created_at=(
                        datetime.fromisoformat(record["created_at"])
                        if record.get("created_at")
                        else None
                    ),
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
