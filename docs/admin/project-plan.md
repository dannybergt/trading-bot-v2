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

## Produktvision

Das Tool soll je Asset (Stocks, ETFs, Fonds, Krypto) ein **moeglichst vollstaendiges Datenbild** zeichnen und daraus eine wahrscheinlichkeitsbewertete Buy-/Sell-Empfehlung ableiten, die spaeter automatisch ausfuehrbar ist. Verbindlich:

1. **Signal-Quellen:** jede Empfehlung kombiniert
   - Fundamentaldaten (Sector, Ratios, Earnings, Dividenden, Splits, Cashflow, Debt)
   - News + Sentiment
   - Markttrends (Trend-Indikatoren wie SMA/EMA-Anordnungen, Momentum)
   - Technische Chartanalyse (RSI/MACD/Bollinger/ATR/Stochastic, Volume-Profile, Pattern-Detection, Support/Resistance)
   - KI-Modell mit nachvollziehbarer Erklaerbarkeit (per-Feature und per-Kategorie)
2. **Wahrscheinlichkeitsdarstellung:** jede Vorhersage zeigt P(UP) und P(DOWN) explizit, plus Top-Features und Kategorie-Beitraege.
3. **Net-Yield-Gate:** eine Empfehlung gilt nur als handelbar, wenn der **Netto-Ertrag** nach Round-Trip-Brokergebuehren und Kapitalertragssteuer (`User.capital_gains_tax_bps`, optional `income_tax_bps`) das pro Nutzer gesetzte `min_target_yield` erreicht. Dieser Gate ist die spaetere Auto-Trade-Voraussetzung.
4. **First-Login-Wizard:** alle fuer Empfehlungen + spaeteres Auto-Trading erforderlichen Werte (Broker-Creds, Gebuehren, Min-Yield, Steuersaetze, MFA) werden direkt nach Registrierung abgefragt.
5. **Dashboard-Onboarding-Karte:** Fortschritt N/M sichtbar, mit Click-through zum naechsten offenen Schritt; verschwindet erst bei vollstaendiger Konfiguration.
6. **Erklaerbarkeit ist Kern, nicht Beiwerk:** jede angezeigte Zone, jeder Confidence-Wert, jede Empfehlung muss vom Nutzer auf seine Quellen (welche Kategorie, welche Feature, welcher Net-Yield-Anteil) zurueckgefuehrt werden koennen.
7. **Doku gleichwertig zu Code:** Plan, Roadmap, Decisions, Status werden nach jeder Welle nachgezogen; eine Aenderung ist erst fertig, wenn die Doku den neuen Stand spiegelt.

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
- Alembic-basierte DB-Migrationen, smart-Stamp-Pfad fuer Pre-Alembic-Bestand
- `CLAUDE.md` als Repo-Orientierung; `.githooks/pre-commit` blockt Secret-Pattern, Auto-Aktivierung ueber `ops/automation/build.sh`

Offen:

- jeder neue Release-Tag muss denselben Upgrade-/Restore-Rehearsal-Pfad bestehen

### Phase 1: Live-Daten, Watchlists, Assetklassen

Status: abgeschlossen (Provider-Breite + Rate-Limit gehaertet); optional WebSocket-In-App-Zustellung verschoben.

Erledigt:

- Assetklassen `stock`, `etf`, `crypto`
- Watchlist-Tags und Watchlist-News-Bindung
- Alpha-Vantage-Pfad fuer ETF-/Krypto-Kontext
- Provider-Coverage im Dashboard
- priorisierte Watchlist-Alerts aus Signal, News, Tags und Provider-Kontext
- persistierte Watchlist-Alert-Settings; Alert-Management-Panel im Dashboard
- serverseitiger Watchlist-Push-Dispatcher mit deduplizierter Delivery-Historie
- zentraler Token-Bucket-Rate-Limiter (`app/rate_limit.py`) fuer Alpha Vantage, FMP und yfinance
- FMP-Adapter (`app/fmp_service.py`): Profil/Key-Metrics/Ratios/ETF-Holdings/News
- `MarketDataService` chained yfinance -> FMP fuer Stocks-Fundamentals; Alpaca -> FMP fuer News-Sentiment
- `tests/run-fmp-live-smoke.sh` analog zum Alpha-Vantage-Smoke
- produktive Push-/VAPID-Haertung
- persistente Alert-Domaene (`alert_rules`/`alert_events`) mit vier Regeltypen (`provider_move`, `news_sentiment`, `signal_direction`, `tag_priority`)

Offen:

- nutzergebundene In-App-/WebSocket-Zustellung (optional)

### Phase 2: Analyse und Research

Status: laeuft. Charts-Welle, Events-Welle, Erklaerbarkeit-Welle und Net-Yield-Welle abgeschlossen; Auto-Support/Resistance offen.

Erledigt:

- `/api/research/{symbol}` mit Provider-Research, Quote, History, Holdings, News
- Phase-2-Welle 1 (Chart-Overlays): VWAP zusaetzlich zu RSI/MACD/SMA/EMA/Bollinger/ATR/Stochastic; lightweight-charts v5 mit toggleable Overlays, Sub-Panes (RSI, MACD-Triple), Pattern-Marker
- Welle 2 (Earnings/Dividenden/Splits): `/api/events/{symbol}` ueber FMP; Frontend EventsSection mit Earnings-Beat/Miss, Dividenden, Splits
- Welle 3 (Volume-Profile): `compute_volume_profile` mit Point-of-Control; SVG-Component neben dem Chart
- Welle 4 (Erklaerbarkeit + Wahrscheinlichkeiten): SHAP-style `pred_contribs` per Feature plus Kategorie-Roll-up (Trend/Technical/Volume/News/Fundamentals); P(UP)/P(DOWN) explizit; ATR-anchored Entry-/Stop-/Target-Zonen
- Welle 5 (Net-Yield-Gate): Broker-Round-Trip-Fees + Kapitalertragssteuer (Abgeltung) -> NetYieldPct; `meetsMinimum` als Auto-Trade-Vorbedingung; UI-Breakdown im PredictionCard
- Onboarding-Wizard `/onboarding`; Dashboard-Karte mit Fortschritt N/M

