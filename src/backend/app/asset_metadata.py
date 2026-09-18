from __future__ import annotations

import re
from typing import Any


CRYPTO_QUOTE_CURRENCIES = {"USD", "USDT", "USDC", "EUR", "GBP", "BTC", "ETH"}
ETF_HINT_PATTERNS = ("etf", "exchange traded fund", "index fund", "mutual fund", "fund")
# Die Werte, die `infer_asset_class` ueberhaupt zurueckgeben kann. Eine
# gespeicherte Einstufung wird dagegen gehalten, bevor sie die Heuristik
# ersetzen darf.
KNOWN_ASSET_CLASSES = {"stock", "etf", "crypto"}


def normalize_symbol(symbol: str | None) -> str:
    return (symbol or "").strip().upper()


def canonicalize_symbol(symbol: str | None) -> str:
    normalized = normalize_symbol(symbol)
    if "/" in normalized:
        return normalized

    if "-" in normalized:
        base, quote = normalized.rsplit("-", 1)
        if base and quote in CRYPTO_QUOTE_CURRENCIES:
            return f"{base}/{quote}"

    return normalized


def to_yfinance_symbol(symbol: str | None) -> str:
    return canonicalize_symbol(symbol).replace("/", "-")


# One segment starts and ends alphanumeric (BRK.B, BF-B, 0700, A), a pair is
# two segments around one "/" (BTC/USD). Never ".." or a second "/": the
# symbol ends up in the path of outbound provider requests (FMP), and
# "A/../../v4/x" was steering the operator's key to arbitrary provider
# paths (security-reviewer, 2026-09-18).
_SYMBOL_SEGMENT = r"[A-Z0-9](?:[A-Z0-9.-]{0,22}[A-Z0-9])?"
_SYMBOL_FORM = re.compile(rf"{_SYMBOL_SEGMENT}(?:/{_SYMBOL_SEGMENT})?")


def is_plausible_symbol_query(value: str | None) -> bool:
    normalized = normalize_symbol(value)
    return (
        0 < len(normalized) <= 24
        and ".." not in normalized
        and _SYMBOL_FORM.fullmatch(normalized) is not None
    )


def symbol_looks_like_crypto(symbol: str | None) -> bool:
    canonical = canonicalize_symbol(symbol)
    if "/" in canonical:
        base, quote = canonical.split("/", 1)
        return bool(base) and quote in CRYPTO_QUOTE_CURRENCIES
    return False


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _string_blob(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            parts.extend(str(item) for item in value if item is not None)
            continue
        parts.append(str(value))
    return " ".join(parts).strip().lower()


def infer_asset_class(
    symbol: str,
    asset: dict[str, Any] | None = None,
    ticker_info: dict[str, Any] | None = None,
    fallback_name: str | None = None,
) -> str:
    asset = asset or {}
    ticker_info = ticker_info or {}

    asset_class_raw = _first_non_empty(asset.get("asset_class"), asset.get("class"), "") or ""
    asset_class_raw = asset_class_raw.lower()
    asset_blob = _string_blob(
        asset.get("attributes"),
        asset.get("name"),
        asset.get("type"),
        asset.get("instrument_type"),
        fallback_name,
    )

    if asset_class_raw == "crypto":
        return "crypto"
    if any(pattern in asset_blob for pattern in ETF_HINT_PATTERNS):
        return "etf"
    if asset_class_raw in {"us_equity", "equity", "stock"}:
        return "stock"

    quote_type = (
        _first_non_empty(
            ticker_info.get("quoteType"),
            ticker_info.get("quote_type"),
            ticker_info.get("instrumentType"),
            "",
        )
        or ""
    ).lower()
    info_blob = _string_blob(
        quote_type,
        ticker_info.get("shortName"),
        ticker_info.get("longName"),
        ticker_info.get("category"),
        ticker_info.get("fundFamily"),
    )

    if quote_type in {"cryptocurrency", "crypto"}:
        return "crypto"
    if quote_type in {"etf", "mutualfund", "fund", "etn"}:
        return "etf"
    if quote_type in {"equity", "stock"}:
        return "stock"
    if any(pattern in info_blob for pattern in ETF_HINT_PATTERNS):
        return "etf"
    if symbol_looks_like_crypto(symbol):
        return "crypto"
    return "stock"


def build_asset_profile(
    symbol: str,
    asset: dict[str, Any] | None = None,
    ticker_info: dict[str, Any] | None = None,
    fallback_name: str | None = None,
    known_asset_class: str | None = None,
) -> dict[str, Any]:
    """`known_asset_class` ist eine bereits aufgeloeste und gespeicherte
    Einstufung. Sie schlaegt die Heuristik — genau dafuer wurde sie gespeichert.
    Ein unbekannter Wert wird ignoriert, statt sich durch die Oberflaeche zu
    ziehen: die Klasse kommt aus der Datenbank und ist damit potenziell aelter
    als der Code, der sie interpretiert."""
    asset = asset or {}
    ticker_info = ticker_info or {}

    asset_class = (known_asset_class or "").strip().lower()
    if asset_class not in KNOWN_ASSET_CLASSES:
        asset_class = infer_asset_class(
            symbol,
            asset=asset,
            ticker_info=ticker_info,
            fallback_name=fallback_name,
        )
    market = "crypto" if asset_class == "crypto" else "equity"
    canonical_symbol = canonicalize_symbol(symbol)
    exchange = _first_non_empty(
        asset.get("exchange"),
        ticker_info.get("exchange"),
        ticker_info.get("fullExchangeName"),
    )
    name = _first_non_empty(
        fallback_name,
        asset.get("name"),
        ticker_info.get("shortName"),
        ticker_info.get("longName"),
        canonical_symbol,
    )

    return {
        "symbol": canonical_symbol,
        "name": name or canonical_symbol,
        "assetClass": asset_class,
        "assetLabel": asset_class.capitalize() if asset_class != "etf" else "ETF",
        "market": market,
        "exchange": exchange,
        "type": asset_class.upper(),
        "isCrypto": asset_class == "crypto",
    }
