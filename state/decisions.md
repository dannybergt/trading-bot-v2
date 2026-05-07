# Entscheidungen

- Datum: 2026-05-07
  Entscheidung: Produktvision wird verbindlich auf "kombinierte Signal-Quellen + Net-Yield-Gate + First-Login-Wizard + Dashboard-Onboarding-Fortschritt" festgezurrt und in `docs/admin/project-plan.md` Sektion "Produktvision" verankert.
  Begruendung: Der Nutzer hat heute mehrere Direktiven gegeben, die zusammen die Tragweite des Produkts definieren:
    1. Buy/Sell-Empfehlungen muessen aus dem Zusammenspiel von Fundamentaldaten, News, Markttrends, Technischer Chartanalyse und KI entstehen.
    2. Wahrscheinlichkeiten muessen explizit dargestellt werden (P(UP)/P(DOWN)), nicht versteckt hinter einem einzelnen Confidence-Wert.
    3. Das Datenbild je Asset soll moeglichst vollstaendig sein, weil das End-Ziel automatisches Trading ist.
    4. Brokergebuehren und Steuern (Kapitalertragssteuer / Abgeltungssteuer / Einkommenssteuer-Fallback) muessen in die Empfehlung einfliessen — actionable nur, wenn nutzerdefinierter Mindest-Yield NETTO erreicht wird.
    5. Pflicht-Konfiguration wird beim ersten Login per Wizard abgefragt und im Dashboard als Fortschritt visualisiert.
    6. Plan/Doku muss alle Direktiven inhaltlich gepruegt und optimiert spiegeln.
  Konsequenzen: `docs/admin/project-plan.md` enthaelt jetzt eine eigene Sektion "Produktvision" mit den 7 verbindlichen Punkten; `docs/admin/product-roadmap.md` reflektiert dieselbe Vision in Phase 2/3/4; `CLAUDE.md` zitiert die Vision; jede neue Welle muss den Vision-Check passieren bevor sie als "fertig" gilt. Backend liefert Net-Yield mit `meetsMinimum`-Flag; Frontend zeigt Net-Yield-Breakdown plus Probability-Bars und Kategorie-Erklaerbarkeit. `/onboarding`-Wizard und Dashboard-Onboarding-Karte sind eingebaut.

- Datum: 2026-05-07
  Entscheidung: User-Schema wird um `capital_gains_tax_bps` und `income_tax_bps` (Integer-Basispunkte) erweitert; `min_target_yield` wird ab jetzt als NETTO-Minimum interpretiert.
  Begruendung: Ohne Steuermodell gilt eine Empfehlung als "10% Gewinn" auch dann, wenn 26.375% Abgeltungssteuer plus Brokergebuehren den Netto-Ertrag unter das Nutzer-Minimum drueckt. Auto-Trade-Freigabe braucht eine harte Netto-Ertrags-Vorbedingung. Basispunkte vermeiden Floating-Point-Drift und halten SQLite + PostgreSQL ohne Numeric-Spalte konsistent.
  Konsequenzen: Alembic-Migration `0003_add_user_tax_rates` (revision `a3c1d4f5e6b7`); `PortfolioSettingsRequest`/`Response` reichen die Felder durch; `_enrich_with_yield_model` berechnet Gross -> Fees -> Tax -> Net und liefert `meetsMinimum`; UI im PredictionCard zeigt Breakdown plus Schwellen-Badge; Backup/Export/Import deckt die neuen Felder mit ab.

