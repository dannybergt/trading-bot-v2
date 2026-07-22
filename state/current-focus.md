# Current Focus

## Resume Codeword

Wenn der Nutzer nur dies schreibt:

`resume trading-bot-v2`

dann zuerst in genau dieser Reihenfolge lesen:

1. `state/current-focus.md`
2. `state/project-status.md`
3. `state/chat/session-log.md`

und danach ohne Rueckfragen an der unten beschriebenen Stelle fortsetzen.

## Port-Disziplin (Pflicht ab 2026-05-08)

Es laufen mehrere Claude-Agents parallel auf demselben Docker-Daemon. **Vor jedem Compose-/Regression-Lauf** zuerst pruefen:

```bash
docker ps --format '{{.Names}} {{.Ports}}' | grep -E '180[89]|181[0-9]{2}'
```

Trifft eine fremde Session schon einen Default-Port, eigene Skripte mit Env-Vars umlenken statt fremde Stacks zu killen:

- `BACKEND_PORT` / `FRONTEND_PORT` fuer den lokalen Devstack (Default 18090 / 18094)
- `PRIMARY_BACKEND_PORT` / `PRIMARY_FRONTEND_PORT` fuer `tests/run-api-regression.sh` und `tests/run-ui-regression.sh` (Default 18150/18154)
- `RESTORE_BACKEND_PORT` / `RESTORE_FRONTEND_PORT` fuer `tests/run-upgrade-rehearsal.sh` (Default 18160/18164)

Niemals `docker rm -f` oder `docker compose --force-recreate` auf scheinbar verwaiste Container loslassen — kann fremde Sessions kappen. Voller Hintergrund: `~/.claude/projects/-root/memory/feedback_trading_bot_v2_ports.md`.

## AUSGELIEFERT 2026-07-22: PR #8 gemergt @ 22ec0e9 (Ehrlichkeit + Gratis-Daten + Analystenkonsens + Provider-Haertung)

PR #8 nach `main` gemergt (ff-only), `publish.yml` + nexainer deployen auf BC-KI01. **Alle 5 Pflicht-Gates lokal GRUEN** (`verify-branch.sh`: build, unit 262, api-regression, ui-regression, upgrade-rehearsal) — auf diesem Sandbox-Host mit `docker build`-DNS + Chrome gefahren. 6 Commits: Mock-Ehrlichkeit, Gratis-yfinance-Daten (Charts+KPIs), Analystenkonsens (Anzeige), + drei Provider-Robustheit (Wall-Clock-Timeouts, Circuit-Breaker, voller yfinance-Sweep). Die Gate-Iteration deckte einen echten Prod-Bug auf und behob ihn: ungebundene yfinance/RSS-Calls liessen Provider-lastige Endpoints (`/api/research`, `/api/search`) unter Yahoo-Drossel >60s haengen → jetzt `app/net_timeout.py` (Wall-Clock + Provider-Circuit-Breaker, 60s Cooldown).
**Offen (User):** Live-Verifikation auf BC-KI01 (Backend `/api/health`, echte Aktien-Charts/KPIs ohne Key, Analystenkonsens-Karte, Mock-Banner bei Fantasie-Symbol).

## NAECHSTES GROSSES ZIEL: alle Signale sollen ECHT in die Kauf/Verkauf-Entscheidung einfliessen (Composite, Option C)

**User-Ansage (mehrfach, verbindlich):** Die Entscheidungen sollen wirklich ALLE verfuegbaren Infos/Quellen nutzen (Technical + Analystenmeinungen + Fundamentals + News + Makro), nicht nur anzeigen. Heutiger Stand (code-belegt, s. ADR 2026-07-22 "wie/warum gewichtet"): Empfehlung ist effektiv REIN TECHNISCH (ML-Ensemble aus 15 Indikatoren); News/Fundamentals sind kosmetische Broadcast-Features (~0 Beitrag); Analysten waren nur Anzeige. Ziel = echter gewichteter Composite-Score + Behebung der Broadcast-Schwaeche.

**Vorschlag-Fahrplan (mit User abzustimmen, mehrstufig, je eigener PR):**
1. Analystenkonsens erfassen + transparent zeigen — **ERLEDIGT** (dieser Slice, Divergenz-Badge).
2. Composite-Decision-Layer einfuehren: expliziter, gewichteter Score aus normalisierten Sub-Signalen (technical ML-P(UP), Analysten-stance/Upside, Fundamentals-Value-Score, News-Sentiment-Frische, Makro-Halt), jede Komponente mit sichtbarem Gewicht + Beitrag (Produktvision "explizite Wahrscheinlichkeiten + Quellen"). Ersetzt NICHT das ML, sondern kombiniert es mit den anderen Quellen zu einem nachvollziehbaren Verdict.
3. News/Fundamentals aus dem kosmetischen ML-Broadcast loesen (entweder echte rolling Features ODER raus aus dem ML und rein in den Composite-Layer als eigene Achsen).
4. Auto-Execution-Gates an den Composite-Score haengen (nicht nur ML-confidence).
Wichtig: Kalibrierung + Backtest je Stufe, sonst nur gefuehltes "nutzt alles". Grosser Umbau (>2h, §13) — Stufen einzeln reviewen.

## Erledigt 2026-07-22: Backlog #1 + Gratis-Daten-Fallbacks + Analystenkonsens (Anzeige) — auf Branch, Merge-Gate offen

**Zusatz diese Session (gleicher Branch `fix/synthetic-data-honesty`, NICHT gepusht):** Nach Rueckfrage des Users (woher echte Daten? Konto/Kosten? fehlende Fundamentaldaten/KPIs) zwei Gratis-Luecken geschlossen — beide mit **yfinance, kein Account/Key noetig**:
- **Aktien-Chart-Historie**: neue `get_yfinance_history_df` (daily/weekly), in `get_stock_data` vor dem synthetischen Fallback fuer `stock` + `1d/1wk` eingehaengt. Aktien-Charts sind jetzt ohne Alpaca-Key echt (Intraday braucht weiter Alpaca → ehrlich synthetisch mit Banner).
- **Fundamentals-KPIs** (KGV/KUV/KBV/EPS/Umsatz/Gewinn/ROE/Verschuldung/Dividende): neue reine Funktion `fundamentals_detail_from_ticker_info(info)`; im Research-Endpoint Fallback wenn FMP unkonfiguriert/leer. FMP bleibt Primaer (ISIN/WKN + datierte Income). Einheiten korrekt normalisiert (debtToEquity /100; Dividendenrendite aus `dividendRate/price` statt dem mehrdeutigen yf-Feld). Quelle-Label im UI dynamisch (`Quelle: FMP` / `Quelle: yfinance`).
- Tests: +3 (History-Fallback, KPI-Mapper-Einheiten, Yield-ohne-Preis). Suite **255 gruen**; `tsc` gruen.

**Datenlage kompakt (fuer den User):** Aktien = komplett gratis ohne Account (yfinance). ETF/Krypto-Historie = kostenloser Alpha-Vantage-Key. FMP/Twelve Data/FRED = optionale Gratis-Keys fuer mehr Tiefe. Alpaca = kostenloser Account fuer offiziellen Aktien-Feed (verdraengt yfinance-Fallback). Kein Provider ist kostenpflichtig noetig.

## Vorheriger Einstiegspunkt 2026-07-22: Backlog #1 (Mock-Daten-Ehrlichkeit)

**Erledigt diese Session (Branch `fix/synthetic-data-honesty`, NICHT gepusht):** Backlog-Punkt #1 aus dem Audit umgesetzt — synthetische Random-Walk-Daten werden jetzt gekennzeichnet und die Empfehlung unterdrueckt statt still ins ML zu fliessen. Aenderungen:
- `services.py`: `get_stock_data` fuehrt `used_synthetic`, gibt `synthetic: bool` zurueck; bei synthetisch → Prognose neutralisiert auf `HOLD/confidence 0.0/synthetic=True` (blockt Auto-Execution [nur UP/DOWN + conf>=0.6] und Push [conf>=0.80] automatisch).
- `main.py`: `/api/stock` reicht `synthetic` durch.
- `data_quality_service.py`: `synthetic` → `price_history` = FALLBACK (nie FULL/PARTIAL), zieht `overall` runter.
- `AnalysisPage.tsx` + `de.json`/`en.json`: deutlicher Warn-Banner (`analysis.synthetic.*`), kein Kauf-/Verkaufssignal mehr auf Platzhalterdaten.
- Tests: 2 neu (Service-Neutralisierung + Data-Quality-Downgrade). Volle Unit-Suite **252 gruen** (skipped=1); Frontend `tsc` gruen.

