from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


ALERT_ASSET_FIELDS = (
    "assetClass",
    "assetLabel",
    "market",
    "exchange",
    "type",
    "isCrypto",
    "provider",
)
TAG_PRIORITY_WEIGHTS = {
    "priority": 16,
    "urgent": 18,
    "swing": 8,
    "momentum": 10,
    "breakout": 10,
    "earnings": 8,
    "macro": 6,
    "catalyst": 10,
    "reversal": 6,
}


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_timestamp(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo else raw_value.replace(tzinfo=timezone.utc)
    if isinstance(raw_value, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw_value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(raw_value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _extract_latest_price(analysis_result: dict[str, Any] | None) -> float | None:
    if not isinstance(analysis_result, dict):
        return None

    data = analysis_result.get("data")
    if data is None:
        return None
    try:
        if getattr(data, "empty", True):
            return None
        latest_row = data.iloc[-1]
    except Exception:
        return None
    return _safe_float(latest_row.get("Close"))


def build_signal_snapshot(analysis_result: dict[str, Any] | None) -> dict[str, Any]:
    prediction = {}
    if isinstance(analysis_result, dict) and isinstance(analysis_result.get("prediction"), dict):
        prediction = analysis_result["prediction"]

    direction = str(prediction.get("direction") or "HOLD").upper()
    confidence = max(0.0, min(_safe_float(prediction.get("confidence")) or 0.0, 1.0))
    latest_price = _extract_latest_price(analysis_result)
    expected_yield = _safe_float(prediction.get("expected_yield_pct"))
    required_yield = _safe_float(prediction.get("required_yield_pct"))

    return {
        "direction": direction,
        "confidence": round(confidence, 4),
        "confidencePercent": round(confidence * 100, 1),
        "latestPrice": round(latest_price, 4) if latest_price is not None else None,
        "expectedYieldPct": round(expected_yield, 2) if expected_yield is not None else None,
        "requiredYieldPct": round(required_yield, 2) if required_yield is not None else None,
        "reason": prediction.get("reason"),
    }


def build_news_snapshot(news_payload: dict[str, Any] | None, *, limit: int = 2) -> dict[str, Any]:
    items = news_payload.get("items", []) if isinstance(news_payload, dict) else []
    normalized_items: list[dict[str, Any]] = []
    latest_timestamp: datetime | None = None

    for item in items:
        timestamp = _normalize_timestamp(item.get("timestamp"))
        if latest_timestamp is None or (timestamp and timestamp > latest_timestamp):
            latest_timestamp = timestamp
        normalized_items.append(
            {
                "title": item.get("title"),
                "summary": item.get("summary"),
                "score": round(_safe_float(item.get("score")) or 0.0, 4),
                "label": item.get("label") or "neutral",
                "timestamp": timestamp.isoformat() if timestamp else item.get("timestamp"),
                "url": item.get("url"),
                "source": item.get("source"),
            }
        )

    normalized_items.sort(key=lambda current: current.get("timestamp") or "", reverse=True)
    aggregate_score = _safe_float((news_payload or {}).get("aggregate_score")) or 0.0
    aggregate_label = str((news_payload or {}).get("aggregate_label") or "neutral").lower()

    return {
        "itemCount": len(normalized_items),
        "aggregateScore": round(aggregate_score, 4),
        "aggregateLabel": aggregate_label,
        "latestTimestamp": latest_timestamp.isoformat() if latest_timestamp else None,
        "headlines": normalized_items[:limit],
    }


def _round_optional_float(value: Any, digits: int = 2) -> float | None:
    numeric = _safe_float(value)
    return round(numeric, digits) if numeric is not None else None


def _first_provider_entry(entries: Any, *, label_key: str) -> dict[str, Any] | None:
    if not isinstance(entries, list) or not entries:
        return None
    entry = entries[0]
    if not isinstance(entry, dict):
        return None

    label_value = entry.get(label_key)
    if not label_value:
        return None

    payload = {
        label_key: label_value,
        "weightPercent": _round_optional_float(entry.get("weightPercent")),
    }
    if entry.get("symbol"):
        payload["symbol"] = entry.get("symbol")
    if entry.get("name"):
        payload["name"] = entry.get("name")
    return payload


def build_provider_context(provider: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(provider, dict):
        return {
            "status": "unavailable",
            "source": None,
            "assetClass": None,
            "lastUpdated": None,
            "price": None,
            "changePercent": None,
            "currency": None,
            "historyPoints": 0,
            "researchAvailable": False,
            "topHolding": None,
            "topSector": None,
            "expenseRatio": None,
            "dividendYield": None,
            "netAssets": None,
        }

    quote = provider.get("quote") if isinstance(provider.get("quote"), dict) else {}
    research = provider.get("research") if isinstance(provider.get("research"), dict) else {}
    top_holding = _first_provider_entry(research.get("topHoldings"), label_key="symbol")
    top_sector = _first_provider_entry(research.get("topSectors"), label_key="sector")
    expense_ratio = _round_optional_float(research.get("expenseRatio"))
    dividend_yield = _round_optional_float(research.get("dividendYield"))
    net_assets = _round_optional_float(research.get("netAssets"), digits=0)
    research_available = any(
        value is not None
        for value in (top_holding, top_sector, expense_ratio, dividend_yield, net_assets, research.get("inceptionDate"))
    )

    return {
        "status": provider.get("status") or "unavailable",
        "source": provider.get("source"),
        "assetClass": provider.get("assetClass"),
        "lastUpdated": provider.get("lastUpdated"),
        "price": _round_optional_float(quote.get("price"), digits=4),
        "changePercent": _round_optional_float(quote.get("changePercent")),
        "currency": quote.get("currency"),
        "historyPoints": len(quote.get("history") or []) if isinstance(quote.get("history"), list) else 0,
        "researchAvailable": research_available,
        "topHolding": top_holding,
        "topSector": top_sector,
        "expenseRatio": expense_ratio,
        "dividendYield": dividend_yield,
        "netAssets": net_assets,
    }


def _collect_tag_matches(tags: list[str]) -> tuple[int, list[str]]:
    score = 0
    matches: list[str] = []
    for tag in sorted({str(tag).strip().lower() for tag in tags if str(tag).strip()}):
        weight = TAG_PRIORITY_WEIGHTS.get(tag)
        if not weight:
            continue
        score += weight
        matches.append(f"tag:{tag}")
    return min(score, 24), matches


def _collect_signal_matches(signal: dict[str, Any]) -> tuple[int, list[str]]:
    direction = signal.get("direction")
    confidence = _safe_float(signal.get("confidence")) or 0.0
    expected_yield = _safe_float(signal.get("expectedYieldPct"))
    required_yield = _safe_float(signal.get("requiredYieldPct"))
    matches: list[str] = []

    if direction in {"UP", "DOWN"}:
        score = 20 + round(confidence * 35)
        matches.append("buy-signal" if direction == "UP" else "sell-signal")
        if confidence >= 0.8:
            score += 8
            matches.append("high-confidence")
        elif confidence >= 0.65:
            score += 4
            matches.append("confirmed-signal")

        if (
            direction == "UP"
            and expected_yield is not None
            and required_yield is not None
            and expected_yield >= required_yield
        ):
            score += 6
            matches.append("yield-cleared")
        return score, matches

    if confidence >= 0.5:
        return 10, ["watch-signal"]
    return 4, matches


def _collect_news_matches(signal: dict[str, Any], news: dict[str, Any]) -> tuple[int, list[str]]:
    item_count = int(news.get("itemCount") or 0)
    label = news.get("aggregateLabel") or "neutral"
    score = _safe_float(news.get("aggregateScore")) or 0.0
    direction = signal.get("direction")
    matches: list[str] = []
    total = min(item_count * 2, 8)

    if item_count and label != "neutral":
        if (direction == "UP" and label == "bullish") or (direction == "DOWN" and label == "bearish"):
            total += 15
            matches.append("news-support")
        elif direction in {"UP", "DOWN"}:
            total -= 10
            matches.append("news-conflict")
        else:
            total += 10
            matches.append(f"{label}-news")

        total += min(int(abs(score) * 10), 4)

    latest_timestamp = _normalize_timestamp(news.get("latestTimestamp"))
    if latest_timestamp:
        age_hours = (datetime.now(timezone.utc) - latest_timestamp).total_seconds() / 3600
        if age_hours <= 6:
            total += 8
            matches.append("fresh-news")
        elif age_hours <= 24:
            total += 4
            matches.append("recent-news")

    return total, matches


def _collect_provider_matches(provider_context: dict[str, Any]) -> tuple[int, list[str]]:
    status = provider_context.get("status")
    change_percent = _safe_float(provider_context.get("changePercent"))
    history_points = int(provider_context.get("historyPoints") or 0)
    matches: list[str] = []
    total = 0

    if status == "live":
        total += 7
        matches.append("provider-live")
    elif status == "partial":
        total += 4
        matches.append("provider-partial")

    if change_percent is not None:
        if abs(change_percent) >= 2:
            total += 10
            matches.append("provider-move")
        elif abs(change_percent) >= 0.5:
            total += 5
            matches.append("provider-active")

    if provider_context.get("researchAvailable"):
        total += 5
        matches.append("provider-research")

    if history_points >= 10:
        total += 3
        matches.append("provider-history")

    return min(total, 20), matches


def classify_priority(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def pick_alert_type(signal: dict[str, Any], news: dict[str, Any], tags: list[str]) -> str:
    direction = signal.get("direction")
    confidence = _safe_float(signal.get("confidence")) or 0.0
    news_label = news.get("aggregateLabel")
    if direction in {"UP", "DOWN"} and confidence >= 0.75:
        return "signal"
    if news.get("itemCount") and news_label in {"bullish", "bearish"}:
        return "news"
    if tags:
        return "watchlist"
    return "watch"


def build_watchlist_alert(
    tracked_asset: dict[str, Any],
    analysis_result: dict[str, Any] | None,
    news_payload: dict[str, Any] | None,
    *,
    news_limit: int = 2,
) -> dict[str, Any]:
    tags = list(tracked_asset.get("tags") or [])
    signal = build_signal_snapshot(analysis_result)
    news = build_news_snapshot(news_payload, limit=news_limit)
    provider_context = build_provider_context(tracked_asset.get("provider"))

    priority_score = 10
    matches: list[str] = []

    signal_score, signal_matches = _collect_signal_matches(signal)
    priority_score += signal_score
    matches.extend(signal_matches)

    news_score, news_matches = _collect_news_matches(signal, news)
    priority_score += news_score
    matches.extend(news_matches)

    tag_score, tag_matches = _collect_tag_matches(tags)
    priority_score += tag_score
    matches.extend(tag_matches)

    provider_score, provider_matches = _collect_provider_matches(provider_context)
    priority_score += provider_score
    matches.extend(provider_matches)

    priority_score = max(0, min(priority_score, 100))
    priority_label = classify_priority(priority_score)

    return {
        "symbol": tracked_asset["symbol"],
        "name": tracked_asset["name"],
        "tags": tags,
        **{field: tracked_asset.get(field) for field in ALERT_ASSET_FIELDS},
        "priorityScore": priority_score,
        "priorityLabel": priority_label,
        "alertType": pick_alert_type(signal, news, tags),
        "matches": matches,
        "signal": signal,
        "news": news,
        "providerContext": provider_context,
    }


def summarize_watchlist_alerts(items: list[dict[str, Any]]) -> dict[str, Any]:
    provider_items = [item for item in items if item.get("providerContext", {}).get("source")]
    return {
        "alertItems": len(items),
        "highPriority": sum(1 for item in items if item.get("priorityLabel") == "high"),
        "mediumPriority": sum(1 for item in items if item.get("priorityLabel") == "medium"),
        "lowPriority": sum(1 for item in items if item.get("priorityLabel") == "low"),
        "signalAlerts": sum(1 for item in items if item.get("alertType") == "signal"),
        "newsAlerts": sum(1 for item in items if item.get("alertType") == "news"),
        "buySignals": sum(1 for item in items if item.get("signal", {}).get("direction") == "UP"),
        "sellSignals": sum(1 for item in items if item.get("signal", {}).get("direction") == "DOWN"),
        "providerLive": sum(1 for item in provider_items if item.get("providerContext", {}).get("status") == "live"),
        "providerPartial": sum(
            1 for item in provider_items if item.get("providerContext", {}).get("status") == "partial"
        ),
        "providerUnavailable": sum(
            1 for item in provider_items if item.get("providerContext", {}).get("status") == "unavailable"
        ),
        "providerResearch": sum(1 for item in provider_items if item.get("providerContext", {}).get("researchAvailable")),
        "providerMovers": sum(
            1
            for item in provider_items
            if abs(_safe_float(item.get("providerContext", {}).get("changePercent")) or 0.0) >= 1
        ),
    }
