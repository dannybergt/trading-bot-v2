# Projektplan

## Stand 2026-05-08

Aktuell validierter Produkt-Release:

- Git-Tag: `v2026.05.08-1`
- Produkt-Commit: `ae77ad1` (`Data wave 6: options flow snapshot from yfinance`)
- Dokumentationsstand: auf `main` nachgezogen
- Backend-Image: `dbergt/trading-bot-backend:2026.05.08-1` (sha256:bbbe4628833921abb880c4ad336ab892445a0254a27bdd066689cd16e4997d13)
- Frontend-Image: `dbergt/trading-bot-frontend:2026.05.08-1` (sha256:e4c09ffa32194500a1c59d3b44bf1bf3ae4d33296d5531a0f9cff1d88aef9b88)
- Upgrade-/Restore-Rehearsal: bestanden (initialer Deploy, Datenanlage, Upgrade ueber bestehenden Datenbestand, Pre-Upgrade-PostgreSQL-Dump, App-Snapshot, Restore in frischen Stack)
- Deployment-Record: `state/runtime/deployments/deployment-20260508T101330Z.env`

Vorheriger Release: `v2026.05.07-1` (Commit `878fcff`).

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

Status: vollstaendig (sechs Wellen abgeschlossen). Tiefere Fundamentals-Anbindung (Cashflow/Debt/Guidance/Ratings) bleibt als optionaler Tiefe-Schritt vor Phase 3.

Erledigt:

- `/api/research/{symbol}` mit Provider-Research, Quote, History, Holdings, News
- Phase-2-Welle 1 (Chart-Overlays): VWAP zusaetzlich zu RSI/MACD/SMA/EMA/Bollinger/ATR/Stochastic; lightweight-charts v5 mit toggleable Overlays, Sub-Panes (RSI, MACD-Triple), Pattern-Marker
- Welle 2 (Earnings/Dividenden/Splits): `/api/events/{symbol}` ueber FMP; Frontend EventsSection mit Earnings-Beat/Miss, Dividenden, Splits
- Welle 3 (Volume-Profile): `compute_volume_profile` mit Point-of-Control; SVG-Component neben dem Chart
- Welle 4 (Erklaerbarkeit + Wahrscheinlichkeiten): SHAP-style `pred_contribs` per Feature plus Kategorie-Roll-up (Trend/Technical/Volume/News/Fundamentals); P(UP)/P(DOWN) explizit; ATR-anchored Entry-/Stop-/Target-Zonen
- Welle 5 (Net-Yield-Gate): Broker-Round-Trip-Fees + Kapitalertragssteuer (Abgeltung) -> NetYieldPct; `meetsMinimum` als Auto-Trade-Vorbedingung; UI-Breakdown im PredictionCard
- Welle 6 (Auto-Support/Resistance): `detect_support_resistance` in `analysis.py` mit Swing-Pivot-Clustering und Stärke-Score; horizontale Linien im Chart mit Opacity nach Stärke; Flip-Zonen markiert
- Onboarding-Wizard `/onboarding`; Dashboard-Karte mit Fortschritt N/M

Offen:

- breitere Fundamentals-Anbindung jenseits Sector/Ratios (Cashflow, Debt, Guidance, Ratings) als optionaler Tiefe-Schritt vor Phase 3

### Datenbasis-Erweiterung (Begleitachse zu Phase 3)

Status: in Arbeit. Welle 1 vom 2026-05-08 liefert Insider-/Institutional-/Earnings-Signale plus Macro-Kontext.

Bereits umgesetzt (Welle 1):

- FMP-Service-Erweiterung: `get_insider_trades` (FMP v4), `get_institutional_holdings`, `get_earnings_surprises`, `get_upcoming_earnings`, plus gebuendelt `normalized_research_signals` mit 90-Tage-Insider-Summary und Earnings-Beat-Quote
- Neuer Adapter `app/macro_service.py`: VIX, 10Y-Yield (^TNX), DXY ueber yfinance, Modul-Cache 5 min
- `/api/research/{symbol}` reicht `researchSignals` + `macroContext` durch
- Frontend AnalysisPage rendert zwei neue Sektionen: ResearchSignalsSection (Insider-Tabelle, Top-Institutional-Holders, Earnings-Beat-Historie, naechstes Earnings-Datum) und MacroContextSection
- 7 neue Unit-Tests (3 FMP, 4 Macro), API-Regression prueft Felder, UI-Regression best-effort fuer Macro