**OFFEN vor Merge:** api-/ui-Regression + upgrade-rehearsal in dieser Sandbox nicht lauffaehig (kein Docker-Netz/Chrome). Vor `main`-Push auf einem Docker-Host `bash ops/automation/verify-branch.sh` gruen ziehen — `main`-Push deployt ungated via nexainer auf BC-KI01. Erst dann `git checkout main && git merge --ff-only fix/synthetic-data-honesty && git push`.

**Naechster Schritt danach:** Backlog #2 (Watchlist-Delete-Bug reproduzieren→fixen) oder #4 (Verdict-Banner Feature B). Reihenfolge #3/#5 wie im Backlog unten.

## Vorige Session 2026-07-21 (Abend UTC): Deploy live + Produkt-Audit + Bug-/Feature-Backlog

**Deploy-Stand:** trading-bot-v2 laeuft jetzt produktiv auf BC-KI01 via nexainer (git-sync `main` + watchtower). Start ueber das neue Root-`docker-compose.yml` (Named Volumes, `.env` im Clone-Root `/data/trading-bot-v2/.env`, Mode 600). Beide heutigen PRs gemergt: Migrations-Haertung (`3f159d8`) + Root-Compose (`a4cb512`), `main` @ `a4cb512`, publish/ci gruen. Achtung: `.env.example` pinnt `IMAGE_TAG=2026.05.07-1` (alt) — der User hat auf `IMAGE_TAG=latest` gesetzt; **TODO** `.env.example`-Default auf `latest` fixen (Footgun).

**Produkt-Audit (zwei Explorer, belegt):** Fertigstellungsgrad + KI-Integration bewertet. Kernbefunde:
- KI = klassisches ML-Ensemble (XGBoost/LightGBM/RandomForest) + Sentiment (VADER/FinBERT). **KEIN LLM/RAG**; "Reasoning" = Template-Strings (`ml_models.py:414`).
- 🔴 **KRITISCH — Mock-Daten:** `services.py:329-331 _generate_mock_data()` speist bei fehlenden Providern erfundene Random-Walk-Kurse ins ML, **ohne Kennzeichnung** in der API-Antwort; `data_quality_service` stuft Mock faelschlich als FULL/high ein. Empfehlung kann auf Fantasiedaten beruhen.
- News/Fundamentals-ML-Features sind konstante Snapshots ueber die ganze Historie (`services.py:349,358-365`) → SHAP-Beitrag kosmetisch (erklaert "News +0.00 / Fundamentals +0.00" im UI).
- Ohne API-Keys (Alpaca/FMP/Alpha Vantage/FRED/Twelve Data — alle leer in `.env.example`) bleibt Grossteil der 14 Wellen leer → "fast alles missing". Frei-ohne-Key: yfinance, CoinGecko, StockTwits/Reddit, RSS-News, Fear&Greed, FX.
- Display-Currency nur in `AnalysisPage.tsx` verdrahtet — Scanner/PaperTrading/Dashboard/Admin/Alerts zeigen rohe USD.
- Phase 4f (echter Broker-Adapter) fehlt komplett → nicht echtgeld-produktiv.

**Priorisierter Backlog (Reihenfolge vom User noch zu bestaetigen — Vertrauen zuerst):**
1. 🔴 Mock-Daten-Ehrlichkeit: Response + Data-Quality als "synthetic/keine echten Daten" kennzeichnen, Verdict/Empfehlung dann unterdruecken/warnen.
2. 🐞 **Watchlist-Delete-Bug**: User kann Watchlist selbst nicht loeschen (Items schon). Backend-Route (`main.py:1532`) + ORM-Cascade sehen korrekt aus; Verdacht: Frontend (`WatchlistsPage.tsx:43`) verschluckt Delete-Fehler (kein `onError`) + `is_default`-Watchlist per 400 still gesperrt. **NOCH NICHT reproduziert/gefixt** — erst reproduzieren.
3. 💱 Display-Currency auf Scanner + restliche Money-Views ausrollen (Welle-15f-Rest).
4. 🧭 **Verdict-Banner (Feature B)** — bereits gemappt, bau-bereit: Felder liegen im Frontend vor (`prediction.direction/confidence/zones.meetsMinimum/zones.riskReward` + `/api/data-quality` `overall`); Banner in `AnalysisPage.tsx` vor Zeile 645 / in `PredictionCard` (788-928, aktuell komplett hart-englisch); i18n-Namespace `analysis.mlSignal.verdict.*` in `de.json`/`en.json` neu. Halt-Trigger (FOMC/Yield-Curve/8-K/Beta) waeren nur mit Backend-Zusatz drin (`_evaluate_halt_triggers` in auto_execution.py, aktuell proposal-gebunden).
5. Danach: A (App-Strings eindeutschen, backend-generierte englische Strings in `data_quality_service.py` u.a.), C (News auf Deutsch — eigene Design-Entscheidung Uebersetzer/Cache/Injection), spaeter Phase 4f.

Diese Session hat NICHTS an diesen 5 Punkten am Code geaendert — nur Deploy + Audit. Naechster Schritt: mit dem vom User gewaehlten Punkt starten (Reproduzieren→Root-Cause→Fix→Test).

## Zuletzt 2026-07-20: Persistenz-/Migrations-Haertung (Branch `refactor/harden-migrations`)

Diese Sitzung war KEIN Probelauf — User wollte "den Stand weiterbringen", Richtung "Struktur haerten (Migrationen)". Ergebnis auf Branch `refactor/harden-migrations`:
- CI-Drift-Gate `test_models_match_migration_head` (alembic check) + `test_all_models_registered_after_init` neu; init_db-Import-Liste auf 16/16 vervollstaendigt; `create_all`-Self-Heal jetzt fail-loud (error statt warning); 3 tote SQLite-Alt-Skripte geloescht.
- Gate fand echten Drift: Migration `0009` fehlte der `id`-Index → neue additive Migration `0010_add_platform_configuration_id_index` (head jetzt `f7a8b9c0d1e2`).
- Testsuite 250 gruen (Image-Mount-Lauf); `build.sh` in Sandbox nicht lauffaehig (kein Netzwerk). Details: `state/decisions.md` (2026-07-20), `state/chat/session-log.md`.
- **Lokaler Verify-Lauf (2026-07-21): ALLE 5 Gates gruen** — build backend+frontend, `test.sh` 250, api-regression, ui-regression, upgrade-rehearsal ("Upgrade rehearsal passed", inkl. Restore-in-frischen-Stack mit verifizierten Daten). Zwei Tooling-Fixes, die der Lauf offenlegte: (1) `SKIP_PULL`-Guard in `deploy.sh` (lokal gebaute Images ohne Docker-Hub-Pull deploybar); (2) `chmod 0777` der Rehearsal-Mount-Dirs in `run-upgrade-rehearsal.sh` — der Restore-Pfad zog den Backend per direktem `compose up` hoch und umging `prepare_runtime_dirs` (env.sh), sodass das root-owned `/app/data` den non-root-Backend beim `mkdir ml_models` crashen liess. Beides committet. Damit ist die Migration `0010` auch end-to-end gegen Backup/Restore auf echtem Postgres-Volume verifiziert.
- **Erledigt 2026-07-21**: PR #6 fast-forward nach `main` gemergt (`3f159d8`), `ci` + `publish` gruen, Images (`latest`+`sha-3f159d8`) auf Docker Hub. nexainer/watchtower deployt auf BC-KI01, Migration `0010` laeuft dort live. **Offen: Live-Verifikation auf BC-KI01** (Backend `/api/health`, Alembic-Head `f7a8b9c0d1e2`, Index `ix_platform_configuration_id` vorhanden) — macht der User, da diese Sandbox keinen Weg nach BC-KI01 hat. Optional post-publish `IMAGE_TAG=sha-3f159d8 run-upgrade-rehearsal.sh` vor einem `v*`-Release-Tag. Diese STATE-Aktualisierung ist bewusst NUR lokal committet (nicht gepusht), um kein redundantes publish/redeploy fuer eine Doku-Aenderung auszuloesen — reist mit der naechsten echten Aenderung mit. Die Pflicht-Pipeline konnte in der Sandbox nicht laufen (kein Docker-Netzwerk) und muss auf einem Docker-Host mit Netzwerk (+Chrome) VOR dem Merge nachgeholt werden — NICHT auf der BC-KI01-Deploy-Node und NICHT manuell dort git-fetchen: das Ausrollen macht nexainer (git-sync + watchtower) automatisch, sobald `main`/`latest` sich aendert, und deployt UNGATED auf das Produktiv-Postgres-Volume (Migration `0010` laeuft dann live). Darum muss besonders das upgrade-rehearsal VOR dem Merge gruen sein. One-Shot: `bash ops/automation/verify-branch.sh` (faehrt build→test→api-reg→ui-reg→lokale rehearsal, Abbruch beim ersten roten Gate; `SKIP_UI`/`SKIP_REHEARSAL` als geloggte Opt-outs). Erst bei allem gruen: `git checkout main && git merge --ff-only refactor/harden-migrations && git push origin main` → publish.yml → nexainer-Deploy; danach optional `IMAGE_TAG=sha-<commit> run-upgrade-rehearsal.sh` vor einem `v*`-Tag. Alternative Teilabdeckung ohne eigenen Build: PR oeffnen → `ci.yml` (Unit+CodeQL auf GitHub-Runnern, aber ohne ui-reg/rehearsal).

