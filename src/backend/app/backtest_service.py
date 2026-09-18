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
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

import pandas as pd

from app.analysis import calculate_indicators
from app.ml_models import MODEL_FEATURE_COLS, PricePredictor
from app.rate_limit import SlidingWindowLimit

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


# The walk-forward never runs in the request path.
#
# Measured 2026-09-11 (verifier, four runs): one request takes 18-26 s, a
# thread that waited in the AnyIO pool computes 3x slower afterwards, two
# requests at once both miss nginx's 60 s upstream timeout, and with the
# background loops active a single request took 165 s. Every variant that
# kept the computation in the request (larger `step`, batch scoring, a
# lock) was refuted at the running system. So the request only *asks*: a
# job per symbol runs on its own single worker thread, the answer is
# `pending` until it is done and `ready` from then on, and the same bars
# for the same symbol are never computed twice.
#
# Process-local by design: the backend runs one uvicorn worker
# (ops/docker/backend.Dockerfile) and results are small dicts. Lid: a second
# worker or a complaint about the cold start after a deploy would justify
# moving the results to the database. The worker is its own executor, not
# `background.get_executor()` — those four threads belong to the periodic
# loops, and a 20-165 s job in there would starve scanner cycles. It still
# competes with the scanner for CPU cores (each ensemble member trains with
# `n_jobs=-1`); if `backtest_job_finished duration_s` stays near 165 s with
# the loops active, the next step is `threadpoolctl.threadpool_limits` in
# this thread alone, which leaves the on-screen prediction untouched.
#
# Jobs are keyed by symbol, not (symbol, stamp): one job per symbol at a
# time. A request that arrives with newer bars while an older stamp is still
# computing gets `pending` and re-asks on its next poll — one extra poll
# cycle, never two concurrent trainings for one symbol.

STATUS_READY = "ready"
STATUS_PENDING = "pending"
STATUS_FAILED = "failed"

#: Jobs that may be queued or running at once (including the running one).
#: One request costs < 1 s but buys up to 165 s of CPU on every core; this
#: bounds the amplification to BACKTEST_MAX_JOBS x job duration. A user who
#: hits it sees `pending` with `queued: false` and is enqueued on a later
#: poll. Raise it once `backtest_queue_full` shows up in the log more than a
#: handful of times a day with several users.
BACKTEST_MAX_JOBS = 8

#: How long `peek` keeps answering `pending, queued: false` for a symbol the
#: cap turned away. Without it every poll of a turned-away symbol misses the
#: shortcut and pays the full path — asset profile, history, on-screen
#: prediction — and can fall back to the synthetic placeholder under a
#: throttled provider, which turns into `ready` + empty and ends the poll
#: with nothing ever enqueued (reviewer, 2026-09-16). Longer than the card's
#: poll interval so a refusal costs one full request per hold, not one per
#: poll; short enough that a free slot is taken within a minute.
BACKTEST_REFUSAL_HOLD_S = 30.0

#: Open jobs (queued or running) one user may own at once, and enqueues one
#: user gets per window. The global cap bounds the amplification for the
#: process; without a per-user share one member fills all eight slots and
#: everyone else reads `queued: false` for as long as they keep polling
#: (security-reviewer, 2026-09-16). Three at once is a user comparing a few
#: symbols; twelve enqueues per ten minutes is more than the analysis page
#: asks for in normal use (one per symbol and new bar) and still bounds a
#: member cycling through the watchlist to ~12 x job duration of worker
#: time per window. Accepted edge: right after a restart the registry is
#: empty, and the first member to open more than twelve symbols in ten
#: minutes waits up to the hold on the thirteenth — a cold start once a
#: deploy, not a steady state. A refusal answers like the global cap — `pending`,
#: `queued: false`, held for BACKTEST_REFUSAL_HOLD_S — so the card waits
#: instead of erroring. Jobs are shared: a second user asking for a symbol
#: that is already open gets `pending` from `peek` and owns nothing.
BACKTEST_MAX_JOBS_PER_USER = 3
BACKTEST_ENQUEUES_PER_USER = SlidingWindowLimit(12, 600.0)

