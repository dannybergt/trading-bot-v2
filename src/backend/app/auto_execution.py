"""Phase 4 Auto-Execution risk model and proposal evaluation.

This module is the gate every automated trade decision must pass. It does
NOT place orders itself — that is intentionally separated. The eventual
auto-trade loop will call `evaluate_proposal` and only act when the result
is `allowed=True`. Even then, defaults stay conservative: the master
switch (`AutoExecutionLimits.enabled`) is `False` until the user enables
it explicitly, and every per-symbol proposal additionally has to pass
five risk gates and four halt-trigger checks.

Risk gates (per-proposal):
1. Master switch (`limits.enabled`) is True.
2. Asset class is in `limits.allowed_asset_classes`.
3. Position size (`qty * limit_price`) is within `limits.max_position_size_usd`.
4. Today's realized losses leave headroom under `limits.max_daily_loss_usd`.
5. Open-position count + 1 is within `limits.max_open_positions`.

Halt-trigger checks (data from Welle 14):
- FOMC decision in less than 24h (FRED upcoming release `category="policy"`).
- 8-K material event filed within the last 7 days (FMP `lastMaterial`).
- Yield curve inverted (FRED `T10Y2Y < 0`).
- Symbol-vs-SPY beta exceeds `limits.max_portfolio_beta`.

Plus the existing Net-Yield-Gate (broker fees + capital-gains tax >= the
user's `min_target_yield`) — same math `paper_trading.evaluate_net_yield_gate`
uses, kept consistent on purpose.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import (
    AutoExecutionEvent,
    AutoExecutionLimits,
    PaperOrder,
    PaperTransaction,
    User,
)

logger = logging.getLogger(__name__)

DEFAULT_LIMITS: dict[str, Any] = {
    "enabled": False,
    "mode": "paper",
    "max_position_size_usd": 500.0,
    "max_daily_loss_usd": 200.0,
    "max_open_positions": 5,
    "max_portfolio_beta": 2.0,
    "allowed_asset_classes": "",
    "per_strategy_budget_pct": "{}",
}

VALID_ASSET_CLASSES = {"stock", "etf", "crypto"}
VALID_MODES = {"paper", "live"}

# HARD CODE LOCK. Do not flip this without:
# 1) shipping a real broker adapter (`app/brokers/<name>.py`),
# 2) a security review of the order-placement code path,
# 3) explicit user opt-in audited as `auto_execution.live_mode_unlocked`.
#
# Rationale: Alpaca is NOT the operator's real-money broker. Routing live-mode
# at Alpaca would be technically harmless (still a paper-tier in the operator's
# Alpaca account) but conceptually misleading — the user could believe live-mode
# means "real broker" and act accordingly. We refuse to surface live-mode at
# all until Phase 4f delivers the actual broker adapter.
LIVE_MODE_LOCKED = True


def is_live_mode_available() -> bool:
    """Single source of truth for the live-mode kill-switch.

    Surfaced via `/api/auto-execution/limits` as `liveModeAvailable` so the
    frontend can reliably disable the radio button without trying to
    re-derive the state from a list of feature flags.
    """
    return not LIVE_MODE_LOCKED
EARNINGS_HALT_DAYS = 7
FOMC_HALT_HOURS = 24


@dataclass
class RiskDecision:
    """Result of a proposal evaluation.

    `allowed` is the AND of every check. `reasons` lists every check that
    blocked the proposal (empty when allowed=True). `halt_triggers` is the
    subset of `reasons` driven by external macro/material-event data so
    the UI can highlight them separately.
    """

    allowed: bool
    reasons: list[str] = field(default_factory=list)
    halt_triggers: list[str] = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)


def get_limits(db: Session, user: User) -> AutoExecutionLimits:
    """Return the user's row, creating a defaults row on first read.

    Defaults are conservative: `enabled=False`, allowed_asset_classes
    empty, max_position_size_usd=$500. The user has to opt in explicitly.
    """
    row = (
        db.query(AutoExecutionLimits)
        .filter(AutoExecutionLimits.user_id == user.id)
        .first()
    )
    if row is None:
        row = AutoExecutionLimits(user_id=user.id, **DEFAULT_LIMITS)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def serialize_limits(row: AutoExecutionLimits) -> dict[str, Any]:
    """JSON-shape for `/api/auto-execution/limits` GET responses."""
    try:
        per_strategy = json.loads(row.per_strategy_budget_pct or "{}")
        if not isinstance(per_strategy, dict):
            per_strategy = {}
    except (TypeError, ValueError):
        per_strategy = {}
    classes = [
        c.strip().lower() for c in (row.allowed_asset_classes or "").split(",") if c.strip()
    ]
    mode = (row.mode or "paper").lower()
    if mode not in VALID_MODES:
        mode = "paper"
    return {
        "enabled": bool(row.enabled),
        "mode": mode,
        "liveModeAvailable": is_live_mode_available(),
        "maxPositionSizeUsd": float(row.max_position_size_usd or 0),
        "maxDailyLossUsd": float(row.max_daily_loss_usd or 0),
        "maxOpenPositions": int(row.max_open_positions or 0),
        "maxPortfolioBeta": float(row.max_portfolio_beta or 0),
        "allowedAssetClasses": classes,
        "perStrategyBudgetPct": per_strategy,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
    }


def update_limits(db: Session, user: User, payload: dict[str, Any]) -> AutoExecutionLimits:
    """Upsert limits for the user with light validation.

    Out-of-range values are clamped rather than rejected so a partial UI
    submission can't lock the user out of the page. The master switch is
    only flipped to True when the payload sets it explicitly.
    """
    row = get_limits(db, user)

    if "enabled" in payload:
        row.enabled = bool(payload["enabled"])
    if "mode" in payload:
        candidate = str(payload["mode"] or "").lower()
        # Unknown values silently drop to paper. The frontend has the
        # confirmation flow that gates live-mode; the API layer additionally
        # logs the live-mode flip via audit_service.
        if candidate == "live" and LIVE_MODE_LOCKED:
            # Hard-coded refusal. Even a malicious or buggy frontend
            # cannot bypass this — the only way to flip into live-mode
            # is to ship the broker adapter and remove the lock.
            logger.warning(
                "auto_execution_live_mode_blocked_locked user_id=%s",
                getattr(user, "id", None),
            )
            row.mode = "paper"
        else:
            row.mode = candidate if candidate in VALID_MODES else "paper"
    if "maxPositionSizeUsd" in payload:
        row.max_position_size_usd = max(0.0, float(payload["maxPositionSizeUsd"] or 0))
    if "maxDailyLossUsd" in payload:
        row.max_daily_loss_usd = max(0.0, float(payload["maxDailyLossUsd"] or 0))
    if "maxOpenPositions" in payload:
        row.max_open_positions = max(0, int(payload["maxOpenPositions"] or 0))
    if "maxPortfolioBeta" in payload:
        row.max_portfolio_beta = max(0.0, float(payload["maxPortfolioBeta"] or 0))
    if "allowedAssetClasses" in payload:
        raw = payload["allowedAssetClasses"]
        if isinstance(raw, list):
            classes = [str(x).strip().lower() for x in raw if str(x).strip()]
        else:
            classes = [c.strip().lower() for c in str(raw or "").split(",") if c.strip()]
        # Drop unknown classes silently — keeps the policy auditable
        # without leaking new asset classes through the UI.
        classes = [c for c in classes if c in VALID_ASSET_CLASSES]
        row.allowed_asset_classes = ",".join(classes)
    if "perStrategyBudgetPct" in payload:
        raw = payload["perStrategyBudgetPct"]
        if isinstance(raw, dict):
            cleaned = {str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))}
        else:
            cleaned = {}
        row.per_strategy_budget_pct = json.dumps(cleaned)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def _today_realized_pnl(db: Session, user: User) -> float:
    """Sum of `realized_pnl` from paper_transactions executed today (UTC)."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total = (
        db.query(func.coalesce(func.sum(PaperTransaction.realized_pnl), 0.0))
        .filter(
            and_(
                PaperTransaction.user_id == user.id,
                PaperTransaction.executed_at >= today_start,
            )
        )
        .scalar()
    )
    return float(total or 0.0)