Der UI-Probelauf-Modus unten bleibt der stehende Default-Modus, sobald der User wieder testen statt bauen will.

## Naechster Einstieg: UI-Probelauf fortsetzen (Modus: User klickt, Claude reagiert)

**Wenn der User mit `resume trading-bot-v2` oder einer aehnlich kurzen Aufforderung wiederkommt: NICHT eigeninitiativ in eine neue Welle starten.** Der explizit gewaehlte naechste Schritt aus der Sitzung 2026-05-15 ist **UI-Probelauf**. Der User klickt selbst durch `http://localhost:18094` (Devstack laeuft mit Postgres-Volume persistiert; `superadmin@local.de` und `dannybergt@yahoo.de` als Login). Claude wartet auf konkrete Bug-Reports und faehrt Fix-Wellen (Pattern: 15g → 15h → 15i → 15j alle aus dem letzten Probelauf am 2026-05-13 entstanden).

Wenn der User stattdessen einen anderen Modus will, sagt er das am Anfang — die Optionen sind:
- **(Default) User klickt, Claude reagiert** — manuelles Testen, ich fixe was kommt
- **Automatischer Probelauf via CDP** — headless Chrome gegen den Devstack, systematischer Walk, Findings als Liste
- **Code-Audit der ungetesteten Pages** — NewsHub, Discover, Scanner, PaperTrading, AutoExecution, Settings, Onboarding gegen typische Schema-Drift-/Lazy-Load-/Defense-in-Depth-Klassen

Stack-Status beim Schluss der Sitzung 2026-05-15:
- BACKEND_PORT=18090, FRONTEND_PORT=18094 (Devstack laeuft mit `trading-bot-v2-{backend,frontend}:local`-Images)
- Postgres-Volume schema-konsistent (Welle 15j Self-Healing aktiv)
- ErrorBoundary in 3 Schichten verdrahtet (Welle 18) — jeder neue Crash bleibt jetzt lokal, kein Tree-Reset mehr
- `main` auf `6b9869a`, alle GitHub Actions gruen (ci/publish/codeql)
- Aktuell offene Backlog-Punkte (NICHT vorziehen ohne User-Go): Welle 17b Multi-line-Werte, Welle 16b N-BEATS, Phase 4f echter Broker-Adapter, Init-DB-Model-Imports vervollstaendigen, Section-Boundaries weiter ausrollen

Probelauf-Workflow-Pattern aus den letzten Wellen:
1. User berichtet Symptom mit Zitat ("die seite wird schwarz", "/admin ist leer", "500 auf /api/watchlists/.../alerts")
2. Claude reproduziert (Browser-DevTools-Probe oder direkter API-Call mit JWT via `docker exec trading-bot-v2-backend-1 python -c "from app.auth import create_access_token; from app.database import SessionLocal; from app.models import User; db=SessionLocal(); u=db.query(User).filter(User.id==1).first(); print(create_access_token(u.id, u.email))"`)
3. Root-Cause-Analyse mit Stacktrace oder Console-Error
4. Fix + Defense-in-Depth (z.B. `db.rollback()` plus Self-Healing) plus Test
5. Build + ops/automation/test.sh + API+UI-Regression
6. Commit + Push + Actions abwarten + State-Doku-Update als neue Welle (15k/15l/...)

## Vorige Sitzung 2026-05-15: Welle 18 — globaler React-ErrorBoundary

Welle 18 — Defense-in-Depth gegen den "Tree-Reset"-Klassiker, der bei Welle 15g (AdminPage blank) und 15i (AnalysisPage Scroll-Crash) jeweils die ganze App schwarz gemacht hat. Idee: ein einzelner Component-Crash darf nicht mehr den ganzen React-Tree mitreissen — der Rest der App muss weiter bedienbar bleiben.

Drei-Schicht-Boundary verdrahtet:
- **App-Level** (`src/frontend/src/main.tsx`): ErrorBoundary direkt um `<App />` als allerletztes Sicherheitsnetz — wenn das Layout selbst crasht (z.B. AuthContext-Bug), gibt es immer noch einen Fallback.
- **Layout-Level** (`src/frontend/src/components/Layout.tsx`): ErrorBoundary um den `<Outlet />`. Header + Navigation bleiben sichtbar, Page-Bereich kriegt Fallback-Card mit Retry- und Reload-Button.
- **Section-Level**: AdminPage (`UsersSection`, `DataSourcesSection`, `BackupsSection`, `ExportSection` — alle 4) und AnalysisPage `DataQualitySection` (die zwei realen Crash-Klassen 15g + 15i) bekommen kompakte Section-Fallbacks, sodass die jeweils anderen Sektionen der Page weiter rendern.

Komponente in `src/frontend/src/components/ErrorBoundary.tsx`: Class-Component mit `getDerivedStateFromError` + `componentDidCatch` (loggt mit Scope-Tag), `variant: "page" | "section"`-Prop fuer die zwei Fallback-Varianten, `scope`-Prop fuer Telemetry, optionale custom `fallback`-Render-Funktion. i18n-Keys `errorBoundary.{pageTitle,pageDescription,sectionTitle,sectionDescription,retry,reload}` in EN + DE.

Bewusst NICHT gemacht: Per-Sektion-Wraps auf den restlichen ~15 Sektionen von AnalysisPage. Layout-Boundary fängt jeden Page-Crash global ab — das Sub-Section-Wrap macht nur bei real beobachteten Crash-Klassen Sinn (15i = DataQualitySection). Wenn der UI-Probelauf weitere Sektion-Crashes findet, wrappt eine Folge-Welle die gezielt. Kein Frontend-Test-Framework eingefuehrt (kein vitest/jest im Repo) — Typecheck (`tsc -b`) und UI-Regression decken Happy-Path-Coverage.

Aktiver Stack weiterhin lokal (BACKEND_PORT=18090, FRONTEND_PORT=18094) gegen `trading-bot-v2-{backend,frontend}:local`-Images. Postgres-Volume persistiert + schema-konsistent (Self-Healing aus 15j).

Aktuell offen:
- **UI-Probelauf** fortsetzen mit der neuen Boundary-Sicherheit; jeder neue Bug ist jetzt nur eine Sektion, nicht der ganze Tree.
- **Welle 17b** — UI fuer Multi-line-Werte (RSS_NEWS_FEEDS verlangt mehrere `label|url`-Eintraege; aktueller Password-Input ist eine Zeile).
- **Welle 16b** — N-BEATS als zweites Time-Series-Modell (darts).
- **Phase 4f** — echter Broker-Adapter (User-Entscheidung: Bitvavo/Kraken zuerst, oder Lemon Markets, oder Interactive Brokers).
- **Init-DB-Model-Imports vervollstaendigen**: 13 von 16 Models werden in init_db importiert; AutoExecutionLimits, AutoExecutionEvent, PlatformConfiguration fehlen explizit (kommen indirekt via main-Imports rein).
- **Section-Boundaries weiter ausrollen**: AnalysisPage hat noch ~15 Sektionen (NewsSection, FundamentalsDetailSection, MacroContextSection, etc.) die alle externe Daten konsumieren — die zu wrappen ist Defense-in-Depth, falls neue Drift-Klassen auftauchen.

