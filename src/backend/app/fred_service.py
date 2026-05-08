"""FRED (Federal Reserve Economic Data) adapter.

Provides three orthogonal data slices the recommendation layer leans on:
- Treasury yields: 2Y (`DGS2`), 10Y (`DGS10`), and the 10Y-2Y spread (`T10Y2Y`).
  Inverted yield curve is a recession signal the Auto-Execution risk model
  will eventually want to gate on.
- Commodities: WTI crude (`DCOILWTICO`) and London PM Gold fix
  (`GOLDAMGBD228NLBM`). Useful for energy-sector and inflation-hedge context.
- Macro release calendar: nearest scheduled release dates for CPI (release 10),
  Employment Situation/NFP (release 50), and FOMC press releases
  (release 101). Phase 4 Auto-Execution can use these to halt automation
  in the 24h before a major print.

API reference: https://fred.stlouisfed.org/docs/api/fred/
The FRED API requires an `api_key`; without it every method returns an empty
payload (no fallback to scraping). Get a free key at
https://fred.stlouisfed.org/docs/api/api_key.html
"""

from __future__ import annotations

import logging
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any

import requests

from app.rate_limit import acquire as acquire_rate_limit

logger = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred"
DEFAULT_TIMEOUT_SECONDS = 12.0

CALENDAR_CACHE_TTL_SECONDS = 60 * 60  # 1h — release dates change rarely
SERIES_CACHE_TTL_SECONDS = 30 * 60  # 30min — treasury/commodities are daily

TREASURY_SERIES: dict[str, dict[str, str]] = {
    "two": {"id": "DGS2", "label": "U.S. 2Y Treasury yield"},
    "ten": {"id": "DGS10", "label": "U.S. 10Y Treasury yield"},
    "spread": {"id": "T10Y2Y", "label": "10Y minus 2Y Treasury spread"},
}

COMMODITY_SERIES: dict[str, dict[str, str]] = {
    "wti": {"id": "DCOILWTICO", "label": "WTI crude oil ($/barrel)"},
    "gold": {"id": "GOLDAMGBD228NLBM", "label": "Gold London PM fix ($/oz)"},
}

POLICY_SERIES: dict[str, dict[str, str]] = {
    "fedFunds": {"id": "FEDFUNDS", "label": "Effective Federal Funds rate"},
    "cpi": {"id": "CPIAUCSL", "label": "CPI All Urban Consumers (index)"},
    "unemployment": {"id": "UNRATE", "label": "U.S. unemployment rate"},
    "payrolls": {"id": "PAYEMS", "label": "Total nonfarm payrolls (thousands)"},
}

# FRED release IDs that map to the macro events traders care about.
# Verified against https://fred.stlouisfed.org/releases/
RELEASE_CALENDAR: list[dict[str, Any]] = [
    {"id": 10, "name": "CPI", "category": "inflation"},
    {"id": 50, "name": "Employment Situation (NFP)", "category": "labor"},
    {"id": 101, "name": "FOMC press release", "category": "policy"},
    {"id": 53, "name": "GDP", "category": "growth"},
    {"id": 175, "name": "PCE Price Index", "category": "inflation"},
]