def _open_position_count(db: Session, user: User) -> int:
    """Open-position proxy: pending + filled paper-trading orders.

    Phase 4d Reconciliation will replace this with the real Alpaca-side
    open-position count. For Phase 4a, paper-trading orders are the
    authoritative local view.
    """
    return (
        db.query(PaperOrder)
        .filter(and_(PaperOrder.user_id == user.id, PaperOrder.status.in_(["pending", "filled"])))
        .count()
    )


def _evaluate_halt_triggers(
    *,
    asset_class: str | None,
    sec_filings: dict[str, Any] | None,
    fred_calendar: dict[str, Any] | None,
    sector_context: dict[str, Any] | None,
    max_portfolio_beta: float,
) -> list[str]:
    """Return the list of halt-trigger reason codes that fire for this proposal.

    Empty list means no trigger fires — every gate is silent.
    """
    triggers: list[str] = []

    if isinstance(sec_filings, dict):
        last_material = sec_filings.get("lastMaterial")
        if isinstance(last_material, dict):
            days_ago = last_material.get("daysAgo")
            if isinstance(days_ago, (int, float)) and 0 <= days_ago < EARNINGS_HALT_DAYS:
                triggers.append("halt_recent_8k_material_event")

    if isinstance(fred_calendar, dict):
        treasury = fred_calendar.get("treasury") or {}
        if treasury.get("spreadInverted") and (asset_class or "").lower() in {"stock", "etf"}:
            triggers.append("halt_yield_curve_inverted")
        for release in fred_calendar.get("upcomingReleases") or []:
            if not isinstance(release, dict):
                continue
            if release.get("category") != "policy":
                continue
            days_until = release.get("daysUntil")
            if isinstance(days_until, (int, float)) and 0 <= days_until <= 1:
                triggers.append("halt_fomc_within_24h")
                break

    if isinstance(sector_context, dict):
        correlation = sector_context.get("correlation") or {}
        beta = correlation.get("beta")
        if isinstance(beta, (int, float)) and beta > max_portfolio_beta:
            triggers.append("halt_symbol_beta_exceeds_limit")

    return triggers