## Vorige Sitzung 2026-05-15: Welle 15j — Watchlist-Alert-500 + Schema-Drift-Self-Healing

Welle 15j — Root-Cause des Watchlist-Alert-500 aus dem Probelauf 2026-05-13 gefunden und gefixt: Postgres-Volume des User-Stacks war auf einer Codex-Era-DB initialisiert worden, deren init_db-Pfad 3 (`stamp_head_pre_existing_full_schema`) auf head stempelte ohne die Tabellen `watchlist_alert_settings` und `watchlist_alert_deliveries` aus Migration 0001 anzulegen — diese Models gab es im Codex-Build noch nicht. Folge: jeder `/api/watchlists/{id}/alerts`-Aufruf scheiterte an `psycopg.errors.UndefinedTable: relation "watchlist_alert_settings" does not exist`. Welle 15a's `try/except`-Wrapper griff zwar, aber der nachgeholte `len(record.items)`-Lazy-Load auf einer Session in Pending-Rollback-State warf eine **zweite** Exception ausserhalb des Wrappers — daraus wurde der harte 500.

Fix dreischichtig:
- `init_db` (database.py) bekommt nach jedem Alembic-Pfad ein `Base.metadata.create_all(bind=engine)`-Safety-Net mit `schema_drift_detected`-Warning-Log. Idempotent (CREATE TABLE IF NOT EXISTS), legt nur Tabellen an die im Models-Set sind aber in der DB fehlen. Repariert die existierenden Codex-Volumes self-healing beim naechsten Container-Start.
- Endpoint `/api/watchlists/{id}/alerts` (main.py): `try/except`-Wrapper bekommt `db.rollback()` plus eine defensive `len(record.items)`-Eindeckung. Damit wird auch ein Folge-Crash auf einer dirty Session oder ein lazy-load-Fehler zum degraded payload statt 500.
- Tests: `test_alembic_init.test_drift_at_head_is_self_healed` (Subprocess + SQLite, simuliert exakte Drift-Situation: alembic_version=head, zwei Tabellen weg, init_db laeuft, Tabellen wieder da). `test_watchlist_alerts.WatchlistAlertEndpointRobustnessTests` (Mock-basiert, deckt RuntimeError + ProgrammingError-Pfad + record.items-Lazy-Crash ab, asserted db.rollback wurde gerufen).

Repro-Pfad fuer kuenftige Sessions: `docker exec trading-bot-v2-backend-1 python -c "from app.auth import create_access_token; from app.database import SessionLocal; from app.models import User; db=SessionLocal(); u=db.query(User).filter(User.id==1).first(); print(create_access_token(u.id, u.email))"` liefert einen JWT fuer User 1 (`superadmin@local.de`); damit lassen sich alle authentifizierten Endpoints ohne Login-Form testen.

Aktiver Stack laeuft weiterhin lokal (BACKEND_PORT=18090, FRONTEND_PORT=18094) gegen `trading-bot-v2-{backend,frontend}:local`-Images. Postgres-Volume persistiert + jetzt schema-konsistent (selbst nach erzwungenem `DROP TABLE` heilt der naechste Container-Start die Drift). Endpoint `/api/watchlists/7433d431/alerts` liefert wieder `200 OK` mit 4 Items.

Aktuell offen:
- **UI-Probelauf** fortsetzen; weitere Feedback-Wellen 15h+/17b+ absehbar.
- **Welle 17b** — UI fuer Multi-line-Werte (RSS_NEWS_FEEDS verlangt mehrere `label|url`-Eintraege; aktueller Password-Input ist eine Zeile, das ist nicht ideal).
- **Welle 16b** — N-BEATS als zweites Time-Series-Modell (darts).
- Phase 4f echter Broker-Adapter (User-Entscheidung welcher Broker zuerst).
- **Welle 18** — globaler React-Error-Boundary, damit ein einzelner Component-Crash nicht den ganzen Page-Tree killt (war Diagnose-Schmerz bei 15g + 15i).
- **Init-DB-Model-Imports vervollstaendigen**: 13 von 16 Models werden in init_db importiert; AutoExecutionLimits, AutoExecutionEvent und PlatformConfiguration fehlen explizit (kommen indirekt via main-Imports rein). Risikoarmer Cleanup, aber besser nicht-implizit.

## Naechster Einstieg 2026-05-13: Welle 17 ausgeliefert + UI-Probelauf laeuft

Welle 17 — Platform-Configuration-UI-Schicht aus dem Probelauf-Feedback geboren: globale Operator-API-Keys (Alpha Vantage, FMP, Twelve Data, CoinGecko, FRED, RSS-Feeds, Sentiment-Provider) sind jetzt direkt aus `/admin` heraus konfigurierbar statt nur via `.env.local`. Allowlist `MANAGED_KEYS` schliesst Bootstrap-Secrets (JWT, APP_ENCRYPTION_KEY, INITIAL_ADMIN, POSTGRES, VAPID) bewusst aus. Werte sind Fernet-encrypted at rest (gleicher `encrypt_secret`-Wrapper wie Alpaca-Keys), Read-Order DB > env > None, 60s-Cache mit expliziter `invalidate()`. Alembic-Migration `0009_add_platform_configuration` (rev `e6f7a8b9c0d1`). UI: DataSourcesSection bekommt "Configure"-Button pro managed Provider, Modal mit Password-Input + Save + Save&Test + Unset. Audit-Events `platform_config.update`/`.delete` loggen Key-Name (NICHT Value, NICHT Fingerprint).

Welle 15g — AdminPage-Blank-Screen-Bug aus Probelauf 2026-05-13 gefixt: `/api/admin/backups` liefert `{items: [...]}`, Frontend rief `.map()` direkt → unhandled TypeError → React reisst den Tree ab. Fix in 3 Zeilen `AdminPage.tsx`, plus UI-Regression-Assertion gegen "Backups"-Heading + Korrektur des veralteten `React.lazy`-Skip-Kommentars.

Aktiver Stack laeuft weiterhin lokal (BACKEND_PORT=18090, FRONTEND_PORT=18094) gegen `trading-bot-v2-{backend,frontend}:local`-Images. Postgres-Volume persistiert. Alembic-Head jetzt `e6f7a8b9c0d1`. 2 Admin-User existieren (`superadmin@local.de`, `dannybergt@yahoo.de`), 4 Watchlists. 243 Unit-Tests OK (+12 platform_config seit Welle 16a).

Zweiter offener Befund aus dem Probelauf (noch nicht gefixt): `GET /api/watchlists/{id}/alerts` liefert HTTP 500 fuer Watchlist `7433d431`. Backend-Stacktrace ist im Container-Log einsehbar — naechster konkreter Fix-Kandidat sobald der User weiter klickt.

Aktuell offen:
- **Watchlist-Alert-500** auf `/api/watchlists/{id}/alerts` analysieren + fixen.
- **UI-Probelauf** fortsetzen; weitere Feedback-Wellen 15h/17b+ absehbar.
- **Welle 17b** — UI fuer Multi-line-Werte (RSS_NEWS_FEEDS verlangt mehrere `label|url`-Eintraege; aktueller Password-Input ist eine Zeile, das ist nicht ideal).
- **Welle 16b** — N-BEATS als zweites Time-Series-Modell (darts).
- Phase 4f echter Broker-Adapter.
- **Welle 18** — globaler React-Error-Boundary, damit ein einzelner Component-Crash nicht den ganzen Page-Tree killt (war Diagnose-Schmerz bei 15g).

## Naechster Einstieg 2026-05-12: Welle 16b/c oder UI-Probelauf

User hat den ersten echten UI-Probelauf am 2026-05-13 gestartet (lokaler Stack auf `trading-bot-v2-backend:local`+`trading-bot-v2-frontend:local`, gepuncht via direktes `docker compose up -d` weil `dbergt/trading-bot-backend:latest` aktuell nur per `docker login` ziehbar ist und der lokale Klon 3 Wochen alt war). Erster Bug-Fund: `/admin`-Seite rendert komplett schwarz. Ursache war ein API-Schema-Drift: `GET /api/admin/backups` liefert `{"items": [...]}`, `AdminPage.BackupsSection` rief `.map()` auf das Wrapper-Objekt → `TypeError: (n.data ?? []).map is not a function` → React reisst den gesamten Tree ab. Fix: Query-Type auf `{items: BackupListItem[]}`, `const backups = backupsQuery.data?.items ?? []`, Renderpfad nutzt `backups`. UI-Regression assertiert jetzt zusaetzlich das "Backups"-Heading, damit ein Re-Drift nicht wieder als `ui_admin best_effort_skipped` durchrutscht. Der veraltete `React.lazy`-Kommentar im UI-Regression-Code ist mitkorrigiert (AdminPage ist seit l. mehreren Wellen kein Lazy-Chunk mehr).