- Datum: 2026-05-07
  Entscheidung: Phase-2-Charts werden mit TradingView-`lightweight-charts` v5 gebaut, nicht mit `recharts`/`chart.js`/`apexcharts`; AnalysisPage lazy-loaded per `React.lazy` damit der Initial-Load-Bundle nicht durch die Chart-Library aufgeblaeht wird.
  Begruendung: `lightweight-charts` ist purpose-built fuer Finanz-Charts (Candlesticks, Volumen, Sub-Panes, Marker) und liefert das deutlich beste Verhaeltnis aus Bundle-Groesse zu Funktionsumfang (~60 KB gzipped fuer den vollen Featuresatz). `chart.js`/`recharts` haetten Candlesticks und Sub-Panes nur ueber Plugins/eigene Komponenten geliefert; `apexcharts` ist groesser. Lazy-Loading der `AnalysisPage` (inkl. Chart-Code) hebt das Initial-JS zurueck auf 96 KB gzipped, der Chart-Chunk laedt erst beim Drilldown.
  Konsequenzen: `app/analysis.py` ergaenzt um `VWAP` (cumulative typical-price * volume); `/api/stock/{symbol}` reicht jetzt zusaetzlich `ema_12`, `ema_26`, `atr`, `vwap`, `stoch_k`, `stoch_d` durch. `src/frontend/src/components/StockChart.tsx` haelt Candle + Volume + Toggleable Overlays (SMA 20/50/200, EMA 12/26, VWAP, Bollinger) + Sub-Panes (RSI, MACD-Triple) + Pattern-Marker. AnalysisPage lazy-loaded ueber `React.lazy` mit Suspense-Fallback. Volume Profile (Phase-2-Punkt) ist absichtlich nicht in dieser Welle, weil `lightweight-charts` das nicht out-of-the-box liefert; kommt als eigene Welle, wenn priorisiert.

- Datum: 2026-05-07
  Entscheidung: Stocks-Fundamentals und News bekommen einen zweiten Provider (FMP) als Fallback, gesteuert durch einen zentralen Token-Bucket-Rate-Limiter pro Provider; Twelve Data wird bewusst zurueckgestellt.
  Begruendung: yfinance liefert bei Lastspitzen verlaesslich 429-Throttles; ohne Fallback fiel `MarketDataService` direkt auf Mock-Daten zurueck. Phase-1-Plan verlangt explizit "breitere Provider-Fallbacks" und "Rate-Limit-Strategie". FMP deckt Profil, Ratios, Key Metrics, ETF-Holdings und News ab und liefert damit echte Substanz fuer beide Endpoints. Twelve Data adressiert vorwiegend internationale Maerkte und Indikatoren — fuer den US-Stocks/ETFs/Crypto-Fokus gewichtet das aktuell weniger und wuerde nur Komplexitaet ohne unmittelbaren Nutzen einfuehren.
  Konsequenzen: `app/rate_limit.py` haelt thread-safe TokenBuckets pro Provider mit konservativen Defaults (Alpha Vantage 5/min, FMP 60/min, yfinance 2/s) und kann pro Prozess umkonfiguriert werden. `app/fmp_service.py` haengt an `requests` und an `acquire("fmp")`. `MarketDataService.get_ticker_info` springt auf FMP, wenn yfinance leer oder rate-gelimitiert ist; `get_market_news` springt auf FMP, wenn Alpaca keine Items liefert. Live-Smoke `tests/run-fmp-live-smoke.sh` fuer Profile/Ratios/News/ETF-Holdings; bricht bei fehlendem `FMP_API_KEY` mit Exit 2 ab, ohne den Wert auszugeben. Compose und `.env.example`/`.env.local.example` reichen `FMP_API_KEY` durch.

- Datum: 2026-05-07
  Entscheidung: Schema-Lifecycle wird ab jetzt ueber Alembic verwaltet; `init_db` ruft `alembic upgrade head` auf, stempelt Pre-Alembic-Deployments (Schema vorhanden, kein `alembic_version`) automatisch auf head.
  Begruendung: `Base.metadata.create_all` als impliziter Schema-Bootstrap war Phase-0-Restpunkt im `docs/admin/project-plan.md` und harte Vorbedingung fuer Phase-3 (Paper-Trading), wo zusaetzliche Tabellen und Schema-Aenderungen ohne Datenverlust gefahren werden muessen. Die initiale Migration `0001_initial_schema` (revision `16389c42c243`) wurde per `alembic revision --autogenerate` gegen die aktuelle `Base.metadata`-Definition erzeugt und enthaelt alle 10 Tabellen inklusive Indizes. Der smarte Stamp-bei-Pre-Alembic-Schema-Pfad sorgt dafuer, dass Bestandsdeployments (z.B. `v2026.05.07-1`) ohne Migrationsbruch upgraden.
  Konsequenzen: `alembic` ist jetzt Hard-Dependency (`requirements.txt`); `src/backend/alembic.ini`, `src/backend/alembic/env.py`, `src/backend/alembic/versions/0001_initial_schema.py` sind im Repo. `tests/test_alembic_init.py` deckt Fresh-DB- und Pre-Alembic-Stamp-Pfad in isolierten Subprocess-Tests ab. Neue Schemata werden ab jetzt ausschliesslich ueber neue Alembic-Revisionen eingefuehrt; `Base.metadata.create_all` ist tot. Upgrade-Rehearsal fuer den naechsten Release-Tag prueft den Stamp-Pfad implizit, weil der Vorgaengerstand `v2026.05.07-1` ohne `alembic_version` deployt war.