_LOCK = threading.Lock()
_RESULTS: dict[str, dict[str, Any]] = {}
_JOBS: dict[str, dict[str, Any]] = {}
#: (owner, symbol) -> perf_counter() of the last refusal. Owner None is the
#: global cap and holds the symbol for everyone; a refusal by a user's own
#: share or window holds it for that user alone — otherwise one member at
#: their limit would keep a symbol `queued: false` for every other member
#: for as long as they poll (reviewer W1, 2026-09-18).
_REFUSED: dict[tuple[str | None, str], float] = {}
_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backtest")
    return _executor


def shutdown(wait: bool = False) -> None:
    """Close the worker on application shutdown. Queued jobs are dropped; a
    job that is already computing keeps the thread until it returns (the
    container's stop grace period bounds that), same as `background.shutdown`."""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=wait, cancel_futures=True)
        _executor = None


def _stamp(df: pd.DataFrame, train_window: int, step: int) -> str:
    return f"{df.index[-1]}|{len(df)}|{train_window}|{step}"


def _payload(status: str, entry: dict[str, Any] | None, *, queued: bool) -> dict[str, Any]:
    return {
        "status": status,
        "queued": queued,
        "result": entry["result"] if entry else _empty_payload(),
        "computedAt": entry["computedAt"] if entry else None,
        "lastBar": entry["lastBar"] if entry else None,
    }


def _job_is_open(job: dict[str, Any] | None) -> bool:
    return job is not None and not job["future"].done()


def peek(symbol: str, owner: str | None = None) -> dict[str, Any] | None:
    """`pending` (with the last known result) while a job for `symbol` is
    queued or running, or for `BACKTEST_REFUSAL_HOLD_S` after the global
    cap turned it away or `owner`'s share/window did (then `queued: false`);
    else None. The endpoint calls this before it fetches any history: a
    poll must not pay for a provider call or the on-screen prediction, and
    it must not be able to fall back to the synthetic placeholder while a
    real-data job is computing or waiting for a free slot."""
    with _LOCK:
        job = _JOBS.get(symbol)
        if _job_is_open(job):
            return _payload(STATUS_PENDING, _RESULTS.get(symbol), queued=True)
        for key in ((None, symbol), (owner, symbol)):
            refused_at = _REFUSED.get(key)
            if refused_at is None:
                continue
            if perf_counter() - refused_at < BACKTEST_REFUSAL_HOLD_S:
                return _payload(STATUS_PENDING, _RESULTS.get(symbol), queued=False)
            del _REFUSED[key]
        return None