Aktiver Stack laeuft weiterhin lokal (BACKEND_PORT=18090, FRONTEND_PORT=18094). Postgres-Volume ist persistiert, Alembic ist auf head (`0008_add_user_display_currency`, rev `d5e6f7a8b9c0`). 2 Admin-User existieren (`superadmin@local.de`, `dannybergt@yahoo.de`), 4 Watchlists ("Tech Giants"+"Crypto Proxies" pro User mit AAPL/MSFT/NVDA/GOOGL bzw. COIN/MSTR/MARA).

Zweiter offener Befund aus dem Probelauf (noch nicht gefixt): `GET /api/watchlists/{id}/alerts` liefert HTTP 500 (mehrfach gesehen fuer Watchlist `7433d431`). Stacktrace noch nicht eingeholt — naechster Schritt wenn der User weiter macht.

Aktuell offen:
- **Watchlist-Alert-500** auf `/api/watchlists/{id}/alerts` analysieren + fixen (Backend-Stacktrace noetig).
- **UI-Probelauf** weiterlaufen lassen; weitere Feedback-Wellen 15g+ sind absehbar.
- **Welle 16b** — N-BEATS als zweites Time-Series-Modell (darts). Vergleich zum XGBoost+LightGBM+RF-Ensemble.
- **Welle 16c** — UI-A/B-Switch zwischen Modellen + Backtest-Vergleichstabelle.
- Phase 4f echter Broker-Adapter (braucht User-Entscheidung welcher Broker zuerst).

## Naechster Einstieg 2026-05-12: Welle 16b/c oder UI-Probelauf

Welle 15b-15f komplett: Dashboard-KPIs klickbar + DE-Hilfe (15b), Fundamentals-Vollausbau (15c), Datumsfilter Chart-MAX + Trade-Journal (15d), native Currency pro Asset (15e), User-Display-Currency + FX-Konvertierung (15f). Damit ist die komplette 15er-Welle aus dem User-Feedback durch.

Welle 15f Details: FX-Service via frankfurter.app (ECB-Reference-Rates, kein API-Key, 60min Cache), neuer `GET /api/fx/rates?base=USD`-Endpoint, User-Model um `display_currency` (Alembic 0008) erweitert, Frontend hat `useDisplayCurrency` + `useFxRates` + `convertMoney`-Helper, SettingsPage hat einen Currency-Dropdown, AnalysisPage-Quote-Header zeigt konvertierten Wert + Native-Wert als Hint. Die weitere UI-Migration (PaperTrading-Journal, Dashboard-Werte, FundamentalsSection) bleibt bewusst offen — das ist Inkrement und kann pro Welle einzeln nachgezogen werden.

Aktuell offen:
- **Welle 16b** — N-BEATS als zweites Time-Series-Modell (darts). Vergleich zum XGBoost+LightGBM+RF-Ensemble.
- **Welle 16c** — UI-A/B-Switch zwischen Modellen + Backtest-Vergleichstabelle.
- **UI-Probelauf** mit dem User (immer noch nicht durchgefuehrt).
- Phase 4f echter Broker-Adapter (braucht User-Entscheidung welcher Broker zuerst).

Phase 4e-paper (Auto-Paper-Trading-Loop) ist ausgeliefert und in `main`. Der User hat das Tool **noch nie selbst angeschaut** — UI-Probelauf-Anleitung waere weiterhin ein guter Einstieg.

**Wichtige Klarstellung:** Alpaca ist NICHT der echte Broker des Operators. Alpaca diente bisher nur als Paper-/Quotes-Source. Der `mode=live`-Pfad ist deshalb aktuell **kein produktiver Pfad fuer echte Geld-Trades**, sondern nur Code-Path-Test gegen die Alpaca-Live-Tier. Phase 4f (echter Broker-Adapter) braucht zuerst eine User-Entscheidung welcher Broker (Trade Republic / Comdirect / Scalable / Interactive Brokers / ...).

Empfehlung beim naechsten Resume:

- **UI-Probelauf** ist der ehrlichste naechste Schritt: der User hat das Tool noch nie selbst gesehen.
- Wenn weiterer Code-Aufbau: **Welle 15d** (Datumsfilter zuerst, Multi-Currency danach) — beides aus der gleichen User-Feedback-Runde. Datumsfilter ist klein, Multi-Currency ist mittelgross.
- ML-Track: **Welle 16b** (N-BEATS) macht die Predictions-Tiefe vergleichbar, ist aber tief technisch.

Parallel-Wellen wie bisher offen:
- **Welle 13 FinBERT-Image-Variant** — `dbergt/trading-bot-backend-finbert` als zweite Build-Stage fuer Premium-Sentiment.
- **Welle 11 Phase B** — Capacitor + Biometric + App-Store fuer echte Native-App.
- **Phase 5+** — UX-Verfeinerung, Multi-Account, Backtesting-UI.

Wichtige Doku-Quellen vor dem Start nochmal kurz lesen:

- `docs/admin/project-plan.md` Sektion "Naechste Prioritaeten" + "Phase 4" + "Sicherheitsachsen"
- `state/decisions.md` Decision-Bloecke 2026-05-08 (Welle 12, Welle 11, Welle 10, Welle 9b, Data-Source-Transparency, Welle 9a, In-App-Hilfe)
- `src/backend/app/paper_trading.py` als Pattern-Referenz (Order-Lifecycle, Net-Yield-Gate) fuer Phase-4-Auto-Execution
- `src/backend/app/alpaca_service.py::submit_order` als Broker-Pfad fuer echte Auto-Trades



- **ML-Persistenz + Backtest** (Phase-4-Vorbedingung)
- **Audit-Log + Daily-Re-Train-Task** (Phase-4-Vorbedingung)
- **In-App-Hilfe + Online-Doku** auf direkten User-Wunsch

User hat zusaetzlich diese drei Themen aufgemacht und in den Plan aufgenommen:

- **Welle 9**: dedizierter News-Hub `/news` (Menuepunkt, chronologisch, alle Quellen inkl. RSS-Feeds wie boerse.de/ariva.de/Reuters)
- **Welle 10**: Security-Welle (Container-Image-Scan, CSP/HSTS, Upload-MIME-Validation, Per-User-Login-Rate-Limit)
- **Welle 11**: Android via PWA (Phase A: Manifest+Service-Worker; Phase B: Capacitor+Biometric)

Naechster konkreter Schnitt = **Welle 9 News-Hub**:

1. Backend: neuer `GET /api/news/feed?limit=&offset=&symbol=&source=&sentiment=&since=` aggregiert Alpaca-News + FMP-News + Alpha-Vantage-NEWS_SENTIMENT-Items ueber alle Watchlist-Symbole, plus optional ein paar RSS-Feeds (boerse.de, ariva.de, Reuters). Modul-Cache 5 min, sortiert by Timestamp desc.
2. RSS-Adapter `app/rss_news_service.py`: parsed RSS-Feeds (z.B. via `feedparser` oder selbst XML), normalisiert auf das gleiche News-Item-Format (title, summary, url, source, timestamp, score, label). VADER auf Title+Summary fuer Sentiment.
3. Frontend `NewsHubPage` (`/news`): chronologische Liste, Filter-Dropdowns (Symbol, Source, Sentiment, Time-Window), Pagination. Per-Item Sentiment-Badge.
4. Layout-Nav-Eintrag "News".
5. Help-Topic `news.md` mit Erklaerung der Quellen + Filter.

Wichtige Doku-Quellen vor dem Start nochmal kurz lesen:

- `docs/admin/project-plan.md` Stand 2026-05-08 + "Naechste Prioritaeten" + "Phase 4"
- `state/decisions.md` letzte vier Decision-Bloecke (In-App-Hilfe, Audit, ML-Persistenz, Phase-3-Slippage)
- `src/backend/app/services.py::MarketDataService.get_market_news` als Pattern fuer den Aggregator
- `docs/inapp/*.md` als Vorlage fuer das neue news.md



