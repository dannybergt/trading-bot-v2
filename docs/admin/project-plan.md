# Projektplan

## Stand 2026-05-07

Aktuell validierter Produkt-Release:

- Git-Tag: `v2026.05.07-1`
- Produkt-Commit: `878fcff` (`Record VAPID hardening publish status`)
- Dokumentationsstand: auf `main` nachgezogen
- Backend-Image: `dbergt/trading-bot-backend:2026.05.07-1`
- Frontend-Image: `dbergt/trading-bot-frontend:2026.05.07-1`
- Upgrade-/Restore-Rehearsal: bestanden
- Deployment-Record: `state/runtime/deployments/deployment-20260507T120020Z.env`

Der aktuelle Stand ist nicht nur gebaut, sondern auch ueber GitHub Actions veroeffentlicht und mit einem isolierten Docker-Hub-Deploy, Upgrade ueber bestehende Daten, PostgreSQL-Dump, App-Snapshot und Restore in einen frischen Stack geprueft.

## Phasenposition

### Phase 0: Plattform und Betrieb

Status: weitgehend abgeschlossen, weiter diszipliniert wiederholen.

Erledigt:

- Docker-Hub-Distribution fuer Backend und Frontend
- GitHub Actions fuer Build, Tests, API-/UI-Regression und Publish
- explizite Release-Tags `v*` mit Docker-Hub-Versionstags
- Docker-Hub-Deploy und Upgrade-Pfad
- Pre-Upgrade-PostgreSQL-Dump und App-Snapshot
- Backup, Export, Import und Restore-Rehearsal
- persistente Runtime-Pfade unter `state/runtime`

Offen:

- jeder neue Release-Tag muss denselben Upgrade-/Restore-Rehearsal-Pfad bestehen

Erledigt seit `v2026.05.07-1`:

- Alembic-basierte DB-Migrationen sind eingefuehrt; `Base.metadata.create_all` ist abgeloest; `init_db` stempelt Pre-Alembic-Deployments automatisch auf head, sodass Bestandsstaende ohne Migrationsbruch upgraden

### Phase 1: Live-Daten, Watchlists, Assetklassen

Status: weitgehend abgeschlossen; Provider-Breite und Rate-Limit-Strategie sind eingebaut, optionale WebSocket-In-App-Zustellung bleibt bewusst spaeter.

Erledigt:

- Assetklassen `stock`, `etf`, `crypto`
- Watchlist-Tags und Watchlist-News-Bindung
- Alpha-Vantage-Pfad fuer ETF-/Krypto-Kontext
- Provider-Coverage im Dashboard
- priorisierte Watchlist-Alerts aus Signal, News, Tags und Provider-Kontext
- persistierte Watchlist-Alert-Settings
- Alert-Management-Panel im Dashboard
- serverseitiger Watchlist-Push-Dispatcher
- deduplizierte Delivery-Historie in `watchlist_alert_deliveries`
- zentraler Token-Bucket-Rate-Limiter (`app/rate_limit.py`) fuer Alpha Vantage, FMP und yfinance
- FMP-Adapter (`app/fmp_service.py`) mit Profil/Key-Metrics/Ratios/ETF-Holdings/News
- `MarketDataService` chained yfinance -> FMP fuer Stocks-Fundamentals und Alpaca-News -> FMP fuer News-Sentiment
- `tests/run-fmp-live-smoke.sh` als FMP-Live-Smoke (analog zum Alpha-Vantage-Smoke)
- produktive Push-/VAPID-Haertung

Offen:

- nutzergebundene In-App-/WebSocket-Zustellung optional nach Push-Haertung

### Phase 2: Analyse und Research

Status: begonnen.

Erledigt:

- `/api/research/{symbol}` fuer Symbol-Research
- Provider-Research-Panel auf `/analysis/<symbol>`
- ETF-/Krypto-Kontext inklusive Quote, History-Abdeckung, Holdings/Research soweit Providerdaten verfuegbar sind

