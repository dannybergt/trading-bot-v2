"""Herkunft jeder angezeigten Kennzahl: wer hat geantwortet, und wann.

Zielkatalog TBV2-Z06 Lesart (b): jede angezeigte Kennzahl nennt Provider
und Zeitstempel. Diese Datei ist die *eine* Quelle dafuer — die
Analyse-Seite haengt an jeder Kennzahlen-Sektion einen Herkunftshinweis,
der ausschliesslich aus dieser Karte gespeist wird. Kein Provider-Name
wird im Frontend noch einmal von Hand geschrieben; sonst gibt es zwei
Darstellungen derselben Tatsache, die auseinanderlaufen koennen.

Drei Regeln, die hier nicht verhandelbar sind:

1. **Kein erfundener Zeitstempel.** Ein Anbieter, der keinen Stand
   mitliefert, bekommt `asOf=None` und `asOfKind="unknown"` — die
   Oberflaeche sagt dann "Zeitpunkt unbekannt" statt eine Zahl zu
   zeigen, die nichts bedeutet. Ein falscher Zeitstempel ist schlechter
   als kein Zeitstempel (Regel K).
2. **Der Zeitstempel nennt seine Bedeutung.** `asOfKind` unterscheidet
   den Stand der Daten (`data`), den Abrufzeitpunkt (`fetch`) und den
   Trainingszeitpunkt eines Modells (`trained`). Ein Abrufzeitpunkt
   darf nie als Datenstand auftreten — bei einem 30 Minuten alten
   Cache waeren das zwei verschiedene Aussagen.
3. **`available` und die Vertrauensnote widersprechen sich nie.** Was
   die Datenqualitaets-Karte als `full`/`partial` fuehrt, ist hier
   `available=True` und umgekehrt. `tests/test_metric_sources.py`
   haelt beide gegeneinander.

Der Dienst ruft selbst keinen Anbieter auf. Er liest dieselben Payloads,
die die Analyse-Seite ohnehin schon anzeigt.
"""
from __future__ import annotations

from typing import Any

# Bedeutung des Zeitstempels. Steht in jedem Eintrag daneben, damit die
# Oberflaeche das richtige Wort davorschreiben kann.
ASOF_DATA = "data"        # Stand der Daten selbst (letzter Balken, Meldungsdatum, Einreichungsdatum)
ASOF_FETCH = "fetch"      # Zeitpunkt, zu dem wir beim Anbieter geholt haben
ASOF_TRAINED = "trained"  # Zeitpunkt, zu dem ein Modell trainiert wurde
ASOF_UNKNOWN = "unknown"  # Der Anbieter liefert keinen Stand — und wir erfinden keinen

ASOF_KINDS = (ASOF_DATA, ASOF_FETCH, ASOF_TRAINED, ASOF_UNKNOWN)

# Die Kennzahlen-Sektionen der Analyse-Seite, fuer die diese Karte
# zustaendig ist. Jeder Schluessel wird im Frontend genau einmal
# verwendet; `tests/test_metric_sources.py` haelt beide Listen
# gegeneinander, damit weder ein Eintrag ohne Anzeige noch eine Anzeige
# ohne Eintrag entstehen kann.
DISPLAY_SOURCE_KEYS: tuple[str, ...] = (
    "price_history",
    "prediction",
    "composite",
    "analyst_consensus",
    "fundamentals",
    "fundamentals_detail",
    "research_depth",
    "research_signals",
    "earnings_calls",
    "crypto_metrics",
    "social_sentiment",
    "options_flow",
    "sector_context",
    "sec_filings",
    "macro_context",
    "holdings",
    "news",
)