Bereits umgesetzt (Welle 2, 2026-05-08):

- Sentiment-Upgrade: `app/sentiment.py` nutzt jetzt VADER (`vaderSentiment.SentimentIntensityAnalyzer`) statt TextBlob als Default; `analyze_sentiment_basic` liefert Compound in [-1, 1], `analyze_news` haelt die alte Schnittstelle und Threshold-Defaults (±0.1) tunbar via `SENTIMENT_BULLISH_THRESHOLD`/`SENTIMENT_BEARISH_THRESHOLD`. `SENTIMENT_PROVIDER=finbert`-Schalter dokumentiert; aktuell Fallback auf VADER mit Warn-Log

Bereits umgesetzt (Welle 3, 2026-05-08):

- CoinGecko-Adapter `app/coingecko_service.py` mit Modul-Cache (5 min Coin-Metriken, 30 min Fear-Greed). Top-30-Static-Map plus `/coins/markets`-Fallback fuer Long-Tail-Coins. Liefert pro Crypto-Symbol Marktkap-Rang/Wert, 24h Cross-Exchange-Volumen, ATH/ATL mit Distance, Community-Daten (Twitter/Reddit) und Developer-Daten (Stars/Forks/Commits 4 Wochen)
- Crypto-Fear-and-Greed-Index ueber `alternative.me`, gecacht 30 min, Provider-Default 0.05 req/s
- `/api/research/{symbol}` ergaenzt um `cryptoMetrics` (None fuer Nicht-Crypto) und `fearGreedIndex` (immer best-effort)
- Frontend `CryptoMetricsSection` auf `/analysis/<symbol>` mit Marktkap/Volumen/ATH-Karten plus Developer-/Community-Tabellen; Fear-and-Greed wandert als 4. Karte in die `MacroContextSection`

Bereits umgesetzt (Welle 4, 2026-05-08):

- Retail-Sentiment-Adapter `app/social_sentiment_service.py` zieht StockTwits (`/streams/symbol/{SYMBOL}.json`, kein Auth) und Reddit (offentliche `search.json`, kein PRAW). Bullish/Bearish-Counts plus VADER-Average pro Quelle, Combined-Sentiment weighted nach Message-Count. Reddit prueft Stock-Subreddits (wallstreetbets/stocks/investing) oder Crypto-Subreddits (CryptoCurrency/Bitcoin/ethereum) und liefert 24h/7d-Mention-Counts plus Mention-Trend-Pct relativ zur 6-Tage-Baseline. Modul-Cache 30 min, Rate-Limit-Provider-Defaults `stocktwits` 1 req/s und `reddit` 0.5 req/s. `/api/research/{symbol}` ergaenzt um `socialSentiment` mit `stocktwits`/`reddit`/`combined`-Bloecken. Frontend `SocialSentimentSection` rendert KPI-Cards plus Top-Reddit-Posts (klickbar) und Top-StockTwits-Posts

Bereits umgesetzt (Welle 5, 2026-05-08):

- Earnings-Call-Transcripts via FMP v4-Batch-Endpoint (`/batch_earning_call_transcript/{SYMBOL}?year=YYYY`); pro Quartal Volltext + VADER-Aggregation; Sentence-Tokenisierung extrahiert die hoechst-positive und hoechst-negative Quote; `/api/research/{symbol}` reicht `earningsCalls`-Liste durch. Frontend `EarningsCallsSection` rendert pro Quartal eine Card mit VADER-Pille und beiden Quotes als farbige Blockquotes

Bereits umgesetzt (Welle 6, 2026-05-08):

- Options-Flow-Adapter `app/options_flow_service.py` zieht yfinance `Ticker.option_chain` fuer das nearest-expiry mit >=7 Tagen Restlaufzeit. Aggregiert Put/Call-Volume-Ratio, Put/Call-OI-Ratio, Average-IV ATM (±5%-Band um Last-Close), Top-3-Strikes Calls und Puts nach Volume. Cache 60 min pro Symbol; Crypto skipped. `/api/research/{symbol}` ergaenzt um `optionsFlow`. Frontend `OptionsFlowSection` rendert KPI-Cards plus Top-Strike-Tabellen mit Skew-Pille (bullish/bearish/neutral)