- Phase 3 Paper-Trading **komplett** (vier Schnitte: Erststand, Background-Fill+Chart-Marker+Recommendation-Verlinkung, asset-spezifische Slippage, dynamische Slippage + Fee-Multipliers)
- Datenbasis-Wellen 1-8: FMP-Signale + Macro-Kontext, VADER-Sentiment, CoinGecko + Fear-and-Greed, StockTwits + Reddit, Earnings-Call-Digest, Options-Flow, FinBERT-Premium-Schalter (opt-in), Twelve Data fuer Non-US
- Release-Tag `v2026.05.08-1` gesetzt + Upgrade-/Restore-Rehearsal bestanden

Phase 3 ist damit aus Daten-/Simulation-Sicht ehrlich genug fuer den Phase-4-Aufsatz. Naechster grosser Block:

**Phase 4 Auto-Execution** — wenn der Nutzer das jetzt freigeben will:

1. **Risk-Modell**: neue Tabelle `auto_execution_limits` mit pro-User-Limits: max-Position-Size in USD, max-DailyLoss, max-OpenPositions, allowed-Asset-Classes. Per-Strategie-Budget (z.B. "Trend-Following 50% des Auto-Capitals"). Audit-Log-Tabelle `auto_execution_events` fuer jeden Auto-Trade-Versuch (accepted/rejected/executed/failed mit Begruendung).
2. **Manuelle Freigabelogik**: Setting `auto_execution_enabled` pro User + pro Asset-Klasse oder Strategie. Default off. UI-Schalter mit Bestaetigungs-Dialog ("Ich verstehe dass dieser Schalter echte Trades ausloest"). Net-Yield-Gate UND Risk-Modell muessen UND-verknuepft pass-en.
3. **Not-Aus**: Endpoint `POST /api/auto-execution/halt` der alle Auto-Strategies sofort deaktiviert + offene Limit-Orders bei Alpaca cancelt. UI-Button "Stop all automation" fuer Notfall.
4. **Broker-Fehlerpfade**: Reconciliation-Task der Alpaca-Order-Status periodisch gegen lokale Datenbank abgleicht; bei Discrepancy (z.B. Alpaca filled, lokal pending) korrigieren. Recovery bei Connection-Errors mit exponentiellem Backoff.

**Datenbasis Welle 9 (optional)**

5. FinBERT-Image-Variant `dbergt/trading-bot-backend-finbert` als zweite Build-Stage im Dockerfile.

**Datenbasis Welle 10**

6. SEC-Filings (10-K/Q/8-K) via FMP `/sec_filings/{symbol}`.
7. Macro-Calendar via FRED API (Fed Funds, CPI, Non-Farm-Payrolls).
8. Insider-Cluster-Detection in der existierenden ResearchSignalsSection.

**Empfehlung beim naechsten Resume**: Phase 4 ist der grosse, gefaehrliche Block. Eine Wahl-Frage an den User stellen:

- A) **Phase 4 jetzt anfangen** (Risk-Modell zuerst, Auto-Execution-Logik danach)
- B) **Welle 10 zuerst** (mehr Datenbasis vor Auto-Execution; defensiver)
- C) **Welle 9 (FinBERT-Image-Variant)** als Aufwaerm-Aufgabe

Wichtige Doku-Quellen vor dem Start nochmal kurz lesen:

- `docs/admin/project-plan.md` Sektion "Phase 4" + "Sicherheitsachsen" + "Architekturachsen"
- `state/decisions.md` Decision-Bloecke 2026-05-08 zu Phase-3-Abschluss + allen acht Datenbasis-Wellen
- `src/backend/app/paper_trading.py` als Pattern-Referenz (Order-Lifecycle, Net-Yield-Gate) fuer den Phase-4-Auto-Execution-Service
- `src/backend/app/alpaca_service.py::submit_order` als Broker-Pfad fuer echte Auto-Trades

## Stand Beim Letzten Handover

- Aktueller Release-Stand: `v2026.05.07-1` auf Commit `878fcff` (`Record VAPID hardening publish status`) ist gepusht, GitHub-Actions-`publish` run `#21` lief erfolgreich und synchronisierte die versionierten Docker-Hub-Tags.
- Docker-Hub-Rehearsal fuer `IMAGE_TAG=2026.05.07-1` lief erfolgreich: initialer Deploy, Datenanlage, Upgrade ueber bestehenden Datenbestand, Pre-Upgrade-PostgreSQL-Dump, App-Snapshot und Dump-Restore in einen frischen Stack.
- Rehearsal-Artefakte: Deployment-Record `state/runtime/deployments/deployment-20260507T120020Z.env`; Backend-Digest `sha256:835f50167496e5bc0fd6e83bdea86bed386590fe88cf71506d759db1380aa4bf`; Frontend-Digest `sha256:f66fe7516f6764bf8a69bd1b920250895013521c73ab6b978165d6846c813d12`.
- Gesamtplan-Verankerung: `docs/admin/project-plan.md` beschreibt aktuellen Release, Phasenposition, Sicherheitsachsen, Architekturachsen und Prioritaeten; README, Roadmap, Release- und Security-Doku wurden darauf ausgerichtet.
- Aktueller lokaler Security-Stand: produktive Push-/VAPID-Konfiguration wurde ohne Code-Defaults gehaertet; Backend und Frontend nutzen keine eingebetteten Default-VAPID-Keys mehr.
- Neue Backend-Pfade:
  - `PushService.validate_configuration()` prueft `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIMS_SUB` und erzwingt sie bei `APP_ENV=production` oder `REQUIRE_VAPID_SECRETS=true`
  - `/api/auth/push/config` liefert Browsern nur `configured` und den oeffentlichen VAPID-Key
  - Web-Push-Versand wird bei fehlender lokaler VAPID-Konfiguration uebersprungen statt mit geteilten Defaults zu senden
- Neuer Smoke: `tests/run-push-config-smoke.sh`; Standardmodus validiert echte Zielkonfiguration ohne Nutzergeraete zu benachrichtigen, `GENERATE_TEST_VAPID=1` prueft den Parser mit einem disposable Keypair.
- Verifikation: `bash ops/automation/build.sh`, `bash ops/automation/test.sh`, `GENERATE_TEST_VAPID=1 bash tests/run-push-config-smoke.sh`, `SKIP_BUILD=1 bash tests/run-api-regression.sh`, `SKIP_BUILD=1 bash tests/run-ui-regression.sh`; ein UI-Zwischenlauf scheiterte transient am bekannten externen Daten-/Navigationspfad, der direkte Wiederholungslauf war gruen.
- Commit `21b970a` (`Harden VAPID push configuration`) wurde nach `main` gepusht; GitHub Actions liefen erfolgreich:
  - `ci` run `#24` / `25488743824`
  - `publish` run `#19` / `25488743838`
  - `codeql` run `#30` / `25488743817`
- Lokale Ziel-VAPID-Werte wurden in der gitignorierten `.env.local` erzeugt, Modus `600`; Werte wurden nicht ausgegeben. `bash tests/run-push-config-smoke.sh` validierte diese Konfiguration erfolgreich.
- Naechster sinnvoller Schritt: den Release-/Rehearsal-Status committen und nach `main` pushen; danach weitere Phase-1-Produktarbeit oder bei Bedarf ein Live-Smoke mit gesetztem Alpha-Vantage-Key gegen `2026.05.07-1`.

- Aktueller lokaler Produkt-Stand: Serverseitiger Watchlist-Alert-Dispatcher umgesetzt; Watchlists mit aktivem `pushEnabled` werden periodisch ausgewertet und erfolgreiche Web-Push-Zustellungen persistent dedupliziert.
- Neue Tabelle `watchlist_alert_deliveries` speichert pro Nutzer, Watchlist, Symbol, Channel, Alert-Key, Prioritaet und Zeitstempel die Zustellhistorie; Backup/Export/Import sichern diese Historie mit.
- Der Alert-Feed-Aufbau ist jetzt als gemeinsame Payload-Funktion wiederverwendet, sodass API und Dispatcher dieselbe Priorisierung, Settings-Auswertung und `notification.pushEligible`-Logik nutzen.
- Verifikation: `bash ops/automation/build.sh`, `bash ops/automation/test.sh`, `SKIP_BUILD=1 bash tests/run-api-regression.sh`, `SKIP_BUILD=1 bash tests/run-ui-regression.sh`; `ci #21`, `codeql #27` und `publish #15` fuer `ec48455` erfolgreich.

