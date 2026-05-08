"""Options-flow snapshot from yfinance.

For US-listed equities, yfinance exposes the full option chain via
`Ticker.options` (list of expiry strings) and `Ticker.option_chain(expiry)`
(returns a `(calls, puts)` namedtuple of DataFrames). We pull the
nearest expiry at least 7 days out and aggregate:

- Put/Call volume ratio (today's traded contracts)
- Put/Call open-interest ratio (current open contracts)
- Average implied volatility ATM (strikes within ±5% of last close)
- Top-3 strikes per side ranked by volume

Crypto, ETFs without listed options, and ticker probes that fail are
all handled defensively — the caller gets an empty-but-shaped payload
so the UI can render "no options data" without branching.
"""
from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any

import pandas as pd
import yfinance as yf

from app.asset_metadata import to_yfinance_symbol
from app.rate_limit import acquire as acquire_rate_limit

logger = logging.getLogger(__name__)

OPTIONS_FLOW_CACHE_TTL_SECONDS = 60 * 60
MIN_DAYS_TO_EXPIRY = 7
ATM_BAND_PCT = 0.05  # ±5% around last close defines "near-the-money"


class OptionsFlowService:
    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def get_options_flow(
        self, symbol: str, *, asset_class: str | None = None
    ) -> dict[str, Any]:
        """Return a single-expiry options snapshot for the symbol.

        Returns the empty payload (everything `None` / empty list) when
        no usable chain is available — never raises into the request
        path.
        """
        empty = _empty_payload(symbol)
        if not symbol:
            return empty
        if (asset_class or "").lower() == "crypto":
            return empty

        cache_key = symbol.upper()
        cached = self._cache.get(cache_key)
        if cached and cached["expires_at"] > monotonic():
            return deepcopy(cached["value"])

        if not acquire_rate_limit("yfinance", timeout=2.0):
            logger.warning("options_flow_yfinance_rate_limit_skip symbol=%s", symbol)
            return empty

        try:
            ticker = yf.Ticker(to_yfinance_symbol(symbol))
        except Exception:
            logger.exception("options_flow_ticker_failed symbol=%s", symbol)
            return empty

        try:
            expiries: list[str] = list(ticker.options or [])
        except Exception:
            logger.exception("options_flow_expiries_failed symbol=%s", symbol)
            return empty
        if not expiries:
            return self._cache_and_return(cache_key, empty)

        chosen_expiry = _select_expiry(expiries)
        if chosen_expiry is None:
            return self._cache_and_return(cache_key, empty)

        try:
            chain = ticker.option_chain(chosen_expiry)
        except Exception:
            logger.exception(
                "options_flow_chain_failed symbol=%s expiry=%s", symbol, chosen_expiry
            )
            return self._cache_and_return(cache_key, empty)

        calls = _safe_dataframe(getattr(chain, "calls", None))
        puts = _safe_dataframe(getattr(chain, "puts", None))
        if calls.empty and puts.empty:
            return self._cache_and_return(cache_key, empty)

        last_close = _resolve_last_close(ticker)
        snapshot = _build_snapshot(
            symbol=symbol,
            expiry=chosen_expiry,
            calls=calls,
            puts=puts,
            last_close=last_close,
        )
        return self._cache_and_return(cache_key, snapshot)

    def _cache_and_return(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._cache[key] = {
            "expires_at": monotonic() + OPTIONS_FLOW_CACHE_TTL_SECONDS,
            "value": payload,
        }
        return deepcopy(payload)


def _empty_payload(symbol: str) -> dict[str, Any]:
    return {
        "symbol": (symbol or "").upper(),
        "expiry": None,
        "lastClose": None,
        "putCallVolumeRatio": None,
        "putCallOpenInterestRatio": None,
        "avgImpliedVolatilityAtm": None,
        "atmStrikeWindow": None,
        "totalCallVolume": 0,
        "totalPutVolume": 0,
        "totalCallOpenInterest": 0,
        "totalPutOpenInterest": 0,
        "topCalls": [],
        "topPuts": [],
        "putCallSignal": None,
    }


def _select_expiry(expiries: list[str]) -> str | None:
    """Pick the nearest expiry that is at least `MIN_DAYS_TO_EXPIRY` out.

    Falls back to the closest expiry overall if every listed expiry is
    inside the buffer (rare, only happens around weekly-cycle rollover).
    """
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=MIN_DAYS_TO_EXPIRY)
    parsed: list[tuple[str, datetime]] = []
    for raw in expiries:
        try:
            parsed_date = datetime.fromisoformat(str(raw)[:10])
        except (TypeError, ValueError):
            continue
        parsed.append((raw, parsed_date))
    if not parsed:
        return None
    eligible = [
        (raw, dt) for raw, dt in parsed if dt.date() >= cutoff
    ] or parsed
    return min(eligible, key=lambda pair: pair[1])[0]


