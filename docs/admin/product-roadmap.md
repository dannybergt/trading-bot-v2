# Product Roadmap

## Zielbild

Das Produkt soll sich von einem rekonstruierten MVP zu einer vollwertigen Trading-Workstation entwickeln:

- Live-Marktdaten fuer Aktien, ETFs, Fonds, Krypto und spaeter Optionen
- klare Trennung und Visualisierung nach Assetklassen
- Watchlists, Scanner, News-Ticker, Popups und Alerts
- technische Analyse mit frei zuschaltbaren Overlays und Indikatoren
- Fundamentaldaten, Bewertungskennzahlen, Holdings und Unternehmensereignisse
- KI-gestuetzte Kauf-/Verkaufszonen mit nachvollziehbarer Begruendung
- Paper-Trading mit lueckenloser Transaktionshistorie
- spaeter Live-Trading mit Budget- und Risikomanagement
- Export, Import, manuelle und geplante Backups
- permanenter Build-/Sync-Pfad Richtung Docker Hub

## Aktueller Standort

Der operative Gesamtplan und der aktuelle Release-Stand sind in `docs/admin/project-plan.md` verankert. Kurzstand am 2026-05-05:

- validierter Release: `v2026.05.05-1` auf Produkt-Commit `ec48455`
- Phase 0 ist operativ weitgehend abgeschlossen und muss fuer jeden Release wiederholt werden
- Phase 1 ist funktional und releasefaehig: Assetklassen, Watchlists, Provider-Kontext, Research, Alert-Management und serverseitiger Push-Dispatcher stehen
- Phase 2 ist begonnen: Symbol-Research und Provider-Research-Panel sind vorhanden
- Phase 3 und Phase 4 bleiben bewusst spaeter, nach Daten-/Security-/Migrationshaertung
- naechster Fokus: produktive Push-/VAPID-Haertung, danach DB-Migrationen und Provider-Ausbau

## Phasen

### Phase 0: Plattform und Betrieb

- Docker-Hub-Namensstrategie bereinigen
- permanenter Sync-Workflow fuer Backend und Frontend
- Export-/Import-API fuer Nutzerdaten, Watchlists, Settings und Transaktionen
- manuelle Backups, Download-Endpunkte und Restore-Importe
- geschedulte Backups mit Aufbewahrung, Integritaetspruefung und Admin-Historie
- CI fuer Build, Test, Scan, Backup-Test und Publish

### Phase 1: Live-Daten, Watchlists, Assetklassen

- Live-Daten fuer Stocks, ETFs, Krypto und nach Moeglichkeit Fonds/Fund-NAV
- Assetklassen am Symbol markieren und in UI/Farbe/Icon unterscheiden
- vollstaendige Watchlist-Verwaltung mit Sortierung, Tags, Alerts und News-Bindung
- News-Ticker als laufendes Band plus Popup-Signal fuer beobachtete Ticker

### Phase 2: Analyse und Research

- ein-/ausblendbare MAs, EMAs, VWAP, RSI, MACD, Bollinger, ATR, Volumenprofile
- automatische Chartanalyse mit Trend, Support/Resistance, Volatilitaet und Mustern
- Fundamentaldaten als aufklappbare Module im UI
- Earnings, Dividenden, Splits, Guidance, Holdings, Ratios, Cashflow, Debt
- KI-Modul fuer Kauf-/Verkaufszonen inklusive Erklaerung der Entscheidungsbasis

### Phase 3: Paper-Trading

- Orders und simulierte Ausfuehrung mit Paper-Geld
- Transaktionsjournal mit absolutem und prozentualem PnL
- Visualisierung von Orders und Exits direkt im Chart
- Nutzerdefinierte Mindest-Rendite und Kostenfilter
- Plausibilitaetsansicht fuer jede KI-Entscheidung

### Phase 4: Live-Trading

- Budgetverwaltung, Positionsgroessenregeln, Exposition und Limits
- Freigabelogik fuer automatisierte Orders
- Broker- und Order-Failover
- Audit-Logs, Risiko-Dashboard und Not-Aus

## Datenanbieter-Empfehlung

### Empfohlener Kernstack

- Trading und Realtime US Stocks/ETFs/Crypto: Alpaca
- Fundamentals, ETF-/Fund-Holdings, Transcripts und breitere Research-Daten: FMP
- Redundante breite Marktfeeds oder globale Erweiterung: Twelve Data
- News fuer Produktivbetrieb: Alpaca News oder Benzinga direkt

### Warum

- Alpaca deckt Trading, Paper-Trading und Realtime-Marktdaten in einem Stack ab
- FMP deckt genau die Fundamentaldaten und Holdings-Luecken ab, die Alpaca nicht vollstaendig schliesst
- Twelve Data ist ein guter Erweiterungsfeed fuer mehr Maerkte und Indikatoren
- reine NewsAPI-Nutzung ist fuer ein Trading-Produkt meist zu generisch und fuer Produktion teuer

## Architektur-Empfehlung

- `market-data-service`: Realtime und historische Preis-/Quote-/Bar-Feeds
- `research-service`: Fundamentals, Ratings, Holdings, Earnings, News-Enrichment
- `analysis-service`: technische Analyse, Signalerzeugung, Zonenberechnung
- `execution-service`: Paper- und spaeter Live-Trading
- `portfolio-service`: Positionen, PnL, Kosten, Budgets, Historie
- `backup-service`: Exporte, Imports, geplante und manuelle Backups

## Minimaler Betriebsumfang fuer die naechste Umsetzung

1. Datenanbieter festlegen
2. Docker-Hub-Strategie festziehen
3. Export-/Import-/Backup-Domäne implementieren
4. Live-Daten- und Assetklassifizierung in der UI starten
5. Fundamentals- und Analyse-Flaeche nachziehen

## Offene Entscheidungen

- ein Projekt mit zwei Images oder Aufteilung in getrennte `/codex`-Projekte
- zentraler PostgreSQL-Wechsel statt SQLite
- Alpaca-only fuer Marktpreise oder Multi-Provider-Fallback
- News primär via Alpaca/Benzinga oder zusaetzlich generischer News-Aggregator