def evaluate_proposal(
    db: Session,
    user: User,
    proposal: dict[str, Any],
    *,
    sec_filings: dict[str, Any] | None = None,
    fred_calendar: dict[str, Any] | None = None,
    sector_context: dict[str, Any] | None = None,
    net_yield_breakdown: dict[str, Any] | None = None,
    persist: bool = True,
) -> RiskDecision:
    """Run every Phase-4 gate against a proposed automation trade.

    `proposal` shape: {symbol, side, qty, limitPrice, targetPrice, assetClass, source, proposalId}.
    External-data inputs are passed in (rather than fetched here) so the
    evaluator stays unit-testable without HTTP and so the caller can share
    one round-trip across multiple per-symbol proposals.
    """
    limits = get_limits(db, user)
    reasons: list[str] = []

    # Gate 1: master switch.
    if not bool(limits.enabled):
        reasons.append("auto_execution_disabled")

    asset_class = str(proposal.get("assetClass") or "").lower()
    allowed_classes = {
        c.strip().lower()
        for c in (limits.allowed_asset_classes or "").split(",")
        if c.strip()
    }

    # Gate 2: asset-class allowlist.
    if asset_class and asset_class not in allowed_classes:
        reasons.append("asset_class_not_allowed")
    elif not asset_class:
        reasons.append("asset_class_missing")

    # Gate 3: position size cap.
    qty = float(proposal.get("qty") or 0)
    limit_price = float(proposal.get("limitPrice") or proposal.get("targetPrice") or 0)
    position_value = abs(qty * limit_price)
    if position_value <= 0:
        reasons.append("position_value_invalid")
    elif position_value > float(limits.max_position_size_usd or 0):
        reasons.append("position_size_exceeds_limit")

    # Gate 4: daily-loss budget. realized_pnl is negative when the user is
    # already down for the day; a fresh proposal is rejected if today's
    # losses are already at or beyond the cap.
    today_pnl = _today_realized_pnl(db, user)
    if today_pnl <= -float(limits.max_daily_loss_usd or 0):
        reasons.append("daily_loss_budget_exhausted")

    # Gate 5: open-position cap.
    open_count = _open_position_count(db, user)
    if open_count >= int(limits.max_open_positions or 0):
        reasons.append("open_position_cap_reached")

    # Gate 6: Net-Yield-Gate. Same math the explainer + paper-trading
    # accept/reject use; we accept the breakdown from the caller so the
    # gate stays consistent across surfaces.
    net_yield_ok = True
    if isinstance(net_yield_breakdown, dict):
        net_yield_ok = bool(net_yield_breakdown.get("meetsMinimum", True))
    if not net_yield_ok:
        reasons.append("net_yield_gate_blocked")

    # Halt triggers (external data).
    halt_triggers = _evaluate_halt_triggers(
        asset_class=asset_class,
        sec_filings=sec_filings,
        fred_calendar=fred_calendar,
        sector_context=sector_context,
        max_portfolio_beta=float(limits.max_portfolio_beta or 0),
    )
    reasons.extend(halt_triggers)

    allowed = len(reasons) == 0
    breakdown = {
        "positionValueUsd": round(position_value, 2),
        "todayRealizedPnlUsd": round(today_pnl, 2),
        "openPositions": open_count,
        "limits": serialize_limits(limits),
        "netYield": net_yield_breakdown,
    }
    decision = RiskDecision(
        allowed=allowed,
        reasons=reasons,
        halt_triggers=halt_triggers,
        breakdown=breakdown,
    )

    if persist:
        try:
            event = AutoExecutionEvent(
                user_id=user.id,
                proposal_id=str(proposal.get("proposalId") or ""),
                symbol=str(proposal.get("symbol") or "") or None,
                side=str(proposal.get("side") or "") or None,
                status="accepted" if allowed else "rejected",
                reason=", ".join(reasons) if reasons else None,
                payload_json=json.dumps(
                    {
                        "proposal": proposal,
                        "halt_triggers": halt_triggers,
                        "breakdown": breakdown,
                    },
                    default=str,
                ),
            )
            db.add(event)
            db.commit()
        except Exception:
            logger.exception("auto_execution_event_persist_failed user_id=%s", user.id)
            db.rollback()

    return decision


