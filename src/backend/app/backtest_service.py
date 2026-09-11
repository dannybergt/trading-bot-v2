"""Walk-forward backtest for the per-symbol PricePredictor.

Phase 4 auto-execution shouldn't fire on a model whose live performance
nobody has measured. This service slides a training window across the
historical bars, predicts the next bar, and tracks how often the
direction call was right plus what a naive long/flat strategy would
have produced. The output is shaped for direct UI rendering on
`/analysis/<symbol>`:

- accuracy / AUC / Brier-score across all walk-forward predictions
- cumulative percent return of "long when UP, flat when DOWN/HOLD"
- buy-and-hold return for comparison
- a 10-bucket reliability table for confidence calibration
"""
from __future__ import annotations

import logging
import math
from typing import Any

import pandas as pd

from app.analysis import calculate_indicators
from app.ml_models import MODEL_FEATURE_COLS, PricePredictor

logger = logging.getLogger(__name__)

# Fewer prepared rows than this cannot carry an 80/20 split with two classes.
MIN_TRAINABLE_ROWS = 10


def run_backtest(
    df: pd.DataFrame,
    *,
    train_window: int = 180,
    step: int = 10,
) -> dict[str, Any]:
    """Walk-forward predictions over `df` (must already include indicators).

    `train_window` is the number of rows the predictor sees before each
    prediction. `step` advances the window between retrains; predictions
    are emitted for every row regardless of `step` so accuracy stays
    measurable.

    Returns an empty payload (everything `None`/`0`) when there isn't
    enough data to even fit one window — the UI degrades gracefully.
    """
    empty = _empty_payload()
    if df is None or df.empty:
        return empty

    work = df.copy()
    if "Close" not in work.columns:
        return empty
    work = work.dropna(subset=["Close"])
    if len(work) < train_window + 5:
        return empty

    predictions: list[dict[str, Any]] = []
    feature_cols = [c for c in MODEL_FEATURE_COLS if c in work.columns]
    last = len(work) - 1  # the final row has no "next close" to score against

    # Train once per block of `step` bars, then score the whole block in one
    # batch. Each bar is still predicted from a model that has seen only the
    # bars before the block, and only from its own features — the same
    # information as a bar-by-bar loop. What changes is the cost: the
    # bar-by-bar loop ran the full on-screen prediction (explanation, zones,
    # yield model) on a growing copy of the frame for every bar; measured
    # 2026-09-11 that was 40 s of a 53 s request, independent of `step`.
    for block_start in range(train_window, last, step):
        slice_df = work.iloc[:block_start].copy()
        predictor = PricePredictor()
        if not _window_is_trainable(predictor, slice_df):
            # Early windows lose most rows to indicator warm-up and can
            # end up with one row or one class. Training there cannot
            # succeed and used to log a traceback at ERROR per window.
            continue
        try:
            predictor.train(slice_df)
        except Exception:
            logger.exception("backtest_train_failed at_index=%s", block_start)
            continue
        if not predictor.is_trained:
            continue

        block_end = min(block_start + step, last)
        block = work.iloc[block_start:block_end]
        if feature_cols:
            block = block.dropna(subset=feature_cols)
        if block.empty:
            continue
        try:
            probs_up = predictor.probability_up(block)
        except Exception:
            logger.exception("backtest_predict_failed at_index=%s", block_start)
            continue
        if probs_up is None:
            continue

        positions = work.index.get_indexer(block.index)
        for pos, prob_up in zip(positions, probs_up):
            prob_up = float(prob_up)
            actual_close = float(work.iloc[pos + 1]["Close"])
            prev_close = float(work.iloc[pos]["Close"])
            actual_up = actual_close > prev_close
            predicted_up = prob_up > 0.5
            confidence = prob_up if predicted_up else 1.0 - prob_up
            ret_pct = (actual_close - prev_close) / prev_close * 100.0 if prev_close else 0.0
            predictions.append(
                {
                    "predictedUp": predicted_up,
                    "actualUp": actual_up,
                    "confidence": confidence,
                    "probabilityUp": prob_up,
                    "returnPct": ret_pct,
                }
            )

    if not predictions:
        return empty

    total = len(predictions)
    correct = sum(1 for p in predictions if p["predictedUp"] == p["actualUp"])
    accuracy = correct / total

    auc = _auc(predictions)
    brier = sum((p["probabilityUp"] - (1.0 if p["actualUp"] else 0.0)) ** 2 for p in predictions) / total

    strategy_return = 0.0
    buyhold_return = 0.0
    for p in predictions:
        buyhold_return += p["returnPct"]
        if p["predictedUp"]:
            strategy_return += p["returnPct"]

    reliability = _reliability_buckets(predictions)

    return {
        "samples": total,
        "accuracy": round(accuracy, 4),
        "auc": round(auc, 4) if auc is not None else None,
        "brierScore": round(brier, 4),
        "strategyReturnPct": round(strategy_return, 4),
        "buyHoldReturnPct": round(buyhold_return, 4),
        "reliability": reliability,
        "trainWindow": train_window,
        "step": step,
    }


