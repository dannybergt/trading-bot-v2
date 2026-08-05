"""Composite decision score — combine every available signal into one
transparent, weighted verdict.

Today the recommendation is effectively technical-only: the ML ensemble learns
from chart indicators while news/fundamentals sit in the model as constant
broadcast columns (near-zero contribution) and analyst data is display-only.
This module lifts each source to a first-class, *visible* axis and combines
them with explicit weights, so a BUY/HOLD/SELL verdict shows exactly how much
each source contributed — no black box.

Design:
- Each axis maps its source onto a signed contribution in [-1, +1]
  (bullish positive, bearish negative). An axis with no data returns ``None``
  and is dropped; the remaining weights are renormalised so a missing source
  does not silently drag the score toward zero.
- The composite is the weighted mean of the available axes. Macro/risk stays a
  hard veto elsewhere (halt triggers) — it is deliberately not a weight here.
- Weights are explicit and configurable; the defaults below are a starting
  point to be calibrated by backtest, not a fixed truth.

This augments the ML prediction (still shown separately); it does not replace it
and it is not yet wired into auto-execution (that is a later, calibrated step).
"""
from __future__ import annotations

from typing import Any

# Default profile chosen with the user: technical leads, analysts + fundamentals
# confirm, news fine-tunes. Configurable + backtest-calibratable later.
DEFAULT_WEIGHTS: dict[str, float] = {
    "technical": 0.40,
    "analyst": 0.25,
    "fundamentals": 0.20,
    "news": 0.15,
}

AXES = ("technical", "analyst", "fundamentals", "news")

# Score bands for the discrete verdict.
_BUY_THRESHOLD = 0.15
_SELL_THRESHOLD = -0.15


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def technical_axis(prediction: dict | None) -> float | None:
    """From the ML probability of an up-move. P(up)=0.5 -> 0, 1.0 -> +1, 0 -> -1.

    Returns ``None`` for a synthetic/placeholder prediction — no real signal."""
    if not prediction or prediction.get("synthetic"):
        return None
    p_up = _num(prediction.get("probabilityUp"))
    if p_up is None:
        conf = _num(prediction.get("confidence"))
        direction = str(prediction.get("direction") or "").upper()
        if conf is None or direction not in ("UP", "DOWN"):
            return None
        p_up = conf if direction == "UP" else 1.0 - conf
    return _clamp(2.0 * p_up - 1.0)


def analyst_axis(consensus: dict | None) -> float | None:
    """From the analyst consensus stance and price-target upside."""
    if not consensus:
        return None
    parts: list[float] = []
    stance = consensus.get("stance")
    if stance == "bullish":
        parts.append(0.6)
    elif stance == "bearish":
        parts.append(-0.6)
    elif stance == "neutral":
        parts.append(0.0)
    upside = _num(consensus.get("targetUpsidePct"))
    if upside is not None:
        parts.append(_clamp(upside / 25.0))  # +/-25% target gap -> +/-1
    if not parts:
        return None
    return _clamp(sum(parts) / len(parts))


def fundamentals_axis(info: dict | None) -> float | None:
    """A simple, transparent value score from the core KPIs. Each available
    sub-signal contributes; the axis is their average.

    - trailing P/E: healthy 0-25 -> +, 25-40 -> neutral, >40 or negative -> -
    - return on equity: scaled, 20% -> +1, negative -> negative
    - debt/equity: low -> +, high -> - (yfinance reports percent; normalised)
    """
    if not info:
        return None
    subs: list[float] = []

    pe = _num(info.get("trailingPE")) or _num(info.get("peRatioTtm"))
    if pe is not None and pe != 0:
        if pe < 0:
            subs.append(-0.5)
        elif pe <= 25:
            subs.append(0.5)
        elif pe <= 40:
            subs.append(0.0)
        else:
            subs.append(-0.5)

    roe = _num(info.get("returnOnEquity"))
    if roe is None:
        roe = _num(info.get("returnOnEquityTtm"))
    if roe is not None:
        subs.append(_clamp(roe / 0.20))

    dte = _num(info.get("debtToEquity"))
    if dte is None:
        # fundamentalsDetail carries the already-normalised ratio
        dte_ratio = _num(info.get("debtToEquityTtm"))
    else:
        # yfinance .info reports debtToEquity as a percentage (e.g. 154.5)
        dte_ratio = dte / 100.0 if dte > 5 else dte
    if dte_ratio is not None:
        subs.append(_clamp(1.0 - dte_ratio))  # ratio 0 -> +1, ratio 2 -> -1

    if not subs:
        return None
    return _clamp(sum(subs) / len(subs))