Bereits umgesetzt (Welle 7, 2026-05-08):

- FinBERT (`ProsusAI/finbert`) als optionaler Premium-Sentiment-Provider ueber `SENTIMENT_PROVIDER=finbert`. Schwere Dependency-Schicht (transformers + torch) liegt in `requirements-finbert.txt`, Default-Container bleibt schmal. Lazy-Singleton-Pipeline, Mapping FinBERT-Label/Score auf [-1, 1]; transparenter Fallback auf VADER bei nicht-installiertem `transformers` oder Load-Fehler. Default-Verhalten ist unveraendert VADER

Bereits umgesetzt (Welle 8, 2026-05-08):

- Twelve Data als dritter Provider-Fallback hinter yfinance + FMP. Schliesst die Non-US-Coverage-Luecke (Frankfurt, Paris, London, Tokio, Hong Kong) — `MarketDataService.get_ticker_info` chained jetzt yfinance → FMP → Twelve Data. Optionaler `TWELVE_DATA_API_KEY`. Adapter analog zu FMP-Pattern, normalisiert auf yfinance-kompatible Felder, defensiv gegen Twelve-Data-typische `{"status":"error"}`-Responses

Bereits umgesetzt (ML-Persistenz + Backtest, 2026-05-08, Phase-4-Vorbedingung):

- Per-Symbol-Modell-Persistenz: `app/ml_persistence.py` mit XGBoost-JSON unter `state/runtime/data/ml_models/<SYMBOL>.json` plus `<SYMBOL>.meta.json`. Default-TTL 24 h. `MarketDataService._get_or_train_predictor(symbol, df)` checkt Memory-Cache (1h) → Disk → Train+Persist. Damit lernt das Modell von Tag zu Tag, statt bei jedem Request neu zu starten
- Walk-Forward-Backtest-Framework: `app/backtest_service.py::run_backtest(df, train_window, step)` trainiert in Slots, sammelt Predictions, berechnet Accuracy, Mann-Whitney-AUC, Brier-Score, Strategy-vs-Buy-Hold-Cum-Return und 10-Bucket-Reliability-Tabelle fuer Confidence-Calibration. Endpoint `GET /api/research/{symbol}/backtest`. Frontend `ModelPerformanceSection` auf `/analysis/<symbol>`

Bereits umgesetzt (Audit-Log + Daily-Re-Train, 2026-05-08, Phase-4-Vorbedingung):

- `audit_events`-Tabelle (Alembic 0005), `app/audit_service.log_event` mit 14 Hooks an sensitiven Endpoints (auth, settings, paper-orders, backups, admin-user-ops). Identifizierende Werte als 16-char-SHA256-Fingerprint. Admin-Endpoint `GET /api/admin/audit-events` mit pagination. Backup/Export/Import deckt audit_events mit
- Background-Task `ml_retrain_task` (1h Intervall) refreshed stale persistierte Predictors proaktiv

Bereits umgesetzt (In-App-Hilfe + Doku, 2026-05-08):

- `docs/inapp/<topic>.md` als Quelle. Endpoints `GET /api/docs/topics` und `GET /api/docs/{slug}` (no-auth, defensiv gegen Path-Escapes). Frontend `HelpDrawer` (?-Button im Layout, kontextueller Slide-Over fuer die aktuelle Page) plus `/docs` Route mit Side-Nav + Markdown-Rendering via lazy-loaded react-markdown + remark-gfm. 9 Markdown-Topics initial (getting-started, dashboard, watchlists, scanner, analysis, alerts, paper-trading, settings, admin). Default EN; DE-Uebersetzungen als spaetere Welle

Bereits umgesetzt (Data-Source-Transparency, 2026-05-08, Phase-4-Vorbedingung):

