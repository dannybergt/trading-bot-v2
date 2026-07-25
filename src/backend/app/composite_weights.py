"""Operator-configurable composite axis weights (non-secret).

The composite decision score (app/composite_score.py) combines four axes
(technical/analyst/fundamentals/news) with weights. `compute_composite`
already accepts a `weights` override; this module is where that override is
persisted and resolved. An admin can tune the weights from the UI, and the
roadmap-2d backtest calibration will later write a calibrated set here.

Unlike `platform_config` these values are plain numbers, not secrets, so they
are stored in clear text (a small JSON object in a singleton DB row).

Read path: DB singleton row (when present and valid) > in-code
`DEFAULT_WEIGHTS`. A 60-second in-memory cache keeps the hot recommendation
path (every `/api/stock`) off the database; `invalidate()` is called on write
so a change propagates immediately. Weights are stored normalised to sum 1.0.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.composite_score import AXES, DEFAULT_WEIGHTS
from app.models import CompositeWeightConfiguration

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60.0
_SINGLETON_ID = 1

_lock = threading.Lock()
# (expires_at monotonic, weights dict | None)
_cache: dict[str, Any] = {"expires_at": 0.0, "weights": None}


def _now() -> float:
    return time.monotonic()


def validate_weights(raw: Any) -> dict[str, float]:
    """Coerce raw input into a valid, normalised weight map (sums to 1.0).

    Requires every axis present as a finite, non-negative number with at least
    one positive weight, and rejects unknown axes. Raises ``ValueError`` on
    anything else so the API layer can return a 400.
    """
    if not isinstance(raw, dict):
        raise ValueError("weights must be an object")
    unknown = set(raw) - set(AXES)
    if unknown:
        raise ValueError(f"unknown axes: {sorted(unknown)}")
    cleaned: dict[str, float] = {}
    for axis in AXES:
        if axis not in raw:
            raise ValueError(f"missing axis: {axis}")
        value = raw[axis]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"weight for {axis} must be a number")
        value = float(value)
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"weight for {axis} must be finite")
        if value < 0:
            raise ValueError(f"weight for {axis} must be >= 0")
        cleaned[axis] = value
    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    return {axis: cleaned[axis] / total for axis in AXES}


def _parse_stored(row: CompositeWeightConfiguration | None) -> dict[str, float] | None:
    if row is None:
        return None
    try:
        return validate_weights(json.loads(row.weights_json))
    except (ValueError, TypeError, json.JSONDecodeError):
        logger.warning("composite_weights_stored_invalid_falling_back_to_default")
        return None


def get_stored(db: Session) -> dict[str, float] | None:
    """The persisted, validated override — or ``None`` when unset/invalid."""
    return _parse_stored(db.get(CompositeWeightConfiguration, _SINGLETON_ID))


def get_weights() -> dict[str, float]:
    """Effective weights for the composite score.

    Cached for 60s; opens its own short-lived session on a cache miss so the
    hot recommendation path does not need a request-scoped session threaded
    through it. Any read failure degrades to ``DEFAULT_WEIGHTS`` (never raises).
    """
    with _lock:
        if _cache["weights"] is not None and _cache["expires_at"] > _now():
            return dict(_cache["weights"])

    weights: dict[str, float] | None = None
    try:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            weights = get_stored(db)
        finally:
            db.close()
    except Exception:
        logger.exception("composite_weights_read_failed_falling_back_to_default")

    effective = weights or dict(DEFAULT_WEIGHTS)
    with _lock:
        _cache["weights"] = dict(effective)
        _cache["expires_at"] = _now() + _CACHE_TTL_SECONDS
    return dict(effective)


def set_weights(
    db: Session, raw: Any, *, updated_by_user_id: int | None
) -> dict[str, float]:
    """Validate and persist the singleton override, returning the normalised
    weights. The caller is responsible for ``db.commit()``. Also invalidates
    the cache; the endpoint invalidates again after commit to close the race
    where a concurrent read re-caches the pre-commit value.
    """
    normalized = validate_weights(raw)
    payload = json.dumps(normalized)
    row = db.get(CompositeWeightConfiguration, _SINGLETON_ID)
    if row is None:
        row = CompositeWeightConfiguration(
            id=_SINGLETON_ID,
            weights_json=payload,
            updated_by_user_id=updated_by_user_id,
        )
        db.add(row)
    else:
        row.weights_json = payload
        row.updated_by_user_id = updated_by_user_id
        row.updated_at = datetime.now(timezone.utc)
    invalidate()
    return normalized


def invalidate() -> None:
    with _lock:
        _cache["weights"] = None
        _cache["expires_at"] = 0.0