def run_backtest_for_history(
    history_fetcher,
    symbol: str,
    *,
    period_days: int = 750,
    train_window: int = 180,
    step: int = 10,
) -> dict[str, Any]:
    """Convenience wrapper: pull history via `history_fetcher(symbol, days)`,
    enrich indicators, and hand off to `run_backtest`.

    The fetcher is injected so callers can plug in `MarketDataService`
    in production and a stub frame in tests without dragging the whole
    network stack into the unit suite.
    """
    df = history_fetcher(symbol, period_days)
    if df is None or df.empty:
        return _empty_payload()
    enriched = calculate_indicators(df.copy())
    return run_backtest(enriched, train_window=train_window, step=step)


def _auc(predictions: list[dict[str, Any]]) -> float | None:
    """Mann-Whitney-style AUC for binary actuals against probabilityUp."""
    pos = [p["probabilityUp"] for p in predictions if p["actualUp"]]
    neg = [p["probabilityUp"] for p in predictions if not p["actualUp"]]
    if not pos or not neg:
        return None
    wins = 0.0
    for hi in pos:
        for lo in neg:
            if hi > lo:
                wins += 1.0
            elif math.isclose(hi, lo):
                wins += 0.5
    return wins / (len(pos) * len(neg))


def _reliability_buckets(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """10 evenly spaced buckets over `probabilityUp`; for each return the
    predicted band, the empirical accuracy, and the bucket size — the
    UI can render this as a calibration plot.
    """
    buckets: list[list[dict[str, Any]]] = [[] for _ in range(10)]
    for p in predictions:
        idx = min(9, max(0, int(p["probabilityUp"] * 10)))
        buckets[idx].append(p)
    out: list[dict[str, Any]] = []
    for idx, bucket in enumerate(buckets):
        if not bucket:
            out.append(
                {
                    "bucket": f"{idx * 10}-{(idx + 1) * 10}%",
                    "predictedMid": (idx + 0.5) / 10.0,
                    "actualUpRate": None,
                    "count": 0,
                }
            )
            continue
        hits = sum(1 for p in bucket if p["actualUp"])
        out.append(
            {
                "bucket": f"{idx * 10}-{(idx + 1) * 10}%",
                "predictedMid": (idx + 0.5) / 10.0,
                "actualUpRate": round(hits / len(bucket), 4),
                "count": len(bucket),
            }
        )
    return out


def _window_is_trainable(predictor: PricePredictor, slice_df: pd.DataFrame) -> bool:
    """Whether `predictor.train` has anything to learn from: enough rows after
    feature preparation, and both classes inside the unshuffled 80 % that
    `train` fits on."""
    try:
        data, _ = predictor.prepare_features(slice_df)
    except Exception:
        return False
    if len(data) < MIN_TRAINABLE_ROWS:
        return False
    train_part = data["Target"].iloc[: max(1, int(len(data) * 0.8))]
    return train_part.nunique() == 2


def _empty_payload() -> dict[str, Any]:
    return {
        "samples": 0,
        "accuracy": None,
        "auc": None,
        "brierScore": None,
        "strategyReturnPct": None,
        "buyHoldReturnPct": None,
        "reliability": [],
        "trainWindow": None,
        "step": None,
    }
