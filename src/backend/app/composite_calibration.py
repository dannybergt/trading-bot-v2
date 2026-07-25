"""Interim partial calibration of the composite weights (roadmap 2d-2).

Grid-searches axis weights against the realised hit-rate on the labeled
`composite_snapshot` data and — only when the best set strictly beats the
current weights — writes it into the operator weights store (Slice A).

Honest by construction: an axis is only calibrated when it has enough coverage
in the labeled data (`COVERAGE_MIN_FRAC`). Axes without coverage (today:
analyst/news, which have no historical source) keep their current/policy
weight, so the search only tunes what it can actually measure. Once
forward-collection matures and all four axes have coverage, the same grid
naturally spans all of them — the "full calibration" turns on by data, not by
a separate code path.
"""
from __future__ import annotations

import itertools
import logging
from typing import Any

from sqlalchemy.orm import Session

from app import composite_weights
from app.composite_score import (
    AXES,
    _BUY_THRESHOLD,
    _SELL_THRESHOLD,
    _clamp,
)
from app.models import CompositeSnapshot

logger = logging.getLogger(__name__)

# Minimum labeled rows before calibrating at all.
MIN_LABELED = 30
# An axis must be present in at least this fraction of labeled rows to be tuned.
COVERAGE_MIN_FRAC = 0.5
# A weight set must produce at least this fraction of actionable (BUY/SELL)
# verdicts to be eligible — guards against a degenerate "one lucky BUY" winner.
MIN_ACTIONABLE_FRAC = 0.2
# The best set must beat the current hit-rate by at least this margin to write.
IMPROVEMENT_MARGIN = 1e-9

_AXIS_COLUMN = {
    "technical": "axis_technical",
    "analyst": "axis_analyst",
    "fundamentals": "axis_fundamentals",
    "news": "axis_news",
}


def _score(axis_values: dict[str, float | None], weights: dict[str, float]) -> float | None:
    """Weighted mean over the axes present in this row (missing axes drop out
    and the remaining weights renormalise) — mirrors compute_composite."""
    available = {a: v for a, v in axis_values.items() if v is not None}
    total = sum(weights.get(a, 0.0) for a in available)
    if total <= 0:
        return None
    return _clamp(sum(weights.get(a, 0.0) * v for a, v in available.items()) / total)


def _verdict(score: float) -> str:
    if score >= _BUY_THRESHOLD:
        return "BUY"
    if score <= _SELL_THRESHOLD:
        return "SELL"
    return "HOLD"


def _hit_rate(
    rows: list[tuple[dict[str, float | None], bool]], weights: dict[str, float]
) -> tuple[float, int]:
    """(hit_rate over actionable verdicts, actionable count). HOLD abstains."""
    actionable = 0
    hits = 0
    for values, realized_up in rows:
        score = _score(values, weights)
        if score is None:
            continue
        verdict = _verdict(score)
        if verdict == "HOLD":
            continue
        actionable += 1
        if (verdict == "BUY" and realized_up) or (verdict == "SELL" and not realized_up):
            hits += 1
    return (hits / actionable if actionable else 0.0), actionable


def _labeled_rows(db: Session) -> list[tuple[dict[str, float | None], bool]]:
    rows: list[tuple[dict[str, float | None], bool]] = []
    for snap in (
        db.query(CompositeSnapshot)
        .filter(CompositeSnapshot.realized_up.isnot(None))
        .all()
    ):
        values = {axis: getattr(snap, _AXIS_COLUMN[axis]) for axis in AXES}
        rows.append((values, bool(snap.realized_up)))
    return rows


def calibrate(
    db: Session, *, apply: bool = False, updated_by_user_id: int | None = None
) -> dict[str, Any]:
    """Grid-search axis weights against realised hit-rate.

    Returns a report. When ``apply`` and the best set strictly beats the current
    hit-rate, writes it via ``composite_weights.set_weights`` (caller commits).
    """
    rows = _labeled_rows(db)
    n = len(rows)
    current = composite_weights.get_weights()
    current_hit_rate, current_actionable = _hit_rate(rows, current)

    report: dict[str, Any] = {
        "applied": False,
        "labeled": n,
        "minLabeled": MIN_LABELED,
        "currentWeights": current,
        "currentHitRate": round(current_hit_rate, 4),
    }

    if n < MIN_LABELED:
        report["reason"] = "insufficient_labeled_data"
        return report

    coverage = {
        axis: sum(1 for values, _ in rows if values[axis] is not None) / n for axis in AXES
    }
    covered = [axis for axis in AXES if coverage[axis] >= COVERAGE_MIN_FRAC]
    report["coverage"] = {a: round(coverage[a], 3) for a in AXES}
    report["calibratedAxes"] = covered

    if not covered:
        report["reason"] = "no_axis_has_enough_coverage"
        return report

    # Coarser grid when many axes are covered, to bound the combination count.
    grid = [round(x * 0.2, 1) for x in range(6)] if len(covered) >= 4 else [
        round(x * 0.1, 1) for x in range(11)
    ]
    fixed = {axis: current.get(axis, 0.0) for axis in AXES if axis not in covered}
    min_actionable = max(1, int(MIN_ACTIONABLE_FRAC * n))

    best_weights: dict[str, float] | None = None
    best_hit_rate = -1.0
    best_actionable = -1
    for combo in itertools.product(grid, repeat=len(covered)):
        weights = dict(fixed)
        weights.update(dict(zip(covered, combo)))
        if sum(weights.values()) <= 0:
            continue
        hit_rate, actionable = _hit_rate(rows, weights)
        if actionable < min_actionable:
            continue
        if hit_rate > best_hit_rate or (
            hit_rate == best_hit_rate and actionable > best_actionable
        ):
            best_hit_rate = hit_rate
            best_actionable = actionable
            best_weights = weights

    if best_weights is None:
        report["reason"] = "no_eligible_weight_set"
        return report

    # Normalise for display/storage (set_weights normalises too).
    total = sum(best_weights.values())
    best_normalized = {axis: best_weights.get(axis, 0.0) / total for axis in AXES}
    report["bestWeights"] = {a: round(best_normalized[a], 4) for a in AXES}
    report["bestHitRate"] = round(best_hit_rate, 4)
    report["bestActionable"] = best_actionable
    report["improved"] = best_hit_rate > current_hit_rate + IMPROVEMENT_MARGIN

    if apply and report["improved"]:
        composite_weights.set_weights(
            db, best_normalized, updated_by_user_id=updated_by_user_id
        )
        report["applied"] = True

    return report
