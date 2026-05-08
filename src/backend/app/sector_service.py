"""Sector relative strength and benchmark correlation.

Two orthogonal Phase-4-relevant readings:
- Relative strength: how much a symbol has outperformed (or lagged) SPY,
  QQQ, and its sector ETF over 1-/3-/6-month windows. Auto-Execution can
  later weight long ideas toward symbols that lead their sector.
- Correlation + beta vs SPY: classic risk-model inputs. Auto-Execution
  needs beta to translate per-position risk budgets into portfolio-level
  exposure.

Backed by yfinance (free, already used by `MacroService`). Results are
cached per-symbol for 60min so the analysis page, dashboard, and the
eventual risk-model loop share one round-trip budget.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from time import monotonic
from typing import Any

import yfinance as yf

from app.rate_limit import acquire as acquire_rate_limit

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60 * 60  # 1h

PRIMARY_BENCHMARK = "SPY"
SECONDARY_BENCHMARKS: dict[str, str] = {
    "spy": "SPY",
    "qqq": "QQQ",
    "iwm": "IWM",
}

# Sector SPDR ETFs (US-style sector classification).
SECTOR_ETFS: dict[str, str] = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

# Trading-day windows for relative-strength comparisons.
WINDOWS_DAYS: dict[str, int] = {
    "oneMonth": 21,
    "threeMonths": 63,
    "sixMonths": 126,
}

CORRELATION_WINDOW_DAYS = 90


class SectorService:
    """Per-symbol relative-strength and correlation/beta facts."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def get_sector_context(
        self, symbol: str, *, sector: str | None = None
    ) -> dict[str, Any]:
        """Return relative-strength + correlation/beta for `symbol`.

        `sector` (when known from the asset profile) selects the matching
        sector ETF; without it we still compute SPY/QQQ readings.
        """
        if not symbol:
            return _empty_payload(symbol, sector)

        key = f"{symbol.upper()}::{(sector or '').lower()}"
        cached = self._cache.get(key)
        if cached and cached["expires_at"] > monotonic():
            return deepcopy(cached["value"])

        sector_etf = _resolve_sector_etf(sector)
        peers: dict[str, str] = dict(SECONDARY_BENCHMARKS)
        if sector_etf:
            peers["sector"] = sector_etf

        symbol_closes = self._fetch_closes(symbol)
        if not symbol_closes:
            payload = _empty_payload(symbol, sector, sector_etf=sector_etf)
            self._cache[key] = {"expires_at": monotonic() + CACHE_TTL_SECONDS, "value": payload}
            return deepcopy(payload)

        relative = {}
        for peer_key, peer_symbol in peers.items():
            peer_closes = self._fetch_closes(peer_symbol)
            relative[peer_key] = _build_relative_block(peer_symbol, symbol_closes, peer_closes)

        primary_closes = self._fetch_closes(PRIMARY_BENCHMARK)
        correlation_block = _build_correlation_block(
            PRIMARY_BENCHMARK, symbol_closes, primary_closes
        )

        payload = {
            "symbol": symbol.upper(),
            "sector": sector,
            "sectorEtf": sector_etf,
            "relativeStrength": relative,
            "correlation": correlation_block,
        }
        self._cache[key] = {"expires_at": monotonic() + CACHE_TTL_SECONDS, "value": payload}
        return deepcopy(payload)

    def _fetch_closes(self, symbol: str) -> list[float]:
        if not symbol:
            return []
        if not acquire_rate_limit("yfinance", timeout=2.0):
            logger.warning("sector_yfinance_rate_limit_skip symbol=%s", symbol)
            return []
        try:
            hist = yf.Ticker(symbol).history(period="9mo")
            if hist is None or hist.empty or "Close" not in hist.columns:
                return []
            return [float(v) for v in hist["Close"].tolist() if v is not None]
        except Exception:
            logger.exception("sector_history_failed symbol=%s", symbol)
            return []


_sector_service_singleton: SectorService | None = None


def get_sector_service() -> SectorService:
    global _sector_service_singleton
    if _sector_service_singleton is None:
        _sector_service_singleton = SectorService()
    return _sector_service_singleton