- Datum: 2026-05-07
  Entscheidung: Persistente Alert-Domaene (`AlertRule` + `AlertEvent`) wird zusaetzlich zum bestehenden `WatchlistAlertSetting`-/`WatchlistAlertDelivery`-Stack eingefuehrt; beide Mechanismen koexistieren komplementaer.
  Begruendung: `WatchlistAlertSetting` regelt globale Watchlist-Toggles (Popup/Push, Min-Prio, Min-Score) und `WatchlistAlertDelivery` haelt Push-Zustellhistorie zur Deduplizierung. `AlertRule` adressiert eine andere Achse: granulare per-Symbol-Regeln mit Threshold/Direction/Tag/Snooze, deren Treffer als persistente `AlertEvent`-Records (open/acknowledged) festgehalten werden. Diese WIP-Arbeit lag in der ehemaligen Sandbox `trading-bot-v2-work` und wurde inhaltlich uebernommen, an die in `-v2` zwischenzeitlich angepasste `build_watchlist_alert_payload`-Signatur angeglichen und mit Backup/Export/Import + API-Regression abgesichert.
  Konsequenzen: Vier Regeltypen liegen vor (`provider_move`, `news_sentiment`, `signal_direction`, `tag_priority`). Neue Endpunkte `/api/alerts/rules` (CRUD), `/api/alerts` (Auswertung), `/api/alerts/events` (Liste), `/api/alerts/events/{id}/ack` (Acknowledge). Frontend-Anbindung steht aus und gehoert in den geplanten React-Quellstand-Wiederaufbau. Bekannter Design-Punkt: `GET /api/alerts` hat bewusst Side-Effects (Event-Erzeugung mit DB-Commit, Dedup ueber `existing_open`), um den Frontend-Polling-Pfad einfach zu halten; spaeter bei UI-Anbindung zu `POST` migrierbar.

- Datum: 2026-05-07
  Entscheidung: Verbindliche Sicherheits-Guardrails werden in `CLAUDE.md` im Repo-Root verankert und durch einen Pre-commit-Hook unter `.githooks/pre-commit` (aktiviert per `core.hooksPath`) als Defense-in-depth flankiert.
  Begruendung: Bei jedem Sitzungswechsel (Codex/Claude) muss der Workflow ohne erneute Komplettanalyse wiederherstellbar sein, und zentrale Sicherheits-Regeln (keine Secrets, Prompt-Injection-Bewusstsein, CORS, Audit-Fingerprints, Test-Pipeline-Pflicht vor jedem Push) duerfen nicht in einer einzelnen Sitzung verlorengehen.
  Konsequenzen: Resume-Codewort bleibt `resume trading-bot-v2`. Pre-commit blockt versehentlich gestagete `.env.local`/`*.pem`/`*.key`/AWS-/GitHub-/Slack-Token-Pattern, `BEGIN PRIVATE KEY`-Bloecke und High-Entropy-`SECRET=`/`API_KEY=`-Zuweisungen ab 32 Zeichen. Hook ist gegen falsche grep-Flag-Interpretation des Dash-Prefix gehaertet (Dash-Dash-Trenner) und mit AWS-Key- + Private-Key-Sample geprueft.

