import asyncio
import json
import logging
import os
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
from pydantic import BaseModel, Field
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
from app.database import init_db, get_db, SessionLocal
from app.figi_service import figi
from app.migrate_watchlists import migrate as migrate_watchlists
from app.models import User, Watchlist as WatchlistRecord, WatchlistItem as WatchlistItemRecord, WatchlistItemTag
from app.push_service import PushService
from app.services import MarketDataService
from app.watchlist_alerts import build_provider_context, build_watchlist_alert, summarize_watchlist_alerts
from app.websocket_manager import manager

logger = logging.getLogger(__name__)

app = FastAPI(title="AI Trading Bot API")


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

class CreateWatchlistRequest(BaseModel):
    name: str

class RenameWatchlistRequest(BaseModel):
    name: str

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

# Initialize database on startup
@app.on_event("startup")
async def on_startup():
    init_db()
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
    tracked_assets = [serialize_tracked_watchlist_item(item) for item in sorted(record.items, key=lambda current: current.id or 0)]

    alert_items: list[dict] = []
    for tracked in tracked_assets:
        symbol = tracked["symbol"]
        try:
            analysis_result = service.get_stock_data(
                symbol,
                period="1mo",
                interval="1h",
                user=current_user,
                include_news=False,
                include_fundamentals=False,
            )
        except Exception:
            logger.exception(
                "watchlist_alert_analysis_failed symbol=%s user_id=%s",
                symbol,
                current_user.id,
            )
            analysis_result = {}

        try:
            news_payload = service.get_market_news(symbol, asset_profile=tracked)
        except Exception:
            logger.exception(
                "watchlist_alert_news_failed symbol=%s user_id=%s",
                symbol,
                current_user.id,
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

    summary = summarize_watchlist_alerts(alert_items)
    summary["trackedSymbols"] = len(tracked_assets)

    return {
        "watchlist": {"id": record.id, "name": record.name},
        "trackedAssets": tracked_assets,
        "items": alert_items,
        "summary": summary,
    }

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

    return {
        'symbol': symbol,
        **asset_response_fields(result['asset']),
        'info': result['info'],
        'provider': result.get('provider'),
        'chart_data': chart_data,
        'patterns': result['patterns'],
        'prediction': prediction
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

    return {
        "symbol": asset_profile["symbol"],
        "name": asset_profile["name"],
        **asset_response_fields(asset_profile),
        "provider": provider_snapshot,
        "providerContext": provider_context,
        "quote": provider_quote,
        "research": provider_research,
        "fundamentals": fundamentals,
        "news": {
            "items": (news_payload or {}).get("items", [])[:5],
            "aggregateScore": (news_payload or {}).get("aggregate_score", 0.0),
            "aggregateLabel": (news_payload or {}).get("aggregate_label", "neutral"),
            "provider": (news_payload or {}).get("provider"),
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

@app.get("/api/news/{symbol:path}")
def get_stock_news(symbol: str, current_user: User = Depends(get_current_user)):
    return service.get_market_news(symbol)

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


@app.get("/api/admin/export")
def export_platform_state(admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    return BackupService.export_snapshot(db)


@app.post("/api/admin/import")
async def import_platform_state(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        payload = json.loads((await file.read()).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid import file") from exc

    BackupService.import_snapshot(db, payload, replace_existing=True)
    return {"status": "imported", "filename": file.filename}


@app.get("/api/admin/backups")
def list_backups(admin: User = Depends(get_current_admin_user)):
    return {"items": BackupService.list_backups()}


@app.post("/api/admin/backups")
def create_backup(label: Optional[str] = None, admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    path = BackupService.create_backup(db, label=label)
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
    try:
        payload = json.loads((await file.read()).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid backup file") from exc

    BackupService.import_snapshot(db, payload, replace_existing=True)
    return {"status": "restored", "filename": file.filename}
