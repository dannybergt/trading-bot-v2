"""Paper-Trading-Order-Lifecycle.

Thin wrapper over PaperOrder/PaperTransaction. Simulated fills run against
the most recent close for the symbol; the Net-Yield-Gate mirrors the
fee + tax math from `PricePredictor._enrich_with_yield_model` so the
order acceptance decision uses the same numbers the recommendation card
already shows the user.

For paper trading we accept fractional quantities (crypto). Slippage is
a fixed adverse 0.1% on market fills against the latest close; limit
orders only fill when the latest close already crosses the limit and
otherwise stay pending.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.models import PaperOrder, PaperTransaction, User

logger = logging.getLogger(__name__)

ORDER_SIDES = {"buy", "sell"}
ORDER_STATUSES = {"pending", "filled", "cancelled"}
ORDER_SOURCES = {"manual", "auto-recommendation"}

# Adverse market-fill slippage in percent. Keyed by asset class so the
# simulator widens the bid/ask gap for crypto (less liquid, larger
# spreads) without touching equities and ETFs. Anything outside this
# map falls back to the default 0.1%.
DEFAULT_SLIPPAGE_PCT = 0.1
SLIPPAGE_PCT_BY_ASSET_CLASS: dict[str, float] = {
    "stock": 0.1,
    "etf": 0.05,
    "crypto": 0.3,
}


def _resolve_slippage_pct(asset_class: str | None) -> float:
    if asset_class is None:
        return DEFAULT_SLIPPAGE_PCT
    return SLIPPAGE_PCT_BY_ASSET_CLASS.get(asset_class, DEFAULT_SLIPPAGE_PCT)


class NetYieldGateRejection(Exception):
    """Raised when the gate refuses to accept the order."""

    def __init__(self, reason: str, breakdown: dict[str, Any] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.breakdown = breakdown or {}


def evaluate_net_yield_gate(
    *,
    user: User,
    side: str,
    entry_price: float,
    target_price: float,
) -> dict[str, Any]:
    """Net target percent for a target-priced trade, fees + tax included.

    Mirrors `PricePredictor._enrich_with_yield_model` so paper-trading
    accept/reject uses the same math the explainer presents.
    """
    if entry_price <= 0 or target_price <= 0:
        return {"meetsMinimum": True, "reason": "no_price"}

    direction = "DOWN" if side == "sell" else "UP"
    gross_pct = (target_price - entry_price) / entry_price * 100.0
    if direction == "DOWN":
        gross_pct = -gross_pct

    fee_pct_per_leg = float(getattr(user, "trade_fee_percent", 0) or 0)
    fee_absolute = float(getattr(user, "trade_fee_absolute", 0) or 0)
    fee_absolute_pct_per_leg = (fee_absolute / entry_price) * 100.0 if entry_price > 0 else 0.0
    cap_gains_rate_pct = float(getattr(user, "capital_gains_tax_bps", 0) or 0) / 100.0
    income_tax_rate_pct = float(getattr(user, "income_tax_bps", 0) or 0) / 100.0
    min_target_yield_pct = float(getattr(user, "min_target_yield", 0) or 0) or None

    round_trip_fee_pct = 2.0 * (fee_pct_per_leg + fee_absolute_pct_per_leg)
    gross_after_fees_pct = gross_pct - round_trip_fee_pct
    effective_tax_rate_pct = cap_gains_rate_pct or income_tax_rate_pct
    tax_drag_pct = 0.0
    if gross_after_fees_pct > 0 and effective_tax_rate_pct > 0:
        tax_drag_pct = gross_after_fees_pct * (effective_tax_rate_pct / 100.0)
    net_pct = gross_after_fees_pct - tax_drag_pct

    breakdown = {
        "grossTargetPct": round(gross_pct, 4),
        "feeRoundTripPct": round(round_trip_fee_pct, 4),
        "taxDragPct": round(tax_drag_pct, 4),
        "netTargetPct": round(net_pct, 4),
        "effectiveTaxRatePct": round(effective_tax_rate_pct, 4),
        "minTargetYieldPct": min_target_yield_pct,
    }
    breakdown["meetsMinimum"] = (
        True if min_target_yield_pct is None else net_pct >= min_target_yield_pct
    )
    return breakdown


def fee_breakdown(user: User, qty: float, price: float) -> tuple[float, float]:
    """(fee_absolute, fee_percent_amount) for one fill leg."""
    fee_absolute = float(getattr(user, "trade_fee_absolute", 0) or 0)
    fee_pct = float(getattr(user, "trade_fee_percent", 0) or 0)
    fee_percent_amount = (qty * price) * (fee_pct / 100.0)
    return fee_absolute, fee_percent_amount


def tax_amount_for_realized(user: User, realized_gross: float) -> float:
    if realized_gross <= 0:
        return 0.0
    cap_bps = float(getattr(user, "capital_gains_tax_bps", 0) or 0)
    if cap_bps <= 0:
        cap_bps = float(getattr(user, "income_tax_bps", 0) or 0)
    if cap_bps <= 0:
        return 0.0
    return realized_gross * (cap_bps / 10000.0)


def _running_avg_entry(
    db: Session, user_id: int, symbol: str
) -> tuple[float, float]:
    """Walk transactions chronologically and return (open_qty, avg_entry).

    Weighted-average cost basis: every buy adds qty*price (excluding
    fees) to cost, every sell removes proportional cost.
    """
    txs = (
        db.query(PaperTransaction)
        .filter(PaperTransaction.user_id == user_id, PaperTransaction.symbol == symbol)
        .order_by(PaperTransaction.executed_at.asc(), PaperTransaction.id.asc())
        .all()
    )
    qty = 0.0
    cost = 0.0
    for tx in txs:
        if tx.side == "buy":
            cost += float(tx.qty) * float(tx.price)
            qty += float(tx.qty)
        else:
            if qty <= 0:
                continue
            avg = cost / qty
            sell_qty = min(float(tx.qty), qty)
            cost -= avg * sell_qty
            qty -= sell_qty
    avg_price = (cost / qty) if qty > 0 else 0.0
    return qty, avg_price


def _try_fill(
    *,
    db: Session,
    user: User,
    order: PaperOrder,
    latest_close: float | None,
    asset_class: str | None = None,
) -> bool:
    if latest_close is None or latest_close <= 0:
        return False

    if order.limit_price is not None:
        if order.side == "buy" and latest_close > float(order.limit_price):
            return False
        if order.side == "sell" and latest_close < float(order.limit_price):
            return False
        fill_price = float(order.limit_price)
    else:
        slip = _resolve_slippage_pct(asset_class) / 100.0
        fill_price = latest_close * (1 + slip if order.side == "buy" else 1 - slip)

    fee_abs, fee_pct_amt = fee_breakdown(user, float(order.qty), fill_price)

    realized_pnl = 0.0
    tax = 0.0
    if order.side == "sell":
        open_qty, avg_entry = _running_avg_entry(db, user.id, order.symbol)
        sell_qty = min(float(order.qty), open_qty)
        if sell_qty > 0 and avg_entry > 0:
            gross = (fill_price - avg_entry) * sell_qty
            tax = tax_amount_for_realized(user, gross)
            realized_pnl = gross - fee_abs - fee_pct_amt - tax

    now = datetime.now(timezone.utc)
    db.add(
        PaperTransaction(
            user_id=user.id,
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            qty=float(order.qty),
            price=fill_price,
            fee_absolute=fee_abs,
            fee_percent_amount=fee_pct_amt,
            tax_amount=tax,
            realized_pnl=realized_pnl,
            executed_at=now,
        )
    )
    order.status = "filled"
    order.filled_at = now
    return True


PriceProvider = Callable[[str], Optional[float]]
AssetClassResolver = Callable[[str], Optional[str]]


def place_order(
    *,
    db: Session,
    user: User,
    symbol: str,
    side: str,
    qty: float,
    limit_price: float | None,
    target_price: float | None,
    source: str,
    latest_close_provider: PriceProvider,
    asset_class_resolver: AssetClassResolver | None = None,
) -> PaperOrder:
    """Place a paper-trading order.

    The Net-Yield-Gate kicks in when `target_price` is supplied: rejects
    if the projected net (after broker fees + capital-gains tax) does not
    meet the user's `min_target_yield`.
    """
    if side not in ORDER_SIDES:
        raise ValueError(f"unsupported side: {side}")
    if source not in ORDER_SOURCES:
        raise ValueError(f"unsupported source: {source}")
    if qty <= 0:
        raise ValueError("qty must be positive")

    canonical_symbol = symbol.upper().strip()
    if not canonical_symbol:
        raise ValueError("symbol required")

    latest_close = latest_close_provider(canonical_symbol)

    if target_price is not None and side == "buy":
        entry = float(limit_price) if limit_price is not None else float(latest_close or 0.0)
        breakdown = evaluate_net_yield_gate(
            user=user, side=side, entry_price=entry, target_price=float(target_price)
        )
        if not breakdown.get("meetsMinimum", True):
            raise NetYieldGateRejection(
                reason="net_target_below_minimum",
                breakdown=breakdown,
            )

    order = PaperOrder(
        user_id=user.id,
        symbol=canonical_symbol,
        side=side,
        qty=float(qty),
        limit_price=float(limit_price) if limit_price is not None else None,
        status="pending",
        source=source,
    )
    db.add(order)
    db.flush()

    asset_class: str | None = None
    if asset_class_resolver is not None:
        try:
            asset_class = asset_class_resolver(canonical_symbol)
        except Exception:
            logger.exception(
                "paper_order_asset_class_lookup_failed symbol=%s", canonical_symbol
            )

    _try_fill(
        db=db,
        user=user,
        order=order,
        latest_close=latest_close,
        asset_class=asset_class,
    )
    db.commit()
    db.refresh(order)
    return order


def dispatch_pending_orders(
    db: Session,
    latest_close_provider: PriceProvider,
    asset_class_resolver: AssetClassResolver | None = None,
) -> int:
    """Re-evaluate every pending limit order against the current close.

    Returns the number of orders that filled in this cycle. The price and
    asset-class lookups are cached per distinct symbol to avoid hammering
    upstream providers when many users hold the same ticker.
    """
    pending = (
        db.query(PaperOrder)
        .filter(PaperOrder.status == "pending")
        .order_by(PaperOrder.placed_at.asc(), PaperOrder.id.asc())
        .all()
    )
    if not pending:
        return 0

    price_cache: dict[str, float | None] = {}
    asset_class_cache: dict[str, str | None] = {}

    def _provider(symbol: str) -> float | None:
        if symbol not in price_cache:
            try:
                price_cache[symbol] = latest_close_provider(symbol)
            except Exception:
                logger.exception(
                    "paper_order_dispatch_price_lookup_failed symbol=%s", symbol
                )
                price_cache[symbol] = None
        return price_cache[symbol]

    def _asset_class(symbol: str) -> str | None:
        if asset_class_resolver is None:
            return None
        if symbol not in asset_class_cache:
            try:
                asset_class_cache[symbol] = asset_class_resolver(symbol)
            except Exception:
                logger.exception(
                    "paper_order_dispatch_asset_class_lookup_failed symbol=%s", symbol
                )
                asset_class_cache[symbol] = None
        return asset_class_cache[symbol]

    filled = 0
    for order in pending:
        user = db.query(User).filter(User.id == order.user_id).one_or_none()
        if user is None:
            logger.warning(
                "paper_order_dispatch_user_missing order_id=%s user_id=%s",
                order.id,
                order.user_id,
            )
            continue
        try:
            if _try_fill(
                db=db,
                user=user,
                order=order,
                latest_close=_provider(order.symbol),
                asset_class=_asset_class(order.symbol),
            ):
                filled += 1
        except Exception:
            logger.exception(
                "paper_order_dispatch_fill_failed order_id=%s symbol=%s",
                order.id,
                order.symbol,
            )

    if filled:
        db.commit()
    return filled


def cancel_order(*, db: Session, user: User, order_id: int) -> PaperOrder:
    order = (
        db.query(PaperOrder)
        .filter(PaperOrder.user_id == user.id, PaperOrder.id == order_id)
        .one_or_none()
    )
    if order is None:
        raise LookupError("order not found")
    if order.status != "pending":
        raise ValueError("only pending orders can be cancelled")
    order.status = "cancelled"
    db.commit()
    db.refresh(order)
    return order


def serialize_order(order: PaperOrder) -> dict:
    return {
        "id": order.id,
        "symbol": order.symbol,
        "side": order.side,
        "qty": float(order.qty),
        "limitPrice": float(order.limit_price) if order.limit_price is not None else None,
        "status": order.status,
        "source": order.source,
        "rejectionReason": order.rejection_reason,
        "placedAt": order.placed_at.isoformat() if order.placed_at else None,
        "filledAt": order.filled_at.isoformat() if order.filled_at else None,
    }


def serialize_transaction(tx: PaperTransaction, *, cost_basis: float | None = None) -> dict:
    fee_total = float(tx.fee_absolute) + float(tx.fee_percent_amount)
    pnl_pct: float | None = None
    if tx.side == "sell" and cost_basis and cost_basis > 0:
        pnl_pct = (float(tx.realized_pnl) / cost_basis) * 100.0
    return {
        "id": tx.id,
        "orderId": tx.order_id,
        "symbol": tx.symbol,
        "side": tx.side,
        "qty": float(tx.qty),
        "price": float(tx.price),
        "feeAbsolute": float(tx.fee_absolute),
        "feePercentAmount": float(tx.fee_percent_amount),
        "feeTotal": round(fee_total, 6),
        "taxAmount": float(tx.tax_amount),
        "realizedPnl": float(tx.realized_pnl),
        "realizedPnlPct": round(pnl_pct, 4) if pnl_pct is not None else None,
        "executedAt": tx.executed_at.isoformat() if tx.executed_at else None,
    }


def list_orders(db: Session, user: User) -> list[dict]:
    rows = (
        db.query(PaperOrder)
        .filter(PaperOrder.user_id == user.id)
        .order_by(PaperOrder.placed_at.desc(), PaperOrder.id.desc())
        .all()
    )
    return [serialize_order(o) for o in rows]


def list_transactions(db: Session, user: User) -> list[dict]:
    """Chronological journal with weighted-avg cost basis annotation.

    Walks transactions in execution order and tracks avg cost per symbol
    on the fly so each sell can carry both nominal PnL and percent PnL
    relative to the cost basis it consumed.
    """
    rows = (
        db.query(PaperTransaction)
        .filter(PaperTransaction.user_id == user.id)
        .order_by(PaperTransaction.executed_at.asc(), PaperTransaction.id.asc())
        .all()
    )
    state: dict[str, dict[str, float]] = {}
    out: list[dict] = []
    for tx in rows:
        bucket = state.setdefault(tx.symbol, {"qty": 0.0, "cost": 0.0})
        cost_basis: float | None = None
        if tx.side == "buy":
            bucket["cost"] += float(tx.qty) * float(tx.price)
            bucket["qty"] += float(tx.qty)
        else:
            if bucket["qty"] > 0:
                avg = bucket["cost"] / bucket["qty"]
                sell_qty = min(float(tx.qty), bucket["qty"])
                cost_basis = avg * sell_qty
                bucket["cost"] -= cost_basis
                bucket["qty"] -= sell_qty
        out.append(serialize_transaction(tx, cost_basis=cost_basis))
    return out


def compute_positions(
    db: Session, user: User, latest_close_provider: PriceProvider
) -> list[dict]:
    txs = (
        db.query(PaperTransaction)
        .filter(PaperTransaction.user_id == user.id)
        .order_by(PaperTransaction.executed_at.asc(), PaperTransaction.id.asc())
        .all()
    )
    by_symbol: dict[str, dict] = {}
    for tx in txs:
        bucket = by_symbol.setdefault(
            tx.symbol,
            {
                "symbol": tx.symbol,
                "qty": 0.0,
                "cost": 0.0,
                "feeTotal": 0.0,
                "taxTotal": 0.0,
                "realizedPnl": 0.0,
            },
        )
        bucket["feeTotal"] += float(tx.fee_absolute) + float(tx.fee_percent_amount)
        bucket["taxTotal"] += float(tx.tax_amount)
        bucket["realizedPnl"] += float(tx.realized_pnl)
        if tx.side == "buy":
            bucket["cost"] += float(tx.qty) * float(tx.price)
            bucket["qty"] += float(tx.qty)
        else:
            if bucket["qty"] > 0:
                avg = bucket["cost"] / bucket["qty"]
                sell_qty = min(float(tx.qty), bucket["qty"])
                bucket["cost"] -= avg * sell_qty
                bucket["qty"] -= sell_qty

    positions: list[dict] = []
    for symbol, bucket in by_symbol.items():
        if bucket["qty"] <= 1e-9:
            continue
        avg_entry = bucket["cost"] / bucket["qty"]
        last_price = latest_close_provider(symbol)
        unrealized: float | None = None
        unrealized_pct: float | None = None
        if last_price is not None and last_price > 0:
            unrealized = (float(last_price) - avg_entry) * bucket["qty"]
            unrealized_pct = (float(last_price) - avg_entry) / avg_entry * 100.0 if avg_entry > 0 else None
        positions.append(
            {
                "symbol": symbol,
                "qty": round(bucket["qty"], 8),
                "avgEntryPrice": round(avg_entry, 6),
                "lastPrice": float(last_price) if last_price is not None else None,
                "unrealizedPnl": round(unrealized, 4) if unrealized is not None else None,
                "unrealizedPnlPct": round(unrealized_pct, 4) if unrealized_pct is not None else None,
                "realizedPnl": round(bucket["realizedPnl"], 4),
                "feeTotal": round(bucket["feeTotal"], 4),
                "taxTotal": round(bucket["taxTotal"], 4),
            }
        )
    positions.sort(key=lambda p: p["symbol"])
    return positions


def compute_summary(
    db: Session, user: User, latest_close_provider: PriceProvider
) -> dict:
    txs = (
        db.query(PaperTransaction)
        .filter(PaperTransaction.user_id == user.id)
        .all()
    )
    realized = sum(float(tx.realized_pnl) for tx in txs)
    fees = sum(float(tx.fee_absolute) + float(tx.fee_percent_amount) for tx in txs)
    tax = sum(float(tx.tax_amount) for tx in txs)
    positions = compute_positions(db, user, latest_close_provider)
    open_exposure = sum(
        ((p["lastPrice"] if p["lastPrice"] is not None else p["avgEntryPrice"]) * p["qty"])
        for p in positions
    )
    unrealized = sum(p["unrealizedPnl"] or 0.0 for p in positions)
    return {
        "realizedPnl": round(realized, 4),
        "unrealizedPnl": round(unrealized, 4),
        "feeTotal": round(fees, 4),
        "taxTotal": round(tax, 4),
        "openExposure": round(open_exposure, 4),
        "openPositions": len(positions),
        "transactionCount": len(txs),
    }