- `app/data_quality_service.py` mit per-Symbol `evaluate_symbol_data_quality` (FULL/PARTIAL/FALLBACK/MISSING pro Feld + Provider), `_overall_confidence` (high/medium/low) und statischem `_build_upgrade_hints` (FMP Starter $14/mo, Alpha Vantage Premium $50/mo, Polygon.io $29/mo, Reddit OAuth free). `PROVIDER_CATALOGUE` als statisches Dict mit covers/freeTierLimit/upgradeTier/upgradeCostUsdMonthly fuer alle Quellen. Endpoints `GET /api/research/{symbol}/data-quality` + Admin-only `GET /api/admin/data-sources`. Frontend `DataQualitySection` oben auf `/analysis/<symbol>` mit Per-Field-Grid + Upgrade-Hint-Block im amber-Theme. Recommendation-Card hat jetzt `Data: high|medium|low`-Badge unter der Direction. AdminPage `DataSourcesSection` rendert Coverage-Matrix mit Monthly-Cost-Footer. Help-Topic `data-quality.md`

Bereits umgesetzt (Welle 9a — News-Hub, 2026-05-08):

- Globaler Multi-Source-News-Feed unter `/news`. Aggregiert FMP `/stock_news` (ohne Symbol-Filter), Alpha-Vantage `NEWS_SENTIMENT` mit Topics, plus RSS-Feeds (boerse.de, ariva.de, Reuters via `feedparser`). Symbol-Extraction aus Item-Titeln, Deduplizierung by URL, Sortierung newest-first ueber geparste Datetimes, Filter nach Source/Sentiment/Time-Window/Symbol. Endpoint `GET /api/news/feed`. Frontend mit Filter-Bar und klickbaren Symbol-Chips zur AnalysisPage als Discovery-Pfad

Offene Subwellen:

- **Welle 9b — Discovery-Engine**: aufbauend auf 9a-News-Aggregation: Trending-Symbols nach News-Volume + Sentiment-Burst der letzten 24h, Top-Gainers/Losers ueber Watchlist hinaus, Unusual-Volume-Detection, Insider-Cluster-Detection (3+ unabhaengige Insider in 90d gleichgerichtet), Reddit/StockTwits-Mention-Spikes ohne Symbol-Filter. Eigene `/discover`-Page oder Section auf der News-Hub-Seite
- **Welle 10 — Security-Welle**: Container-Image-Vulnerability-Scan (trivy/grype als CI-Step), CSP/HSTS-Header auf Frontend, Upload-MIME-Validation + Size-Limits fuer Backup-Imports, Per-User-Rate-Limit fuer Login (heute global). Echtes Anti-Malware (Binary-Scan) erst wenn Binary-Uploads kommen
- **Welle 11 — Android (PWA-First-Strategie)**: Phase A = Manifest + Service-Worker fuer "Installierbar auf Homescreen", offline-Fallback (~1-2 Tage). Phase B = Capacitor-Wrapper fuer App-Store-Distribution + Biometric-Auth (~3-5 Tage). Phase C = React-Native nur wenn UX-Anforderungen das wirklich brauchen
- **Welle 12 — DE-Uebersetzungen** der sechs neuen Sektionen + neuen Doku-Topics: ResearchSignals, MacroContext, EarningsCalls, CryptoMetrics, SocialSentiment, OptionsFlow, ModelPerformance + alle 9 Markdown-Topics
- **Welle 13 (optional)** — FinBERT-Image-Variant `dbergt/trading-bot-backend-finbert` als zweite Build-Stage
- **Welle 14 — Datenbasis-Tiefe**: SEC-Filings (10-K/10-Q/8-K) ueber FMP, Macro-Calendar (Fed/CPI/Jobs) ueber FRED, Insider-Cluster-Detection, Sektor-/Index-Relativstaerke (SPY/QQQ/XLK/XLF/XLE), Korrelations-/Beta-zu-Benchmark, Yield-Curve-Spread (2Y/10Y), Commodities (Oil/Gold)

### Phase 3: Paper-Trading

Status: abgeschlossen am 2026-05-08. Vier Schnitte: Erststand (Schema, Lifecycle, Endpunkte, Frontend-Page), zweiter Schnitt (Background-Fill, Chart-Marker, Recommendation-Verlinkung), dritter Schnitt (asset-spezifische Slippage), vierter Schnitt (dynamische Slippage + asset-Fee-Multipliers). Bereit fuer Phase 4 nach Risk-Modell.

Bereits umgesetzt:

- Tabellen `paper_orders` und `paper_transactions` ueber Alembic-Migration `0004_add_paper_trading` (`c8e2a1b9d4f3`)
- Endpunkte `POST/GET/DELETE /api/paper-trading/orders`, `GET /api/paper-trading/transactions|positions|summary`
- Order-Lifecycle-Service `app/paper_trading.py`: simulierte Fills gegen letzten Close (0.1% adverse Slippage), Limit-Order-Logik, weighted-average Cost-Basis fuer realisierte PnL nach Brokergebuehren und Kapitalertragssteuer
- Net-Yield-Gate auf Order-Annahme: bei gesetztem `target_price` rechnet die Service-Schicht denselben Fees+Tax-Pfad wie `PricePredictor._enrich_with_yield_model` und lehnt unterhalb von `min_target_yield` ab
- `MarketDataService.get_latest_close` als Best-Effort-Preisquelle (Alpaca -> Alpha Vantage -> yfinance)
- Backup/Export/Import deckt `paper_orders` und `paper_transactions` mit ab
- Frontend `/paper-trading` Page (DE/EN) mit Place-Order-Form, Tab-Navigation Open Orders / Trade-Journal / Positions / Summary; Journal zeigt jeden Fill chronologisch mit nominaler PnL, prozentualer PnL, Gebuehren und Steuerlast plus Gesamtsummen
- Unit-Tests `tests/test_paper_trading_service.py` (10 Tests), API-Regression um Settings, Gate-Reject, Place/List/Cancel und Backup-/Export-Coverage erweitert, UI-Regression-Schritt `ui_paper_trading ok`

Bereits umgesetzt (zweiter Schnitt, 2026-05-08):

- Pending Limit-Orders fuellen sich ueber Background-Task `paper_order_fill_task` periodisch gegen `MarketDataService.get_latest_close` (Default 180s Intervall, 60s Initial-Delay; per-Symbol-Cache pro Zyklus)
- Paper-Trades als Marker im StockChart auf `/analysis/<symbol>` (Buy/Sell-Pfeile mit Qty + Preis als Label)
- Recommendation-Card bekommt "Place paper order at this target"-Link, der `/paper-trading` mit symbol/side/limitPrice/targetPrice/source-Parametern vorbelegt; PaperTradingPage liest die Params via `useSearchParams` und befuellt das Form

Bereits umgesetzt (dritter Schnitt, 2026-05-08):

- Asset-Klassen-spezifische Slippage im Fill-Simulator: Stocks 0.1%, ETFs 0.05%, Crypto 0.3% (`SLIPPAGE_PCT_BY_ASSET_CLASS`-Map). `_try_fill` nimmt einen `asset_class`-Parameter; `place_order` und `dispatch_pending_orders` einen optionalen `asset_class_resolver`. `main.py` haengt das per `service.get_asset_profile`-Wrapper an

Bereits umgesetzt (vierter Schnitt, 2026-05-08, Phase 3 abgeschlossen):

- Dynamische Slippage skaliert mit Position-Size relativ zum 20-Tage-Volumen: `_resolve_slippage_pct(asset_class, qty, avg_daily_volume)` multipliziert die Base-Slippage mit `(1 + qty / avg_volume)` und cappt bei `MAX_SLIPPAGE_PCT=1.0`. `MarketDataService.get_avg_daily_volume(symbol)` als Provider (Alpaca → yfinance-Fallback)
- Asset-spezifische Fee-Multipliers: `FEE_MULTIPLIER_BY_ASSET_CLASS` (Stock/ETF 1.0, Crypto 5.0) skaliert User-Fee-Settings, `evaluate_net_yield_gate` und `fee_breakdown` nutzen denselben Multiplier
- Phase 3 damit komplett. Phase 4 Auto-Execution kann nach Risk-Modell + Limits angegangen werden

### Phase 4: Live-Trading mit Auto-Execution

Status: bewusst spaeter.

Vorbedingungen:

- Phase-2-Empfehlungen vollstaendig (Auto-Support/Resistance, Fundamentals-Tiefe, Erklaerbarkeit gepraegt) — erfuellt
- Phase 3 Paper-Trading stabil mit Net-Yield-Gate verifiziert — erfuellt
- ML-Persistenz + Backtest-Framework (Modell-Validierung gegen historische Daten) — erfuellt am 2026-05-08
- Audit-Trail in eigener DB-Tabelle, im Backup mitgefuehrt — erfuellt am 2026-05-08
- Risk-Modell, Limits, Budgetsteuerung — offen, Phase-4-Block 1
- manuelle Freigabelogik und Not-Aus — offen, Phase-4-Block 2
- Broker-Fehlerpfade und Recovery (Order-Reconciliation gegen Alpaca) — offen, Phase-4-Block 3
- Auto-Trade darf nur ausloesen, wenn die Empfehlung den Net-Yield-Gate erfuellt UND der Nutzer den Asset/Strategie-Korridor explizit freigegeben hat

## UX-Direktive

Verbindlich fuer alle Frontend-Arbeit:

- Bedienung muss uebersichtlich, einfach und schnell wirken — Menues, Dropdowns, klare Aktionen, keine versteckten Pfade.
- Jede Empfehlung, Zone, Wahrscheinlichkeit muss vom Nutzer auf ihre Quellen zurueckfuehrbar sein (Fundamentals/News/Trend/Technical/AI), nicht nur als Confidence-Zahl.
- Mehrere Aktionen pro Element gehoeren in eindeutige Buttons oder Dropdowns; keine geheimen Icon-Klicks ohne Beschriftung/Tooltip.
- Sprachen: Deutsch und Englisch werden parallel unterstuetzt; Toggle ist auf der Login-Seite und im eingeloggten Layout erreichbar; Auswahl persistiert per Nutzer.
- Wichtige Werte (Preise, Erloese, Steuern, Gebuehren, P(UP)/P(DOWN)) immer mit Einheit, Vorzeichen und Vergleichswert anzeigen, damit Interpretation nicht beim Nutzer haengen bleibt.
- Onboarding und Setup-Status sind Teil der Hauptnavigation, nicht versteckt; das Dashboard zeigt Restschritte und stellt sie per Klick wieder zustellbar.

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

Stand 2026-05-08 nach Abschluss von Phase 3, allen acht Datenbasis-Wellen, ML-Persistenz/Backtest, Audit-Log, In-App-Hilfe:

1. **Welle 9b — Discovery-Engine** (Trending nach News-Volume, Top-Mover, Unusual-Volume, Insider-Cluster) — direkt aufbauend auf 9a
2. **Welle 10 — Security-Welle** (Container-Image-Scan in CI, CSP/HSTS-Header, Upload-MIME-Validation, Per-User-Login-Rate-Limit)
3. **Welle 11 — Android via PWA** (Manifest + Service-Worker, Phase A; Capacitor + Biometric optional in Phase B)
4. **Welle 12 — DE-Uebersetzungen** der seit Welle 1 hinzugekommenen Frontend-Sektionen + Doku-Topics
5. **Phase 4 Auto-Execution** — beginnt erst NACH Welle 9b-12 plus Risk-Modell + manuelle Freigabe-Logik + Not-Aus + Order-Reconciliation
6. Welle 13 (optional, Premium-Sentiment): FinBERT-Image-Variant
7. Welle 14 (Datenbasis-Tiefe): SEC-Filings, FRED-Calendar, Sektor-Relativstaerke, Korrelations-/Beta-Tabellen, Yield-Curve-Spread, Commodities

Erfuellte Phase-4-Vorbedingungen (Phase 3 + ML-Persistenz + Backtest + Audit-Trail) muessen jetzt nicht mehr neu eroertert werden.

## Entscheidungsregel

Eine Aenderung ist erst fertig, wenn sie:

- fachlich zum Phasenplan und zur Produktvision passt
- keine bekannten Security-Schulden verschlechtert
- lokal verifiziert ist (Build, Tests, ggf. Cross-Version-/Live-Smoke)
- in Backup/Export/Import beruecksichtigt ist, falls sie Persistenz beruehrt
- in Doku (Plan, Roadmap, Decisions, Status, ggf. CLAUDE.md) reflektiert ist
- per GitHub Actions gruen ist, wenn sie gepusht wurde
- fuer Release-Staende den Upgrade-/Restore-Rehearsal-Pfad besteht