- Datum: 2026-05-07
  Entscheidung: Sync nach `origin/main` und Docker Hub erfolgt voll automatisch ohne separates User-OK; auch versionierte Release-Tags `v*` werden direkt nach erfolgreichem Upgrade-/Restore-Rehearsal gesetzt.
  Begruendung: Nutzer hat Sync-Autonomie explizit auf "voll automatisch, alles" gesetzt. Disziplin bleibt durch die bestehenden Pre-Push-Gates (Build, Unit, API-Regression, UI-Regression, bei Persistenz-Aenderungen Rehearsal) und die GitHub-Actions-Gates erhalten.
  Konsequenzen: Jeder sinnvolle Codeschnitt geht direkt nach `main`; `latest`+`sha-<commit>` werden automatisch nach Docker Hub publiziert. Release-Tags duerfen erst nach gruenem Rehearsal gesetzt werden — diese Sicherheitslinie bleibt erhalten.

- Datum: 2026-05-07
  Entscheidung: Frontend-Strategie wechselt von "Patch-Schicht weiter ausbauen" auf "echten Vite/React-Quellstand neu aufbauen". Source-Aufbau erfolgt parallel zum bestehenden `src/frontend-dist`-Bundle; Production-Swap erst nach Feature-Paritaet.
  Begruendung: Die patch-basierte UI in `src/frontend-dist/ui-patches.js` (2.132 Zeilen) blockt langfristig das Wachstum, weil neue Features wie das jetzt vorhandene Alert-Rule-System keine echte React-Komponentenflaeche haben. Sofortiger Production-Swap wuerde aber die UI-Regression brechen, weil viele Flows (Scanner, Analyse, Alpaca, Settings, Admin, News-Ticker, Provider-Research-Panel) noch nicht im neuen Source existieren.
  Konsequenzen: Neuer Frontend-Quellstand liegt unter `src/frontend/` (Vite/React 19/TypeScript/Tailwind/React-Router 7/TanStack Query 5/Zod). Erste Welle (vertical slice) deckt Auth (Login/Register mit MFA-Pfad), Layout, Dashboard mit Stats, Watchlist-Uebersicht und Alert-Regel-UI (CRUD plus Event-Acknowledge) ab. CI-Stufe `Build frontend source` (in `ci.yml` und `publish.yml`) haelt das Scaffold per `npm ci && npm run build` lauffaehig, damit es nicht bitrotiert. Folge-Wellen migrieren die fehlenden Bundle-Flows in echte Komponenten; sobald Paritaet steht wird `ops/docker/frontend.Dockerfile` von Bundle-Copy auf Vite-Multi-Stage-Build umgestellt und der Bundle-Ordner entfernt.

- Datum: 2026-05-05
  Entscheidung: `docs/admin/project-plan.md` ist ab jetzt die kanonische Kurzverankerung fuer Gesamtstand, Phasenposition, Sicherheitsachsen und naechste Prioritaeten.
  Begruendung: Nach `v2026.05.05-1` ist das Projekt nicht mehr nur ein rekonstruiertes MVP, sondern ein releasefaehiger Phase-1-Stand mit begonnener Research-Schicht und aktivem Alert-Dispatcher. Der Gesamtplan muss deshalb explizit sichtbar bleiben, damit einzelne Folgeaufgaben nicht vom Produkt-, Betriebs- oder Sicherheitsziel abweichen.
  Konsequenzen: Roadmap, README, Release- und Security-Doku verweisen auf den aktuellen validierten Release und die naechsten Guardrails; neue groessere Arbeiten muessen gegen Phasenplan, Security, Tests, Backup/Export/Import und Rehearsal-Regeln eingeordnet werden.

- Datum: 2026-04-26
  Entscheidung: Dauerhafte private lokale Secrets und persoenliche Zugangsdaten werden in einer gitignorierten `.env.local` gepflegt, die von den Ops-Skripten immer nach `.env` geladen wird.
  Begruendung: Der bisherige Betriebsweg war fehleranfaellig, weil `docker compose -f ops/docker/compose.yaml ...` die Root-`.env` nicht verlaesslich als Projektkontext behandelt und Nutzer dadurch Keys bei Wiedereinstiegen wiederholt neu eintragen mussten.
  Konsequenzen: `start.sh`, `stop.sh` und `logs.sh` kapseln den Compose-Zugriff; `.env` bleibt Basis-Konfiguration, `.env.local` gewinnt fuer private Overrides; Deploy- und Rehearsal-Skripte verwenden denselben Ladepfad.

