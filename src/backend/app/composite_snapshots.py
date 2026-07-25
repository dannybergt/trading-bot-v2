"""Forward-collection of composite snapshots for calibration (roadmap 2d-3).

The analyst/news/fundamentals composite axes have no historical/as-of-date
source, so their weights cannot be back-tested against past data (see the 2d
ADR). The only honest path to calibrate them is to record the axis values +
verdict *going forward* at recommendation time and join the realised forward
return once a horizon matures. This module does exactly that:

  * ``record_snapshot`` — best-effort write, one row per (symbol, UTC date),
    keeping the most axis-complete snapshot of the day. Never raises into the
    recommendation path.
  * ``label_due_snapshots`` — fills the realised forward return for matured,
    unlabeled rows (bounded per cycle; provider fetches are rate-limited).
  * ``readiness`` — how much labeled data exists and whether the full 4-axis
    calibration is usable yet.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func as safunc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.composite_score import AXES
from app.models import CompositeSnapshot

logger = logging.getLogger(__name__)

# Calendar-day forward window for the outcome label (~1 trading week).
HORIZON_DAYS = 7

# Full-axis labeled samples needed before the full 4-axis calibration (Slice C)
# is considered usable. Heuristic starting point, revisited when C lands.
READY_THRESHOLD = 200

_AXIS_COLUMN = {
    "technical": "axis_technical",
    "analyst": "axis_analyst",
    "fundamentals": "axis_fundamentals",
    "news": "axis_news",
}


def _axis_values(composite: dict) -> dict[str, float | None]:
    out: dict[str, float | None] = {axis: None for axis in AXES}
    for entry in composite.get("breakdown", []) or []:
        axis = entry.get("axis")
        if axis in out:
            value = entry.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out[axis] = float(value)
    return out


def _axis_count(values: dict[str, float | None]) -> int:
    return sum(1 for v in values.values() if v is not None)


def _stored_axis_count(row: CompositeSnapshot) -> int:
    return sum(1 for axis in AXES if getattr(row, _AXIS_COLUMN[axis]) is not None)


def write_snapshot(db: Session, symbol: str, close: Any, composite: dict | None) -> bool:
    """Upsert one snapshot per (symbol, UTC date). Returns True when a row was
    inserted or updated. Keeps the most axis-complete snapshot of the day: a
    user's full-axis visit is not clobbered by a technical-only background
    refresh, and an already-labeled row is left untouched.
    """
    if not composite:
        return False
    try:
        close_f = float(close)
    except (TypeError, ValueError):
        return False
    if close_f <= 0:
        return False
    score = composite.get("score")
    verdict = composite.get("verdict")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not verdict:
        return False

    values = _axis_values(composite)
    sym = str(symbol).upper()
    today = datetime.now(timezone.utc).date()

    existing = (
        db.query(CompositeSnapshot)
        .filter(
            CompositeSnapshot.symbol == sym,
            CompositeSnapshot.snapshot_date == today,
        )
        .one_or_none()
    )

    if existing is None:
        row = CompositeSnapshot(
            symbol=sym,
            snapshot_date=today,
            close=close_f,
            score=float(score),
            verdict=str(verdict)[:8],
            horizon_days=HORIZON_DAYS,
            **{_AXIS_COLUMN[axis]: values[axis] for axis in AXES},
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            # Race on the unique (symbol, date) — another writer won; fine.
            db.rollback()
            return False
        return True

    # Only overwrite an unlabeled row, and only with at-least-as-complete data.
    if existing.realized_up is not None:
        return False
    if _axis_count(values) < _stored_axis_count(existing):
        return False
    existing.close = close_f
    existing.score = float(score)
    existing.verdict = str(verdict)[:8]
    for axis in AXES:
        setattr(existing, _AXIS_COLUMN[axis], values[axis])
    existing.updated_at = datetime.now(timezone.utc)
    db.commit()
    return True


def record_snapshot(symbol: str, close: Any, composite: dict | None) -> None:
    """Best-effort wrapper for the recommendation path — opens its own
    short-lived session and never raises into the caller."""
    if not composite:
        return
    try:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            write_snapshot(db, symbol, close, composite)
        finally:
            db.close()
    except Exception:
        logger.exception("composite_snapshot_record_failed symbol=%s", symbol)


def _forward_close(service: Any, row: CompositeSnapshot) -> float | None:
    """Close price on the first trading day at/after the snapshot's horizon."""
    target = row.snapshot_date + timedelta(days=row.horizon_days)
    hist = service.get_yfinance_history_df(row.symbol, period="3mo", interval="1d")
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    for index, close_val in hist["Close"].items():
        index_date = index.date() if hasattr(index, "date") else index
        if index_date >= target:
            try:
                return float(close_val)
            except (TypeError, ValueError):
                return None
    return None


def label_due_snapshots(
    db: Session, service: Any, *, limit: int = 15, now: datetime | None = None
) -> int:
    """Fill the realised forward return for matured, unlabeled snapshots.

    A row is due once its horizon has elapsed. Returns the count newly labeled.
    Best-effort per row; provider fetches are rate-limited so ``limit`` bounds
    a single cycle.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=HORIZON_DAYS)).date()
    due = (
        db.query(CompositeSnapshot)
        .filter(
            CompositeSnapshot.realized_up.is_(None),
            CompositeSnapshot.snapshot_date <= cutoff,
        )
        .order_by(CompositeSnapshot.snapshot_date.asc())
        .limit(limit)
        .all()
    )
    labeled = 0
    for row in due:
        try:
            forward = _forward_close(service, row)
            if forward is None:
                continue
            row.forward_close = forward
            row.forward_return_pct = (
                round((forward - row.close) / row.close * 100.0, 4) if row.close else None
            )
            row.realized_up = forward > row.close
            row.labeled_at = now
            row.updated_at = now
            db.commit()
            labeled += 1
        except Exception:
            db.rollback()
            logger.exception("composite_snapshot_label_failed id=%s", getattr(row, "id", None))
    return labeled


def readiness(db: Session) -> dict[str, Any]:
    """How much labeled data exists and whether the full 4-axis calibration is
    usable yet (all four axes present AND labeled, past the threshold)."""
    total = db.query(CompositeSnapshot).count()
    labeled = (
        db.query(CompositeSnapshot)
        .filter(CompositeSnapshot.realized_up.isnot(None))
        .count()
    )
    full_axis_labeled = (
        db.query(CompositeSnapshot)
        .filter(
            CompositeSnapshot.realized_up.isnot(None),
            CompositeSnapshot.axis_technical.isnot(None),
            CompositeSnapshot.axis_analyst.isnot(None),
            CompositeSnapshot.axis_fundamentals.isnot(None),
            CompositeSnapshot.axis_news.isnot(None),
        )
        .count()
    )
    earliest = db.query(safunc.min(CompositeSnapshot.snapshot_date)).scalar()
    latest = db.query(safunc.max(CompositeSnapshot.snapshot_date)).scalar()
    return {
        "total": total,
        "labeled": labeled,
        "fullAxisLabeled": full_axis_labeled,
        "threshold": READY_THRESHOLD,
        "ready": full_axis_labeled >= READY_THRESHOLD,
        "earliestSnapshot": earliest.isoformat() if earliest else None,
        "latestSnapshot": latest.isoformat() if latest else None,
        "horizonDays": HORIZON_DAYS,
    }