def _empty_payload(
    symbol: str, sector: str | None, *, sector_etf: str | None = None
) -> dict[str, Any]:
    relative = {key: _empty_relative_block(peer) for key, peer in SECONDARY_BENCHMARKS.items()}
    if sector_etf:
        relative["sector"] = _empty_relative_block(sector_etf)
    return {
        "symbol": (symbol or "").upper(),
        "sector": sector,
        "sectorEtf": sector_etf,
        "relativeStrength": relative,
        "correlation": {
            "benchmark": PRIMARY_BENCHMARK,
            "windowDays": CORRELATION_WINDOW_DAYS,
            "correlation": None,
            "beta": None,
        },
    }


def _resolve_sector_etf(sector: str | None) -> str | None:
    if not sector:
        return None
    canonical = sector.strip().lower()
    for known, etf in SECTOR_ETFS.items():
        if known.lower() == canonical or known.lower() in canonical or canonical in known.lower():
            return etf
    return None


def _empty_relative_block(peer_symbol: str) -> dict[str, Any]:
    return {
        "peer": peer_symbol,
        "windows": {key: {"symbolReturnPct": None, "peerReturnPct": None, "alphaPct": None} for key in WINDOWS_DAYS},
    }


def _build_relative_block(
    peer_symbol: str, symbol_closes: list[float], peer_closes: list[float]
) -> dict[str, Any]:
    block: dict[str, Any] = {"peer": peer_symbol, "windows": {}}
    for label, days in WINDOWS_DAYS.items():
        symbol_ret = _trailing_return(symbol_closes, days)
        peer_ret = _trailing_return(peer_closes, days)
        alpha = (
            round(symbol_ret - peer_ret, 4)
            if symbol_ret is not None and peer_ret is not None
            else None
        )
        block["windows"][label] = {
            "symbolReturnPct": symbol_ret,
            "peerReturnPct": peer_ret,
            "alphaPct": alpha,
        }
    return block


def _build_correlation_block(
    benchmark: str, symbol_closes: list[float], peer_closes: list[float]
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "benchmark": benchmark,
        "windowDays": CORRELATION_WINDOW_DAYS,
        "correlation": None,
        "beta": None,
    }
    if not symbol_closes or not peer_closes:
        return block
    symbol_returns = _daily_returns(symbol_closes, CORRELATION_WINDOW_DAYS)
    peer_returns = _daily_returns(peer_closes, CORRELATION_WINDOW_DAYS)
    n = min(len(symbol_returns), len(peer_returns))
    if n < 5:
        return block
    symbol_returns = symbol_returns[-n:]
    peer_returns = peer_returns[-n:]
    correlation = _pearson(symbol_returns, peer_returns)
    beta = _beta(symbol_returns, peer_returns)
    if correlation is not None:
        block["correlation"] = round(correlation, 4)
    if beta is not None:
        block["beta"] = round(beta, 4)
    return block


def _trailing_return(closes: list[float], days: int) -> float | None:
    if not closes or days <= 0 or len(closes) < days + 1:
        return None
    end = closes[-1]
    start = closes[-days - 1]
    if not start:
        return None
    return round((end - start) / start * 100.0, 4)


def _daily_returns(closes: list[float], window: int) -> list[float]:
    if len(closes) < 2:
        return []
    series = closes[-(window + 1):] if len(closes) > window + 1 else closes
    returns: list[float] = []
    for prev, current in zip(series[:-1], series[1:]):
        if prev:
            returns.append((current - prev) / prev)
    return returns


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 2:
        return None
    mean_a = _mean(a)
    mean_b = _mean(b)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    denom = (var_a * var_b) ** 0.5
    if denom == 0:
        return None
    return num / denom


def _beta(symbol_returns: list[float], benchmark_returns: list[float]) -> float | None:
    if len(symbol_returns) != len(benchmark_returns) or len(symbol_returns) < 2:
        return None
    mean_s = _mean(symbol_returns)
    mean_b = _mean(benchmark_returns)
    cov = sum((s - mean_s) * (b - mean_b) for s, b in zip(symbol_returns, benchmark_returns))
    var_b = sum((b - mean_b) ** 2 for b in benchmark_returns)
    if var_b == 0:
        return None
    return cov / var_b