Offen:

- Chart-Overlays und Analyse-Module systematisch erweitern
- Fundamentaldaten, Events, Earnings, Dividenden, Splits und Ratings breiter anbinden
- KI-Erklaerungen und Kauf-/Verkaufszonen nachvollziehbarer machen

### Phase 3: Paper-Trading

Status: noch nicht substanziell gestartet.

Naechste Zielpunkte:

- Order- und Ausfuehrungsmodell fuer Paper-Trading
- Transaktionsjournal
- PnL, Kosten, Slippage und Mindest-Rendite-Filter
- Darstellung von Entries/Exits im Chart

### Phase 4: Live-Trading

Status: bewusst spaeter.

Vorbedingungen:

- Paper-Trading stabil
- Risk-Modell, Limits, Budgetsteuerung und Audit-Logs belastbar
- manuelle Freigabelogik und Not-Aus vorhanden
- Broker-Fehlerpfade und Recovery getestet

## Sicherheitsachsen

Immer mitzudenken:

- keine Secrets in Git, Logs, Exceptions oder Testausgaben
- produktive Secrets ueber `.env.local`, GitHub Actions Secrets oder Zielumgebung
- keine unsicheren Code-Defaults im Produktivbetrieb
- explizite Origins statt Wildcard-CORS
- sensible Audit-Felder nur redigiert oder als Fingerprint loggen
- Admin-Bootstrap nur ueber explizite Env-Werte
- Releases nur nach Build, Unit/Syntax, API-Regression, UI-Regression und Rehearsal als deploybar betrachten

Aktuell wichtigster Security-Block:

- produktive VAPID-Werte in `.env.local` oder der Zielumgebung setzen
- `REQUIRE_VAPID_SECRETS=true` fuer produktive Deployments aktivieren
- `bash tests/run-push-config-smoke.sh` vor produktiven Push-Rollouts ausfuehren; der Smoke validiert nur die Konfiguration und benachrichtigt keine Nutzergeraete

## Architekturachsen

Kurzfristig:

- bestehende FastAPI-Monolith-Struktur stabil halten
- gemeinsame Backend-Logik fuer API und Background-Jobs weiter herausziehen
- Tests immer an neue Persistenz-/Backup-/Import-Flaechen koppeln

Mittelfristig:

- Alembic oder gleichwertige Migrationen einfuehren
- Frontend-Quellstand beschaffen oder kontrolliert neu aufbauen
- Provider-Adapter sauberer trennen
- Background-Jobs mit Telemetrie, Locking und Lifecycle-Guardrails versehen

Langfristig:

- `market-data-service`
- `research-service`
- `analysis-service`
- `portfolio-service`
- `execution-service`
- `backup-service`

Diese Aufteilung ist Zielarchitektur, nicht Sofort-Refactor. Neue Arbeit soll aber so geschnitten werden, dass sie spaeter in diese Grenzen migrierbar bleibt.

## Naechste Prioritaeten

1. Produktive Push-/VAPID-Haertung.
2. DB-Migrationsstrategie fuer PostgreSQL-first einfuehren.
3. Provider- und Live-Datenabdeckung fuer ETF/Krypto/Stocks verbreitern.
4. Frontend-Quellstrategie klaeren.
5. Phase-2-Analyse/Research ausbauen.
6. Danach Paper-Trading als Phase 3 sauber modellieren.

## Entscheidungsregel

Eine Aenderung ist erst fertig, wenn sie:

- fachlich zum Phasenplan passt
- keine bekannten Security-Schulden verschlechtert
- lokal verifiziert ist
- in Backup/Export/Import beruecksichtigt ist, falls sie Persistenz beruehrt
- per GitHub Actions gruen ist, wenn sie gepusht wurde
- fuer Release-Staende den Upgrade-/Restore-Rehearsal-Pfad besteht