- Datum: 2026-03-18
  Entscheidung: Lokalen Projektordner als `trading-bot-v2` angelegt.
  Begruendung: Dieser Name ist in beiden Images als Compose-/Projektname verankert und beschreibt das Gesamtprodukt besser als die getrennten Image-Namen.
  Konsequenzen: Publish-Automation braucht eine gesonderte Namensentscheidung.

- Datum: 2026-03-18
  Entscheidung: Backend-Quellcode aus Image extrahiert und als Arbeitsbasis uebernommen.
  Begruendung: Docker Hub war die einzig verifizierbare Quelle. Damit ist wenigstens der serverseitige Stand nachvollziehbar bearbeitbar.
  Konsequenzen: Der lokale Stand ist editierbar, aber nicht automatisch identisch mit einem moeglichen privaten Git-Repository.

- Datum: 2026-03-18
  Entscheidung: Frontend nur als `frontend-dist` abgelegt.
  Begruendung: Im Image war kein Quellstand vorhanden, nur das ausgelieferte Bundle.
  Konsequenzen: Tiefere Frontend-Weiterentwicklung ist ohne weitere Rekonstruktion oder Originalquelle eingeschraenkt.

- Datum: 2026-03-18
  Entscheidung: Publish-Automation nicht auf Docker Hub freigeschaltet.
  Begruendung: Die globale Regel verlangt exakte Namensgleichheit zwischen Projektordner und Image-Repository; diese ist aktuell nicht gegeben.
  Konsequenzen: Build und Analyse sind moeglich, Publish erst nach Strukturentscheidung.

- Datum: 2026-03-18
  Entscheidung: Backend-Container bleibt als nicht-root User laufend; beschreibbare Bind-Mount-Pfade werden ueber Automation vorbereitet.
  Begruendung: Die Runtime-Pruefung zeigte Schreibprobleme fuer `state/runtime/backups`, aber ein Root-Container waere der falsche Sicherheitsrueckschritt.
  Konsequenzen: `ops/automation/build.sh` erzeugt und chmodet die benoetigten Runtime-Verzeichnisse vor dem Compose-Start.

- Datum: 2026-03-18
  Entscheidung: Backup-Scheduler faengt Laufzeitfehler ab und beendet sich nicht dauerhaft beim ersten Fehler.
  Begruendung: Ein einzelner Schreib- oder IO-Fehler darf die gesamte geplante Backup-Funktion nicht stilllegen.
  Konsequenzen: Scheduler-Fehler landen im Log, der Task laeuft danach weiter.

- Datum: 2026-03-18
  Entscheidung: Frontend-Zugriffe laufen ueber Nginx mit SPA-Fallback sowie Proxy fuer `/api` und `/ws`.
  Begruendung: Das ausgelieferte Frontend-Bundle verwendet relative `/api/...`-Aufrufe und clientseitige Routen wie `/login`; ohne Proxy und `try_files` war der Compose-Gesamtlauf funktional unvollstaendig.
  Konsequenzen: `ops/docker/frontend.nginx.conf` ist nun Teil des produktiven Frontend-Images und muss bei Frontend-Anpassungen mitgedacht werden.

- Datum: 2026-03-18
  Entscheidung: Distribution und Deployments werden operativ ausschliesslich ueber Docker Hub gefahren; GitHub ist kein benoetigter Betriebsbaustein.
  Begruendung: Nutzerseitige Vorgabe ist Docker Hub als einzige Ablage und als Distribution Point.
  Konsequenzen: Release- und Upgrade-Prozeduren muessen lokal per Shell/Compose reproduzierbar sein; Doku und naechste Schritte duerfen keinen GitHub-Pflichtpfad mehr voraussetzen.

- Datum: 2026-03-18
  Entscheidung: Persistente Runtime-Daten werden standardmaessig unter `state/runtime/...` gehalten, nicht im Quellbaum.
  Begruendung: Code und laufende Daten muessen fuer verlustfreie Upgrades und saubere Docker-Hub-Deployments getrennt sein.
  Konsequenzen: Compose und Build-Automation verwenden jetzt `state/runtime/backend-data`, `state/runtime/backups` und `state/runtime/postgres`.

