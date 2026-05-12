import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import List, Optional
import uuid

import concurrent.futures
import pandas as pd
import requests
import yfinance as yf
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.logging_config import (
    configure_logging,
    reset_request_log_context,
    set_request_log_context,
)
configure_logging()

from app.alpaca_service import AlpacaService
from app.alpaca_stream import alpaca_stream
from app.auth import decrypt_secret, ensure_initial_admin, get_current_admin_user, get_current_user
from app.auth_routes import router as auth_router
from app.asset_metadata import build_asset_profile, canonicalize_symbol, is_plausible_symbol_query, to_yfinance_symbol
from app.backup_service import BackupService, backup_scheduler_task
from app import audit_service, auto_execution, backtest_service, data_quality_service, docs_service
from app.coingecko_service import get_coingecko_service
from app.discovery_service import get_discovery_service
from app.news_hub_service import get_news_hub_service
from app.database import init_db, get_db, SessionLocal
from app.figi_service import figi
from app.fred_service import get_fred_service
from app.macro_service import get_macro_service
from app.migrate_watchlists import migrate as migrate_watchlists
from app.options_flow_service import get_options_flow_service
from app.sector_service import get_sector_service
from app.social_sentiment_service import get_social_sentiment_service
from app.models import (
    AlertEvent as AlertEventRecord,
    AlertRule as AlertRuleRecord,
    AutoExecutionEvent as AutoExecutionEventRecord,
    AutoExecutionLimits as AutoExecutionLimitsRecord,
    PaperOrder as PaperOrderRecord,
    PaperTransaction as PaperTransactionRecord,
    User,
    Watchlist as WatchlistRecord,
    WatchlistAlertDelivery,
    WatchlistAlertSetting,
    WatchlistItem as WatchlistItemRecord,
    WatchlistItemTag,
)
from app import paper_trading
from app.push_service import PushService
from app.services import MarketDataService
from app.watchlist_alerts import (
    build_provider_context,
    build_watchlist_alert,
    build_watchlist_alert_delivery_key,
    summarize_watchlist_alerts,
)
from app.websocket_manager import manager

logger = logging.getLogger(__name__)

app = FastAPI(title="AI Trading Bot API")
ALERT_PRIORITY_RANKS = {"low": 1, "medium": 2, "high": 3}
ALERT_RULE_TYPES = {"provider_move", "news_sentiment", "signal_direction", "tag_priority"}
WATCHLIST_ALERT_DISPATCH_INTERVAL_SECONDS = int(os.getenv("WATCHLIST_ALERT_DISPATCH_INTERVAL_SECONDS", "300"))
WATCHLIST_ALERT_DISPATCH_INITIAL_DELAY_SECONDS = int(os.getenv("WATCHLIST_ALERT_DISPATCH_INITIAL_DELAY_SECONDS", "90"))
WATCHLIST_ALERT_DEDUP_HOURS = int(os.getenv("WATCHLIST_ALERT_DEDUP_HOURS", "12"))
PAPER_ORDER_FILL_INTERVAL_SECONDS = int(os.getenv("PAPER_ORDER_FILL_INTERVAL_SECONDS", "180"))
PAPER_ORDER_FILL_INITIAL_DELAY_SECONDS = int(os.getenv("PAPER_ORDER_FILL_INITIAL_DELAY_SECONDS", "60"))
ML_RETRAIN_INTERVAL_SECONDS = int(os.getenv("ML_RETRAIN_INTERVAL_SECONDS", "3600"))
ML_RETRAIN_INITIAL_DELAY_SECONDS = int(os.getenv("ML_RETRAIN_INITIAL_DELAY_SECONDS", "300"))
AUTO_EXECUTION_PAPER_LOOP_INTERVAL_SECONDS = int(
    os.getenv("AUTO_EXECUTION_PAPER_LOOP_INTERVAL_SECONDS", "900")  # 15 min
)
AUTO_EXECUTION_PAPER_LOOP_INITIAL_DELAY_SECONDS = int(
    os.getenv("AUTO_EXECUTION_PAPER_LOOP_INITIAL_DELAY_SECONDS", "180")
)
AUTO_EXECUTION_PAPER_MAX_TRADES_PER_LOOP = int(
    os.getenv("AUTO_EXECUTION_PAPER_MAX_TRADES_PER_LOOP", "3")
)


def get_allowed_origins() -> list[str]:
    raw_origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:18094,http://localhost:18094",
    )
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    if not origins:
        raise RuntimeError("ALLOWED_ORIGINS must contain at least one origin")
    if "*" in origins:
        raise RuntimeError("ALLOWED_ORIGINS must not contain '*' when credentials are enabled")
    return origins


def normalize_request_id(raw_value: str | None) -> str:
    candidate = (raw_value or "").strip().replace("\r", "").replace("\n", "")
    return candidate[:64] or str(uuid.uuid4())


def asset_response_fields(asset_profile: dict) -> dict:
    return {
        "assetClass": asset_profile["assetClass"],
        "assetLabel": asset_profile["assetLabel"],
        "market": asset_profile["market"],
        "exchange": asset_profile["exchange"],
        "type": asset_profile["type"],
        "isCrypto": asset_profile["isCrypto"],
    }


def build_search_result(
    symbol: str,
    *,
    asset: dict | None = None,
    ticker_info: dict | None = None,
    fallback_name: str | None = None,
) -> dict:
    asset_profile = build_asset_profile(
        symbol,
        asset=asset,
        ticker_info=ticker_info,
        fallback_name=fallback_name,
    )
    return {
        "symbol": asset.get("symbol") if asset and asset.get("symbol") else asset_profile["symbol"],
        "name": asset_profile["name"],
        "exchange": asset_profile["exchange"],
        "market": asset_profile["market"],
        "type": asset_profile["type"],
        "assetClass": asset_profile["assetClass"],
        "assetLabel": asset_profile["assetLabel"],
        "isCrypto": asset_profile["isCrypto"],
        "isin": "",
        "wkn": "",
    }


def get_search_fallback_result(query_upper: str) -> dict | None:
    if not is_plausible_symbol_query(query_upper):
        return None

    ticker_info = {}
    try:
        ticker_info = yf.Ticker(to_yfinance_symbol(query_upper)).info or {}
    except Exception:
        logger.debug("symbol_search_fallback_lookup_failed query=%s", query_upper, exc_info=True)

    fallback_name = None
    if isinstance(ticker_info, dict):
        fallback_name = ticker_info.get("shortName") or ticker_info.get("longName")

    return build_search_result(
        query_upper,
        ticker_info=ticker_info if isinstance(ticker_info, dict) else None,
        fallback_name=fallback_name,
    )


def normalize_tags(tags: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_tag in tags or []:
        tag = str(raw_tag).strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag[:32])
        if len(normalized) >= 12:
            break
    return normalized


def apply_watchlist_item_tags(record: WatchlistItemRecord, tags: list[str] | None) -> None:
    if tags is None:
        return

    record.tags.clear()
    for tag in normalize_tags(tags):
        record.tags.append(WatchlistItemTag(tag=tag))


def serialize_watchlist_item(record: WatchlistItemRecord) -> "WatchlistItem":
    asset_profile = service.get_asset_profile(record.symbol, fallback_name=record.name)
    return WatchlistItem(
        symbol=record.symbol,
        name=asset_profile["name"],
        tags=sorted(tag.tag for tag in record.tags),
        assetClass=asset_profile["assetClass"],
        assetLabel=asset_profile["assetLabel"],
        market=asset_profile["market"],
        exchange=asset_profile["exchange"],
        type=asset_profile["type"],
        isCrypto=asset_profile["isCrypto"],
    )


def serialize_tracked_watchlist_item(record: WatchlistItemRecord) -> dict:
    payload = serialize_watchlist_item(record).model_dump()
    payload["provider"] = service.get_provider_snapshot(record.symbol, asset_profile=payload)
    return payload


def normalize_alert_priority(value: str | None) -> str:
    normalized = str(value or "high").strip().lower()
    return normalized if normalized in ALERT_PRIORITY_RANKS else "high"


def clamp_alert_score(value: int | None) -> int:
    if value is None:
        return 70
    return max(0, min(int(value), 100))


