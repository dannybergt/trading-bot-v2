"""Per-symbol XGBoost model persistence.

The current `MarketDataService` re-trained its single PricePredictor on
every `/api/stock/{symbol}` request — slow, indeterministic, and unable
to learn from anything other than what was on the screen at that moment.
This module replaces that with a per-symbol on-disk cache. Each model is
written as XGBoost's native JSON next to a tiny metadata file that
records when it was trained, on how many rows, and the train-set
accuracy.

`MarketDataService` checks `load_predictor` first, retrains only when
the on-disk model is stale (>24h by default) or missing, and persists
the freshly trained model immediately. Training metadata is exposed on
`/api/research/{symbol}` so the user can see when the model was last
refreshed.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

MODEL_DIR = Path(
    os.getenv(
        "ML_MODEL_DIR",
        Path(__file__).resolve().parent.parent / "data" / "ml_models",
    )
)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_TTL_HOURS = float(os.getenv("ML_MODEL_TTL_HOURS", "24"))


def _safe_symbol(symbol: str) -> str:
    """`BTC/USD` → `BTC_USD`. Reject anything that could escape the model dir."""
    safe = symbol.replace("/", "_").replace("\\", "_").upper().strip()
    if not safe or any(ch in safe for ch in ("..", "\x00")):
        raise ValueError(f"unsafe symbol: {symbol!r}")
    return safe


def _model_paths(symbol: str) -> tuple[Path, Path]:
    safe = _safe_symbol(symbol)
    return MODEL_DIR / f"{safe}.json", MODEL_DIR / f"{safe}.meta.json"


def save_predictor(
    symbol: str,
    predictor: Any,
    *,
    accuracy: float,
    features: list[str],
    n_samples: int,
) -> dict[str, Any] | None:
    """Persist a trained PricePredictor and return the written metadata.

    No-op when the predictor is not trained or the underlying xgboost
    model is unavailable.
    """
    if predictor is None or not getattr(predictor, "is_trained", False):
        return None
    model = getattr(predictor, "model", None)
    if model is None:
        return None
    try:
        model_path, meta_path = _model_paths(symbol)
    except ValueError:
        logger.warning("ml_persistence_save_skipped_unsafe_symbol symbol=%s", symbol)
        return None

    try:
        model.save_model(str(model_path))
    except Exception:
        logger.exception("ml_persistence_save_model_failed symbol=%s", symbol)
        return None

    metadata = {
        "symbol": symbol.upper(),
        "trainedAt": datetime.now(timezone.utc).isoformat(),
        "accuracy": round(float(accuracy or 0.0), 6),
        "featureCount": len(features or []),
        "features": list(features or []),
        "nSamples": int(n_samples or 0),
    }
    try:
        meta_path.write_text(json.dumps(metadata, indent=2))
    except Exception:
        logger.exception("ml_persistence_save_metadata_failed symbol=%s", symbol)
        return None
    return metadata


def load_predictor(
    symbol: str, predictor_factory: Callable[[], Any]
) -> tuple[Any, dict[str, Any]] | None:
    """Return (predictor, metadata) when both files exist, else None.

    `predictor_factory` is a zero-arg constructor — typically just
    `PricePredictor`. Keeping the dependency at the call site avoids a
    circular import between this module and `ml_models`.
    """
    try:
        model_path, meta_path = _model_paths(symbol)
    except ValueError:
        return None
    if not model_path.exists() or not meta_path.exists():
        return None

    try:
        metadata = json.loads(meta_path.read_text())
    except Exception:
        logger.exception("ml_persistence_load_metadata_failed symbol=%s", symbol)
        return None

    predictor = predictor_factory()
    if getattr(predictor, "model", None) is None:
        return None
    try:
        predictor.model.load_model(str(model_path))
        predictor.is_trained = True
    except Exception:
        logger.exception("ml_persistence_load_model_failed symbol=%s", symbol)
        return None
    return predictor, metadata


def is_stale(metadata: dict[str, Any] | None, *, ttl_hours: float | None = None) -> bool:
    """True when the model is older than `ttl_hours` (default `MODEL_TTL_HOURS`)."""
    if not metadata:
        return True
    raw = metadata.get("trainedAt") or metadata.get("trained_at")
    if not raw:
        return True
    try:
        trained_at = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return True
    if trained_at.tzinfo is None:
        trained_at = trained_at.replace(tzinfo=timezone.utc)
    ttl = float(ttl_hours) if ttl_hours is not None else MODEL_TTL_HOURS
    age_hours = (datetime.now(timezone.utc) - trained_at).total_seconds() / 3600.0
    return age_hours >= ttl


def list_models() -> list[dict[str, Any]]:
    """All on-disk model metadata, used by admin/dashboard surfaces."""
    rows: list[dict[str, Any]] = []
    for meta_path in sorted(MODEL_DIR.glob("*.meta.json")):
        try:
            rows.append(json.loads(meta_path.read_text()))
        except Exception:
            continue
    return rows


def delete_model(symbol: str) -> None:
    """Remove the on-disk model + metadata for a symbol — used by tests
    and ad-hoc admin commands."""
    try:
        model_path, meta_path = _model_paths(symbol)
    except ValueError:
        return
    for path in (model_path, meta_path):
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except Exception:
            logger.exception("ml_persistence_delete_failed path=%s", path)