- Datum: 2026-03-18
  Entscheidung: Der Legacy-Watchlist-Migrationspfad darf bei nicht-SQLite-Datenbanken nicht mehr ausgefuehrt werden.
  Begruendung: Ein PostgreSQL-basierter Deploy oder Dump-Restore darf nicht an einem alten SQLite-Sidepath scheitern.
  Konsequenzen: `migrate_watchlists.py` ueberspringt den SQLite-Migrationspfad nun sauber bei nicht-SQLite-`DATABASE_URL` oder fehlender SQLite-Datei.

- Datum: 2026-03-20
  Entscheidung: Assetklassifizierung fuer Phase 1 wird zentral aus Provider-Metadaten mit heuristischen Symbol-Fallbacks abgeleitet.
  Begruendung: Suche, Scanner und Analyse brauchen sofort nutzbare Assetmetadaten, obwohl Providerzugriff und Frontend-Quellstand aktuell nicht in jedem Pfad vollstaendig verfuegbar sind.
  Konsequenzen: `asset_metadata.py` liefert die gemeinsame Klassifizierungslogik fuer `stock`, `etf` und `crypto`; API-Responses nutzen einheitliche Felder und koennen auch ohne Alpaca-Assetcache fuer symbolbasierte Requests sinnvoll antworten.

- Datum: 2026-03-20
  Entscheidung: Watchlist-Tags werden als eigene relationale Tabelle statt als Freitextfeld oder JSON-Spalte modelliert.
  Begruendung: Tags sollen spaeter fuer Filter, Alerts, News-Bindung und potenzielle UI-Gruppierung wiederverwendbar sein und muessen sauber exportierbar bleiben.
  Konsequenzen: `watchlist_item_tags` wird bei `init_db()` automatisch angelegt; Watchlist-Export/-Import und API-Responses tragen Tags nun explizit; Krypto-Symbole muessen in Watchlist-Item-Routen als `path`-Parameter behandelt werden.

- Datum: 2026-03-20
  Entscheidung: Watchlist-Alerts werden vorerst backend-seitig aus technischer Signalstaerke, News-Sentiment, News-Frische und Watchlist-Tags priorisiert.
  Begruendung: Der Frontend-Quellstand fehlt noch, aber Phase 1 braucht bereits eine nutzbare Alert-/Popup-Basis statt nur ungeordneter News-Listen.
  Konsequenzen: `/api/watchlists/{id}/alerts` liefert jetzt priorisierte Alert-Kandidaten; die Priorisierungslogik liegt isoliert in `watchlist_alerts.py` und ist host-seitig unit-getestet, kann spaeter aber mit produktiveren Providerdaten und UI-Feedback weiter kalibriert werden.

- Datum: 2026-03-20
  Entscheidung: Der Trading-Bot bekommt einen Bootstrap-Superadmin per Umgebungsvariablen statt eines hartcodierten Default-Kontos.
  Begruendung: Es braucht einen sicheren Erstzugang fuer Benutzerverwaltung und Admin-Endpunkte, aber globale Regeln verbieten Demo-Secrets oder fest eingebaute Standardpasswoerter.
  Konsequenzen: `INITIAL_ADMIN_EMAIL` und `INITIAL_ADMIN_PASSWORD` muessen fuer den Erstaufbau gesetzt werden; bei `INITIAL_ADMIN_MFA_ENABLED=false` ist der erste Login ohne OTP moeglich; der Seed-Pfad greift nur, wenn noch kein Admin existiert.

- Datum: 2026-03-23
  Entscheidung: Pushes nach `main` publizieren Docker-Hub-Images automatisch sowohl als `latest` als auch als unveraenderlichen `sha-<commit>`-Tag; Git-Tags `v*` publizieren weiterhin versionierte Release-Tags.
  Begruendung: Der Nutzer will die Git- und Registry-Synchronisierung ohne manuellen Nachlauf. Gleichzeitig muss der produktive Deploy-Pfad weiter an explizit nachvollziehbare Release-Tags gebunden bleiben.
  Konsequenzen: GitHub Actions wird zum kontinuierlichen Sync-Pfad fuer Integrationsstaende; `latest` ist nur ein beweglicher Integrationszeiger, produktive Upgrades bleiben bei expliziten Versionstags; fuer den Automatikpfad muessen funktionierende Docker-Hub-Secrets im Repository hinterlegt bleiben.