def _safe_dataframe(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    return pd.DataFrame()


def _resolve_last_close(ticker: yf.Ticker) -> float | None:
    """Pull the most recent close so we can centre the ATM window."""
    try:
        hist = ticker.history(period="5d")
    except Exception:
        logger.exception("options_flow_last_close_failed")
        return None
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    try:
        return float(hist["Close"].iloc[-1])
    except (TypeError, ValueError):
        return None


def _build_snapshot(
    *,
    symbol: str,
    expiry: str,
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    last_close: float | None,
) -> dict[str, Any]:
    total_call_volume = _safe_sum(calls.get("volume"))
    total_put_volume = _safe_sum(puts.get("volume"))
    total_call_oi = _safe_sum(calls.get("openInterest"))
    total_put_oi = _safe_sum(puts.get("openInterest"))

    pc_volume_ratio = (
        total_put_volume / total_call_volume if total_call_volume > 0 else None
    )
    pc_oi_ratio = (
        total_put_oi / total_call_oi if total_call_oi > 0 else None
    )

    atm_band: tuple[float, float] | None = None
    avg_iv_atm: float | None = None
    if last_close and last_close > 0:
        lower = last_close * (1 - ATM_BAND_PCT)
        upper = last_close * (1 + ATM_BAND_PCT)
        atm_band = (round(lower, 2), round(upper, 2))
        avg_iv_atm = _atm_average_iv(calls, puts, lower, upper)

    return {
        "symbol": symbol.upper(),
        "expiry": expiry,
        "lastClose": round(last_close, 4) if last_close is not None else None,
        "putCallVolumeRatio": round(pc_volume_ratio, 3) if pc_volume_ratio is not None else None,
        "putCallOpenInterestRatio": round(pc_oi_ratio, 3) if pc_oi_ratio is not None else None,
        "avgImpliedVolatilityAtm": round(avg_iv_atm, 4) if avg_iv_atm is not None else None,
        "atmStrikeWindow": atm_band,
        "totalCallVolume": int(total_call_volume),
        "totalPutVolume": int(total_put_volume),
        "totalCallOpenInterest": int(total_call_oi),
        "totalPutOpenInterest": int(total_put_oi),
        "topCalls": _top_strikes(calls, n=3),
        "topPuts": _top_strikes(puts, n=3),
        "putCallSignal": _classify_pc_signal(pc_volume_ratio, pc_oi_ratio),
    }


def _safe_sum(series: Any) -> float:
    if not isinstance(series, pd.Series):
        return 0.0
    try:
        total = series.fillna(0).sum()
    except Exception:
        return 0.0
    try:
        return float(total)
    except (TypeError, ValueError):
        return 0.0


def _atm_average_iv(
    calls: pd.DataFrame, puts: pd.DataFrame, lower: float, upper: float
) -> float | None:
    """Mean implied volatility across both sides within the ATM band."""
    pieces: list[float] = []
    for frame in (calls, puts):
        if frame.empty or "strike" not in frame.columns:
            continue
        if "impliedVolatility" not in frame.columns:
            continue
        mask = (frame["strike"] >= lower) & (frame["strike"] <= upper)
        slice_ = frame.loc[mask, "impliedVolatility"].dropna()
        for value in slice_:
            try:
                pieces.append(float(value))
            except (TypeError, ValueError):
                continue
    if not pieces:
        return None
    return sum(pieces) / len(pieces)


def _top_strikes(frame: pd.DataFrame, *, n: int) -> list[dict[str, Any]]:
    if frame.empty or "strike" not in frame.columns:
        return []
    if "volume" not in frame.columns:
        return []
    sortable = frame.copy()
    sortable["volume"] = sortable["volume"].fillna(0)
    sortable = sortable.sort_values("volume", ascending=False).head(n)
    out: list[dict[str, Any]] = []
    for _, row in sortable.iterrows():
        out.append(
            {
                "strike": _to_float(row.get("strike")),
                "volume": _to_int(row.get("volume")),
                "openInterest": _to_int(row.get("openInterest")),
                "impliedVolatility": _to_float(row.get("impliedVolatility")),
                "lastPrice": _to_float(row.get("lastPrice")),
            }
        )
    return out


def _classify_pc_signal(
    volume_ratio: float | None, oi_ratio: float | None
) -> str | None:
    """Translate ratios into a coarse signal label.

    P/C > 1.2 historically reads as bearish-skewed (more puts in play),
    < 0.7 as bullish-skewed. Anything in between is neutral. We prefer
    the volume ratio (today's flow) and fall back to OI when volume is
    absent.
    """
    ratio = volume_ratio if volume_ratio is not None else oi_ratio
    if ratio is None:
        return None
    if ratio >= 1.2:
        return "bearish_skew"
    if ratio <= 0.7:
        return "bullish_skew"
    return "neutral"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result


def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None


_singleton: OptionsFlowService | None = None


def get_options_flow_service() -> OptionsFlowService:
    global _singleton
    if _singleton is None:
        _singleton = OptionsFlowService()
    return _singleton