- Aktueller lokaler Produkt-Stand: Watchlist-Alert-Management umgesetzt; pro Watchlist gibt es persistente Alert-Settings fuer Alerts an/aus, Popups, Push-Bereitschaft, Mindestprioritaet und Mindestscore.
- `/api/watchlists/{id}/alerts` annotiert Alert-Items jetzt mit `notification.popupEligible`/`pushEligible` und liefert `alertSettings` sowie `notificationPlan`; Backup/Export/Import sichern `watchlist_alert_settings`.
- Das Dashboard rendert ein `Alert Management`-Panel im Watchlist-Bereich und koppelt In-App-Popups an die gespeicherten Einstellungen.
- Verifikation: `bash ops/automation/test.sh`, `bash ops/automation/build.sh`, `SKIP_BUILD=1 bash tests/run-api-regression.sh`, `SKIP_BUILD=1 bash tests/run-ui-regression.sh`; UI bestaetigt `ui_watchlist_alert_management ok`.
- Naechster Schritt nach Push/Actions: Alert-Ausloesung serverseitig periodisch/dedupliziert machen oder einen expliziten Release-Tag mit Upgrade-/Restore-Rehearsal fahren.

- Aktueller lokaler Produkt-Stand: Symbol-Research-Schnitt fuer `/api/research/{symbol}` plus UI-Panel `Provider Research` auf `/analysis/<symbol>` umgesetzt und lokal verifiziert
- Verifikation: `bash ops/automation/test.sh`, `bash ops/automation/build.sh`, `SKIP_BUILD=1 bash tests/run-api-regression.sh`, `SKIP_BUILD=1 bash tests/run-ui-regression.sh`
- Die API-Regression prueft jetzt Crypto- und ETF-Research-Kontext; die UI-Regression bestaetigt `ui_symbol_research ok`
- Naechster Schritt nach Push/Actions: entweder GitHub-Actions-Lauf fuer diesen Commit beobachten oder als naechsten Produktschnitt echte Nutzer-Alerts/Popup-Alert-Management aus dem vorhandenen Watchlist-Alert-Feed bauen

- Aktueller Produkt-Commit auf `main`: `df6f0fa` (`Surface provider coverage in watchlist alerts`)
- Letzter gepruefter GitHub-Actions-`publish`-Run: `#10`
- Run-Link: `https://github.com/dannybergt/trading-bot-v2/actions/runs/24461808225`
- Run-Zeitpunkt: Start `2026-04-15 14:59:28 UTC`, Ende `2026-04-15 15:02:40 UTC`
- Ergebnis: Build/Test/API/UI, `Validate Docker Hub secrets`, `Log in to Docker Hub`, `Sync primary image tag` und `Sync latest image tag` liefen erfolgreich durch
- Ebenfalls fuer `df6f0fa` erfolgreich: `ci` run `24461808223`, `codeql` run `24461808224`
- Der Parserfix-Stand `sha-f826304a7850` wurde live-smoke- und upgrade-/restore-validiert; der nachfolgende Script-/Doku-Follow-up und der Provider-Coverage-Produktschnitt sind gepusht und durch Actions bestaetigt.

## Aktueller Unterbrechungspunkt 2026-05-07 Frontend-Paritaetsschub

- Nach erfolgreicher Codex-Uebergabe, Alert-Rule-Migration aus Sandbox, und Alembic-Einfuehrung wurde der Frontend-Quellstand-Wiederaufbau substanziell vorangezogen.
- Neuer `src/frontend/`-Quellstand deckt jetzt zehn Pages ab (Login, Register, ForgotPassword, ResetPassword, Dashboard, Watchlists, Scanner, Analysis, Alerts, Settings, Admin).
- Production laeuft unveraendert ueber `src/frontend-dist`-Bundle; Swap des `ops/docker/frontend.Dockerfile` wartet bewusst auf koordinierte UI-Regression-Umschrift.
- Naechster sinnvoller Schritt:
  - Bei Bedarf weitere Pages (Alpaca-Account/-Positions, Watchlist-Alert-Settings-UI) ergaenzen
  - Danach koordinierter Swap: `ops/docker/frontend.Dockerfile` auf Vite-Multi-Stage-Build umstellen UND `tests/run-ui-regression.mjs` auf neue React-Selektoren umschreiben (gleicher Commit, damit der Swap nicht im Voraus rotbricht)
  - `src/frontend-dist`-Bundle nach erfolgreichem Swap entfernen
  - Erst danach: Phase-3 Paper-Trading beginnen

## Aktueller Unterbrechungspunkt 2026-05-07 Uebergabe Codex -> Claude

- Vollstaendige Projektuebernahme abgeschlossen; Architektur, Phasenposition und State-Pflegeworkflow uebernommen.
- Ehemals divergente Sandbox `/root/trading-bot-v2-work` enthielt eine WIP-Alert-Domaene; Inhalt wurde an `-v2`'s zwischenzeitlich erweiterte Alert-Setting-Schicht angepasst und integriert.
- Lokale Verifikation: `bash ops/automation/test.sh`, `SKIP_BUILD=1 bash tests/run-api-regression.sh` und `CHROME_BIN=/usr/bin/google-chrome SKIP_BUILD=1 bash tests/run-ui-regression.sh` erfolgreich (UI-Lauf nach einem transienten Yahoo-429-Reset).
- Vom Nutzer freigegebene neue Arbeitsweise:
  - voll automatischer Sync nach `origin/main` UND Docker Hub inklusive Release-Tags `v*` (nach Rehearsal)
  - Frontend-Strategie wechselt von Patch-Schicht auf echten Vite/React-Quellstand-Wiederaufbau
  - security-review als Standardschritt nach jedem nicht-trivialen Code-Schnitt
  - `CLAUDE.md` und Pre-commit-Hook als Sicherheits-Guardrails verankert
- Naechster sinnvoller Schritt:
  - Sandbox `/root/trading-bot-v2-work` nach erfolgreicher Push-Bestaetigung loeschen
  - Alembic-Migrationen einfuehren (Phase-0-Restpunkt)
  - Vite/React-Quellstand unter `src/frontend/` neu aufbauen, am bestehenden Bundle orientiert; Alert-Rule-UI als erste Komponente
  - Provider-Abdeckung fuer ETF/Krypto/Stocks weiter ausbauen

## Aktueller Fokus

- Nicht mehr am Build-Hook, an den Regressionen oder am Docker-Hub-Login arbeiten; diese Huerden sind fuer den aktuellen Stand genommen.
- Der automatische GitHub-Actions-Publish-Pfad ist mit echten Secrets live bestaetigt.
- Der veroeffentlichte `sha-d4939da591ec`-Stand ist durch ein Upgrade-/Restore-Rehearsal als deploybar bestaetigt; der neuere Parserfix-Stand `sha-f826304a7850` ist ebenfalls live-smoke- und upgrade-/restore-validiert.
- Der Alpha-Vantage-BTC-Liveblocker ist behoben: `DIGITAL_CURRENCY_DAILY` liefert fuer `BTC/USD` aktuell generische OHLC-Keys (`1. open`, `2. high`, `3. low`, `4. close`) statt der alten waehrungsspezifischen Keys; der Parser akzeptiert jetzt beide Formen.
- Das Upgrade-Rehearsal ignoriert fuer seine isolierten Wegwerf-Stacks jetzt reale `INITIAL_ADMIN_*`-Werte aus `.env`, damit eine lokale Zielumgebungs-Konfiguration den Test-Admin-Seed nicht entprivilegiert.
- Naechster sinnvoller Schritt ist:
  - echte Zielumgebungs-VAPID-Werte per `tests/run-push-config-smoke.sh` validieren, sobald sie gesetzt sind
  - optional danach Live-Smokes fuer den neuen Release-Stand mit gesetztem Alpha-Vantage-Key fahren

## Wichtiger Kontext