def get_or_create_watchlist_alert_setting(
    db: Session,
    user: User,
    watchlist: WatchlistRecord,
) -> WatchlistAlertSetting:
    setting = (
        db.query(WatchlistAlertSetting)
        .filter(
            WatchlistAlertSetting.user_id == user.id,
            WatchlistAlertSetting.watchlist_id == watchlist.id,
        )
        .first()
    )
    if setting:
        return setting

    setting = WatchlistAlertSetting(
        user_id=user.id,
        watchlist_id=watchlist.id,
        enabled=True,
        toast_enabled=True,
        push_enabled=False,
        min_priority="high",
        min_score=70,
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def serialize_alert_setting(setting: WatchlistAlertSetting) -> dict:
    return {
        "enabled": bool(setting.enabled),
        "toastEnabled": bool(setting.toast_enabled),
        "pushEnabled": bool(setting.push_enabled),
        "minPriority": normalize_alert_priority(setting.min_priority),
        "minScore": clamp_alert_score(setting.min_score),
    }


def alert_matches_setting(alert_item: dict, setting: WatchlistAlertSetting) -> bool:
    if not setting.enabled:
        return False

    priority_rank = ALERT_PRIORITY_RANKS.get(str(alert_item.get("priorityLabel") or "low").lower(), 1)
    min_priority_rank = ALERT_PRIORITY_RANKS[normalize_alert_priority(setting.min_priority)]
    score = int(alert_item.get("priorityScore") or 0)
    return priority_rank >= min_priority_rank and score >= clamp_alert_score(setting.min_score)


def apply_alert_notifications(alert_items: list[dict], setting: WatchlistAlertSetting) -> dict:
    popup_symbols: list[str] = []
    push_symbols: list[str] = []

    for item in alert_items:
        matches = alert_matches_setting(item, setting)
        popup_eligible = matches and bool(setting.toast_enabled)
        push_eligible = matches and bool(setting.push_enabled)
        item["notification"] = {
            "popupEligible": popup_eligible,
            "pushEligible": push_eligible,
        }
        if popup_eligible:
            popup_symbols.append(item.get("symbol") or "")
        if push_eligible:
            push_symbols.append(item.get("symbol") or "")

    return {
        **serialize_alert_setting(setting),
        "popupCount": len(popup_symbols),
        "pushCount": len(push_symbols),
        "popupSymbols": [symbol for symbol in popup_symbols if symbol],
        "pushSymbols": [symbol for symbol in push_symbols if symbol],
    }


def build_watchlist_alert_payload(
    db: Session,
    user: User,
    record: WatchlistRecord,
    *,
    setting: WatchlistAlertSetting | None = None,
    limit: int = 10,
    news_limit: int = 2,
) -> dict:
    alert_setting = setting or get_or_create_watchlist_alert_setting(db, user, record)
    tracked_assets = [serialize_tracked_watchlist_item(item) for item in sorted(record.items, key=lambda current: current.id or 0)]

    alert_items: list[dict] = []
    for tracked in tracked_assets:
        symbol = tracked["symbol"]
        try:
            analysis_result = service.get_stock_data(
                symbol,
                period="1mo",
                interval="1h",
                user=user,
                include_news=False,
                include_fundamentals=False,
            )
        except Exception:
            logger.exception(
                "watchlist_alert_analysis_failed symbol=%s user_id=%s",
                symbol,
                user.id,
            )
            analysis_result = {}

        try:
            news_payload = service.get_market_news(symbol, asset_profile=tracked)
        except Exception:
            logger.exception(
                "watchlist_alert_news_failed symbol=%s user_id=%s",
                symbol,
                user.id,
            )
            news_payload = {}

        alert_items.append(
            build_watchlist_alert(
                tracked,
                analysis_result,
                news_payload,
                news_limit=news_limit,
            )
        )

    alert_items.sort(
        key=lambda current: (
            current.get("priorityScore", 0),
            current.get("news", {}).get("latestTimestamp") or "",
            current.get("signal", {}).get("confidence", 0),
        ),
        reverse=True,
    )
    alert_items = alert_items[:limit]

    notification_plan = apply_alert_notifications(alert_items, alert_setting)
    summary = summarize_watchlist_alerts(alert_items)
    summary["trackedSymbols"] = len(tracked_assets)
    summary["popupEligible"] = notification_plan["popupCount"]
    summary["pushEligible"] = notification_plan["pushCount"]

    return {
        "watchlist": {"id": record.id, "name": record.name},
        "alertSettings": serialize_alert_setting(alert_setting),
        "notificationPlan": notification_plan,
        "trackedAssets": tracked_assets,
        "items": alert_items,
        "summary": summary,
    }


def was_watchlist_alert_recently_delivered(
    db: Session,
    user_id: int,
    watchlist_id: str,
    alert_item: dict,
    *,
    channel: str,
    now: datetime | None = None,
) -> bool:
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(hours=WATCHLIST_ALERT_DEDUP_HOURS)
    alert_key = build_watchlist_alert_delivery_key(alert_item)
    existing = (
        db.query(WatchlistAlertDelivery)
        .filter(
            WatchlistAlertDelivery.user_id == user_id,
            WatchlistAlertDelivery.watchlist_id == watchlist_id,
            WatchlistAlertDelivery.channel == channel,
            WatchlistAlertDelivery.alert_key == alert_key,
            WatchlistAlertDelivery.sent_at >= cutoff,
        )
        .first()
    )
    return existing is not None


def record_watchlist_alert_delivery(
    db: Session,
    user_id: int,
    watchlist_id: str,
    alert_item: dict,
    *,
    channel: str,
    now: datetime | None = None,
) -> WatchlistAlertDelivery:
    delivery = WatchlistAlertDelivery(
        user_id=user_id,
        watchlist_id=watchlist_id,
        symbol=alert_item.get("symbol") or "",
        channel=channel,
        alert_key=build_watchlist_alert_delivery_key(alert_item),
        alert_type=alert_item.get("alertType") or "watch",
        priority_label=normalize_alert_priority(alert_item.get("priorityLabel")),
        priority_score=clamp_alert_score(alert_item.get("priorityScore")),
        sent_at=now or datetime.now(timezone.utc),
    )
    db.add(delivery)
    return delivery


def normalize_rule_type(rule_type: str) -> str:
    normalized = str(rule_type or "").strip().lower()
    if normalized not in ALERT_RULE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported alert rule type")
    return normalized


def normalize_rule_direction(rule_type: str, direction: str | None) -> str | None:
    if direction is None:
        return None
    normalized = str(direction).strip()
    if not normalized:
        return None
    if rule_type == "signal_direction":
        normalized = normalized.upper()
        if normalized not in {"UP", "DOWN", "HOLD"}:
            raise HTTPException(status_code=400, detail="Unsupported signal direction")
        return normalized
    if rule_type == "news_sentiment":
        normalized = normalized.lower()
        if normalized not in {"bullish", "bearish", "neutral"}:
            raise HTTPException(status_code=400, detail="Unsupported news sentiment direction")
        return normalized
    return normalized


def normalize_rule_tag(tag: str | None) -> str | None:
    normalized_tags = normalize_tags([tag] if tag is not None else [])
    return normalized_tags[0] if normalized_tags else None


def get_watchlist_item_symbol_or_400(record: WatchlistRecord, symbol: str) -> str:
    canonical_symbol = canonicalize_symbol(symbol)
    for item in record.items:
        if canonicalize_symbol(item.symbol) == canonical_symbol:
            return item.symbol
    raise HTTPException(status_code=400, detail="Alert rule symbol must exist in the watchlist")


def get_alert_rule_or_404(db: Session, user: User, rule_id: int) -> AlertRuleRecord:
    rule = (
        db.query(AlertRuleRecord)
        .filter(AlertRuleRecord.user_id == user.id, AlertRuleRecord.id == rule_id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return rule


def serialize_alert_rule(rule: AlertRuleRecord) -> dict:
    return {
        "id": rule.id,
        "watchlistId": rule.watchlist_id,
        "symbol": rule.symbol,
        "name": rule.name,
        "ruleType": rule.rule_type,
        "threshold": rule.threshold_value,
        "direction": rule.direction,
        "tag": rule.tag,
        "enabled": rule.enabled,
        "snoozedUntil": rule.snoozed_until.isoformat() if rule.snoozed_until else None,
        "lastTriggeredAt": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
        "createdAt": rule.created_at.isoformat() if rule.created_at else None,
    }


def serialize_alert_event(event: AlertEventRecord) -> dict:
    payload = {}
    try:
        payload = json.loads(event.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "id": event.id,
        "ruleId": event.alert_rule_id,
        "watchlistId": event.watchlist_id,
        "symbol": event.symbol,
        "eventType": event.event_type,
        "severity": event.severity,
        "status": event.status,
        "title": event.title,
        "message": event.message,
        "payload": payload,
        "triggeredAt": event.triggered_at.isoformat() if event.triggered_at else None,
        "acknowledgedAt": event.acknowledged_at.isoformat() if event.acknowledged_at else None,
    }


def build_alert_event_payload(rule: AlertRuleRecord, alert_item: dict) -> dict | None:
    rule_type = rule.rule_type
    symbol = alert_item.get("symbol") or rule.symbol
    threshold = rule.threshold_value

    if rule_type == "provider_move":
        provider_context = alert_item.get("providerContext") or {}
        change_percent = provider_context.get("changePercent")
        if change_percent is None:
            return None
        threshold_value = 1.0 if threshold is None else float(threshold)
        if abs(float(change_percent)) < threshold_value:
            return None
        severity = "high" if abs(float(change_percent)) >= 5 else "medium" if abs(float(change_percent)) >= 2 else "low"
        return {
            "severity": severity,
            "title": f"{symbol} provider move",
            "message": f"{symbol} moved {float(change_percent):+.2f}% on provider data.",
            "trigger": {
                "changePercent": change_percent,
                "threshold": threshold_value,
                "source": provider_context.get("source"),
            },
        }

    if rule_type == "news_sentiment":
        news = alert_item.get("news") or {}
        label = news.get("aggregateLabel")
        score = abs(float(news.get("aggregateScore") or 0.0))
        threshold_value = 0.1 if threshold is None else float(threshold)
        direction = rule.direction
        if direction and label != direction:
            return None
        if not direction and label == "neutral":
            return None
        if score < threshold_value:
            return None
        return {
            "severity": "medium" if score < 0.4 else "high",
            "title": f"{symbol} news sentiment",
            "message": f"{symbol} has {label} watchlist news sentiment.",
            "trigger": {"label": label, "score": score, "threshold": threshold_value},
        }

    if rule_type == "signal_direction":
        signal = alert_item.get("signal") or {}
        direction = rule.direction or "UP"
        confidence = float(signal.get("confidence") or 0.0)
        threshold_value = 0.75 if threshold is None else float(threshold)
        if signal.get("direction") != direction or confidence < threshold_value:
            return None
        return {
            "severity": "high" if confidence >= 0.85 else "medium",
            "title": f"{symbol} {direction} signal",
            "message": f"{symbol} signal direction is {direction} with {confidence * 100:.1f}% confidence.",
            "trigger": {"direction": direction, "confidence": confidence, "threshold": threshold_value},
        }

    if rule_type == "tag_priority":
        tags = {str(tag).lower() for tag in alert_item.get("tags") or []}
        if rule.tag and rule.tag not in tags:
            return None
        priority_score = int(alert_item.get("priorityScore") or 0)
        threshold_value = 45 if threshold is None else int(threshold)
        if priority_score < threshold_value:
            return None
        return {
            "severity": alert_item.get("priorityLabel") or "medium",
            "title": f"{symbol} watchlist priority",
            "message": f"{symbol} reached watchlist priority score {priority_score}.",
            "trigger": {
                "priorityScore": priority_score,
                "threshold": threshold_value,
                "tag": rule.tag,
            },
        }

    return None


def rule_is_snoozed(rule: AlertRuleRecord) -> bool:
    if not rule.snoozed_until:
        return False
    snoozed_until = rule.snoozed_until
    if snoozed_until.tzinfo is None:
        snoozed_until = snoozed_until.replace(tzinfo=timezone.utc)
    return snoozed_until > datetime.now(timezone.utc)


def evaluate_alert_rules(db: Session, user: User) -> list[AlertEventRecord]:
    rules = (
        db.query(AlertRuleRecord)
        .filter(AlertRuleRecord.user_id == user.id, AlertRuleRecord.enabled == True)
        .all()
    )
    watchlist_payloads: dict[str, dict] = {}
    created_events: list[AlertEventRecord] = []

    for rule in rules:
        if rule_is_snoozed(rule):
            continue

        if rule.watchlist_id not in watchlist_payloads:
            record = get_watchlist_record_or_404(db, user, rule.watchlist_id)
            watchlist_payloads[rule.watchlist_id] = build_watchlist_alert_payload(
                db,
                user,
                record,
                limit=max(10, len(record.items)),
                news_limit=2,
            )

        payload = watchlist_payloads[rule.watchlist_id]
        alert_item = next(
            (
                item
                for item in payload.get("items", [])
                if canonicalize_symbol(item.get("symbol")) == canonicalize_symbol(rule.symbol)
            ),
            None,
        )
        if not alert_item:
            continue

        event_payload = build_alert_event_payload(rule, alert_item)
        if not event_payload:
            continue

        existing_open = (
            db.query(AlertEventRecord)
            .filter(
                AlertEventRecord.user_id == user.id,
                AlertEventRecord.alert_rule_id == rule.id,
                AlertEventRecord.status == "open",
            )
            .first()
        )
        if existing_open:
            continue

        rule.last_triggered_at = datetime.now(timezone.utc)
        event = AlertEventRecord(
            user_id=user.id,
            alert_rule_id=rule.id,
            watchlist_id=rule.watchlist_id,
            symbol=rule.symbol,
            event_type=rule.rule_type,
            severity=event_payload["severity"],
            status="open",
            title=event_payload["title"],
            message=event_payload["message"],
            payload_json=json.dumps(
                {
                    "rule": serialize_alert_rule(rule),
                    "trigger": event_payload["trigger"],
                    "alert": alert_item,
                },
                default=str,
            ),
        )
        db.add(event)
        created_events.append(event)

    if created_events:
        db.commit()
        for event in created_events:
            db.refresh(event)
    return created_events


def build_push_alert_payload(watchlist: WatchlistRecord, alert_item: dict) -> dict:
    symbol = alert_item.get("symbol") or "watchlist item"
    priority = str(alert_item.get("priorityLabel") or "alert").upper()
    signal = alert_item.get("signal") if isinstance(alert_item.get("signal"), dict) else {}
    direction = signal.get("direction") or "WATCH"
    score = int(alert_item.get("priorityScore") or 0)
    return {
        "title": f"NexusPulse {priority} Alert: {symbol}",
        "body": f"{direction} signal on {watchlist.name} with priority score {score}.",
        "url": f"/analysis/{symbol}",
        "watchlistId": watchlist.id,
        "symbol": symbol,
        "priority": alert_item.get("priorityLabel"),
        "score": score,
    }


def dispatch_watchlist_push_alerts(
    db: Session,
    user: User,
    watchlist: WatchlistRecord,
    setting: WatchlistAlertSetting,
) -> int:
    if not setting.enabled or not setting.push_enabled:
        return 0

    payload = build_watchlist_alert_payload(db, user, watchlist, setting=setting)
    dispatched = 0
    now = datetime.now(timezone.utc)
    for alert_item in payload.get("items", []):
        notification = alert_item.get("notification") if isinstance(alert_item.get("notification"), dict) else {}
        if not notification.get("pushEligible"):
            continue
        if was_watchlist_alert_recently_delivered(
            db,
            user.id,
            watchlist.id,
            alert_item,
            channel="push",
            now=now,
        ):
            continue

        sent_count = PushService.send_notification_to_user(
            db,
            user.id,
            build_push_alert_payload(watchlist, alert_item),
        )
        if sent_count:
            record_watchlist_alert_delivery(
                db,
                user.id,
                watchlist.id,
                alert_item,
                channel="push",
                now=now,
            )
            dispatched += 1
            logger.info(
                "watchlist_push_alert_dispatched",
                extra={
                    "user_id": user.id,
                    "watchlist_id": watchlist.id,
                    "symbol": alert_item.get("symbol"),
                    "priority": alert_item.get("priorityLabel"),
                },
            )

    if dispatched:
        db.commit()
    return dispatched


def dispatch_configured_watchlist_alerts(db: Session) -> int:
    settings = (
        db.query(WatchlistAlertSetting)
        .filter(
            WatchlistAlertSetting.enabled.is_(True),
            WatchlistAlertSetting.push_enabled.is_(True),
        )
        .all()
    )
    dispatched = 0
    for setting in settings:
        user = setting.user
        watchlist = setting.watchlist
        if not user or not user.is_active or not watchlist or not watchlist.items:
            continue
        try:
            dispatched += dispatch_watchlist_push_alerts(db, user, watchlist, setting)
        except Exception:
            logger.exception(
                "watchlist_alert_dispatch_failed user_id=%s watchlist_id=%s",
                setting.user_id,
                setting.watchlist_id,
            )
    return dispatched


def get_user_watchlist_symbol_name(db: Session, user: User, symbol: str) -> str | None:
    canonical_symbol = canonicalize_symbol(symbol)
    record = (
        db.query(WatchlistItemRecord)
        .join(WatchlistRecord, WatchlistRecord.id == WatchlistItemRecord.watchlist_id)
        .filter(WatchlistRecord.user_id == user.id)
        .all()
    )
    for item in record:
        if canonicalize_symbol(item.symbol) == canonical_symbol and item.name:
            return item.name
    return None


DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Models
class WatchlistItem(BaseModel):
    symbol: str
    name: str = ""
    tags: List[str] = Field(default_factory=list)
    assetClass: str | None = None
    assetLabel: str | None = None
    market: str | None = None
    exchange: str | None = None
    type: str | None = None
    isCrypto: bool = False


class WatchlistItemRequest(BaseModel):
    symbol: str
    name: str = ""
    tags: List[str] = Field(default_factory=list)


class UpdateWatchlistItemRequest(BaseModel):
    name: str | None = None
    tags: List[str] | None = None

class Watchlist(BaseModel):
    id: str
    name: str
    items: List[WatchlistItem]

class AlertRuleRequest(BaseModel):
    watchlistId: str
    symbol: str
    ruleType: str
    name: str = ""
    threshold: float | None = None
    direction: str | None = None
    tag: str | None = None
    enabled: bool = True
    snoozedUntil: datetime | None = None


class UpdateAlertRuleRequest(BaseModel):
    name: str | None = None
    threshold: float | None = None
    direction: str | None = None
    tag: str | None = None
    enabled: bool | None = None
    snoozedUntil: datetime | None = None


class CreateWatchlistRequest(BaseModel):
    name: str

class RenameWatchlistRequest(BaseModel):
    name: str


class WatchlistAlertSettingsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool | None = None
    toast_enabled: bool | None = Field(default=None, alias="toastEnabled")
    push_enabled: bool | None = Field(default=None, alias="pushEnabled")
    min_priority: str | None = Field(default=None, alias="minPriority")
    min_score: int | None = Field(default=None, ge=0, le=100, alias="minScore")


class PaperOrderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    symbol: str
    side: str
    qty: float = Field(gt=0)
    limit_price: float | None = Field(default=None, alias="limitPrice")
    target_price: float | None = Field(default=None, alias="targetPrice")
    source: str = "manual"

# Default Data
DEFAULT_WATCHLISTS = [
    Watchlist(
        id="default",
        name="Tech Giants",
        items=[
            WatchlistItem(symbol="NVDA", name="NVIDIA Corp"),
            WatchlistItem(symbol="AAPL", name="Apple Inc"),
            WatchlistItem(symbol="MSFT", name="Microsoft Corp"),
            WatchlistItem(symbol="GOOGL", name="Alphabet Inc"),
        ]
    ),
    Watchlist(
        id="crypto",
        name="Crypto Proxies",
        items=[
            WatchlistItem(symbol="COIN", name="Coinbase Global"),
            WatchlistItem(symbol="MSTR", name="MicroStrategy"),
            WatchlistItem(symbol="MARA", name="Marathon Digital"),
        ]
    )
]

def serialize_watchlist(record: WatchlistRecord) -> Watchlist:
    return Watchlist(
        id=record.id,
        name=record.name,
        items=[
            serialize_watchlist_item(item)
            for item in sorted(record.items, key=lambda current: current.id or 0)
        ],
    )


def seed_default_watchlists(db: Session, user: User) -> None:
    existing = db.query(WatchlistRecord).filter(WatchlistRecord.user_id == user.id).count()
    if existing:
        return

    for default_watchlist in DEFAULT_WATCHLISTS:
        record = WatchlistRecord(
            id=str(uuid.uuid4())[:8],
            user_id=user.id,
            name=default_watchlist.name,
            is_default=True,
        )
        record.items = [
            WatchlistItemRecord(symbol=item.symbol, name=item.name or "")
            for item in default_watchlist.items
        ]
        db.add(record)
    db.commit()


def get_user_watchlist_records(db: Session, user: User) -> list[WatchlistRecord]:
    seed_default_watchlists(db, user)
    return (
        db.query(WatchlistRecord)
        .filter(WatchlistRecord.user_id == user.id)
        .all()
    )


def get_watchlist_record_or_404(db: Session, user: User, watchlist_id: str) -> WatchlistRecord:
    record = (
        db.query(WatchlistRecord)
        .filter(WatchlistRecord.user_id == user.id, WatchlistRecord.id == watchlist_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return record

# --- APP SETUP ---
# --- BACKGROUND SCANNER ---
async def auto_scanner_task():
    logger.info("auto_scanner_started")
    # Wait for the system to boot up fully before first scan
    await asyncio.sleep(60)
    
    while True:
        try:
            logger.debug("auto_scanner_cycle_started")
            db = SessionLocal()
            try:
                users = db.query(User).filter(User.is_active == True).all()
                if not users:
                    logger.debug("auto_scanner_skipped_no_active_users")
                else:
                    unique_symbols = set()
                    for user in users:
                        for watchlist in get_user_watchlist_records(db, user):
                            for item in watchlist.items:
                                unique_symbols.add(item.symbol)

                    for sym in unique_symbols:
                        try:
                            res = service.get_stock_data(sym, include_fundamentals=False)
                            pred = res.get('prediction')
                            df = res.get('data')

                            if not pred or df is None or df.empty:
                                continue

                            base_direction = pred.get('direction')
                            conf = pred.get('confidence', 0)

                            # Only alert on strong signals
                            if conf >= 0.75 and base_direction in ['UP', 'DOWN']:
                                latest = df.iloc[-1]
                                close_price = float(latest['Close'])
                                atr = float(latest.get('ATR', 0))
                                expected_gain_pct = ((atr * 1.5) / close_price) * 100 if close_price > 0 else 0

                                for user in users:
                                    min_yield = float(user.min_target_yield)
                                    fee_pct = float(user.trade_fee_percent)
                                    fee_abs_pct = (float(user.trade_fee_absolute) / close_price) * 100 if close_price > 0 else 0
                                    req_yield = min_yield + fee_pct + fee_abs_pct

                                    final_direction = base_direction
                                    if base_direction == 'UP' and expected_gain_pct < req_yield:
                                        final_direction = 'HOLD'

                                    if final_direction in ['UP', 'DOWN']:
                                        action = "BUY" if final_direction == 'UP' else "SELL"
                                        action_icon = "🟢" if action == "BUY" else "🔴"
                                        PushService.send_notification_to_user(db, user.id, {
                                            "title": f"NexusPulse {action_icon} {action} {sym}",
                                            "body": f"Strong {action} signal ({int(conf*100)}% conf). Expected Yield: {expected_gain_pct:.1f}%. Required margin: {req_yield:.1f}%",
                                            "url": f"/analysis/{sym}"
                                        })
                                        logger.info(
                                            "auto_scanner_alert_sent",
                                            extra={
                                                "user_id": user.id,
                                                "action": action,
                                                "symbol": sym,
                                            },
                                        )
                        except Exception:
                            logger.exception("auto_scanner_symbol_failed symbol=%s", sym)
            finally:
                db.close()
                
        except Exception:
            logger.exception("auto_scanner_cycle_failed")
            
        # Scan every 15 minutes
        await asyncio.sleep(60 * 15)


async def paper_order_fill_task():
    logger.info(
        "paper_order_fill_task_started interval_seconds=%s",
        PAPER_ORDER_FILL_INTERVAL_SECONDS,
    )
    await asyncio.sleep(PAPER_ORDER_FILL_INITIAL_DELAY_SECONDS)

    while True:
        try:
            db = SessionLocal()
            try:
                filled = paper_trading.dispatch_pending_orders(
                    db,
                    service.get_latest_close,
                    asset_class_resolver=_asset_class_resolver,
                    avg_daily_volume_provider=service.get_avg_daily_volume,
                )
                if filled:
                    logger.info(
                        "paper_order_fill_task_cycle_completed",
                        extra={"filled_orders": filled},
                    )
            finally:
                db.close()
        except Exception:
            logger.exception("paper_order_fill_task_cycle_failed")

        await asyncio.sleep(PAPER_ORDER_FILL_INTERVAL_SECONDS)


async def ml_retrain_task():
    """Periodically refresh stale per-symbol predictors in the background.

    Walks the union of (a) symbols held across all watchlists and (b)
    already-persisted models on disk, and re-trains each entry whose
    on-disk metadata has aged past the configured TTL. Reduces the
    first-`/api/stock/{symbol}` latency hit when the user opens an
    analysis page after a long quiet period.
    """
    from app import ml_persistence
    from app.models import WatchlistItem as WatchlistItemRecord

    logger.info(
        "ml_retrain_task_started interval_seconds=%s",
        ML_RETRAIN_INTERVAL_SECONDS,
    )
    await asyncio.sleep(ML_RETRAIN_INITIAL_DELAY_SECONDS)

    while True:
        try:
            db = SessionLocal()
            try:
                watchlist_symbols = {
                    str(item.symbol).upper()
                    for item in db.query(WatchlistItemRecord).all()
                    if item.symbol
                }
                persisted_symbols = {row["symbol"] for row in ml_persistence.list_models()}
                candidates = sorted(watchlist_symbols | persisted_symbols)
                refreshed = 0
                for symbol in candidates:
                    try:
                        loaded = ml_persistence.load_predictor(symbol, lambda: __import__("app.ml_models", fromlist=["PricePredictor"]).PricePredictor())
                    except Exception:
                        loaded = None
                    metadata = loaded[1] if loaded else None
                    if metadata is not None and not ml_persistence.is_stale(metadata):
                        continue
                    try:
                        stock = service.get_stock_data(
                            symbol,
                            period="6mo",
                            interval="1d",
                            user=None,
                            include_news=False,
                            include_fundamentals=False,
                        )
                    except Exception:
                        logger.exception("ml_retrain_fetch_failed symbol=%s", symbol)
                        continue
                    df = stock.get("data") if isinstance(stock, dict) else None
                    if df is None or df.empty:
                        continue
                    # Re-running get_or_train_predictor inside a fresh-fetch
                    # path persists the new model as a side effect because
                    # the in-memory cache for that symbol is now stale.
                    service._predictor_cache.pop(symbol, None)
                    service._get_or_train_predictor(symbol, df)
                    refreshed += 1
                if refreshed:
                    logger.info(
                        "ml_retrain_task_cycle_completed",
                        extra={"refreshed_symbols": refreshed, "total_candidates": len(candidates)},
                    )
            finally:
                db.close()
        except Exception:
            logger.exception("ml_retrain_task_cycle_failed")

        await asyncio.sleep(ML_RETRAIN_INTERVAL_SECONDS)


async def auto_execution_paper_loop_task():
    """Auto-paper-trading loop.

    For every user with `auto_execution_limits.enabled=True AND mode='paper'`,
    walk the union of their watchlist symbols, run each through the
    existing prediction pipeline, and submit a paper-trading order when
    `evaluate_proposal_from_prediction` returns `allowed=True`. The loop
    NEVER calls Alpaca — paper-mode is wired to the in-process paper
    book only. Live-mode lives behind a separate gate that this task
    deliberately ignores.

    Per-loop guardrails:
    - Hard cap of `AUTO_EXECUTION_PAPER_MAX_TRADES_PER_LOOP` orders per
      user, regardless of how many watchlist symbols would otherwise pass.
    - Symbol-level try/except so one bad ticker can't take the whole loop
      down for the user.
    - No reentrant work for symbols the user already has an open paper
      order on (paper_order_fill_task handles fills separately).
    """
    from app.models import WatchlistItem as WatchlistItemRecord

    logger.info(
        "auto_execution_paper_loop_started interval_seconds=%s",
        AUTO_EXECUTION_PAPER_LOOP_INTERVAL_SECONDS,
    )
    await asyncio.sleep(AUTO_EXECUTION_PAPER_LOOP_INITIAL_DELAY_SECONDS)

    while True:
        try:
            db = SessionLocal()
            try:
                # Strict allowlist: only users explicitly on `mode=paper`.
                # Even if a future bug somehow stored "live" in the column,
                # this loop never picks them up — and the live-mode branch
                # below would still refuse to place anything because the
                # paper_trading.place_order path is the only thing wired in.
                eligible_users = (
                    db.query(User)
                    .join(AutoExecutionLimitsRecord, AutoExecutionLimitsRecord.user_id == User.id)
                    .filter(
                        AutoExecutionLimitsRecord.enabled == True,  # noqa: E712
                        AutoExecutionLimitsRecord.mode == "paper",
                    )
                    .all()
                )
                if not eligible_users:
                    logger.debug("auto_execution_paper_loop_no_eligible_users")
                else:
                    fred_calendar: dict | None = None
                    try:
                        fred_calendar = get_fred_service().normalized_macro_calendar()
                    except Exception:
                        logger.exception("auto_execution_paper_loop_fred_lookup_failed")

                    for user in eligible_users:
                        try:
                            await asyncio.to_thread(
                                _run_auto_execution_paper_for_user,
                                db,
                                user,
                                fred_calendar,
                            )
                        except Exception:
                            logger.exception(
                                "auto_execution_paper_loop_user_failed user_id=%s", user.id
                            )
            finally:
                db.close()
        except Exception:
            logger.exception("auto_execution_paper_loop_cycle_failed")

        await asyncio.sleep(AUTO_EXECUTION_PAPER_LOOP_INTERVAL_SECONDS)


def _run_auto_execution_paper_for_user(
    db: Session, user: User, fred_calendar: dict | None
) -> None:
    """Synchronous per-user worker for the auto-paper-trading loop."""
    from app.models import WatchlistItem as WatchlistItemRecord

    watchlist_ids = [
        wl.id
        for wl in db.query(WatchlistRecord).filter(WatchlistRecord.user_id == user.id).all()
    ]
    if not watchlist_ids:
        return
    symbols = sorted(
        {
            str(item.symbol).upper()
            for item in db.query(WatchlistItemRecord)
            .filter(WatchlistItemRecord.watchlist_id.in_(watchlist_ids))
            .all()
            if item.symbol
        }
    )
    if not symbols:
        return

    trades_placed = 0
    for symbol in symbols:
        if trades_placed >= AUTO_EXECUTION_PAPER_MAX_TRADES_PER_LOOP:
            break
        try:
            # Skip symbols where we already have an open paper position
            # waiting to fill — no point stacking proposals on the same name.
            already_open = (
                db.query(PaperOrderRecord)
                .filter(
                    PaperOrderRecord.user_id == user.id,
                    PaperOrderRecord.symbol == symbol,
                    PaperOrderRecord.status.in_(["pending", "filled"]),
                )
                .count()
            )
            if already_open > 0:
                continue

            stock_payload = service.get_stock_data(symbol, period="6mo", interval="1d", user=user)
            if not stock_payload:
                continue
            prediction = stock_payload.get("prediction") or {}
            asset_profile = stock_payload.get("asset") or {}
            asset_class = asset_profile.get("assetClass")
            sector = (stock_payload.get("info") or {}).get("sector")

            sec_filings = None
            if (asset_class or "").lower() != "crypto" and service.fmp.configured:
                try:
                    sec_filings = service.fmp.normalized_sec_filings(symbol)
                except Exception:
                    logger.exception("auto_execution_paper_sec_lookup_failed symbol=%s", symbol)
            sector_context = None
            if (asset_class or "").lower() != "crypto":
                try:
                    sector_context = get_sector_service().get_sector_context(symbol, sector=sector)
                except Exception:
                    logger.exception(
                        "auto_execution_paper_sector_lookup_failed symbol=%s", symbol
                    )

            latest_close = service.get_latest_close(symbol)

            decision, proposal = auto_execution.evaluate_proposal_from_prediction(
                db,
                user,
                symbol=symbol,
                asset_class=asset_class,
                sector=sector,
                prediction=prediction,
                latest_close=latest_close,
                sec_filings=sec_filings,
                fred_calendar=fred_calendar,
                sector_context=sector_context,
            )
            if not (decision.allowed and proposal):
                continue

            try:
                order = paper_trading.place_order(
                    db=db,
                    user=user,
                    symbol=str(proposal["symbol"]),
                    side=str(proposal["side"]),
                    qty=float(proposal["qty"]),
                    limit_price=float(proposal["limitPrice"]) if proposal.get("limitPrice") else None,
                    target_price=float(proposal["targetPrice"]) if proposal.get("targetPrice") else None,
                    source="auto-execution-paper",
                    latest_close_provider=service.get_latest_close,
                    asset_class_resolver=_asset_class_resolver,
                    avg_daily_volume_provider=service.get_avg_daily_volume,
                )
            except Exception as exc:
                auto_execution.record_event(
                    db,
                    user,
                    status="failed",
                    proposal_id=str(proposal.get("proposalId") or ""),
                    symbol=symbol,
                    side=str(proposal.get("side") or ""),
                    reason=f"paper_order_place_failed: {exc!s}",
                    payload={"proposal": proposal},
                )
                continue

            auto_execution.record_event(
                db,
                user,
                status="executed",
                proposal_id=str(proposal.get("proposalId") or ""),
                symbol=symbol,
                side=str(proposal.get("side") or ""),
                reason="auto-execution paper order placed",
                payload={
                    "proposal": proposal,
                    "paperOrderId": order.id,
                    "mode": "paper",
                },
            )
            trades_placed += 1
            logger.info(
                "auto_execution_paper_order_placed user_id=%s symbol=%s side=%s qty=%s",
                user.id,
                symbol,
                proposal["side"],
                proposal["qty"],
            )
        except Exception:
            logger.exception(
                "auto_execution_paper_loop_symbol_failed user_id=%s symbol=%s",
                user.id,
                symbol,
            )


async def watchlist_alert_dispatch_task():
    logger.info(
        "watchlist_alert_dispatcher_started interval_seconds=%s dedup_hours=%s",
        WATCHLIST_ALERT_DISPATCH_INTERVAL_SECONDS,
        WATCHLIST_ALERT_DEDUP_HOURS,
    )
    await asyncio.sleep(WATCHLIST_ALERT_DISPATCH_INITIAL_DELAY_SECONDS)

    while True:
        try:
            db = SessionLocal()
            try:
                dispatched = dispatch_configured_watchlist_alerts(db)
                logger.info(
                    "watchlist_alert_dispatcher_cycle_completed",
                    extra={"dispatched_alerts": dispatched},
                )
            finally:
                db.close()
        except Exception:
            logger.exception("watchlist_alert_dispatcher_cycle_failed")

        await asyncio.sleep(WATCHLIST_ALERT_DISPATCH_INTERVAL_SECONDS)

# Initialize database on startup
@app.on_event("startup")
async def on_startup():
    init_db()
    push_config = PushService.validate_configuration()
    logger.info(
        "push_configuration_validated",
        extra={
            "configured": push_config["configured"],
            "required": push_config["required"],
        },
    )
    bootstrap_db = SessionLocal()
    try:
        ensure_initial_admin(bootstrap_db)
    finally:
        bootstrap_db.close()
    migrate_watchlists()
    logger.info("application_startup_complete")
    logger.info("alpaca_stream_starting")
    # Start the stream in the background
    asyncio.create_task(alpaca_stream.start())
    # Start the auto-scanner
    asyncio.create_task(auto_scanner_task())
    asyncio.create_task(watchlist_alert_dispatch_task())
    asyncio.create_task(paper_order_fill_task())
    asyncio.create_task(ml_retrain_task())
    asyncio.create_task(auto_execution_paper_loop_task())
    asyncio.create_task(backup_scheduler_task())

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("application_shutdown_started")
    await alpaca_stream.stop()


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = normalize_request_id(request.headers.get("x-request-id"))
    request.state.request_id = request_id
    context_token = set_request_log_context(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else None,
    )
    started_at = perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        logger.exception(
            "request_failed",
            extra={
                "status_code": 500,
                "duration_ms": duration_ms,
            },
        )
        raise
    else:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
    finally:
        reset_request_log_context(context_token)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount auth routes (no auth required for these)
app.include_router(auth_router)

alpaca = AlpacaService()
service = MarketDataService(alpaca)

# --- WEBSOCKET ENDPOINT ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We just keep the connection open to receive messages from the client if needed
            data = await websocket.receive_text()
            # If the client sends something like {"action": "subscribe", "symbol": "AAPL"}
            # We could parse and handle it here. For MVP, we just ping-pong or ignore.
    except WebSocketDisconnect:
        manager.disconnect(websocket)

class OrderRequest(BaseModel):
    symbol: str
    qty: int
    side: str
    type: str = 'market'

@app.get("/")
def read_root():
    return {"status": "online", "message": "AI Trading Bot Backend V2"}

@app.get("/api/docs/topics")
def list_doc_topics(lang: str | None = None):
    """Public list of in-app help topics. No auth — the docs are
    descriptive, not sensitive. `lang=de` returns the German variant
    of any topic that has been translated; missing translations fall
    back to English transparently."""
    return {
        "topics": docs_service.list_topics(locale=lang),
        "pageMap": docs_service.get_page_to_topic_map(locale=lang),
        "supportedLocales": list(docs_service.supported_locales()),
    }


@app.get("/api/docs/{slug}")
def get_doc_topic(slug: str, lang: str | None = None):
    topic = docs_service.get_topic(slug, locale=lang)
    if topic is None:
        raise HTTPException(status_code=404, detail="Doc topic not found")
    return topic


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "trading-bot-backend"}

# --- WATCHLIST ENDPOINTS ---

@app.get("/api/watchlists", response_model=List[Watchlist])
def get_watchlists(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [serialize_watchlist(record) for record in get_user_watchlist_records(db, current_user)]

@app.post("/api/watchlists", response_model=Watchlist)
def create_watchlist(req: CreateWatchlistRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    seed_default_watchlists(db, current_user)
    new_record = WatchlistRecord(id=str(uuid.uuid4())[:8], user_id=current_user.id, name=req.name)
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return serialize_watchlist(new_record)

@app.put("/api/watchlists/{id}", response_model=Watchlist)
def rename_watchlist(id: str, req: RenameWatchlistRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = get_watchlist_record_or_404(db, current_user, id)
    record.name = req.name
    db.commit()
    db.refresh(record)
    return serialize_watchlist(record)

@app.delete("/api/watchlists/{id}")
def delete_watchlist(id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = get_watchlist_record_or_404(db, current_user, id)
    if record.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default watchlist")
    db.delete(record)
    db.commit()
    return {"status": "deleted", "id": id}

@app.post("/api/watchlists/{id}/items")
def add_item(id: str, item: WatchlistItemRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = get_watchlist_record_or_404(db, current_user, id)
    canonical_symbol = canonicalize_symbol(item.symbol)
    existing = next((current for current in record.items if canonicalize_symbol(current.symbol) == canonical_symbol), None)
    if existing:
        if item.name:
            existing.name = item.name
        apply_watchlist_item_tags(existing, item.tags)
    else:
        new_item = WatchlistItemRecord(watchlist_id=record.id, symbol=canonical_symbol, name=item.name or "")
        apply_watchlist_item_tags(new_item, item.tags)
        db.add(new_item)
    db.commit()
    db.refresh(record)
    return serialize_watchlist(record)

@app.put("/api/watchlists/{id}/items/{symbol:path}")
def update_item(id: str, symbol: str, req: UpdateWatchlistItemRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = get_watchlist_record_or_404(db, current_user, id)
    canonical_symbol = canonicalize_symbol(symbol)
    target_item = next((current for current in record.items if canonicalize_symbol(current.symbol) == canonical_symbol), None)
    if not target_item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")

    if req.name is not None:
        target_item.name = req.name
    if req.tags is not None:
        apply_watchlist_item_tags(target_item, req.tags)
    db.commit()
    db.refresh(record)
    return serialize_watchlist(record)

@app.delete("/api/watchlists/{id}/items/{symbol:path}")
def remove_item(id: str, symbol: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = get_watchlist_record_or_404(db, current_user, id)
    canonical_symbol = canonicalize_symbol(symbol)
    target_item = next((existing for existing in record.items if canonicalize_symbol(existing.symbol) == canonical_symbol), None)
    if target_item:
        db.delete(target_item)
        db.commit()
        db.refresh(record)
    return serialize_watchlist(record)


@app.get("/api/watchlists/{id}/alert-settings")
def get_watchlist_alert_settings(
    id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_watchlist_record_or_404(db, current_user, id)
    setting = get_or_create_watchlist_alert_setting(db, current_user, record)
    return serialize_alert_setting(setting)


@app.put("/api/watchlists/{id}/alert-settings")
def update_watchlist_alert_settings(
    id: str,
    req: WatchlistAlertSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_watchlist_record_or_404(db, current_user, id)
    setting = get_or_create_watchlist_alert_setting(db, current_user, record)

    if req.enabled is not None:
        setting.enabled = req.enabled
    if req.toast_enabled is not None:
        setting.toast_enabled = req.toast_enabled
    if req.push_enabled is not None:
        setting.push_enabled = req.push_enabled
    if req.min_priority is not None:
        setting.min_priority = normalize_alert_priority(req.min_priority)
    if req.min_score is not None:
        setting.min_score = clamp_alert_score(req.min_score)

    db.commit()
    db.refresh(setting)
    return serialize_alert_setting(setting)


@app.get("/api/watchlists/{id}/news")
def get_watchlist_news(
    id: str,
    limit_per_symbol: int = Query(default=5, ge=1, le=20),
    limit_total: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_watchlist_record_or_404(db, current_user, id)
    tracked_assets = [serialize_tracked_watchlist_item(item) for item in sorted(record.items, key=lambda current: current.id or 0)]

    news_items: list[dict] = []
    for tracked in tracked_assets:
        news_payload = service.get_market_news(tracked["symbol"], asset_profile=tracked)
        for news_item in news_payload.get("items", [])[:limit_per_symbol]:
            news_items.append(
                {
                    "symbol": tracked["symbol"],
                    "name": tracked["name"],
                    "tags": tracked["tags"],
                    **asset_response_fields(tracked),
                    "title": news_item.get("title"),
                    "summary": news_item.get("summary"),
                    "score": news_item.get("score"),
                    "label": news_item.get("label"),
                    "timestamp": news_item.get("timestamp"),
                    "url": news_item.get("url"),
                    "source": news_item.get("source"),
                }
            )

    news_items.sort(key=lambda current: current.get("timestamp") or "", reverse=True)
    news_items = news_items[:limit_total]

    return {
        "watchlist": {"id": record.id, "name": record.name},
        "trackedAssets": tracked_assets,
        "items": news_items,
        "summary": {
            "trackedSymbols": len(tracked_assets),
            "newsItems": len(news_items),
            "bullish": sum(1 for item in news_items if item.get("label") == "bullish"),
            "bearish": sum(1 for item in news_items if item.get("label") == "bearish"),
            "neutral": sum(1 for item in news_items if item.get("label") == "neutral"),
        },
    }


@app.get("/api/watchlists/{id}/alerts")
def get_watchlist_alerts(
    id: str,
    limit: int = Query(default=10, ge=1, le=50),
    news_limit: int = Query(default=2, ge=1, le=5),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_watchlist_record_or_404(db, current_user, id)
    try:
        return build_watchlist_alert_payload(
            db,
            current_user,
            record,
            limit=limit,
            news_limit=news_limit,
        )
    except Exception:
        # Yahoo 429 / provider hiccup must not 500 the whole dashboard.
        # Return a degraded but well-shaped payload so the UI keeps rendering
        # the watchlist while the alerts column shows an empty state.
        logger.exception(
            "watchlist_alert_payload_failed watchlist_id=%s user_id=%s",
            id,
            current_user.id,
        )
        return {
            "watchlist": {"id": record.id, "name": record.name},
            "alertSettings": {},
            "notificationPlan": {"popupCount": 0, "pushCount": 0},
            "trackedAssets": [],
            "items": [],
            "summary": {
                "trackedSymbols": len(record.items),
                "popupEligible": 0,
                "pushEligible": 0,
                "degraded": True,
                "degradedReason": "provider_temporarily_unavailable",
            },
        }


# --- ALERT RULES / EVENTS ---

@app.get("/api/alerts/rules")
def list_alert_rules(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rules = (
        db.query(AlertRuleRecord)
        .filter(AlertRuleRecord.user_id == current_user.id)
        .order_by(AlertRuleRecord.id.asc())
        .all()
    )
    return {"items": [serialize_alert_rule(rule) for rule in rules]}


@app.post("/api/alerts/rules")
def create_alert_rule(
    request: AlertRuleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_watchlist_record_or_404(db, current_user, request.watchlistId)
    rule_type = normalize_rule_type(request.ruleType)
    symbol = get_watchlist_item_symbol_or_400(record, request.symbol)
    direction = normalize_rule_direction(rule_type, request.direction)
    tag = normalize_rule_tag(request.tag)
    rule = AlertRuleRecord(
        user_id=current_user.id,
        watchlist_id=record.id,
        symbol=symbol,
        name=request.name.strip() or f"{symbol} {rule_type.replace('_', ' ')}",
        rule_type=rule_type,
        threshold_value=request.threshold,
        direction=direction,
        tag=tag,
        enabled=request.enabled,
        snoozed_until=request.snoozedUntil,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return serialize_alert_rule(rule)


@app.put("/api/alerts/rules/{rule_id}")
def update_alert_rule(
    rule_id: int,
    request: UpdateAlertRuleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = get_alert_rule_or_404(db, current_user, rule_id)
    if request.name is not None:
        rule.name = request.name.strip() or rule.name
    if request.threshold is not None:
        rule.threshold_value = request.threshold
    if request.direction is not None:
        rule.direction = normalize_rule_direction(rule.rule_type, request.direction)
    if request.tag is not None:
        rule.tag = normalize_rule_tag(request.tag)
    if request.enabled is not None:
        rule.enabled = request.enabled
    if request.snoozedUntil is not None:
        rule.snoozed_until = request.snoozedUntil
    db.commit()
    db.refresh(rule)
    return serialize_alert_rule(rule)


@app.delete("/api/alerts/rules/{rule_id}")
def delete_alert_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = get_alert_rule_or_404(db, current_user, rule_id)
    db.delete(rule)
    db.commit()
    return {"status": "deleted", "id": rule_id}


@app.get("/api/alerts")
def evaluate_alerts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    created_events = evaluate_alert_rules(db, current_user)
    rules = (
        db.query(AlertRuleRecord)
        .filter(AlertRuleRecord.user_id == current_user.id)
        .order_by(AlertRuleRecord.id.asc())
        .all()
    )
    open_events = (
        db.query(AlertEventRecord)
        .filter(AlertEventRecord.user_id == current_user.id, AlertEventRecord.status == "open")
        .order_by(AlertEventRecord.triggered_at.desc(), AlertEventRecord.id.desc())
        .limit(50)
        .all()
    )
    return {
        "rules": [serialize_alert_rule(rule) for rule in rules],
        "events": [serialize_alert_event(event) for event in open_events],
        "summary": {
            "rules": len(rules),
            "enabledRules": sum(1 for rule in rules if rule.enabled),
            "openEvents": len(open_events),
            "createdEvents": len(created_events),
        },
    }


@app.get("/api/alerts/events")
def list_alert_events(
    status: str = Query(default="open", pattern="^(open|acknowledged|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(AlertEventRecord).filter(AlertEventRecord.user_id == current_user.id)
    if status != "all":
        query = query.filter(AlertEventRecord.status == status)
    events = query.order_by(AlertEventRecord.triggered_at.desc(), AlertEventRecord.id.desc()).limit(limit).all()
    return {"items": [serialize_alert_event(event) for event in events]}


@app.post("/api/alerts/events/{event_id}/ack")
def acknowledge_alert_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = (
        db.query(AlertEventRecord)
        .filter(AlertEventRecord.user_id == current_user.id, AlertEventRecord.id == event_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Alert event not found")
    event.status = "acknowledged"
    event.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)
    return serialize_alert_event(event)


# --- SCANNER ---

@app.get("/api/scanner")
def get_scanner_data(
    watchlist_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch data for symbols in a specific watchlist using Alpaca."""
    # 1. Determine which watchlist to use
    watchlists = get_user_watchlist_records(db, current_user)
    target_wl = None
    if watchlist_id:
        target_wl = next((w for w in watchlists if w.id == watchlist_id), None)

    if not target_wl and watchlists:
        target_wl = watchlists[0]

    if not target_wl or not target_wl.items:
        return []

    results = []

    for item in target_wl.items:
        sym = item.symbol
        market_symbol = canonicalize_symbol(sym)
        asset_profile = service.get_asset_profile(sym, fallback_name=item.name)
        provider_snapshot = service.get_provider_snapshot(sym, asset_profile=asset_profile)
        try:
            # History for 5 days to calculate change using Alpaca
            hist = alpaca.get_bars_df(market_symbol, timeframe='1Day', limit=5)

            if hist.empty:
                provider_quote = (provider_snapshot or {}).get("quote") or {}
                if provider_quote.get("price") is None:
                    results.append({
                        'symbol': sym,
                        'name': asset_profile['name'],
                        'price': 0,
                        'change': 0,
                        'changePercent': 0,
                        'history': [],
                        'provider': provider_snapshot,
                        **asset_response_fields(asset_profile),
                    })
                    continue

                results.append({
                    'symbol': sym,
                    'name': asset_profile['name'],
                    'price': round(float(provider_quote.get("price") or 0), 2),
                    'change': round(float(provider_quote.get("change") or 0), 2),
                    'changePercent': round(float(provider_quote.get("changePercent") or 0), 2),
                    'history': provider_quote.get("history") or [],
                    'provider': provider_snapshot,
                    **asset_response_fields(asset_profile),
                })
                continue

            current_price = float(hist['Close'].iloc[-1])
            prev_price = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price
            change = current_price - prev_price
            change_pct = (change / prev_price * 100) if prev_price else 0

            spark_hist = alpaca.get_bars_df(market_symbol, timeframe='1Day', limit=20)
            if spark_hist.empty and not hist.empty:
                spark_hist = hist

            sparkline = [{'close': round(float(r['Close']), 2)} for _, r in spark_hist.iterrows()]

            results.append({
                'symbol': sym,
                'name': asset_profile['name'],
                'price': round(current_price, 2),
                'change': round(change, 2),
                'changePercent': round(change_pct, 2),
                'history': sparkline,
                'provider': provider_snapshot,
                **asset_response_fields(asset_profile),
            })
        except Exception:
            logger.exception("scanner_symbol_failed symbol=%s", sym)
            results.append({
                'symbol': sym,
                'name': asset_profile['name'],
                'price': 0,
                'change': 0,
                'changePercent': 0,
                'history': [],
                'provider': provider_snapshot,
                **asset_response_fields(asset_profile),
            })

    return results

# --- STANDARD ANALYSIS/SEARCH ---

PERIOD_MAP = {
    "1D": ("1d", "5m"),
    "1W": ("5d", "15m"),
    "1M": ("1mo", "1h"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "1Y": ("1y", "1d"),
    "ALL": ("max", "1wk"),
}

@app.get("/api/stock/{symbol:path}")
def get_stock_analysis(symbol: str, timeframe: str = "6M", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tf = PERIOD_MAP.get(timeframe, PERIOD_MAP["6M"])
    period, interval = tf
    
    result = service.get_stock_data(symbol, period=period, interval=interval, user=current_user)
    
    if not result:
        raise HTTPException(status_code=404, detail="Stock data not found")
        
    df = result['data']
    chart_data = []
    
    for index, row in df.iterrows():
        def safe_float(val):
            return round(float(val), 4) if pd.notna(val) else None

        item = {
            'time': index.strftime('%Y-%m-%d %H:%M') if interval in ('5m','15m','1h') else index.strftime('%Y-%m-%d'),
            'open': safe_float(row['Open']),
            'high': safe_float(row['High']),
            'low': safe_float(row['Low']),
            'close': safe_float(row['Close']),
            'volume': int(row['Volume']),
            'rsi': safe_float(row.get('RSI')),
            'macd': safe_float(row.get('MACD_12_26_9')),
            'macd_signal': safe_float(row.get('MACDs_12_26_9')),
            'macd_hist': safe_float(row.get('MACDh_12_26_9')),
            'sma_20': safe_float(row.get('SMA_20')),
            'sma_50': safe_float(row.get('SMA_50')),
            'sma_100': safe_float(row.get('SMA_100')),
            'sma_200': safe_float(row.get('SMA_200')),
            'bb_upper': safe_float(row.get('BBU_20_2.0')),
            'bb_lower': safe_float(row.get('BBL_20_2.0')),
            'bb_mid': safe_float(row.get('BBM_20_2.0')),
            'ema_12': safe_float(row.get('EMA_12')),
            'ema_26': safe_float(row.get('EMA_26')),
            'atr': safe_float(row.get('ATR')),
            'vwap': safe_float(row.get('VWAP')),
            'stoch_k': safe_float(row.get('STOCH_K')),
            'stoch_d': safe_float(row.get('STOCH_D')),
        }
        chart_data.append(item)
        
    prediction = result.get('prediction')
    
    # Broadcast a push notification if the signal is very strong
    if prediction and prediction.get('confidence', 0) >= 0.80:
        try:
            PushService.send_notification_to_user(db, current_user.id, {
                "title": f"AI Alert: {prediction['direction']} {symbol}",
                "body": f"NexusPulse detected a {prediction['direction']} signal with {int(prediction['confidence']*100)}% confidence.",
                "url": f"/"
            })
        except Exception:
            logger.exception("analysis_push_notification_failed symbol=%s user_id=%s", symbol, current_user.id)

    from app.analysis import compute_volume_profile, detect_support_resistance
    volume_profile = compute_volume_profile(df, bins=24)
    support_resistance = detect_support_resistance(df)

    return {
        'symbol': symbol,
        **asset_response_fields(result['asset']),
        'info': result['info'],
        'provider': result.get('provider'),
        'chart_data': chart_data,
        'patterns': result['patterns'],
        'prediction': prediction,
        'volume_profile': volume_profile,
        'support_resistance': support_resistance,
    }


@app.get("/api/research/{symbol:path}")
def get_symbol_research(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fallback_name = get_user_watchlist_symbol_name(db, current_user, symbol)
    asset_profile = service.get_asset_profile(symbol, fallback_name=fallback_name)
    provider_snapshot = service.get_provider_snapshot(symbol, asset_profile=asset_profile)
    provider_context = build_provider_context(provider_snapshot)

    news_payload = service.get_market_news(symbol, limit=5, asset_profile=asset_profile)
    ticker_info = {} if asset_profile.get("isCrypto") else service.get_ticker_info(symbol, asset_profile=asset_profile)
    if ticker_info:
        asset_profile = service.get_asset_profile(symbol, ticker_info=ticker_info, fallback_name=fallback_name)
        provider_snapshot = service.get_provider_snapshot(symbol, asset_profile=asset_profile)
        provider_context = build_provider_context(provider_snapshot)

    provider_research = {}
    provider_quote = {}
    if isinstance(provider_snapshot, dict):
        provider_research = provider_snapshot.get("research") if isinstance(provider_snapshot.get("research"), dict) else {}
        provider_quote = provider_snapshot.get("quote") if isinstance(provider_snapshot.get("quote"), dict) else {}

    fundamentals = {
        "sector": ticker_info.get("sector"),
        "industry": ticker_info.get("industry"),
        "marketCap": ticker_info.get("marketCap"),
        "dividendYield": ticker_info.get("dividendYield"),
        "fiftyTwoWeekHigh": ticker_info.get("fiftyTwoWeekHigh"),
        "fiftyTwoWeekLow": ticker_info.get("fiftyTwoWeekLow"),
        "trailingPE": ticker_info.get("trailingPE"),
        "forwardPE": ticker_info.get("forwardPE"),
        "priceToBook": ticker_info.get("priceToBook"),
    }

    research_depth = (
        service.fmp.normalized_research_depth(asset_profile["symbol"])
        if service.fmp.configured and not asset_profile.get("isCrypto")
        else {"cashflow": [], "debt": [], "rating": None, "estimates": []}
    )

    fundamentals_detail = (
        service.fmp.normalized_fundamentals_detail(asset_profile["symbol"])
        if service.fmp.configured and not asset_profile.get("isCrypto")
        else {}
    )

    research_signals = (
        service.fmp.normalized_research_signals(asset_profile["symbol"])
        if service.fmp.configured and not asset_profile.get("isCrypto")
        else {
            "insiderTrades": [],
            "insiderSummary": {"buys90dShares": 0, "sells90dShares": 0, "netValue90d": 0},
            "institutionalHoldings": [],
            "earningsSurprises": [],
            "earningsBeatRate": None,
            "upcomingEarnings": None,
            "daysUntilEarnings": None,
        }
    )

    earnings_calls: list[dict] = (
        service.fmp.normalized_earnings_calls(asset_profile["symbol"])
        if service.fmp.configured and not asset_profile.get("isCrypto")
        else []
    )

    sec_filings = (
        service.fmp.normalized_sec_filings(asset_profile["symbol"])
        if service.fmp.configured and not asset_profile.get("isCrypto")
        else {
            "filings": [],
            "recentMaterial": [],
            "lastAnnual": None,
            "lastQuarterly": None,
            "lastMaterial": None,
            "countsByCategory": {},
        }
    )

    macro_context = get_macro_service().get_context()

    crypto_metrics = None
    if asset_profile.get("isCrypto"):
        crypto_metrics = get_coingecko_service().get_coin_metrics(asset_profile["symbol"])
    fear_greed = get_coingecko_service().get_fear_greed_index()

    social_sentiment = get_social_sentiment_service().get_social_signal(
        asset_profile["symbol"], asset_class=asset_profile.get("assetClass")
    )

    options_flow = get_options_flow_service().get_options_flow(
        asset_profile["symbol"], asset_class=asset_profile.get("assetClass")
    )

    sector_context = (
        get_sector_service().get_sector_context(
            asset_profile["symbol"],
            sector=ticker_info.get("sector") or fundamentals.get("sector"),
        )
        if not asset_profile.get("isCrypto")
        else None
    )

    return {
        "symbol": asset_profile["symbol"],
        "name": asset_profile["name"],
        **asset_response_fields(asset_profile),
        "provider": provider_snapshot,
        "providerContext": provider_context,
        "quote": provider_quote,
        "research": provider_research,
        "fundamentals": fundamentals,
        "fundamentalsDetail": fundamentals_detail,
        "researchDepth": research_depth,
        "researchSignals": research_signals,
        "earningsCalls": earnings_calls,
        "secFilings": sec_filings,
        "macroContext": macro_context,
        "cryptoMetrics": crypto_metrics,
        "fearGreedIndex": fear_greed,
        "socialSentiment": social_sentiment,
        "optionsFlow": options_flow,
        "sectorContext": sector_context,
        "news": {
            "items": (news_payload or {}).get("items", [])[:5],
            "aggregateScore": (news_payload or {}).get("aggregate_score", 0.0),
            "aggregateLabel": (news_payload or {}).get("aggregate_label", "neutral"),
            "provider": (news_payload or {}).get("provider"),
        },
    }


@app.get("/api/data-quality/{symbol:path}")
def get_symbol_data_quality(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-symbol data-source transparency report.

    Tells the user *which* provider answered for *which* field and how
    confident the system is in that answer. Drives the in-app
    `DataQualitySection` so a buy/sell recommendation is never opaque
    about its data foundation.
    """
    fallback_name = get_user_watchlist_symbol_name(db, current_user, symbol)
    asset_profile = service.get_asset_profile(symbol, fallback_name=fallback_name)
    canonical = asset_profile.get("symbol") or canonicalize_symbol(symbol)

    # Build the same payloads the analysis page consumes so the report
    # reflects what the user actually sees.
    research_payload = get_symbol_research(symbol, current_user=current_user, db=db)
    try:
        stock_payload = service.get_stock_data(
            symbol,
            period="6mo",
            interval="1d",
            user=current_user,
            include_news=False,
            include_fundamentals=False,
        )
    except Exception:
        stock_payload = None

    report = data_quality_service.evaluate_symbol_data_quality(
        symbol=canonical,
        asset_class=asset_profile.get("assetClass"),
        research_payload=research_payload,
        stock_payload=stock_payload if isinstance(stock_payload, dict) else None,
    )
    return report


@app.get("/api/admin/data-sources")
def list_data_sources(admin: User = Depends(get_current_admin_user)):
    """Admin-only provider catalogue with current configuration state.

    Used by the admin coverage matrix to surface which providers are
    active, what they cost, and where an upgrade would unlock more
    coverage. The free-tier limits and upgrade prices are static so
    operators don't have to chase them in vendor docs.
    """
    return {"providers": data_quality_service.get_provider_catalogue()}


@app.get("/api/backtest/{symbol:path}")
def get_symbol_backtest(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Walk-forward backtest of the persisted PricePredictor.

    Pulls daily history (without the heavy news/fundamentals chain),
    runs the backtest service, and returns accuracy + AUC + Brier
    plus the cumulative strategy P&L vs buy-and-hold and a 10-bucket
    reliability table for confidence calibration.
    """
    fallback_name = get_user_watchlist_symbol_name(db, current_user, symbol)
    asset_profile = service.get_asset_profile(symbol, fallback_name=fallback_name)
    canonical = asset_profile.get("symbol") or canonicalize_symbol(symbol)

    try:
        stock_data = service.get_stock_data(
            symbol,
            period="2y",
            interval="1d",
            user=None,
            include_news=False,
            include_fundamentals=False,
        )
    except Exception:
        logger.exception("backtest_history_fetch_failed symbol=%s", symbol)
        return {"symbol": canonical, "result": backtest_service._empty_payload()}

    df = stock_data.get("data") if isinstance(stock_data, dict) else None
    if df is None:
        return {"symbol": canonical, "result": backtest_service._empty_payload()}

    result = backtest_service.run_backtest(df, train_window=180, step=10)
    return {
        "symbol": canonical,
        **asset_response_fields(asset_profile),
        "result": result,
    }


@app.get("/api/events/{symbol:path}")
def get_symbol_events(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return historical earnings, dividends, and splits for a symbol.

    Sourced from FMP (Free tier covers most of this). When `FMP_API_KEY` is
    unset or the provider returns nothing, every list is empty so the
    frontend can render a neutral "no data" state.
    """
    fallback_name = get_user_watchlist_symbol_name(db, current_user, symbol)
    asset_profile = service.get_asset_profile(symbol, fallback_name=fallback_name)
    canonical = asset_profile.get("symbol") or canonicalize_symbol(symbol)

    if not service.fmp.configured or asset_profile.get("isCrypto"):
        events = {"dividends": [], "splits": [], "earnings": []}
        provider_status = "unavailable"
    else:
        events = service.fmp.normalized_events(canonical)
        any_data = any(events[k] for k in ("dividends", "splits", "earnings"))
        provider_status = "live" if any_data else "unavailable"

    return {
        "symbol": canonical,
        **asset_response_fields(asset_profile),
        "events": events,
        "provider": {
            "status": provider_status,
            "source": "FMP" if provider_status == "live" else None,
        },
    }


@app.get("/api/search/{query:path}")
def search_symbols(query: str, current_user: User = Depends(get_current_user)):
    """
    Search stocks by symbol or name via Alpaca asset cache.
    Also handles ISIN and WKN queries via OpenFIGI mapping.
    """
    try:
        query_upper = query.strip().upper()
        canonical_query = canonicalize_symbol(query_upper)
        logger.debug("symbol_search_received query=%s", query_upper)
        
        # 1. Resolve ISIN/WKN to Ticker using OpenFIGI
        if figi.is_isin(query_upper):
            ticker = figi.get_ticker_by_isin(query_upper)
            logger.debug("symbol_search_resolved_isin query=%s ticker=%s", query_upper, ticker)
            if ticker:
                query_upper = ticker
        elif figi.is_wkn(query_upper):
            ticker = figi.get_ticker_by_wkn(query_upper)
            logger.debug("symbol_search_resolved_wkn query=%s ticker=%s", query_upper, ticker)
            if ticker:
                query_upper = ticker

        canonical_query = canonicalize_symbol(query_upper)
        
        all_assets = alpaca.get_all_assets()
        logger.debug("symbol_search_assets_loaded query=%s asset_count=%s", query_upper, len(all_assets))
        
        # Simple fuzzy search
        results = []
        for a in all_assets:
            sym = a.get('symbol', '').upper()
            canonical_symbol = canonicalize_symbol(sym)
            name = a.get('name', '').upper()
            
            if query_upper in sym or canonical_query in canonical_symbol or query_upper in name:
                results.append(build_search_result(a.get('symbol'), asset=a, fallback_name=a.get('name')))
                # Cap the rough filter
                if len(results) >= 50:
                    break
                    
        # Sort exact symbol matches first
        results.sort(key=lambda x: (canonicalize_symbol(x['symbol']) != canonical_query, x['symbol']))
        top_results = results[:8]

        if not top_results:
            fallback_result = get_search_fallback_result(query_upper)
            return [fallback_result] if fallback_result else []
        
        # 2. Enrich search results with ISIN using yfinance (in parallel for speed)
        def fetch_isin(r):
            try:
                t = yf.Ticker(to_yfinance_symbol(r['symbol']))
                isin = t.isin
                if isin and isin != '-':
                    r['isin'] = isin
            except Exception:
                logger.debug("symbol_search_isin_enrichment_failed symbol=%s", r['symbol'], exc_info=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            executor.map(fetch_isin, top_results)
            
        return top_results
    except Exception:
        logger.exception("symbol_search_failed query=%s", query)
        return []

@app.get("/api/macro/calendar")
def get_macro_calendar(current_user: User = Depends(get_current_user)):
    """Macro calendar: treasury yields, commodities, and upcoming FRED releases.

    Global payload (no per-symbol filter). Auto-Execution will eventually
    use `upcomingReleases` to halt automation in the 24h before CPI/NFP/FOMC
    prints; for now the dashboard surfaces it so users can self-throttle.
    """
    return get_fred_service().normalized_macro_calendar()


@app.get("/api/discover")
def get_discovery_dashboard(current_user: User = Depends(get_current_user)):
    """Discovery dashboard: trending symbols, top movers, insider clusters.

    Surfaces tickers the user does not yet track, so a watchlist can grow
    based on what the market is doing right now rather than what the user
    already knew about.
    """
    return get_discovery_service().get_dashboard()


@app.get("/api/news/feed")
def get_news_hub_feed(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sources: str | None = None,
    sentiment: str | None = None,
    since: str | None = None,
    symbol: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Global news feed across every configured provider, with filters
    for source / sentiment / since-timestamp / symbol. Used by the
    news-hub page to surface stories well outside the user's watchlist
    so new tickers can be discovered."""
    source_list: list[str] | None = None
    if sources:
        source_list = [s.strip() for s in sources.split(",") if s.strip()]
    return get_news_hub_service().get_global_feed(
        limit=limit,
        offset=offset,
        sources=source_list,
        sentiment=sentiment,
        since=since,
        symbol=symbol.upper() if symbol else None,
    )


@app.get("/api/news/{symbol:path}")
def get_stock_news(symbol: str, current_user: User = Depends(get_current_user)):
    return service.get_market_news(symbol)


# --- PAPER-TRADING ROUTES ---
def _asset_class_resolver(symbol: str) -> str | None:
    profile = service.get_asset_profile(symbol)
    return profile.get("assetClass") if isinstance(profile, dict) else None


@app.post("/api/paper-trading/orders")
def create_paper_order(
    req: PaperOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        order = paper_trading.place_order(
            db=db,
            user=current_user,
            symbol=req.symbol,
            side=req.side,
            qty=req.qty,
            limit_price=req.limit_price,
            target_price=req.target_price,
            source=req.source,
            latest_close_provider=service.get_latest_close,
            asset_class_resolver=_asset_class_resolver,
            avg_daily_volume_provider=service.get_avg_daily_volume,
        )
    except paper_trading.NetYieldGateRejection as exc:
        audit_service.log_event(
            db,
            user_id=current_user.id,
            action=audit_service.ACTION_PAPER_ORDER_PLACE_REJECTED,
            outcome="denied",
            details={
                "symbol": req.symbol,
                "side": req.side,
                "reason": exc.reason,
                "breakdown": exc.breakdown,
            },
        )
        raise HTTPException(
            status_code=400,
            detail={"reason": exc.reason, "breakdown": exc.breakdown},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.log_event(
        db,
        user_id=current_user.id,
        action=audit_service.ACTION_PAPER_ORDER_PLACE,
        resource_type="paper_order",
        resource_id=order.id,
        details={
            "symbol": order.symbol,
            "side": order.side,
            "qty": order.qty,
            "status": order.status,
            "source": order.source,
        },
    )
    return paper_trading.serialize_order(order)


@app.get("/api/paper-trading/orders")
def list_paper_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"orders": paper_trading.list_orders(db, current_user)}


@app.delete("/api/paper-trading/orders/{order_id}")
def cancel_paper_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        order = paper_trading.cancel_order(db=db, user=current_user, order_id=order_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Order not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.log_event(
        db,
        user_id=current_user.id,
        action=audit_service.ACTION_PAPER_ORDER_CANCEL,
        resource_type="paper_order",
        resource_id=order.id,
        details={"symbol": order.symbol, "side": order.side},
    )
    return paper_trading.serialize_order(order)


@app.get("/api/paper-trading/transactions")
def list_paper_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"transactions": paper_trading.list_transactions(db, current_user)}


@app.get("/api/paper-trading/positions")
def list_paper_positions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "positions": paper_trading.compute_positions(
            db, current_user, service.get_latest_close
        )
    }


@app.get("/api/paper-trading/summary")
def get_paper_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return paper_trading.compute_summary(db, current_user, service.get_latest_close)


# --- ALPACA ROUTES ---
def get_user_alpaca_service(user: User):
    """Helper to instantiate AlpacaService for the specific user."""
    if not user.alpaca_api_key or not user.alpaca_secret_key:
        raise HTTPException(
            status_code=400, 
            detail="Alpaca API keys are not configured for this user. Please configure them in Settings."
        )
    # Check if a mask placeholder was somehow sent to the backend
    secret_key = decrypt_secret(user.alpaca_secret_key)
    if not secret_key or secret_key.startswith("*"):
        raise HTTPException(status_code=400, detail="Invalid Alpaca secret key.")
        
    service = AlpacaService(
        api_key=user.alpaca_api_key,
        secret_key=secret_key,
        paper=user.alpaca_paper
    )
    
    if not service.api:
        raise HTTPException(
            status_code=401, 
            detail="Failed to connect to Alpaca with the provided keys."
        )
    return service

@app.get("/api/auto-execution/limits")
def get_auto_execution_limits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-user automation limits + master switch state.

    Defaults to a conservative all-off row when the user has no record yet.
    """
    row = auto_execution.get_limits(db, current_user)
    return auto_execution.serialize_limits(row)


@app.put("/api/auto-execution/limits")
def update_auto_execution_limits(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upsert risk limits for the user.

    Out-of-range values are clamped silently. The master switch only
    flips to True when the payload explicitly sets `enabled=true`. Every
    update is audited via `audit_service` so a flipped switch leaves a
    persistent trail.
    """
    previous_mode = (auto_execution.get_limits(db, current_user).mode or "paper").lower()
    row = auto_execution.update_limits(db, current_user, payload or {})
    new_mode = (row.mode or "paper").lower()
    audit_service.log_event(
        db,
        action="auto_execution.limits_updated",
        user_id=current_user.id,
        outcome="success",
        details={"enabled": bool(row.enabled), "mode": new_mode},
    )
    # Flipping into live-mode is a load-bearing event — log it separately
    # so a security review of the audit trail can spot every transition
    # from paper to live without scanning every limits update.
    if previous_mode != "live" and new_mode == "live":
        audit_service.log_event(
            db,
            action="auto_execution.live_mode_enabled",
            user_id=current_user.id,
            outcome="success",
            details={"previousMode": previous_mode},
        )
    return auto_execution.serialize_limits(row)


@app.get("/api/auto-execution/events")
def list_auto_execution_events(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent automation events for the user, newest-first."""
    return {
        "items": auto_execution.list_events(db, current_user, limit=limit, offset=offset),
    }


@app.post("/api/auto-execution/proposals/evaluate")
def evaluate_auto_execution_proposal(
    proposal: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dry-run a proposal against every gate without placing an order.

    Used by the UI's "preview" mode and by future auto-trade loops. The
    decision is audited even though no broker call follows.
    """
    if not isinstance(proposal, dict):
        raise HTTPException(status_code=400, detail="proposal must be an object")

    symbol = str(proposal.get("symbol") or "")
    asset_class = str(proposal.get("assetClass") or "")
    fred_calendar = None
    sec_filings = None
    sector_context = None
    net_yield_breakdown = None
    if symbol:
        try:
            fred_calendar = get_fred_service().normalized_macro_calendar()
        except Exception:
            logger.exception("auto_execution_proposal_fred_lookup_failed")
        try:
            if asset_class.lower() != "crypto" and service.fmp.configured:
                sec_filings = service.fmp.normalized_sec_filings(symbol.upper())
        except Exception:
            logger.exception("auto_execution_proposal_sec_lookup_failed symbol=%s", symbol)
        try:
            if asset_class.lower() != "crypto":
                sector_context = get_sector_service().get_sector_context(
                    symbol.upper(), sector=proposal.get("sector")
                )
        except Exception:
            logger.exception("auto_execution_proposal_sector_lookup_failed symbol=%s", symbol)

    target_price = proposal.get("targetPrice")
    limit_price = proposal.get("limitPrice")
    side = proposal.get("side") or "buy"
    if target_price and limit_price:
        try:
            net_yield_breakdown = paper_trading.evaluate_net_yield_gate(
                user=current_user,
                side=str(side),
                entry_price=float(limit_price),
                target_price=float(target_price),
                asset_class=asset_class or None,
            )
        except Exception:
            logger.exception("auto_execution_proposal_net_yield_failed symbol=%s", symbol)

    decision = auto_execution.evaluate_proposal(
        db,
        current_user,
        proposal,
        sec_filings=sec_filings,
        fred_calendar=fred_calendar,
        sector_context=sector_context,
        net_yield_breakdown=net_yield_breakdown,
    )
    return {
        "allowed": decision.allowed,
        "reasons": decision.reasons,
        "haltTriggers": decision.halt_triggers,
        "breakdown": decision.breakdown,
    }


@app.post("/api/auto-execution/halt")
def halt_auto_execution(
    payload: dict | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Emergency halt: flip the master switch off + audit it.

    Phase 4c will additionally cancel open Alpaca limit orders here. For
    now we record the halt and rely on the user-side stop-trade flow.
    """
    reason = (payload or {}).get("reason") or "manual_user_halt"
    open_at_halt = auto_execution.halt_all_for_user(db, current_user, reason=str(reason))
    audit_service.log_event(
        db,
        action="auto_execution.halted",
        user_id=current_user.id,
        outcome="success",
        details={"reason": str(reason), "openOrdersAtHalt": open_at_halt},
    )
    return {"halted": True, "openOrdersAtHalt": open_at_halt}


@app.get("/api/alpaca/account")
def get_alpaca_account(current_user: User = Depends(get_current_user)):
    user_alpaca = get_user_alpaca_service(current_user)
    return user_alpaca.get_account()

@app.get("/api/alpaca/positions")
def get_alpaca_positions(current_user: User = Depends(get_current_user)):
    user_alpaca = get_user_alpaca_service(current_user)
    try:
        positions = user_alpaca.api.list_positions()
        return [{
            'symbol': p.symbol,
            'qty': float(p.qty),
            'market_value': float(p.market_value),
            'unrealized_pl': float(p.unrealized_pl),
            'unrealized_plpc': float(p.unrealized_plpc) * 100,
            'avg_entry': float(p.avg_entry_price),
            'current_price': float(p.current_price),
        } for p in positions]
    except Exception:
        logger.exception("alpaca_positions_fetch_failed user_id=%s", current_user.id)
        return []

@app.get("/api/alpaca/orders")
def get_alpaca_orders(current_user: User = Depends(get_current_user)):
    user_alpaca = get_user_alpaca_service(current_user)
    try:
        return [o._raw for o in user_alpaca.api.list_orders(limit=10)]
    except Exception:
        logger.exception("alpaca_orders_fetch_failed user_id=%s", current_user.id)
        return []

@app.get("/api/alpaca/portfolio/history")
def get_portfolio_history(period: str = "1M", timeframe: str = "1D", current_user: User = Depends(get_current_user)):
    user_alpaca = get_user_alpaca_service(current_user)
    hist = user_alpaca.get_portfolio_history(period, timeframe)
    if not hist:
        return {}
    return hist

@app.get("/api/alpaca/activities")
def get_alpaca_activities(limit: int = 100, current_user: User = Depends(get_current_user)):
    user_alpaca = get_user_alpaca_service(current_user)
    return user_alpaca.get_activities(limit)

@app.get("/api/alpaca/bars/{symbol:path}")
def get_alpaca_bars(symbol: str, timeframe: str = "1Day", current_user: User = Depends(get_current_user)):
    # Bars are market data, we can optionally use user credentials if available, 
    # but fallback to system API for users who haven't set keys yet to ensure charts render.
    secret_key = decrypt_secret(current_user.alpaca_secret_key)
    if current_user.alpaca_api_key and secret_key and not secret_key.startswith("*"):
        user_alpaca = AlpacaService(
            api_key=current_user.alpaca_api_key,
            secret_key=secret_key,
            paper=current_user.alpaca_paper
        )
        if user_alpaca.api:
            return user_alpaca.get_bars(symbol, timeframe)
            
    # Fallback to system API
    if not alpaca.api: return []
    return alpaca.get_bars(symbol, timeframe)

@app.post("/api/alpaca/orders")
def place_order(order: OrderRequest, current_user: User = Depends(get_current_user)):
    user_alpaca = get_user_alpaca_service(current_user)
    return user_alpaca.submit_order(order.symbol, order.qty, order.side, order.type)


# --- Admin upload validation -------------------------------------------------

ADMIN_UPLOAD_MAX_BYTES = int(os.getenv("ADMIN_UPLOAD_MAX_BYTES", str(50 * 1024 * 1024)))
ADMIN_UPLOAD_ALLOWED_MIME = {"application/json", "application/octet-stream"}


async def _read_admin_upload_json(file: UploadFile) -> dict:
    """Validate + parse an admin-only JSON upload.

    The browser File-API sometimes ships JSON as `application/octet-stream`
    when the user picked a file without a recognised extension, so the
    allowlist accepts both. Anything else is rejected before the bytes
    are even read.

    The size cap is enforced while the bytes stream in: we read the body
    incrementally and abort once we cross `ADMIN_UPLOAD_MAX_BYTES`. That
    way an attacker can't pin the worker to swap by sending a multi-GB
    "JSON" payload.
    """
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in ADMIN_UPLOAD_ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type: {content_type}",
        )

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > ADMIN_UPLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds maximum allowed size of {ADMIN_UPLOAD_MAX_BYTES} bytes",
            )
        chunks.append(chunk)
    raw = b"".join(chunks)

    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON upload") from exc


@app.get("/api/admin/export")
def export_platform_state(admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    snapshot = BackupService.export_snapshot(db)
    audit_service.log_event(
        db,
        user_id=admin.id,
        action=audit_service.ACTION_BACKUP_EXPORT,
    )
    return snapshot


@app.post("/api/admin/import")
async def import_platform_state(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    payload = await _read_admin_upload_json(file)
    BackupService.import_snapshot(db, payload, replace_existing=True)
    audit_service.log_event(
        db,
        user_id=admin.id,
        action=audit_service.ACTION_BACKUP_IMPORT,
        details={"filename": file.filename},
    )
    return {"status": "imported", "filename": file.filename}


@app.get("/api/admin/audit-events")
def list_audit_events(
    user_id: int | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Admin-only audit-event browser, filterable by user and action."""
    from app.models import AuditEvent

    query = db.query(AuditEvent)
    if user_id is not None:
        query = query.filter(AuditEvent.user_id == user_id)
    if action:
        query = query.filter(AuditEvent.action == action)
    total = query.count()
    rows = (
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [audit_service.serialize_event(row) for row in rows],
    }


@app.get("/api/admin/backups")
def list_backups(admin: User = Depends(get_current_admin_user)):
    return {"items": BackupService.list_backups()}


@app.post("/api/admin/backups")
def create_backup(label: Optional[str] = None, admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    path = BackupService.create_backup(db, label=label)
    audit_service.log_event(
        db,
        user_id=admin.id,
        action=audit_service.ACTION_BACKUP_CREATE,
        resource_type="backup",
        resource_id=path.name,
        details={"label": label},
    )
    return {"status": "created", "filename": path.name}


@app.get("/api/admin/backups/{filename}")
def download_backup(filename: str, admin: User = Depends(get_current_admin_user)):
    try:
        path = BackupService.backup_path(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid backup filename") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Backup not found") from exc

    return FileResponse(path, media_type="application/json", filename=path.name)


@app.post("/api/admin/backups/import")
async def import_backup(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    payload = await _read_admin_upload_json(file)
    BackupService.import_snapshot(db, payload, replace_existing=True)
    audit_service.log_event(
        db,
        user_id=admin.id,
        action=audit_service.ACTION_BACKUP_RESTORE,
        details={"filename": file.filename},
    )
    return {"status": "restored", "filename": file.filename}