class FredService:
    """Wraps the FRED REST API with caching + rate limiting."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("FRED_API_KEY", "")).strip()
        self._series_cache: dict[str, dict[str, Any]] = {}
        self._calendar_cache: dict[str, Any] = {"expires_at": 0.0, "value": None}

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _request(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        if not self.configured:
            return None
        if not acquire_rate_limit("fred", timeout=8.0):
            logger.warning("fred_rate_limit_skip path=%s", path)
            return None
        merged: dict[str, Any] = {"api_key": self.api_key, "file_type": "json"}
        if params:
            merged.update(params)
        url = f"{FRED_BASE_URL}{path}"
        try:
            response = requests.get(url, params=merged, timeout=DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            logger.warning(
                "fred_http_error path=%s status=%s",
                path,
                exc.response.status_code if exc.response is not None else "n/a",
            )
            return None
        except requests.RequestException:
            logger.exception("fred_request_failed path=%s", path)
            return None
        except ValueError:
            logger.exception("fred_invalid_json path=%s", path)
            return None

    def get_series_observations(
        self, series_id: str, *, limit: int = 30
    ) -> list[dict[str, Any]]:
        """Recent observations for a FRED series, newest-first.

        Each entry has `date` (YYYY-MM-DD) and `value` (float) — FRED returns
        `"."` for missing observations; we drop those so callers always get
        usable numerics.
        """
        if not series_id:
            return []
        cache_key = f"obs::{series_id}::{limit}"
        cached = self._series_cache.get(cache_key)
        if cached and cached["expires_at"] > monotonic():
            return deepcopy(cached["value"])

        payload = self._request(
            "/series/observations",
            params={
                "series_id": series_id,
                "limit": max(1, min(limit, 1000)),
                "sort_order": "desc",
            },
        )
        observations = []
        if isinstance(payload, dict):
            for entry in payload.get("observations") or []:
                if not isinstance(entry, dict):
                    continue
                value = entry.get("value")
                if value is None or value == ".":
                    continue
                try:
                    observations.append({"date": entry.get("date"), "value": float(value)})
                except (TypeError, ValueError):
                    continue

        self._series_cache[cache_key] = {
            "expires_at": monotonic() + SERIES_CACHE_TTL_SECONDS,
            "value": observations,
        }
        return deepcopy(observations)

    def get_release_dates(
        self, release_id: int, *, limit: int = 5, include_no_data: bool = True
    ) -> list[str]:
        """Upcoming + recent release dates for a FRED release.

        FRED returns dates ascending by default. We slice forward-looking
        dates plus the most recent past one so the calendar always has at
        least one entry to render.
        """
        if not release_id:
            return []
        payload = self._request(
            f"/release/dates",
            params={
                "release_id": release_id,
                "include_release_dates_with_no_data": "true" if include_no_data else "false",
                "sort_order": "asc",
            },
        )
        if not isinstance(payload, dict):
            return []
        dates = []
        for entry in payload.get("release_dates") or []:
            if not isinstance(entry, dict):
                continue
            value = entry.get("date")
            if value:
                dates.append(str(value))
        if not dates:
            return []
        today_iso = datetime.now(timezone.utc).date().isoformat()
        future = [d for d in dates if d >= today_iso][:limit]
        if not future:
            # Nothing scheduled — return the most recent past date so the
            # calendar still shows what was published last.
            return dates[-1:]
        return future

    def normalized_macro_calendar(self) -> dict[str, Any]:
        """Build the macro calendar payload for `/api/macro/calendar`.

        Best-effort: instruments that fail to fetch surface as None values
        rather than failing the whole payload. Caches the assembled result
        for `CALENDAR_CACHE_TTL_SECONDS` so repeat calls from the dashboard
        and analysis page share one round-trip budget.
        """
        if (
            self._calendar_cache["value"] is not None
            and self._calendar_cache["expires_at"] > monotonic()
        ):
            return deepcopy(self._calendar_cache["value"])

        if not self.configured:
            empty = {
                "configured": False,
                "treasury": {},
                "commodities": {},
                "policy": {},
                "upcomingReleases": [],
                "asOf": datetime.now(timezone.utc).isoformat(),
            }
            self._calendar_cache = {
                "expires_at": monotonic() + CALENDAR_CACHE_TTL_SECONDS,
                "value": empty,
            }
            return deepcopy(empty)

        treasury = {key: self._latest_with_change(spec) for key, spec in TREASURY_SERIES.items()}
        commodities = {key: self._latest_with_change(spec) for key, spec in COMMODITY_SERIES.items()}
        policy = {key: self._latest_with_change(spec) for key, spec in POLICY_SERIES.items()}

        spread_value = (treasury.get("spread") or {}).get("value")
        treasury["spreadInverted"] = bool(spread_value is not None and spread_value < 0)

        today = datetime.now(timezone.utc).date()
        upcoming: list[dict[str, Any]] = []
        for release in RELEASE_CALENDAR:
            dates = self.get_release_dates(int(release["id"]), limit=3)
            for raw_date in dates:
                parsed = _parse_date(raw_date)
                if not parsed:
                    continue
                upcoming.append(
                    {
                        "releaseId": release["id"],
                        "name": release["name"],
                        "category": release["category"],
                        "date": raw_date,
                        "daysUntil": (parsed - today).days,
                    }
                )
        upcoming.sort(key=lambda r: r["date"])

        payload = {
            "configured": True,
            "treasury": treasury,
            "commodities": commodities,
            "policy": policy,
            "upcomingReleases": upcoming[:12],
            "asOf": datetime.now(timezone.utc).isoformat(),
        }
        self._calendar_cache = {
            "expires_at": monotonic() + CALENDAR_CACHE_TTL_SECONDS,
            "value": payload,
        }
        return deepcopy(payload)

    def _latest_with_change(self, spec: dict[str, str]) -> dict[str, Any]:
        observations = self.get_series_observations(spec["id"], limit=5)
        if not observations:
            return {"id": spec["id"], "label": spec["label"], "value": None, "changePct": None, "asOf": None}
        latest = observations[0]
        change_pct: float | None = None
        if len(observations) >= 2:
            prev = observations[1]
            if prev["value"]:
                change_pct = (latest["value"] - prev["value"]) / prev["value"] * 100.0
        return {
            "id": spec["id"],
            "label": spec["label"],
            "value": round(latest["value"], 4),
            "changePct": round(change_pct, 4) if change_pct is not None else None,
            "asOf": latest.get("date"),
        }


_fred_service_singleton: FredService | None = None


def get_fred_service() -> FredService:
    global _fred_service_singleton
    if _fred_service_singleton is None:
        _fred_service_singleton = FredService()
    return _fred_service_singleton


def _parse_date(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None