def news_axis(sentiment_score: Any) -> float | None:
    """From the aggregate news sentiment (already roughly [-1, +1])."""
    score = _num(sentiment_score)
    if score is None:
        return None
    return _clamp(score)


def compute_composite(
    *,
    prediction: dict | None,
    analyst: dict | None,
    fundamentals_info: dict | None,
    news_sentiment: Any,
    weights: dict[str, float] | None = None,
) -> dict[str, Any] | None:
    """Combine the available axes into one weighted verdict with a full,
    per-axis breakdown. Returns ``None`` when no axis has data."""
    weights = weights or DEFAULT_WEIGHTS
    values = {
        "technical": technical_axis(prediction),
        "analyst": analyst_axis(analyst),
        "fundamentals": fundamentals_axis(fundamentals_info),
        "news": news_axis(news_sentiment),
    }
    available = {axis: v for axis, v in values.items() if v is not None}
    if not available:
        return None
    total_weight = sum(weights.get(axis, 0.0) for axis in available)
    if total_weight <= 0:
        return None

    score = _clamp(
        sum(weights.get(axis, 0.0) * v for axis, v in available.items()) / total_weight
    )
    verdict = (
        "BUY" if score >= _BUY_THRESHOLD
        else "SELL" if score <= _SELL_THRESHOLD
        else "HOLD"
    )

    breakdown = []
    for axis in AXES:
        v = values[axis]
        effective_weight = weights.get(axis, 0.0) / total_weight if axis in available else 0.0
        breakdown.append(
            {
                "axis": axis,
                "weight": round(weights.get(axis, 0.0), 3),
                # Das tatsaechlich wirksame Gewicht. Es wurde bisher nur intern
                # fuer `contribution` benutzt und nicht ausgeliefert — die
                # Oberflaeche zeigte deshalb neben einer nicht verfuegbaren
                # Achse weiter deren konfiguriertes Gewicht, waehrend die
                # Ueberschrift "alle Quellen gewichtet" behauptete. Genau die
                # stille Umverteilung, die der Zielkatalog in TBV2-Z01
                # ausschliesst. Jetzt kann die Karte 0 % ausweisen.
                "effectiveWeight": round(effective_weight, 3),
                "value": round(v, 3) if v is not None else None,
                "contribution": round(effective_weight * v, 3) if v is not None else None,
                "available": v is not None,
            }
        )

    # Abdeckung: welcher Anteil des vorgesehenen Signalgewichts stand
    # tatsaechlich zur Verfuegung. Bei Krypto fallen `fundamentals` und
    # `analyst` aus, das Urteil ruht dann auf 55 % des geplanten Gewichts.
    configured_weight = sum(max(0.0, weights.get(axis, 0.0)) for axis in AXES)
    coverage = total_weight / configured_weight if configured_weight > 0 else 0.0
    coverage = _clamp(coverage, 0.0, 1.0)

    return {
        "score": round(score, 3),
        "verdict": verdict,
        # Die Ueberzeugung wird an der Abdeckung gedaempft. Vorher trug ein
        # Urteil aus zwei von vier Achsen dieselbe Zahl wie ein vollstaendig
        # belegtes — die Anzeige behauptete eine Sicherheit, die die Datenlage
        # nicht hergab. Fuer das Risiko-Gate der Automatik
        # (`min_composite_confidence`) wirkt das strenger, nie lockerer.
        "confidence": round(abs(score) * coverage, 3),
        # Ungedaempft weiter mitgeliefert, damit die Herkunft der Zahl
        # nachvollziehbar bleibt (Erklaerbarkeit, TBV2-Z06).
        "rawConfidence": round(abs(score), 3),
        "coverage": round(coverage, 3),
        "axesAvailable": len(available),
        "axesTotal": len(AXES),
        "breakdown": breakdown,
    }
