"""Financial Modeling Prep adapter for stock fundamentals, ratios, ETF holdings,
and news.

Lives alongside the existing yfinance and Alpha Vantage providers. The
service is intentionally narrow: every method returns dict/list/None and
swallows transport errors with structured logging. Callers in
`MarketDataService` chain providers and treat empty results as "skip this
source, try the next."

All outbound calls go through the shared rate limiter
(`app.rate_limit.acquire("fmp")`) so the FMP key budget stays predictable
even when scanner, alerts, and analysis paths fire concurrently.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from app.rate_limit import acquire as acquire_rate_limit

logger = logging.getLogger(__name__)

FMP_BASE_URL_V3 = "https://financialmodelingprep.com/api/v3"
FMP_BASE_URL_V4 = "https://financialmodelingprep.com/api/v4"
# Backwards-compatible alias for callers that still reference the v3 default.
FMP_BASE_URL = FMP_BASE_URL_V3
DEFAULT_TIMEOUT_SECONDS = 12.0


class FmpService:
    """Wraps FMP REST endpoints used by the trading-bot-v2 backend."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("FMP_API_KEY", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _request(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        version: str = "v3",
    ) -> Any:
        if not self.configured:
            return None
        if not acquire_rate_limit("fmp", timeout=8.0):
            logger.warning("fmp_rate_limit_skip path=%s", path)
            return None
        merged = {"apikey": self.api_key}
        if params:
            merged.update(params)
        base_url = FMP_BASE_URL_V4 if version == "v4" else FMP_BASE_URL_V3
        url = f"{base_url}{path}"
        try:
            response = requests.get(url, params=merged, timeout=DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            logger.warning(
                "fmp_http_error path=%s status=%s",
                path,
                exc.response.status_code if exc.response is not None else "n/a",
            )
            return None
        except requests.RequestException:
            logger.exception("fmp_request_failed path=%s", path)
            return None
        except ValueError:
            logger.exception("fmp_invalid_json path=%s", path)
            return None

    def get_profile(self, symbol: str) -> dict[str, Any] | None:
        if not symbol:
            return None
        payload = self._request(f"/profile/{symbol.upper()}")
        if isinstance(payload, list) and payload:
            return payload[0]
        return None

    def get_key_metrics(self, symbol: str) -> dict[str, Any] | None:
        if not symbol:
            return None
        payload = self._request(f"/key-metrics/{symbol.upper()}", params={"limit": 1})
        if isinstance(payload, list) and payload:
            return payload[0]
        return None

    def get_ratios(self, symbol: str) -> dict[str, Any] | None:
        if not symbol:
            return None
        payload = self._request(f"/ratios/{symbol.upper()}", params={"limit": 1})
        if isinstance(payload, list) and payload:
            return payload[0]
        return None

    def get_etf_holdings(self, symbol: str) -> list[dict[str, Any]]:
        if not symbol:
            return []
        payload = self._request(f"/etf-holder/{symbol.upper()}")
        if isinstance(payload, list):
            return payload
        return []

    def get_dividends(self, symbol: str) -> list[dict[str, Any]]:
        """Recent dividend history for the symbol.

        FMP returns the payload nested as `{"symbol": ..., "historical": [...]}`
        on this endpoint; we unwrap and return only the inner list so callers
        get a uniform list-of-events shape.
        """
        if not symbol:
            return []
        payload = self._request(f"/historical-price-full/stock_dividend/{symbol.upper()}")
        if isinstance(payload, dict):
            historical = payload.get("historical")
            if isinstance(historical, list):
                return historical
        if isinstance(payload, list):
            return payload
        return []

    def get_splits(self, symbol: str) -> list[dict[str, Any]]:
        """Recent stock-split history for the symbol."""
        if not symbol:
            return []
        payload = self._request(f"/historical-price-full/stock_split/{symbol.upper()}")
        if isinstance(payload, dict):
            historical = payload.get("historical")
            if isinstance(historical, list):
                return historical
        if isinstance(payload, list):
            return payload
        return []

    def get_earnings(self, symbol: str, *, limit: int = 12) -> list[dict[str, Any]]:
        """Past earnings reports with EPS actual/estimate. FMP free tier
        coverage varies; an empty list is a normal "no data" signal."""
        if not symbol:
            return []
        payload = self._request(
            f"/historical/earning_calendar/{symbol.upper()}",
            params={"limit": max(1, min(limit, 50))},
        )
        if isinstance(payload, list):
            return payload
        return []

    def get_cash_flow(self, symbol: str, *, period: str = "annual", limit: int = 4) -> list[dict[str, Any]]:
        """Recent cash-flow statements for the symbol."""
        if not symbol:
            return []
        payload = self._request(
            f"/cash-flow-statement/{symbol.upper()}",
            params={"period": period, "limit": max(1, min(limit, 12))},
        )
        return payload if isinstance(payload, list) else []

    def get_balance_sheet(self, symbol: str, *, period: str = "annual", limit: int = 4) -> list[dict[str, Any]]:
        """Recent balance-sheet statements (debt + equity highlights)."""
        if not symbol:
            return []
        payload = self._request(
            f"/balance-sheet-statement/{symbol.upper()}",
            params={"period": period, "limit": max(1, min(limit, 12))},
        )
        return payload if isinstance(payload, list) else []

    def get_rating(self, symbol: str) -> dict[str, Any] | None:
        """Latest aggregate analyst rating snapshot for the symbol."""
        if not symbol:
            return None
        payload = self._request(f"/rating/{symbol.upper()}")
        if isinstance(payload, list) and payload:
            return payload[0]
        return None

    def get_analyst_estimates(self, symbol: str, *, period: str = "annual", limit: int = 4) -> list[dict[str, Any]]:
        """Forward analyst estimates (revenue + EPS guidance)."""
        if not symbol:
            return []
        payload = self._request(
            f"/analyst-estimates/{symbol.upper()}",
            params={"period": period, "limit": max(1, min(limit, 12))},
        )
        return payload if isinstance(payload, list) else []

    def normalized_research_depth(self, symbol: str) -> dict[str, Any]:
        """Bundle the deeper fundamentals (cashflow, debt highlights, rating,
        forward estimates) into a single payload for /api/research extension.
        """
        cashflow_raw = self.get_cash_flow(symbol)
        balance_raw = self.get_balance_sheet(symbol)
        rating_raw = self.get_rating(symbol)
        estimates_raw = self.get_analyst_estimates(symbol)

        cashflow = []
        for row in cashflow_raw[:6]:
            if not isinstance(row, dict):
                continue
            cashflow.append({
                "date": row.get("date"),
                "operatingCashFlow": row.get("operatingCashFlow"),
                "capitalExpenditure": row.get("capitalExpenditure"),
                "freeCashFlow": row.get("freeCashFlow"),
                "netCashUsedForInvestingActivities": row.get("netCashUsedForInvestingActivites")
                    or row.get("netCashUsedForInvestingActivities"),
                "netCashUsedProvidedByFinancingActivities": row.get(
                    "netCashUsedProvidedByFinancingActivities"
                ),
            })

        debt = []
        for row in balance_raw[:6]:
            if not isinstance(row, dict):
                continue
            debt.append({
                "date": row.get("date"),
                "totalDebt": row.get("totalDebt"),
                "longTermDebt": row.get("longTermDebt"),
                "shortTermDebt": row.get("shortTermDebt"),
                "totalEquity": row.get("totalStockholdersEquity") or row.get("totalEquity"),
                "cashAndShortTermInvestments": row.get("cashAndShortTermInvestments"),
                "netDebt": row.get("netDebt"),
            })

        rating = None
        if isinstance(rating_raw, dict):
            rating = {
                "date": rating_raw.get("date"),
                "rating": rating_raw.get("rating"),
                "ratingScore": rating_raw.get("ratingScore"),
                "ratingRecommendation": rating_raw.get("ratingRecommendation"),
                "ratingDetailsDcfRecommendation": rating_raw.get("ratingDetailsDCFRecommendation"),
                "ratingDetailsRoeRecommendation": rating_raw.get("ratingDetailsROERecommendation"),
                "ratingDetailsRoaRecommendation": rating_raw.get("ratingDetailsROARecommendation"),
                "ratingDetailsDeRecommendation": rating_raw.get("ratingDetailsDERecommendation"),
                "ratingDetailsPeRecommendation": rating_raw.get("ratingDetailsPERecommendation"),
                "ratingDetailsPbRecommendation": rating_raw.get("ratingDetailsPBRecommendation"),
            }

        estimates = []
        for row in estimates_raw[:6]:
            if not isinstance(row, dict):
                continue
            estimates.append({
                "date": row.get("date"),
                "estimatedRevenueAvg": row.get("estimatedRevenueAvg"),
                "estimatedRevenueLow": row.get("estimatedRevenueLow"),
                "estimatedRevenueHigh": row.get("estimatedRevenueHigh"),
                "estimatedEpsAvg": row.get("estimatedEpsAvg"),
                "estimatedEpsLow": row.get("estimatedEpsLow"),
                "estimatedEpsHigh": row.get("estimatedEpsHigh"),
                "numberAnalystEstimatedRevenue": row.get("numberAnalystEstimatedRevenue"),
                "numberAnalystsEstimatedEps": row.get("numberAnalystsEstimatedEps"),
            })

        return {
            "cashflow": cashflow,
            "debt": debt,
            "rating": rating,
            "estimates": estimates,
        }

    def get_insider_trades(self, symbol: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """Recent insider transactions (CEO/CFO/director buys + sells).

        FMP serves this on the v4 API, not v3. Empty list = either FMP key
        unconfigured, no insider activity reported, or v4 path 404'd.
        """
        if not symbol:
            return []
        payload = self._request(
            "/insider-trading",
            params={"symbol": symbol.upper(), "limit": max(1, min(limit, 100))},
            version="v4",
        )
        return payload if isinstance(payload, list) else []

    def get_institutional_holdings(self, symbol: str) -> list[dict[str, Any]]:
        """Top institutional holders (Vanguard/BlackRock-style positions)."""
        if not symbol:
            return []
        payload = self._request(f"/institutional-holder/{symbol.upper()}")
        return payload if isinstance(payload, list) else []

    def get_earnings_surprises(self, symbol: str) -> list[dict[str, Any]]:
        """Historical EPS-actual vs EPS-estimate (beat/miss history)."""
        if not symbol:
            return []
        payload = self._request(f"/earnings-surprises/{symbol.upper()}")
        return payload if isinstance(payload, list) else []

    def get_upcoming_earnings(
        self, symbol: str, *, days_ahead: int = 180
    ) -> list[dict[str, Any]]:
        """Upcoming earnings calendar entries for the symbol within `days_ahead`.

        FMP's `/earning_calendar` is a global endpoint — we filter to the
        target symbol on the client. Free-tier window is roughly 90 days;
        we ask for the larger window and let the server clamp.
        """
        if not symbol:
            return []
        today = datetime.now(timezone.utc).date()
        horizon = today + timedelta(days=max(1, min(days_ahead, 365)))
        payload = self._request(
            "/earning_calendar",
            params={"from": today.isoformat(), "to": horizon.isoformat()},
        )
        if not isinstance(payload, list):
            return []
        canonical = symbol.upper()
        return [
            row
            for row in payload
            if isinstance(row, dict)
            and (row.get("symbol") or "").upper() == canonical
        ]

    def normalized_research_signals(self, symbol: str) -> dict[str, Any]:
        """Bundle insider, institutional, surprise and upcoming-earnings into
        one payload for `/api/research/{symbol}` consumption.

        Each block is shaped for direct UI consumption:
        - insiderTrades: latest 20 transactions with buy/sell + qty + value
        - insiderSummary: 90-day net flow (buys vs sells in shares + nominal)
        - institutionalHoldings: top 10 holders sorted by shares
        - earningsSurprises: latest 8 quarters with beat flag + surprise %
        - earningsBeatRate: rolling beat-rate over the available history
        - upcomingEarnings: nearest scheduled earnings event with estimates
        - daysUntilEarnings: integer countdown or None
        """
        insider_raw = self.get_insider_trades(symbol, limit=100)
        institutional_raw = self.get_institutional_holdings(symbol)
        surprises_raw = self.get_earnings_surprises(symbol)
        upcoming_raw = self.get_upcoming_earnings(symbol)

        today = datetime.now(timezone.utc).date()
        cutoff_90d = today - timedelta(days=90)
        insider_buys_90d_shares = 0.0
        insider_sells_90d_shares = 0.0
        insider_net_value_90d = 0.0
        insider_normalized: list[dict[str, Any]] = []

        for row in insider_raw[:20]:
            if not isinstance(row, dict):
                continue
            date_raw = row.get("transactionDate") or row.get("filingDate")
            tx_date = _parse_date(date_raw)
            ttype = str(row.get("transactionType") or "").strip()
            acq_disp = str(row.get("acquistionOrDisposition") or "").strip()
            # FMP encodes purchases as "P-..." and acquisitions as "A"; sales
            # as "S-..." and dispositions as "D". Buys are anything that
            # increased the insider's stake.
            is_buy = ttype.startswith("P") or acq_disp == "A"
            shares = _safe_float(row.get("securitiesTransacted")) or 0.0
            price = _safe_float(row.get("price")) or 0.0
            value = shares * price
            insider_normalized.append(
                {
                    "date": str(date_raw)[:10] if date_raw else None,
                    "type": ttype,
                    "isBuy": is_buy,
                    "name": row.get("reportingName"),
                    "title": row.get("typeOfOwner") or row.get("typeOfRelationship"),
                    "shares": shares,
                    "price": price,
                    "value": round(value, 2),
                }
            )
            if tx_date and tx_date >= cutoff_90d:
                if is_buy:
                    insider_buys_90d_shares += shares
                    insider_net_value_90d += value
                else:
                    insider_sells_90d_shares += shares
                    insider_net_value_90d -= value

        sorted_inst = sorted(
            (r for r in institutional_raw if isinstance(r, dict)),
            key=lambda r: _safe_float(r.get("shares")) or 0.0,
            reverse=True,
        )
        institutional_normalized = []
        for row in sorted_inst[:10]:
            institutional_normalized.append(
                {
                    "holder": row.get("holder"),
                    "shares": _safe_float(row.get("shares")),
                    "weightPct": _safe_float(row.get("weightPercent")),
                    "changeShares": _safe_float(row.get("change")),
                    "dateReported": row.get("dateReported"),
                }
            )

        beats = 0
        misses = 0
        surprises_normalized: list[dict[str, Any]] = []
        for row in surprises_raw[:8]:
            if not isinstance(row, dict):
                continue
            actual = _safe_float(row.get("actualEarningResult"))
            estimated = _safe_float(row.get("estimatedEarning"))
            beat: bool | None = None
            surprise_pct: float | None = None
            if actual is not None and estimated is not None:
                beat = actual >= estimated
                if beat:
                    beats += 1
                else:
                    misses += 1
                if estimated:
                    surprise_pct = (actual - estimated) / abs(estimated) * 100.0
            surprises_normalized.append(
                {
                    "date": row.get("date"),
                    "actual": actual,
                    "estimated": estimated,
                    "beat": beat,
                    "surprisePct": round(surprise_pct, 2) if surprise_pct is not None else None,
                }
            )
        total_observed = beats + misses
        beat_rate = (beats / total_observed) if total_observed > 0 else None

        upcoming_normalized = None
        days_until: int | None = None
        if upcoming_raw:
            nearest = sorted(
                (r for r in upcoming_raw if isinstance(r, dict)),
                key=lambda r: str(r.get("date") or ""),
            )[0]
            ev_date = _parse_date(nearest.get("date"))
            if ev_date:
                days_until = (ev_date - today).days
            upcoming_normalized = {
                "date": str(nearest.get("date") or "")[:10] or None,
                "epsEstimated": _safe_float(nearest.get("epsEstimated")),
                "revenueEstimated": _safe_float(nearest.get("revenueEstimated")),
                "time": nearest.get("time"),
                "fiscalDateEnding": nearest.get("fiscalDateEnding"),
            }

        return {
            "insiderTrades": insider_normalized,
            "insiderSummary": {
                "buys90dShares": round(insider_buys_90d_shares, 2),
                "sells90dShares": round(insider_sells_90d_shares, 2),
                "netValue90d": round(insider_net_value_90d, 2),
            },
            "institutionalHoldings": institutional_normalized,
            "earningsSurprises": surprises_normalized,
            "earningsBeatRate": round(beat_rate, 3) if beat_rate is not None else None,
            "upcomingEarnings": upcoming_normalized,
            "daysUntilEarnings": days_until,
        }

    def get_news(self, symbol: str, *, limit: int = 5) -> list[dict[str, Any]]:
        if not symbol:
            return []
        payload = self._request(
            "/stock_news",
            params={"tickers": symbol.upper(), "limit": max(1, min(limit, 50))},
        )
        if isinstance(payload, list):
            return payload
        return []

    def normalized_ticker_info(self, symbol: str) -> dict[str, Any]:
        """Return a yfinance-compatible subset so MarketDataService can use FMP
        as a drop-in fallback without rewriting downstream consumers.

        Empty dict if FMP is unconfigured, rate-limited, or has no data.
        """
        profile = self.get_profile(symbol) or {}
        metrics = self.get_key_metrics(symbol) or {}
        ratios = self.get_ratios(symbol) or {}
        if not profile and not metrics and not ratios:
            return {}

        info: dict[str, Any] = {
            "shortName": profile.get("companyName") or profile.get("symbol"),
            "longName": profile.get("companyName"),
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "marketCap": profile.get("mktCap"),
            "fiftyTwoWeekHigh": (
                _parse_range_high(profile.get("range")) if profile.get("range") else None
            ),
            "fiftyTwoWeekLow": (
                _parse_range_low(profile.get("range")) if profile.get("range") else None
            ),
            "dividendYield": ratios.get("dividendYielTTM") or ratios.get("dividendYieldTTM"),
            "trailingPE": metrics.get("peRatio") or ratios.get("priceEarningsRatioTTM"),
            "forwardPE": metrics.get("forwardPE"),
            "priceToBook": ratios.get("priceToBookRatioTTM") or metrics.get("pbRatio"),
            "fmp_source": True,
        }
        return {k: v for k, v in info.items() if v is not None}

    def normalized_events(self, symbol: str) -> dict[str, list[dict[str, Any]]]:
        """Aggregate dividends/splits/earnings into a single shape consumed by
        `/api/events/{symbol}`. Each list contains the raw provider rows
        normalized to camelCase keys the frontend expects.
        """
        dividends_raw = self.get_dividends(symbol)
        splits_raw = self.get_splits(symbol)
        earnings_raw = self.get_earnings(symbol)

        dividends = []
        for row in dividends_raw[:60]:
            if not isinstance(row, dict):
                continue
            dividends.append({
                "date": row.get("date"),
                "amount": row.get("dividend") or row.get("adjDividend"),
                "adjAmount": row.get("adjDividend"),
                "recordDate": row.get("recordDate"),
                "paymentDate": row.get("paymentDate"),
                "declarationDate": row.get("declarationDate"),
                "label": row.get("label"),
            })

        splits = []
        for row in splits_raw[:30]:
            if not isinstance(row, dict):
                continue
            splits.append({
                "date": row.get("date"),
                "numerator": row.get("numerator"),
                "denominator": row.get("denominator"),
                "label": row.get("label"),
            })

        earnings = []
        for row in earnings_raw[:30]:
            if not isinstance(row, dict):
                continue
            earnings.append({
                "date": row.get("date"),
                "epsEstimate": row.get("epsEstimated"),
                "epsActual": row.get("eps"),
                "revenueEstimate": row.get("revenueEstimated"),
                "revenueActual": row.get("revenue"),
                "fiscalDateEnding": row.get("fiscalDateEnding"),
                "time": row.get("time"),
                "updatedFromDate": row.get("updatedFromDate"),
            })

        return {
            "dividends": dividends,
            "splits": splits,
            "earnings": earnings,
        }

    def normalized_news_items(self, symbol: str, *, limit: int = 5) -> list[dict[str, Any]]:
        items = self.get_news(symbol, limit=limit)
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "title": item.get("title"),
                    "summary": item.get("text"),
                    "url": item.get("url"),
                    "timestamp": item.get("publishedDate"),
                    "source": item.get("site") or "FMP",
                    "label": None,
                    "score": None,
                }
            )
        return normalized


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _parse_range_high(value: str) -> float | None:
    try:
        parts = [p.strip() for p in str(value).split("-")]
        if len(parts) == 2:
            return float(parts[1])
    except (ValueError, TypeError):
        return None
    return None


def _parse_range_low(value: str) -> float | None:
    try:
        parts = [p.strip() for p in str(value).split("-")]
        if len(parts) == 2:
            return float(parts[0])
    except (ValueError, TypeError):
        return None
    return None