def list_events(
    db: Session, user: User, *, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    """Recent automation events, newest-first, for the user."""
    rows = (
        db.query(AutoExecutionEvent)
        .filter(AutoExecutionEvent.user_id == user.id)
        # `id desc` as tiebreak: SQLite timestamps are second-granular,
        # so two events written within the same second would otherwise
        # come back in arbitrary order.
        .order_by(AutoExecutionEvent.created_at.desc(), AutoExecutionEvent.id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 200)))
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row.payload_json or "{}")
        except (TypeError, ValueError):
            payload = {}
        out.append(
            {
                "id": row.id,
                "proposalId": row.proposal_id,
                "symbol": row.symbol,
                "side": row.side,
                "status": row.status,
                "reason": row.reason,
                "payload": payload,
                "createdAt": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return out


def record_event(
    db: Session,
    user: User,
    *,
    status: str,
    proposal_id: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Direct write for status transitions outside `evaluate_proposal`.

    Phase 4c (halt) and Phase 4d (reconciliation) write `halted` /
    `executed` / `failed` rows through this helper rather than going
    through `evaluate_proposal` again.
    """
    try:
        event = AutoExecutionEvent(
            user_id=user.id,
            proposal_id=proposal_id,
            symbol=symbol,
            side=side,
            status=status,
            reason=reason,
            payload_json=json.dumps(payload or {}, default=str),
        )
        db.add(event)
        db.commit()
    except Exception:
        logger.exception("auto_execution_event_record_failed user_id=%s status=%s", user.id, status)
        db.rollback()


def evaluate_proposal_from_prediction(
    db: Session,
    user: User,
    *,
    symbol: str,
    asset_class: str | None,
    sector: str | None,
    prediction: dict[str, Any],
    latest_close: float | None,
    sec_filings: dict[str, Any] | None = None,
    fred_calendar: dict[str, Any] | None = None,
    sector_context: dict[str, Any] | None = None,
) -> tuple[RiskDecision, dict[str, Any] | None]:
    """Build a proposal from a per-symbol ML prediction and evaluate it.

    Returns `(decision, proposal)`. Proposal is None when the prediction
    is not actionable (no UP/DOWN direction, missing prices, qty would be
    zero). When the prediction is actionable, the proposal carries the
    qty + limit + target prices the auto-loop would actually submit; the
    caller decides whether to act on `decision.allowed`.
    """
    direction = str(prediction.get("direction") or "").upper()
    if direction not in {"UP", "DOWN"}:
        return RiskDecision(allowed=False, reasons=["prediction_not_actionable"]), None
    confidence = float(prediction.get("confidence") or 0)
    if confidence < 0.6:
        return RiskDecision(allowed=False, reasons=["prediction_confidence_below_threshold"]), None

    side = "buy" if direction == "UP" else "sell"
    zones = prediction.get("zones") or {}
    entry_price = (
        float(zones.get("entry") or 0)
        or float(latest_close or 0)
    )
    target_price = float(zones.get("target") or 0) or None
    if entry_price <= 0:
        return RiskDecision(allowed=False, reasons=["entry_price_unavailable"]), None

    limits = get_limits(db, user)
    max_position_usd = float(limits.max_position_size_usd or 0)
    if max_position_usd <= 0 or entry_price <= 0:
        qty = 0.0
    else:
        qty = max(0.0, max_position_usd / entry_price)
        # Stocks/ETFs trade in whole shares; crypto allows fractional.
        if (asset_class or "").lower() != "crypto":
            qty = float(int(qty))
    if qty <= 0:
        return RiskDecision(allowed=False, reasons=["qty_below_one_share"]), None

    proposal = {
        "symbol": symbol.upper(),
        "side": side,
        "qty": qty,
        "limitPrice": entry_price,
        "targetPrice": target_price,
        "assetClass": asset_class,
        "sector": sector,
        "proposalId": f"auto-{symbol.upper()}-{int(datetime.now(timezone.utc).timestamp())}",
        "predictionConfidence": confidence,
    }

    net_yield_breakdown: dict[str, Any] | None = None
    if target_price and entry_price:
        try:
            from app import paper_trading  # local import to avoid cycle

            net_yield_breakdown = paper_trading.evaluate_net_yield_gate(
                user=user,
                side=side,
                entry_price=entry_price,
                target_price=target_price,
                asset_class=asset_class,
            )
        except Exception:
            logger.exception("auto_execution_net_yield_failed symbol=%s", symbol)

    decision = evaluate_proposal(
        db,
        user,
        proposal,
        sec_filings=sec_filings,
        fred_calendar=fred_calendar,
        sector_context=sector_context,
        net_yield_breakdown=net_yield_breakdown,
    )
    return decision, proposal


def halt_all_for_user(db: Session, user: User, *, reason: str) -> int:
    """Flip the master switch off and audit the event.

    Returns the number of orders that *would* have been canceled at the
    broker. Phase 4c will plug in the actual Alpaca cancel call here.
    """
    row = get_limits(db, user)
    was_enabled = bool(row.enabled)
    row.enabled = False
    row.updated_at = datetime.now(timezone.utc)
    open_count = _open_position_count(db, user)
    db.commit()
    record_event(
        db,
        user,
        status="halted",
        reason=reason,
        payload={"wasEnabled": was_enabled, "openOrdersAtHalt": open_count},
    )
    return open_count