def request_backtest(
    df: pd.DataFrame,
    *,
    symbol: str,
    train_window: int = 180,
    step: int = 10,
    owner: str | None = None,
) -> dict[str, Any]:
    """The answer for `symbol` on these bars: `ready` when it is known,
    `pending` after enqueueing (or while a job is open), `failed` when the
    job raised for exactly these bars. The stamp is the last bar plus the
    row count — a new bar recomputes, a repeat is free. `owner` is the
    requesting user's key for the per-user share; None (internal callers,
    tests) is exempt from it, never from the global cap."""
    if df is None or df.empty:
        return _payload(STATUS_READY, None, queued=False)
    stamp = _stamp(df, train_window, step)
    with _LOCK:
        entry = _RESULTS.get(symbol)
        if entry is not None and entry["stamp"] == stamp:
            return _payload(entry["status"], entry, queued=False)
        job = _JOBS.get(symbol)
        if _job_is_open(job):
            if job["stamp"] != stamp and job["future"].cancel():
                # Still waiting for the worker with bars that are already
                # stale: replace it instead of computing twice.
                del _JOBS[symbol]
            else:
                return _payload(STATUS_PENDING, entry, queued=True)
        open_jobs = [j for j in _JOBS.values() if _job_is_open(j)]
        # Per-user share first, so a member at their own limit never spends
        # a global slot or an enqueue from their window on a refusal.
        if owner is not None:
            owned = sum(1 for j in open_jobs if j["owner"] == owner)
            if owned >= BACKTEST_MAX_JOBS_PER_USER:
                logger.warning(
                    "backtest_user_quota_full",
                    extra={"symbol": symbol, "user": owner, "jobs": owned,
                           "max_jobs_per_user": BACKTEST_MAX_JOBS_PER_USER},
                )
                _REFUSED[(owner, symbol)] = perf_counter()
                return _payload(STATUS_PENDING, entry, queued=False)
        if len(open_jobs) >= BACKTEST_MAX_JOBS:
            logger.warning(
                "backtest_queue_full",
                extra={"symbol": symbol, "jobs": len(open_jobs), "max_jobs": BACKTEST_MAX_JOBS},
            )
            _REFUSED[(None, symbol)] = perf_counter()
            return _payload(STATUS_PENDING, entry, queued=False)
        # Last, because a granted enqueue is spent even when it is refused
        # further down — and nothing is refused further down.
        if owner is not None and not BACKTEST_ENQUEUES_PER_USER.try_acquire(owner):
            logger.warning(
                "backtest_user_window_full",
                extra={"symbol": symbol, "user": owner,
                       "enqueues": BACKTEST_ENQUEUES_PER_USER.limit,
                       "window_s": BACKTEST_ENQUEUES_PER_USER.window_seconds},
            )
            _REFUSED[(owner, symbol)] = perf_counter()
            return _payload(STATUS_PENDING, entry, queued=False)
        future = _get_executor().submit(
            _run_job, df, symbol=symbol, stamp=stamp, train_window=train_window, step=step,
            queued_at=perf_counter(),
        )
        _JOBS[symbol] = {"stamp": stamp, "future": future, "owner": owner}
        _REFUSED.pop((None, symbol), None)
        _REFUSED.pop((owner, symbol), None)
        return _payload(STATUS_PENDING, entry, queued=True)


def _run_job(
    df: pd.DataFrame,
    *,
    symbol: str,
    stamp: str,
    train_window: int,
    step: int,
    queued_at: float,
) -> None:
    started = perf_counter()
    logger.info(
        "backtest_job_started",
        extra={"symbol": symbol, "queued_s": round(started - queued_at, 3)},
    )
    status = STATUS_READY
    try:
        # Resolved at call time so tests can substitute the computation.
        result = run_backtest(df, train_window=train_window, step=step)
    except Exception:
        logger.exception("backtest_job_failed", extra={"symbol": symbol})
        status = STATUS_FAILED
        result = _empty_payload()
    entry = {
        "stamp": stamp,
        "status": status,
        "result": result,
        "computedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lastBar": _bar_label(df.index[-1]),
    }
    # Publish and retire the job in one step, and only if this job is still
    # the one registered for the symbol — a cancelled predecessor never runs
    # this body, and a successor must not be retired by mistake.
    with _LOCK:
        _RESULTS[symbol] = entry
        job = _JOBS.get(symbol)
        if job is not None and job["stamp"] == stamp:
            del _JOBS[symbol]
    if status == STATUS_READY:
        logger.info(
            "backtest_job_finished",
            extra={
                "symbol": symbol,
                "duration_s": round(perf_counter() - started, 3),
                "samples": result.get("samples", 0),
            },
        )


def _bar_label(value: Any) -> str:
    """The last bar as the UI shows a data stamp: a plain date for daily
    bars (the only interval the endpoint fetches), the full timestamp for
    anything with a time of day, `str()` for anything else."""
    if isinstance(value, datetime):
        if (value.hour, value.minute, value.second) == (0, 0, 0):
            return value.date().isoformat()
        return value.isoformat()
    return str(value)


def _reset_for_tests() -> None:
    """Wait for the worker, then forget every job and result."""
    shutdown(wait=True)
    with _LOCK:
        _JOBS.clear()
        _RESULTS.clear()
        _REFUSED.clear()
    BACKTEST_ENQUEUES_PER_USER.reset()


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
