"""Data-source transparency.

Surfaces *which* provider answered for *which* data field on a per-
symbol basis, plus an honest confidence label that lets the user know
whether the recommendation rests on full data, a partial fallback, or
nothing at all. Drives the in-app `DataQualitySection` and the admin
provider-coverage matrix.

The service does not call any provider itself — it inspects the
shape of the research/quote/signals payload that the existing
endpoints already produce, plus the per-provider configuration
flags. That keeps it cheap (no extra HTTP) and consistent with what
the user actually sees in the rest of the analysis page.

Upgrade hints are static rules: "if FMP is unconfigured AND symbol
is a US-equity, recommend FMP Starter ($14/mo) for fundamentals
depth and earnings-call coverage." These rules are explicit so the
user can audit why an upgrade is suggested instead of trusting an
opaque heuristic.
"""
from __future__ import annotations

import os
from typing import Any

# Confidence vocabulary.
FULL = "full"          # Live data from the primary provider for this field.
PARTIAL = "partial"    # Data present but from a fallback provider.
FALLBACK = "fallback"  # Heuristic / mock / cached path.
MISSING = "missing"    # No provider produced data; the section will be empty.


# Static catalogue used by the admin coverage matrix and the per-symbol
# upgrade hints. Each entry encodes what the provider covers, the
# tier's free-tier limit, the upgrade tier (if any) and the cost.
PROVIDER_CATALOGUE: list[dict[str, Any]] = [
    {
        "key": "alpaca",
        "label": "Alpaca",
        "covers": ["stock_bars", "crypto_bars", "live_stream", "stock_news", "broker"],
        "freeTierLimit": "IEX feed for stocks; crypto bars unlimited",
        "upgradeTier": "Alpaca SIP feed",
        "upgradeCostUsdMonthly": 9,
        "upgradeBenefit": "Full US-equity SIP-feed instead of IEX-only",
        "envFlag": None,  # Alpaca is configured per user, not globally
    },
    {
        "key": "yfinance",
        "label": "yfinance (Yahoo Finance)",
        "covers": ["stock_bars_fallback", "fundamentals_fallback", "options_flow", "macro_indices"],
        "freeTierLimit": "Unofficial — undocumented limits, occasional 429s",
        "upgradeTier": None,
        "upgradeCostUsdMonthly": 0,
        "upgradeBenefit": "Free, but no SLA. Polygon.io ($29-99/mo) is the documented alternative",
        "envFlag": None,
    },
    {
        "key": "alpha_vantage",
        "label": "Alpha Vantage",
        "covers": ["etf_profile", "etf_history", "crypto_history", "news_sentiment"],
        "freeTierLimit": "5 req/min, 25 req/day",
        "upgradeTier": "Premium",
        "upgradeCostUsdMonthly": 50,
        "upgradeBenefit": "75 req/min, no daily cap — required if multiple users hit ETF/crypto frequently",
        "envFlag": "ALPHA_VANTAGE_API_KEY",
    },
    {
        "key": "fmp",
        "label": "Financial Modeling Prep (FMP)",
        "covers": [
            "profile",
            "key_metrics",
            "ratios",
            "cashflow",
            "balance_sheet",
            "rating",
            "analyst_estimates",
            "insider_trades",
            "institutional_holders",
            "earnings_surprises",
            "earnings_calls",
            "stock_news",
        ],
        "freeTierLimit": "250 req/day",
        "upgradeTier": "Starter",
        "upgradeCostUsdMonthly": 14,
        "upgradeBenefit": "300 req/min lifts the daily cap; covers all twelve FMP-backed fields without throttling",
        "envFlag": "FMP_API_KEY",
    },
    {
        "key": "twelve_data",
        "label": "Twelve Data",
        "covers": ["non_us_fundamentals", "non_us_quote", "non_us_history"],
        "freeTierLimit": "8 req/min, 800 req/day",
        "upgradeTier": "Grow",
        "upgradeCostUsdMonthly": 29,
        "upgradeBenefit": "75 req/min — useful only if many non-US (DE/FR/UK/JP/HK) symbols are tracked",
        "envFlag": "TWELVE_DATA_API_KEY",
    },
    {
        "key": "coingecko",
        "label": "CoinGecko",
        "covers": ["crypto_market_cap", "crypto_volume", "crypto_developer", "crypto_community"],
        "freeTierLimit": "~10-50 req/min without key",
        "upgradeTier": "Pro",
        "upgradeCostUsdMonthly": 129,
        "upgradeBenefit": "Higher limits + dedicated SLA. Only worthwhile when crypto-symbol coverage is the primary use case",
        "envFlag": "COINGECKO_API_KEY",
    },
    {
        "key": "stocktwits",
        "label": "StockTwits",
        "covers": ["retail_sentiment_stream"],
        "freeTierLimit": "Public stream API; conservative without auth",
        "upgradeTier": None,
        "upgradeCostUsdMonthly": 0,
        "upgradeBenefit": "Free public access is sufficient for the news-hub flow",
        "envFlag": None,
    },
    {
        "key": "reddit",
        "label": "Reddit (public search)",
        "covers": ["retail_sentiment_mentions"],
        "freeTierLimit": "60 req/10min without OAuth",
        "upgradeTier": "OAuth",
        "upgradeCostUsdMonthly": 0,
        "upgradeBenefit": "OAuth is free but raises the request cap — wire up REDDIT_CLIENT_ID/SECRET when needed",
        "envFlag": None,
    },
    {
        "key": "rss",
        "label": "RSS feeds (boerse.de, ariva.de, Reuters)",
        "covers": ["news_market_general"],
        "freeTierLimit": "Public, cached 5 min",
        "upgradeTier": None,
        "upgradeCostUsdMonthly": 0,
        "upgradeBenefit": "Configurable via RSS_NEWS_FEEDS",
        "envFlag": None,
    },
    {
        "key": "fear_greed",
        "label": "alternative.me Fear & Greed",
        "covers": ["crypto_sentiment_index"],
        "freeTierLimit": "Public, daily-updated",
        "upgradeTier": None,
        "upgradeCostUsdMonthly": 0,
        "upgradeBenefit": "No paid tier needed",
        "envFlag": None,
    },
    {
        "key": "finbert",
        "label": "FinBERT (premium sentiment)",
        "covers": ["sentiment_premium"],
        "freeTierLimit": "Opt-in via SENTIMENT_PROVIDER=finbert + requirements-finbert.txt",
        "upgradeTier": "Activate",
        "upgradeCostUsdMonthly": 0,
        "upgradeBenefit": "Better financial-news scoring than VADER. Container size grows ~900 MB",
        "envFlag": "SENTIMENT_PROVIDER",
    },
]