- Der neue ETF-/Krypto-Providerpfad ist bereits implementiert und lokal verifiziert.
- In `/root/trading-bot-v2-work/.env` ist ein `ALPHA_VANTAGE_API_KEY` gesetzt; Werte wurden nicht ausgegeben und duerfen auch kuenftig nicht geloggt werden.
- `tests/run-alpha-vantage-live-smoke.sh` bricht ohne gesetzten Key bewusst ab, ohne den Key-Wert auszugeben.
- Der bereits veroeffentlichte Docker-Hub-Stand `sha-d4939da591ec` enthaelt den BTC-Parserfix noch nicht; Live-Smokes fuer diesen alten Stand koennen bei `BTC/USD` weiter am History-Parsing scheitern.
- Der Docker-Hub-Stand `sha-f826304a7850` enthaelt den BTC-Parserfix und wurde erfolgreich live-smoke- und upgrade-/restore-validiert.
- Der Docker-Hub-Stand `sha-9c2f2b08fa76` enthaelt die Start-/Stop-Kommandos und wurde durch den Actions-Publish-Pfad erfolgreich synchronisiert.
- Der Docker-Hub-Stand `sha-df6f0fa13a5d` enthaelt den Provider-Coverage-Produktschnitt und wurde durch den Actions-Publish-Pfad erfolgreich synchronisiert.
- `.github/workflows/publish.yml` meldet fehlende Docker-Hub-Secrets jetzt explizit vor `docker/login-action`; beim letzten echten Lauf waren die benoetigten Secrets gesetzt und gueltig.
- Die Docker-Hub-Frontend-Tags sind ueber die oeffentliche API sichtbar. Das Backend-Repo ist ueber die unauthentifizierte Docker-Hub-API nicht sichtbar, aber der Pull mit lokaler Docker-Authentifizierung funktioniert.
- Die Resume-Formel ist absichtlich kurz; ein nacktes Codewort ohne Dateipfad ist nicht robust genug, weil Sitzungen nicht verlaesslich fortleben.

## Aktueller Unterbrechungspunkt 2026-04-12

- Die alte echte Env-Datei wurde nach `/root/trading-bot-v2-work/.env` kopiert, auf Modus `600` gesetzt und ist ueber `.gitignore` ignoriert.
- `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` und `ALPHA_VANTAGE_API_KEY` sind in der aktiven `.env` gesetzt; Werte wurden nicht ausgegeben.
- `tests/run-alpha-vantage-live-smoke.sh` wurde nachgebessert:
  - Shell-Overrides wie `IMAGE_TAG=sha-d4939da591ec` gewinnen jetzt gegen Werte aus `.env`
  - Alpha-Vantage-Requests werden fuer den Free-Tier gepaced
  - die MarketDataService-Pruefung nutzt Provider-Helper mit explizitem Asset-Profil statt den YFinance-Fallback-Pfad
- Letzter Live-Test:
  - Befehl: `IMAGE_TAG=sha-d4939da591ec bash tests/run-alpha-vantage-live-smoke.sh`
  - `VOO` kam bis einschliesslich Alpha-Vantage-History und ETF-Profil durch
  - `BTC/USD` scheiterte mit `BTC/USD returned too little Alpha Vantage history`
- Der danach offene Inspect der Alpha-Vantage-BTC-Antwortstruktur wurde am 2026-04-14 abgeschlossen; siehe naechsten Abschnitt.

## Aktueller Unterbrechungspunkt 2026-04-14

- Die BTC-Antwortstruktur wurde ohne API-Key-Ausgabe geprueft:
  - Top-Level-Keys: `Meta Data`, `Time Series (Digital Currency Daily)`
  - Row-Keys fuer aktuelle BTC/USD-Daten: `1. open`, `2. high`, `3. low`, `4. close`, `5. volume`
  - keine `Note`, keine `Information`, keine `Error Message`
- `src/backend/app/alpha_vantage_service.py` akzeptiert fuer Krypto-History jetzt sowohl generische OHLC-Keys als auch die alten `1a./1b.`-Keys mit Market-Suffix.
- `tests/test_alpha_vantage_service.py` enthaelt eine neue Regression fuer die generischen BTC-OHLC-Keys.
- Verifikation:
  - `docker run --rm -v /root/trading-bot-v2-work/src/backend:/app:ro -v /root/trading-bot-v2-work/tests:/tests:ro -w /app trading-bot-v2-backend:local python -m unittest discover -s /tests -p 'test_alpha_vantage_service.py'` -> 4 Tests OK
  - `docker build -f ops/docker/backend.Dockerfile -t trading-bot-v2-backend:local .` -> erfolgreich
  - `BACKEND_IMAGE=trading-bot-v2-backend:local bash tests/run-alpha-vantage-live-smoke.sh` -> erfolgreich; `VOO` und `BTC/USD` live, BTC 30 History-Zeilen, `MarketDataService` live
  - `bash ops/automation/test.sh` -> 23 Tests OK
- Commit `f826304` wurde nach `main` gepusht; GitHub Actions `ci`, `publish` und `codeql` liefen erfolgreich.
- `IMAGE_TAG=sha-f826304a7850 bash tests/run-alpha-vantage-live-smoke.sh` lief gegen das veroeffentlichte Docker-Hub-Backend erfolgreich; Backend-Digest `sha256:8c7c741f1f2ede35046b640b1044ab6cd3f16f216a509c831138a0e23622ff5d`.
- Das erste Upgrade-Rehearsal fuer `sha-f826304a7850` scheiterte beim Seeding mit `403 Admin privileges required`, weil die aktive `.env` einen Bootstrap-Admin setzte und der Test-Register-User dadurch kein erster Admin mehr war.
- `ops/automation/deploy.sh` respektiert jetzt Shell-Overrides fuer `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD` und `INITIAL_ADMIN_MFA_ENABLED`; `tests/run-upgrade-rehearsal.sh` setzt diese Variablen fuer seine isolierten Stacks leer/false.
- Das wiederholte `IMAGE_TAG=sha-f826304a7850 bash tests/run-upgrade-rehearsal.sh` lief erfolgreich durch; Upgrade-Record `state/runtime/deployments/deployment-20260414T192521Z.env`.
- Beim naechsten Resume nicht mehr die BTC-Struktur untersuchen und nicht erneut den Rehearsal-Admin-Seed debuggen; naechster sinnvoller Schritt ist der Script-/Doku-Follow-up-Push und danach weiterer Phase-1-Produktschnitt.

## Aktueller Unterbrechungspunkt 2026-04-15

- GitHub Actions fuer den bereits gepushten Start-/Stop-Commit `9c2f2b` wurden geprueft:
  - `publish` run `24423017757` erfolgreich, inklusive Docker-Hub-Login, primaerem `sha-9c2f2b08fa76`-Sync und `latest`-Sync
  - `ci` run `24423017764` erfolgreich
  - `codeql` run `24423017762` erfolgreich
- Danach wurde der Phase-1-Produktschnitt fuer ETF-/Krypto-Providerdaten lokal umgesetzt:
  - `src/backend/app/watchlist_alerts.py` baut aus Alpha-Vantage-Snapshots jetzt `providerContext` fuer Alert-Items
  - Alert-Ranking beruecksichtigt Provider-Live-Status, staerkere Provider-Moves, Research-Verfuegbarkeit und History-Abdeckung
  - Alert-Summary enthaelt `providerLive`, `providerPartial`, `providerUnavailable`, `providerResearch` und `providerMovers`
  - `src/frontend-dist/ui-patches.js` zeigt im Dashboard eine neue `Provider Coverage`-Sektion fuer ETF-/Krypto-Watchlistwerte mit Live-/Partial-/Research-/Mover-Zahlen und Provider-Highlights
  - API- und UI-Regressionen pruefen den neuen Provider-Kontext und die neue Dashboard-Sektion
- Verifikation:
  - `docker build -f ops/docker/backend.Dockerfile -t trading-bot-v2-backend:local .` -> erfolgreich
  - `bash ops/automation/test.sh` -> 23 Tests OK
  - `SKIP_BUILD=1 bash tests/run-api-regression.sh` -> erfolgreich
  - `bash tests/run-ui-regression.sh` -> erfolgreich; Browserprobe bestaetigte `ui_watchlist_provider_coverage ok`
- Commit `df6f0fa` wurde nach `main` gepusht; GitHub Actions liefen erfolgreich:
  - `publish` run `24461808225` erfolgreich, inklusive Docker-Hub-Login, primaerem `sha-df6f0fa13a5d`-Sync und `latest`-Sync
  - `ci` run `24461808223` erfolgreich
  - `codeql` run `24461808224` erfolgreich
- Beim naechsten Resume nicht erneut den `9c2f2b`- oder `df6f0fa`-Actions-Stand beobachten; naechster sinnvoller Schritt ist weiterer Phase-1-Produktschnitt oder ein expliziter Release-Tag mit Upgrade-/Restore-Rehearsal.
