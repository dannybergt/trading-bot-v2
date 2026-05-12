<!-- page: /docs/data-quality -->
# Datenqualitaet und Provider-Transparenz

Buy/Sell-Empfehlungen sind nur so gut wie die Daten, die sie speisen. Die Plattform macht das Datenfundament sichtbar, damit du entscheiden kannst, wie viel Gewicht du einer Empfehlung gibst.

## Per-Symbol Data-Quality-Sektion

Auf jeder `/analysis/<symbol>`-Seite sitzt die Data-Quality-Sektion ganz oben mit zwei Informationen:

- **Overall confidence** — `high` / `medium` / `low`. High = der Grossteil der Datenfelder kam voll von den Primaer-Providern; medium toleriert teilweise Fallbacks; low = die meisten Felder fehlen oder beruhen auf heuristischen Fallbacks.
- **Per-Field-Grid** — jeder Datentyp (Price-History, Fundamentals, Research-Depth, Insider/Institutional, Earnings-Calls, Options-Flow, Macro-Context, …) mit aktueller Confidence und dem Provider, der tatsaechlich geantwortet hat. Dasselbe Overall-Label wird als kleines Badge unter dem ML-Signal gespiegelt, so dass die Empfehlungs-Karte immer neben ihrem Datenfundament steht.

Wenn etwas fehlt oder partial ist, steht das **warum** dabei: z.B. "earnings calls — missing — FMP unconfigured" oder "options flow — partial — yfinance throttled".

## Upgrade-Hints

Wenn ein konfigurierbarer, kostenpflichtiger Provider fehlende Daten fuer das angesehene Symbol freischalten wuerde, listet ein Upgrade-Hint-Block den empfohlenen Tarif mit Kosten und konkretem Nutzen. Beispiele:

- **FMP Starter (14 USD/Monat)** — wenn FMP nicht konfiguriert ist: schaltet Fundamentals-Tiefe, Insider/Institutional-Signale und Earnings-Call-Digest in einem Tarif frei.
- **Alpha Vantage Premium (50 USD/Monat)** — nur relevant, wenn Crypto-Live-Quotes hoehere Throughput als der Free-Tier brauchen.
- **Polygon.io Stocks (29 USD/Monat)** — nur relevant, wenn die Genauigkeit des Options-Flows tatsaechlich Entscheidungen treibt.

Das sind **explizite statische Regeln**, keine opaken Heuristiken — der Regelsatz ist in `app/data_quality_service.py::_build_upgrade_hints` auditierbar.

## Admin Data-Source-Coverage-Matrix

Unter [Admin](/admin) → Data sources wird der vollstaendige Provider-Katalog als Tabelle gerendert: jeder Provider, was er abdeckt, Free-Tier-Limit, empfohlener Upgrade-Tarif, monatliche Kosten und eine Zeile zum Grund, warum der Upgrade sich lohnt. Der Footer zeigt die zusaetzlichen monatlichen Kosten, wenn jedes empfohlene Upgrade fuer aktuell konfigurierte Provider aktiviert wuerde.

## Confidence-Mathematik

Das Overall-Label reduziert die Per-Field-Labels:

- `high`: >= 60 Prozent der Felder sind `full`
- `medium`: >= 60 Prozent der Felder sind `full` + `partial` zusammen
- `low`: alles andere

Diese Schwelle ist bewusst konservativ: wenn weniger als 60 Prozent der Felder voll sind, sollte die Empfehlung mit einem "kleinere Position-Size"-Mindset gelesen werden.

## Wo die Regeln liegen

- Regeln: `src/backend/app/data_quality_service.py` (Per-Field-Confidence, Upgrade-Hints, Provider-Katalog)
- Endpoints: `GET /api/research/{symbol}/data-quality`, `GET /api/admin/data-sources`
- UI: `DataQualitySection` auf `/analysis/<symbol>`, `DataSourcesSection` auf `/admin`