def _provider_configured(key: str) -> bool:
    catalogue = {entry["key"]: entry for entry in PROVIDER_CATALOGUE}
    flag = catalogue.get(key, {}).get("envFlag")
    if flag is None:
        # Treat "no flag" as "always configured" (yfinance, RSS, etc.)
        return True
    if flag == "SENTIMENT_PROVIDER":
        return os.getenv(flag, "").lower() == "finbert"
    return bool(os.getenv(flag, "").strip())


def get_provider_catalogue() -> list[dict[str, Any]]:
    """Return the full provider catalogue annotated with current
    configuration state. Used by the admin coverage matrix."""
    out: list[dict[str, Any]] = []
    for entry in PROVIDER_CATALOGUE:
        item = dict(entry)
        item["configured"] = _provider_configured(entry["key"])
        out.append(item)
    return out


def evaluate_symbol_data_quality(
    *,
    symbol: str,
    asset_class: str | None,
    research_payload: dict[str, Any] | None,
    stock_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect the research + stock payloads and produce a per-field
    confidence report.

    `research_payload` is the structure returned by `/api/research/{symbol}`.
    `stock_payload` is what `/api/stock/{symbol}` returns; it carries
    the chart data + ML prediction. We don't call them here — the
    caller passes whatever it already has.
    """
    research = research_payload or {}
    stock = stock_payload or {}

    asset_class_normalized = (asset_class or "").lower()
    fields: list[dict[str, Any]] = []

    # Chart bars
    chart_data = (stock or {}).get("chart_data") or []
    if isinstance(chart_data, list) and len(chart_data) >= 30:
        provider = "Alpaca" if (stock.get("provider") or {}).get("source") == "Alpaca" else "yfinance / Alpha Vantage fallback"
        fields.append(_field("price_history", FULL, provider))
    elif isinstance(chart_data, list) and len(chart_data) > 0:
        fields.append(_field("price_history", PARTIAL, "yfinance / Alpha Vantage fallback"))
    else:
        fields.append(_field("price_history", MISSING, "no provider returned data"))

    # Provider snapshot (Alpha Vantage path for ETF/crypto)
    provider = research.get("provider") if isinstance(research.get("provider"), dict) else {}
    provider_status = provider.get("status") if provider else None
    if asset_class_normalized in {"etf", "crypto"}:
        if provider_status == "live":
            fields.append(_field("provider_quote", FULL, "Alpha Vantage"))
        elif provider_status == "partial":
            fields.append(_field("provider_quote", PARTIAL, "Alpha Vantage"))
        else:
            fields.append(_field("provider_quote", MISSING, "Alpha Vantage not configured"))

    # Fundamentals
    fundamentals = research.get("fundamentals") or {}
    fundamentals_filled = sum(1 for value in fundamentals.values() if value not in (None, 0, ""))
    if fundamentals_filled >= 4:
        fields.append(_field("fundamentals", FULL, _fundamentals_source(fundamentals)))
    elif fundamentals_filled > 0:
        fields.append(_field("fundamentals", PARTIAL, _fundamentals_source(fundamentals)))
    else:
        fields.append(_field("fundamentals", MISSING, "no provider returned fundamentals"))

    # Research depth (FMP)
    depth = research.get("researchDepth") or {}
    if depth.get("rating") and depth.get("estimates"):
        fields.append(_field("research_depth", FULL, "FMP"))
    elif depth.get("rating") or depth.get("estimates") or depth.get("cashflow") or depth.get("debt"):
        fields.append(_field("research_depth", PARTIAL, "FMP"))
    else:
        fields.append(_field("research_depth", MISSING, "FMP unconfigured or out of budget"))

    # Research signals (insider, institutional, earnings)
    signals = research.get("researchSignals") or {}
    if signals.get("insiderTrades") and signals.get("institutionalHoldings"):
        fields.append(_field("research_signals", FULL, "FMP"))
    elif any(signals.get(key) for key in ("insiderTrades", "institutionalHoldings", "earningsSurprises", "upcomingEarnings")):
        fields.append(_field("research_signals", PARTIAL, "FMP"))
    else:
        fields.append(_field("research_signals", MISSING, "FMP unconfigured"))

    # Earnings calls
    calls = research.get("earningsCalls") or []
    if isinstance(calls, list) and len(calls) >= 2:
        fields.append(_field("earnings_calls", FULL, "FMP v4"))
    elif isinstance(calls, list) and len(calls) >= 1:
        fields.append(_field("earnings_calls", PARTIAL, "FMP v4"))
    else:
        fields.append(_field("earnings_calls", MISSING, "FMP unconfigured or no transcripts available"))

    # Crypto metrics
    if asset_class_normalized == "crypto":
        crypto = research.get("cryptoMetrics")
        if isinstance(crypto, dict) and crypto.get("marketCapUsd"):
            fields.append(_field("crypto_metrics", FULL, "CoinGecko"))
        else:
            fields.append(_field("crypto_metrics", MISSING, "CoinGecko unreachable"))

    # Options flow
    options = research.get("optionsFlow") or {}
    if asset_class_normalized in {"stock", "etf"}:
        if options.get("expiry") and (options.get("totalCallVolume") or options.get("totalCallOpenInterest")):
            fields.append(_field("options_flow", FULL, "yfinance"))
        elif options.get("expiry"):
            fields.append(_field("options_flow", PARTIAL, "yfinance"))
        else:
            fields.append(_field("options_flow", MISSING, "no listed options or yfinance throttled"))

    # Social sentiment
    social = research.get("socialSentiment") or {}
    combined = social.get("combined") or {}
    if combined.get("totalMessages", 0) >= 10:
        fields.append(_field("social_sentiment", FULL, "StockTwits + Reddit"))
    elif combined.get("totalMessages", 0) > 0:
        fields.append(_field("social_sentiment", PARTIAL, "StockTwits / Reddit (single source)"))
    else:
        fields.append(_field("social_sentiment", MISSING, "no recent retail chatter"))

    # News
    news = research.get("news") or {}
    news_items = news.get("items") or []
    if isinstance(news_items, list) and len(news_items) >= 3:
        fields.append(_field("news", FULL, news.get("provider") or "Alpaca / FMP / Alpha Vantage"))
    elif isinstance(news_items, list) and len(news_items) > 0:
        fields.append(_field("news", PARTIAL, news.get("provider") or "single news provider"))
    else:
        fields.append(_field("news", MISSING, "no recent news"))

    # Macro context (asset-agnostic, but always present)
    macro = research.get("macroContext") or {}
    macro_filled = sum(1 for instr in ("vix", "yield10y", "dxy") if (macro.get(instr) or {}).get("value") is not None)
    if macro_filled >= 2:
        fields.append(_field("macro_context", FULL, "yfinance"))
    elif macro_filled > 0:
        fields.append(_field("macro_context", PARTIAL, "yfinance partial"))
    else:
        fields.append(_field("macro_context", MISSING, "yfinance unreachable"))

    overall = _overall_confidence(fields)
    upgrades = _build_upgrade_hints(asset_class_normalized, fields)

    return {
        "symbol": symbol,
        "assetClass": asset_class,
        "overall": overall,
        "fields": fields,
        "upgradeHints": upgrades,
    }


def _field(key: str, confidence: str, provider: str) -> dict[str, Any]:
    return {"key": key, "confidence": confidence, "provider": provider}


def _fundamentals_source(fundamentals: dict[str, Any]) -> str:
    # Heuristic: if fields look like the FMP-shaped subset (twelve_data_source / fmp_source flags
    # would have been merged into the dict at MarketDataService level), label accordingly.
    if fundamentals.get("twelve_data_source"):
        return "Twelve Data"
    if fundamentals.get("fmp_source"):
        return "FMP"
    return "yfinance"


def _overall_confidence(fields: list[dict[str, Any]]) -> str:
    """Reduce field-level confidences to a single label.

    - any FULL > 60% of fields → "high"
    - else any combination of FULL+PARTIAL > 60% → "medium"
    - else "low"
    """
    if not fields:
        return "low"
    full = sum(1 for f in fields if f["confidence"] == FULL)
    partial = sum(1 for f in fields if f["confidence"] == PARTIAL)
    total = len(fields)
    if full / total >= 0.6:
        return "high"
    if (full + partial) / total >= 0.6:
        return "medium"
    return "low"


def _build_upgrade_hints(asset_class: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    missing = {f["key"] for f in fields if f["confidence"] == MISSING}
    partial = {f["key"] for f in fields if f["confidence"] == PARTIAL}

    if "research_depth" in missing or "research_signals" in missing or "earnings_calls" in missing:
        if not _provider_configured("fmp"):
            hints.append(
                {
                    "provider": "fmp",
                    "label": "FMP Starter ($14/month)",
                    "reason": "Fundamentals depth, insider/institutional signals, and earnings-call digest are missing because FMP is unconfigured. The Starter tier covers all twelve FMP-backed fields without throttling.",
                }
            )

    if "provider_quote" in missing or "crypto_metrics" in missing:
        if asset_class == "crypto" and not _provider_configured("alpha_vantage"):
            hints.append(
                {
                    "provider": "alpha_vantage",
                    "label": "Alpha Vantage Premium ($50/month)",
                    "reason": "Crypto live quotes need Alpha Vantage. The free tier (5 req/min, 25/day) caps multi-user analysis; Premium unblocks the path.",
                }
            )

    if "options_flow" in missing and asset_class in {"stock", "etf"}:
        hints.append(
            {
                "provider": "polygon",
                "label": "Polygon.io Stocks ($29/month)",
                "reason": "yfinance options-chain access is best-effort and frequently throttled. Polygon Stocks gives a documented OPRA feed with no rate-limit surprises — only worth it if options-flow is decision-relevant.",
            }
        )

    if "social_sentiment" in partial:
        hints.append(
            {
                "provider": "reddit_oauth",
                "label": "Reddit OAuth (free)",
                "reason": "Reddit search.json without OAuth caps at ~60 req/10 min. Wiring REDDIT_CLIENT_ID/SECRET unlocks higher limits and removes occasional throttling.",
            }
        )

    return hints