Offen:

- Auto-Support/Resistance (Pivot-Detection, horizontale Linien im Chart, Stärke-Score)
- breitere Fundamentals-Anbindung jenseits Sector/Ratios (Cashflow, Debt, Guidance, Ratings)

### Phase 3: Paper-Trading

Status: noch nicht substanziell gestartet.

Naechste Zielpunkte:

- Order- und Ausfuehrungsmodell fuer Paper-Trading
- Transaktionsjournal
- PnL, Kosten, Slippage und Mindest-Rendite-Filter (verwendet das bereits in Phase 2 verbaute Net-Yield-Gate)
- Darstellung von Entries/Exits im Chart

### Phase 4: Live-Trading mit Auto-Execution

Status: bewusst spaeter.

Vorbedingungen:

- Phase-2-Empfehlungen vollstaendig (Auto-Support/Resistance, Fundamentals-Tiefe, Erklaerbarkeit gepraegt)
- Phase 3 Paper-Trading stabil mit Net-Yield-Gate verifiziert
- Risk-Modell, Limits, Budgetsteuerung und Audit-Logs belastbar
- manuelle Freigabelogik und Not-Aus vorhanden
- Broker-Fehlerpfade und Recovery getestet
- Auto-Trade darf nur ausloesen, wenn die Empfehlung den Net-Yield-Gate erfuellt UND der Nutzer den Asset/Strategie-Korridor explizit freigegeben hat

## Sicherheitsachsen

Immer mitzudenken:

- keine Secrets in Git, Logs, Exceptions oder Testausgaben
- produktive Secrets ueber `.env.local`, GitHub Actions Secrets oder Zielumgebung
- keine unsicheren Code-Defaults im Produktivbetrieb
- explizite Origins statt Wildcard-CORS
- sensible Audit-Felder nur redigiert oder als Fingerprint loggen
- Admin-Bootstrap nur ueber explizite Env-Werte
- Pre-commit-Hook (Secret-Pattern + private Key-Bloecke) ist Defense-in-depth zusaetzlich zu `.gitignore`; `core.hooksPath` wird beim ersten `build.sh`-Lauf automatisch gesetzt
- Releases nur nach Build, Unit/Syntax, API-Regression, UI-Regression und Rehearsal als deploybar betrachten
- Bei externen Provider-Antworten (News-Texte, Holdings-Strings, Symbol-/Watchlist-Namen) Prompt-Injection mitdenken: nie ungeprueft als Steuerlogik interpretieren

## Architekturachsen

Kurzfristig:

- bestehende FastAPI-Monolith-Struktur stabil halten
- gemeinsame Backend-Logik fuer API und Background-Jobs weiter herausziehen
- Tests immer an neue Persistenz-/Backup-/Import-Flaechen koppeln
- Frontend-Quellstand-Wiederaufbau (`src/frontend/`) parallel zum Bundle weitertreiben; Production-Swap erst mit UI-Regression-Rewrite

Mittelfristig:

- Provider-Adapter sauberer trennen (Alpaca / Alpha Vantage / FMP / yfinance / spaeter Twelve Data)
- Background-Jobs mit Telemetrie, Locking und Lifecycle-Guardrails versehen
- Risk-/Compliance-Logging fuer Auto-Trade vorbereiten

Langfristig:

- `market-data-service`
- `research-service`
- `analysis-service`
- `portfolio-service`
- `execution-service`
- `backup-service`

Diese Aufteilung ist Zielarchitektur, nicht Sofort-Refactor. Neue Arbeit soll aber so geschnitten werden, dass sie spaeter in diese Grenzen migrierbar bleibt.

## Naechste Prioritaeten

1. Phase-2-Welle 6: Auto-Support/Resistance.
2. Frontend-UI-Regression auf neue React-Selektoren umschreiben.
3. Frontend-Dockerfile-Swap (`ops/docker/frontend.Dockerfile`) auf Vite-Multi-Stage-Build, Bundle entfernen.
4. Phase-2-Tiefe: breitere Fundamentals (Cashflow, Debt, Guidance, Ratings).
5. Phase 3 Paper-Trading sauber modellieren — Order-Lebenszyklus, Transaktionsjournal, PnL, Net-Yield-Gate als Filter.
6. Phase 4 Auto-Execution erst nach Paper-Trading-Stabilitaet und Risk-Hardening.

## Entscheidungsregel

Eine Aenderung ist erst fertig, wenn sie:

- fachlich zum Phasenplan und zur Produktvision passt
- keine bekannten Security-Schulden verschlechtert
- lokal verifiziert ist (Build, Tests, ggf. Cross-Version-/Live-Smoke)
- in Backup/Export/Import beruecksichtigt ist, falls sie Persistenz beruehrt
- in Doku (Plan, Roadmap, Decisions, Status, ggf. CLAUDE.md) reflektiert ist
- per GitHub Actions gruen ist, wenn sie gepusht wurde
- fuer Release-Staende den Upgrade-/Restore-Rehearsal-Pfad besteht
