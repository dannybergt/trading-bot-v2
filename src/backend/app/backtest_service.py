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
from app.ml_models import PricePredictor

logger = logging.getLogger(__name__)


def run_backtest(
    df: pd.DataFrame,
    *,
    train_window: int = 180,
    step: int = 10,
    feature_padding: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Walk-forward predictions over `df` (must already include indicators).

    `train_window` is the number of rows the predictor sees before each
    prediction. `step` advances the window between retrains; predictions
    are emitted for every row regardless of `step` so accuracy stays
    measurable. `feature_padding` lets the caller supply default values
    for sentiment/fundamental features that the indicator frame doesn't
    populate (we'd otherwise drop every row at `prepare_features`).

    Returns an empty payload (everything `None`/`0`) when there isn't
    enough data to even fit one window — the UI degrades gracefully.
    """
    empty = _empty_payload()
    if df is None or df.empty:
        return empty

    work = df.copy()
    padding = {
        "News_Sentiment": 0.0,
        "PE_Ratio": 0.0,
        "Forward_PE": 0.0,
        "Price_To_Book": 0.0,
    }
    padding.update(feature_padding or {})
    for col, default in padding.items():
        if col not in work.columns:
            work[col] = default

    if "Close" not in work.columns:
        return empty
    work = work.dropna(subset=["Close"])
    if len(work) < train_window + 5:
        return empty

    predictions: list[dict[str, Any]] = []
    last_trained_at: int | None = None
    predictor: PricePredictor | None = None

    for i in range(train_window, len(work) - 1):
        if predictor is None or last_trained_at is None or i - last_trained_at >= step:
            slice_df = work.iloc[: i].copy()
            predictor = PricePredictor()
            try:
                predictor.train(slice_df)
            except Exception:
                logger.exception("backtest_train_failed at_index=%s", i)
                predictor = None
                continue
            if not predictor.is_trained:
                continue
            last_trained_at = i

        try:
            row_df = work.iloc[: i + 1].copy()
            prediction = predictor.predict_next_movement(row_df, user=None)
        except Exception:
            logger.exception("backtest_predict_failed at_index=%s", i)
            continue
        if not prediction:
            continue
        actual_close = float(work.iloc[i + 1]["Close"])
        prev_close = float(work.iloc[i]["Close"])
        actual_up = actual_close > prev_close
        predicted_up = prediction.get("direction") == "UP"
        confidence = float(prediction.get("confidence") or 0.0)
        prob_up = float(prediction.get("probabilityUp") or (confidence if predicted_up else 1.0 - confidence))
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