def build_source_map(
    *,
    asset_class: str | None,
    research_payload: dict[str, Any] | None,
    stock_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Herkunftskarte fuer alle Kennzahlen-Sektionen der Analyse-Seite.

    Nimmt dieselben Payloads wie `data_quality_service.evaluate_symbol_data_quality`
    und liefert je Sektion, welcher Anbieter geantwortet hat und auf
    welchen Stand sich die Zahlen beziehen.
    """
    research = research_payload or {}
    stock = stock_payload or {}
    normalized_class = (asset_class or "").lower()

    entries: list[dict[str, Any]] = []

    # --- Kursverlauf: Kopfzeile, Chart, Volume-Profile -------------------
    if stock.get("synthetic"):
        # Synthetische Balken sind kein Anbieter. Die Sektion nennt hier
        # bewusst keine Quelle — der Platzhalter-Hinweis oben auf der
        # Seite sagt bereits, dass die Kurse erfunden sind.
        entries.append(_entry("price_history", provider=None, available=False))
    else:
        bars_as_of = _last_bar_timestamp(stock)
        provider_source = (stock.get("provider") or {}).get("source") if isinstance(stock.get("provider"), dict) else None
        entries.append(
            _entry(
                "price_history",
                provider=provider_source or "yfinance / Alpha Vantage",
                available=bars_as_of is not None,
                as_of=bars_as_of,
                as_of_kind=ASOF_DATA if bars_as_of else ASOF_UNKNOWN,
            )
        )

    # --- Prognose und Composite -----------------------------------------
    prediction = stock.get("prediction") if isinstance(stock.get("prediction"), dict) else {}
    trained_at = prediction.get("modelTrainedAt") if prediction else None
    entries.append(
        _entry(
            "prediction",
            provider="Modell (lokal trainiert)" if prediction else None,
            available=bool(prediction),
            as_of=trained_at,
            as_of_kind=ASOF_TRAINED if trained_at else ASOF_UNKNOWN,
        )
    )

    composite = stock.get("composite") if isinstance(stock.get("composite"), dict) else {}
    composite_as_of = _last_bar_timestamp(stock) if composite else None
    entries.append(
        _entry(
            "composite",
            # Der Composite hat keinen eigenen Anbieter — er ist die
            # gewichtete Verrechnung der Achsen, die auf dieser Seite
            # jeweils ihre eigene Herkunft nennen.
            provider="berechnet aus den Achsen dieser Seite" if composite else None,
            available=bool(composite),
            as_of=composite_as_of,
            as_of_kind=ASOF_DATA if composite_as_of else ASOF_UNKNOWN,
        )
    )

    # --- Alles, was aus der Stammdaten-Kette kommt ------------------------
    # yfinance -> FMP -> Twelve Data. Welches Glied geantwortet hat, steht
    # als `fundamentalsSource` im Research-Payload; ohne diese Angabe
    # nennen wir die Kette statt zu raten.
    chain_source = research.get("fundamentalsSource") or None
    chain_fetched_at = research.get("fundamentalsFetchedAt") or None
    fundamentals = research.get("fundamentals") or {}
    fundamentals_filled = sum(1 for value in fundamentals.values() if value not in (None, 0, ""))
    entries.append(
        _entry(
            "fundamentals",
            provider=chain_source or "yfinance / FMP / Twelve Data",
            available=fundamentals_filled > 0,
            as_of=chain_fetched_at if fundamentals_filled else None,
            as_of_kind=ASOF_FETCH if (chain_fetched_at and fundamentals_filled) else ASOF_UNKNOWN,
        )
    )
    # Die Analystenstimmen stammen aus demselben `ticker_info`-Objekt wie
    # die Stammdaten — gleiche Quelle, gleicher Abrufzeitpunkt.
    entries.append(
        _entry(
            "analyst_consensus",
            provider=chain_source or "yfinance / FMP / Twelve Data",
            available=fundamentals_filled > 0,
            as_of=chain_fetched_at if fundamentals_filled else None,
            as_of_kind=ASOF_FETCH if (chain_fetched_at and fundamentals_filled) else ASOF_UNKNOWN,
        )
    )

    detail = research.get("fundamentalsDetail") or {}
    detail_as_of = detail.get("revenueDate") or detail.get("netIncomeDate") or None
    entries.append(
        _entry(
            "fundamentals_detail",
            provider=("FMP" if detail.get("isin") or detail.get("cusip") else chain_source or "yfinance / FMP") if detail else None,
            available=bool(detail),
            as_of=detail_as_of,
            as_of_kind=ASOF_DATA if detail_as_of else ASOF_UNKNOWN,
        )
    )

    # Der Alpha-Vantage-Schnappschuss selbst hat auf der Analyse-Seite keine
    # eigene Kennzahlen-Sektion; er datiert aber die ETF-Bestaende unten.
    provider_snapshot = research.get("provider") if isinstance(research.get("provider"), dict) else {}

    # --- FMP-Bloecke ------------------------------------------------------
    depth = research.get("researchDepth") or {}
    depth_available = bool(depth.get("rating") or depth.get("estimates") or depth.get("cashflow") or depth.get("debt"))
    depth_as_of = (depth.get("rating") or {}).get("date") if isinstance(depth.get("rating"), dict) else None
    if not depth_as_of:
        depth_as_of = _newest_date(depth.get("cashflow")) or _newest_date(depth.get("debt"))
    entries.append(
        _entry(
            "research_depth",
            provider="FMP" if depth_available else None,
            available=depth_available,
            as_of=depth_as_of,
            as_of_kind=ASOF_DATA if depth_as_of else ASOF_UNKNOWN,
        )
    )

    signals = research.get("researchSignals") or {}
    signals_available = any(
        signals.get(key)
        for key in ("insiderTrades", "institutionalHoldings", "earningsSurprises", "upcomingEarnings")
    )
    signals_as_of = _newest_date(signals.get("insiderTrades"), field="transactionDate") or _newest_date(
        signals.get("earningsSurprises")
    )
    entries.append(
        _entry(
            "research_signals",
            provider="FMP" if signals_available else None,
            available=signals_available,
            as_of=signals_as_of,
            as_of_kind=ASOF_DATA if signals_as_of else ASOF_UNKNOWN,
        )
    )

    calls = research.get("earningsCalls") or []
    calls_as_of = _newest_date(calls)
    entries.append(
        _entry(
            "earnings_calls",
            provider="FMP" if calls else None,
            available=bool(calls),
            as_of=calls_as_of,
            as_of_kind=ASOF_DATA if calls_as_of else ASOF_UNKNOWN,
        )
    )

    filings = research.get("secFilings") or {}
    filing_list = filings.get("filings") or []
    filings_as_of = _newest_date(filing_list)
    entries.append(
        _entry(
            "sec_filings",
            provider="SEC EDGAR ueber FMP" if filing_list else None,
            available=bool(filing_list),
            as_of=filings_as_of,
            as_of_kind=ASOF_DATA if filings_as_of else ASOF_UNKNOWN,
        )
    )

    # --- Krypto -----------------------------------------------------------
    if normalized_class == "crypto":
        crypto = research.get("cryptoMetrics") or {}
        crypto_available = bool(isinstance(crypto, dict) and crypto.get("marketCapUsd"))
        entries.append(
            _entry(
                "crypto_metrics",
                provider="CoinGecko" if crypto_available else None,
                available=crypto_available,
                as_of=crypto.get("lastUpdated") if crypto_available else None,
                as_of_kind=ASOF_DATA if (crypto_available and crypto.get("lastUpdated")) else ASOF_UNKNOWN,
            )
        )

    # --- Retail-Stimmung, Optionen, Sektor --------------------------------
    social = research.get("socialSentiment") or {}
    combined = social.get("combined") or {}
    social_available = bool(combined.get("totalMessages", 0))
    entries.append(
        _entry(
            "social_sentiment",
            provider="StockTwits / Reddit" if social_available else None,
            available=social_available,
            as_of=_newest_social_post(social),
            as_of_kind=ASOF_DATA if _newest_social_post(social) else ASOF_UNKNOWN,
        )
    )

    options = research.get("optionsFlow") or {}
    options_available = bool(options.get("expiry"))
    options_fetched_at = options.get("fetchedAt") if options_available else None
    entries.append(
        _entry(
            "options_flow",
            provider="yfinance (Optionskette)" if options_available else None,
            available=options_available,
            # Die Kette traegt keinen Datenstand — `expiry` liegt in der
            # Zukunft und ist keiner. Genannt wird deshalb der Abruf.
            as_of=options_fetched_at,
            as_of_kind=ASOF_FETCH if options_fetched_at else ASOF_UNKNOWN,
        )
    )

    sector = research.get("sectorContext") or {}
    sector_available = _sector_has_readings(sector)
    sector_fetched_at = sector.get("fetchedAt") if sector_available else None
    entries.append(
        _entry(
            "sector_context",
            provider="yfinance (Sektor-ETF)" if sector_available else None,
            available=sector_available,
            as_of=sector_fetched_at,
            as_of_kind=ASOF_FETCH if sector_fetched_at else ASOF_UNKNOWN,
        )
    )

    # --- Makro ------------------------------------------------------------
    macro = research.get("macroContext") or {}
    macro_as_of = _newest_macro_as_of(macro)
    macro_available = macro_as_of is not None or any(
        (macro.get(instr) or {}).get("value") is not None for instr in ("vix", "yield10y", "dxy")
    )
    entries.append(
        _entry(
            "macro_context",
            provider="yfinance (VIX / 10Y / DXY)" if macro_available else None,
            available=macro_available,
            as_of=macro_as_of,
            as_of_kind=ASOF_DATA if macro_as_of else ASOF_UNKNOWN,
        )
    )

    # --- ETF-Bestaende und Nachrichten ------------------------------------
    holdings = research.get("research") or {}
    holdings_available = bool(isinstance(holdings, dict) and holdings)
    entries.append(
        _entry(
            "holdings",
            provider="Alpha Vantage" if holdings_available else None,
            available=holdings_available,
            as_of=provider_snapshot.get("lastUpdated") if holdings_available else None,
            as_of_kind=ASOF_DATA if (holdings_available and provider_snapshot.get("lastUpdated")) else ASOF_UNKNOWN,
        )
    )

    news = research.get("news") or {}
    news_items = news.get("items") or []
    news_provider_raw = news.get("provider")
    if isinstance(news_provider_raw, dict):
        news_provider = news_provider_raw.get("source") or None
        news_as_of = news_provider_raw.get("lastUpdated") or None
    else:
        news_provider = news_provider_raw if isinstance(news_provider_raw, str) else None
        news_as_of = None
    if not news_as_of:
        news_as_of = _newest_news_timestamp(news_items)
    entries.append(
        _entry(
            "news",
            provider=(news_provider or "Alpaca / FMP / Alpha Vantage") if news_items else None,
            available=bool(news_items),
            as_of=news_as_of if news_items else None,
            as_of_kind=ASOF_DATA if (news_items and news_as_of) else ASOF_UNKNOWN,
        )
    )

    return entries


def _entry(
    key: str,
    *,
    provider: str | None,
    available: bool,
    as_of: str | None = None,
    as_of_kind: str = ASOF_UNKNOWN,
) -> dict[str, Any]:
    """Ein Karten-Eintrag, defensiv normalisiert.

    Ein Zeitstempel ohne Bedeutung und eine Bedeutung ohne Zeitstempel
    sind beide unzulaessig — die Kombination wird hier aufgeloest statt
    im Frontend, damit es nur eine Stelle gibt, an der das passieren kann.
    """
    normalized_as_of = str(as_of).strip() if as_of not in (None, "") else None
    if normalized_as_of is None or as_of_kind not in ASOF_KINDS or as_of_kind == ASOF_UNKNOWN:
        normalized_as_of = None
        as_of_kind = ASOF_UNKNOWN
    return {
        "key": key,
        "provider": provider or None,
        "available": bool(available),
        "asOf": normalized_as_of,
        "asOfKind": as_of_kind,
    }


def _last_bar_timestamp(stock: dict[str, Any]) -> str | None:
    """Datum des juengsten Kursbalkens, in beiden Payload-Formen.

    `service.get_stock_data` liefert den DataFrame unter `data`,
    `GET /api/stock/{symbol}` die serialisierten Kerzen unter
    `chart_data` — dieselbe Falle, die den Grader schon einmal jede
    echte Kursreihe als `missing` bewerten liess.
    """
    # `.index` gibt es auch an einer Liste — dort ist es eine Methode.
    # Ohne diese Unterscheidung stirbt der Zugriff an `len(list.index)`.
    index = getattr(stock.get("data"), "index", None)
    if index is not None and not callable(index):
        try:
            if len(index) > 0:
                return str(index[-1])[:19]
        except (TypeError, IndexError):  # pragma: no cover - exotische Indizes
            pass

    for key in ("data", "chart_data"):
        candles = stock.get(key)
        if isinstance(candles, list) and candles:
            last = candles[-1]
            if isinstance(last, dict):
                value = last.get("date") or last.get("time") or last.get("timestamp")
                return str(value)[:19] if value else None
    return None


def _newest_date(rows: Any, *, field: str = "date") -> str | None:
    """Juengstes Datum einer Liste von Zeilen.

    Bewusst `max` statt "erstes Element": ob eine Anbieterliste absteigend
    sortiert ankommt, ist eine Annahme, die kein Test haelt. Die Werte sind
    ISO-praefixiert (`YYYY-MM-DD...`), damit ist der lexikografische
    Vergleich auch der chronologische.
    """
    if not isinstance(rows, list):
        return None
    values = []
    for row in rows:
        if isinstance(row, dict):
            value = row.get(field) or row.get("date")
            if value:
                values.append(str(value)[:19])
    return max(values) if values else None


def _sector_has_readings(sector: Any) -> bool:
    """Hat der Sektor-Block tatsaechlich Zahlen, oder nur seine Huelle?

    `_empty_payload` fuellt `sectorEtf` bereits, sobald der Sektorname
    passte — auf `sectorEtf` zu pruefen haette jede leere Antwort als
    vorhandene Quelle ausgegeben.
    """
    if not isinstance(sector, dict):
        return False
    correlation = sector.get("correlation") or {}
    if isinstance(correlation, dict) and correlation.get("correlation") is not None:
        return True
    relative = sector.get("relativeStrength") or {}
    if isinstance(relative, dict):
        for block in relative.values():
            if isinstance(block, dict) and any(
                value is not None
                for key, value in block.items()
                if key not in {"peer", "symbol", "peerSymbol"}
            ):
                return True
    return False


def _newest_social_post(social: dict[str, Any]) -> str | None:
    stocktwits = social.get("stocktwits") if isinstance(social.get("stocktwits"), dict) else {}
    posts = stocktwits.get("topPosts") or stocktwits.get("posts") or []
    return _newest_date(posts, field="created")


def _newest_macro_as_of(macro: dict[str, Any]) -> str | None:
    candidates = []
    for instrument in ("vix", "yield10y", "dxy"):
        entry = macro.get(instrument) or {}
        if isinstance(entry, dict) and entry.get("asOf"):
            candidates.append(str(entry["asOf"]))
    return max(candidates) if candidates else None


def _newest_news_timestamp(items: Any) -> str | None:
    if not isinstance(items, list):
        return None
    stamps = [
        str(item.get("timestamp") or item.get("providerPublishTime"))
        for item in items
        if isinstance(item, dict) and (item.get("timestamp") or item.get("providerPublishTime"))
    ]
    return max(stamps) if stamps else None
