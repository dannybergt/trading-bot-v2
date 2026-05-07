# Product Roadmap

## Zielbild

Vollwertige Trading-Workstation mit moeglichst vollstaendigem Datenbild je Asset (Aktien, ETFs, Fonds, Krypto) und automatisch ausfuehrbarer, wahrscheinlichkeitsbewerteter Buy-/Sell-Empfehlung. Konkrete Eckpunkte:

- Live-Marktdaten fuer Aktien, ETFs, Fonds, Krypto und spaeter Optionen
- klare Trennung und Visualisierung nach Assetklassen
- Watchlists, Scanner, News-Ticker, Popups und Alerts
- technische Analyse mit frei zuschaltbaren Overlays und Indikatoren
- Fundamentaldaten, Bewertungskennzahlen, Holdings und Unternehmensereignisse
- News + Sentiment als gleichberechtigte Signal-Quelle
- KI-gestuetzte Kauf-/Verkaufszonen mit nachvollziehbarer Begruendung (Kategorie- und Feature-Erklaerbarkeit) und expliziten P(UP)/P(DOWN)
- Net-Yield-Gate: Empfehlungen werden nur ausgesprochen, wenn nach Brokergebuehren und Kapitalertragssteuer (`min_target_yield` netto) das nutzergesetzte Minimum erreicht wird; spaeter wird genau dieser Gate die Auto-Execution freischalten
- First-Login-Wizard fuer Pflichtwerte (Broker, Fees, Min-Yield, Steuern, MFA) und Dashboard-Karte mit Konfigurationsfortschritt
- Paper-Trading mit lueckenloser Transaktionshistorie als Vorstufe zum Live-Trading
- Live-Trading mit Budget- und Risikomanagement, Audit-Logs, Not-Aus
- Export, Import, manuelle und geplante Backups
- permanenter Build-/Sync-Pfad Richtung Docker Hub

## Aktueller Standort

Der operative Gesamtplan und der aktuelle Release-Stand sind in `docs/admin/project-plan.md` verankert. Kurzstand am 2026-05-07:

- validierter Release: `v2026.05.07-1` auf Produkt-Commit `878fcff`
- Phase 0 ist operativ weitgehend abgeschlossen und muss fuer jeden Release wiederholt werden
- Phase 1 ist funktional und releasefaehig: Assetklassen, Watchlists, Provider-Kontext, Research, Alert-Management und serverseitiger Push-Dispatcher stehen
- Phase 2 ist begonnen: Symbol-Research und Provider-Research-Panel sind vorhanden
- Phase 3 und Phase 4 bleiben bewusst spaeter, nach Daten-/Security-/Migrationshaertung
- naechster Fokus: DB-Migrationen und Provider-Ausbau; produktive Push-/VAPID-Haertung ist umgesetzt und release-validiert

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
- News + Sentiment-Aggregat als sichtbare Signal-Quelle in der Analyse
- KI-Modul fuer Kauf-/Verkaufszonen inklusive Kategorie-Erklaerbarkeit (Trend, Technical, Volume, News, Fundamentals) und Top-Feature-Beitraegen
- explizite Wahrscheinlichkeiten P(UP) / P(DOWN) plus Risk/Reward
- Net-Yield-Projektion (Gross -> Fees -> Tax -> Net) als Vorstufe der Auto-Trade-Freigabe

### Phase 3: Paper-Trading

- Orders und simulierte Ausfuehrung mit Paper-Geld
- Vollstaendiges chronologisches Trade-Journal: jede ausgeloeste Order wird persistent erfasst (kein Verlust), pro Position absoluter und prozentualer PnL, summierte Gebuehren und Steuerlast, Backup/Export/Import wie alle anderen Persistenz-Tabellen
- Visualisierung von Orders und Exits direkt im Chart
- Net-Yield-Gate aus Phase 2 als Filter: Empfehlung wird nur als Order vorgeschlagen, wenn Netto-Ertrag >= `min_target_yield`
- Plausibilitaetsansicht fuer jede KI-Entscheidung mit Kategorie- und Feature-Erklaerbarkeit

### Phase 4: Live-Trading mit Auto-Execution

- Budgetverwaltung, Positionsgroessenregeln, Exposition und Limits
- Freigabelogik fuer automatisierte Orders mit per-User-Korridor (Asset-Klassen, max. Positionsgroesse, max. Tagesvolumen)
- Auto-Trade-Vorbedingung: Empfehlung MUSS den Phase-2-Net-Yield-Gate bestanden haben UND der Nutzer hat Asset/Strategie freigegeben
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
