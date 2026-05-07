# Sitzungslog

- Datum: 2026-05-07
  Kontext: Nutzer hat Produktvision in mehreren Nachrichten praezisiert (kombinierte Signal-Quellen, Wahrscheinlichkeitsdarstellung, vollstaendigeres Datenbild, Brokergebuehren + Kapitalertragssteuer im Net-Yield-Gate, First-Login-Wizard, Dashboard-Fortschritt, Plan/Doku konsequent nachziehen) und mehrere Phase-2-Wellen autorisiert.
  Erledigt: Phase-2-Welle 1 (Earnings/Dividenden/Splits) im Backend (`fmp_service.normalized_events`, `/api/events/{symbol}`) und im Frontend (EventsSection mit Earnings-Beat/Miss, Dividenden, Splits). Welle 2 (Erklaerbarkeit + Zonen) im Backend (`xgboost_pred_contribs`, ATR-anchored Entry/Stop/Target) und Frontend (PredictionCard mit Top-Features + Zonen). Welle 2.5 (Kategorie-Roll-up + P(UP)/P(DOWN)) erweitert Erklaerung um Trend/Technical/Volume/News/Fundamentals-Beitraege, Probability-Bars und Reasoning-Narrative. Welle 2.6 (Net-Yield-Gate) erweitert User-Schema um `capital_gains_tax_bps` und `income_tax_bps` (Alembic-Migration `0003_add_user_tax_rates`/`a3c1d4f5e6b7`); `_enrich_with_yield_model` berechnet Gross -> Fees -> Tax -> Net mit `meetsMinimum`-Flag; UI zeigt YieldBreakdown plus Schwellen-Badge. Welle 3 (Volume-Profile) backend `compute_volume_profile` mit Point-of-Control, Frontend `VolumeProfile` SVG neben dem Chart. Onboarding-Wizard `/onboarding` mit vier Schritten (MFA, Alpaca, Trading-Defaults, Steuern); Dashboard `OnboardingCard` mit Fortschritt N/M; Register-Flow leitet auf `/onboarding`. Plan/Doku konsolidiert: `docs/admin/project-plan.md` mit verbindlicher Sektion "Produktvision"; `docs/admin/product-roadmap.md` Phase 2/3/4 auf Produktvision ausgerichtet; `state/decisions.md` mit zwei neuen Decision-Bloecken (Vision-Verankerung, Schema-Erweiterung); `CLAUDE.md` zitiert Vision.
  Verifikation: 60 Unit-Tests OK (52 + 3 ML-Yield-Tests + 3 Volume-Profile-Tests + 2 Welle-2.5-Erweiterungen). `SKIP_BUILD=1 bash tests/run-api-regression.sh` gruen inklusive Schema-Migration. `npm run build` clean nach jeder Welle; Initial-Bundle 96-98 KB gzipped, AnalysisPage-Chunk 65 KB, AdminPage-Chunk 2 KB. Cross-Version-Postgres-Verifikation der Welle-2.6-Migration nicht separat gefahren — Pre-Alembic-Pfad in `init_db` ist unveraendert; Migration 0003 ist additiv (Spalten mit `server_default='0'`) und somit aufwaerts-kompatibel.
  Offen: Phase-2-Welle 6 (Auto-Support/Resistance) noch ausstehend. Frontend-UI-Regression-Rewrite + Dockerfile-Swap weiter geplant. Verifikation der vollen Stack-Laufzeit fuer den neuen Wizard-Flow steht aus (typecheck + Build sind clean, Browser-Walk-through nicht).

- Datum: 2026-05-07
  Kontext: Nach Phase-1-Closure sollte Phase 2 mit Chart-Overlays angegriffen werden (groesster sichtbarer Schnitt aus dem `docs/admin/project-plan.md`).
  Erledigt: Backend-Indikatoren um `VWAP` ergaenzt (cumulative typical-price-weighted), `/api/stock/{symbol}` reicht zusaetzlich `ema_12`, `ema_26`, `atr`, `vwap`, `stoch_k`, `stoch_d` durch. `tests/test_analysis_indicators.py` deckt die vollstaendige Indikator-Spaltenliste sowie das VWAP-Konvex-Hull-Verhalten und Zero-Volume-Edge-Case ab. Frontend `lightweight-charts` v5 als neue Dependency aufgenommen; `src/frontend/src/components/StockChart.tsx` rendert Candle-Hauptpane mit Volumen-Histogramm-Subpane, toggleable Overlay-Linien (SMA 20/50/200, EMA 12/26, VWAP, Bollinger Bands oben/unten) und Sub-Panes fuer RSI und MACD-Triple (Macd-Linie, Signal-Linie, Histogramm); Pattern-Detections (Bullish/Bearish Engulfing, Hammer, Shooting Star, Doji, Morning/Evening Star) werden als Marker im Hauptchart eingehaengt. `src/frontend/src/pages/AnalysisPage.tsx` neu strukturiert: Header mit Live-Quote + Period-Change + Timeframe-Selector (1M/3M/6M/1Y/MAX), ML-Prediction-Card, Detected-Patterns-Card, Chart, Fundamentals, Holdings, News. AnalysisPage und AdminPage ueber `React.lazy` ausgelagert; Initial-Bundle bleibt 96 KB gzipped, AnalysisPage-Chunk mit Chart 62 KB gzipped, AdminPage 2 KB gzipped.
  Verifikation: 51 Unit-Tests OK (48 alte + 3 neue Indikator-Tests). `npm run build` clean: index 319 KB / 96 KB gzipped, AnalysisPage 195 KB / 62 KB gzipped, AdminPage 7 KB / 2 KB gzipped. Production stack unveraendert auf `src/frontend-dist`-Bundle; neue Source weiter als Parallel-Artefakt mit CI-Bitrot-Gate.
  Offen: Volume-Profile (Phase-2-Punkt aus `product-roadmap.md`) bewusst noch nicht; benoetigt eigene Implementierung weil `lightweight-charts` das nicht out-of-the-box liefert. Naechste Phase-2-Wellen: Earnings/Dividenden/Splits-Anbindung, KI-Erklaerbarkeit fuer Kauf-/Verkaufszonen.

- Datum: 2026-05-07
  Kontext: Phase 1 zu Ende fahren — bewusst die zwei offenen Items aus `docs/admin/project-plan.md` schliessen: breitere Provider-Fallbacks und zentrale Rate-Limit-Strategie. Nutzer hatte als Naechstes "A" gewaehlt.
  Erledigt: Erstes Verification-Pass vor der eigentlichen Arbeit deckte zwei echte Bugs auf: (1) `0001_initial_schema` enthielt alle 10 Tabellen und stempelte direkt at-head; bei einem Production-Upgrade von v2026.05.07-1 (8 Tabellen) waere alembic_version auf "Head" gesetzt worden, ohne `alert_rules`/`alert_events` zu erzeugen — der naechste `/api/alerts/*`-Request waere gecrasht. Migration auf 0001 (Baseline 8 Tabellen, revision `b97b927c8690`) + 0002 (`d939f2abcdc2`, alert_rules/alert_events) gesplittet; `init_db` differenziert zwischen Fresh-DB, Pre-Alembic-Baseline (stamp 0001 + upgrade) und Pre-Alembic-Full (stamp Head); Cross-Version-Verifikation gegen `dbergt/trading-bot-backend:2026.05.07-1` erfolgreich. (2) Pre-commit-Hook war bei frischen Clones silently inaktiv, weil `core.hooksPath` per-repo ist; `ops/automation/build.sh` aktiviert ihn jetzt automatisch beim ersten Lauf. Danach Phase-1-Provider-Schliessung: `app/rate_limit.py` mit Token-Bucket pro Provider und Subprocess-isolierte FakeClock-Tests; `app/fmp_service.py` mit Profile/Key-Metrics/Ratios/ETF-Holdings/News + Rate-Limiter-Integration + `normalized_ticker_info` als yfinance-kompatibler Subset; `MarketDataService.get_ticker_info` chained yfinance -> FMP wenn yfinance leer oder rate-gelimitiert; `get_market_news` chained Alpaca -> FMP fuer News-Sentiment; `tests/run-fmp-live-smoke.sh` analog zum Alpha-Vantage-Smoke (Exit 2 ohne Key, kein Leak); `.env.example`/`.env.local.example`/Compose um `FMP_API_KEY` ergaenzt.
  Verifikation: 48 Unit-Tests OK (35 alte + 6 rate-limit + 6 FMP + 1 Alembic-baseline-then-upgrade-Test). `SKIP_BUILD=1 bash tests/run-api-regression.sh` -> komplett gruen. Cross-Version-Postgres-Test: alte Image populiert 8 Tabellen via create_all -> neue Image stempelt Baseline `b97b927c8690` -> upgradet auf `d939f2abcdc2` -> alle 10 Tabellen + alembic_version vorhanden, idempotent.
  Offen: `tests/run-ui-regression.mjs` umschreiben fuer neue React-Selektoren als Voraussetzung fuer Frontend-Dockerfile-Swap. Phase 2 (Chart-Overlays, Fundamentals tiefer, KI-Erklaerbarkeit) als naechster Block.

- Datum: 2026-05-07
  Kontext: Nach erstem Frontend-Vertical-Slice (Login/Register/Dashboard/Watchlists/Alerts) sollten die fehlenden Bundle-Flows fuer Feature-Paritaet im neuen `src/frontend/`-Quellstand nachgezogen werden.
  Erledigt: Sechs zusammenhaengende Pages neu gebaut. `SettingsPage` mit Profile-Read-out, Alpaca-Config (api/secret/paper, masked-secret-skip on save), Portfolio-Defaults (fee absolute/percent, min target yield) und MFA-Lifecycle (setup mit Secret + Provisioning-URI-Anzeige; enable/disable mit Code). `ScannerPage` mit Watchlist-Selector, sortierbarer Anzeige nach changePercent und Provider-Status-Pills; Symbol-Zellen verlinken auf `AnalysisPage`. `AnalysisPage` haengt an `/api/research/{symbol}` und rendert Provider-Research-Block (Status/Source/History/Research-Available), Fundamentals (Sector/Industry/MarketCap/Yield/PE/PB/52W), Top-Holdings (verlinkbar bei ETFs), aggregierte News mit Sentiment-Badge. `AdminPage` mit Users-CRUD (Create + Reset MFA + Set Password + Toggle Active), Backups-Liste mit manuellem Snapshot + Download via Blob-Fetch (Authorization-Header), und Platform-Export-Download. Nav-Filter via `user.is_admin`; Route greift hart auf `/` zurueck wenn Non-Admin direkt navigiert. `DashboardPage` erweitert um Active-Watchlist-Selector, Tracked-Assets-Section (Asset-Mix, Top-Tags, Symbol-Liste mit Drilldown), Provider-Coverage-Section (Live/Partial/Unavailable/Research/Movers Mini-Cards), News-Ticker-Card (rolling, Drilldown, Sentiment). `WatchlistsPage` neu strukturiert als Per-Watchlist-Karten mit Item-Add (symbol/name/tags) und Item-Remove (Slash-tolerant via `encodeURI` fuer `BTC/USD`); Watchlist-Delete fuer Non-Default. `ForgotPasswordPage` und `ResetPasswordPage` schliessen die Auth-Flaeche; Reset-Page liest Token aus Query-String passend zu `PASSWORD_RESET_BASE_URL=/reset-password`.
  Verifikation: Nach jedem Schnitt `npm run build` clean (jeweils 300-330 KB / 92-98 KB gzipped). Production-Stack laeuft weiter unveraendert ueber `src/frontend-dist`-Bundle. CI/Publish-Stages `Install frontend source dependencies` + `Build frontend source` laufen fuer alle Commits gruen durch.
  Offen: Production-Swap des `ops/docker/frontend.Dockerfile` ist der einzige verbliebene grosse Schritt, wartet aber bewusst auf eine zweite Welle, in der die UI-Regression (`tests/run-ui-regression.mjs`) parallel auf die neuen React-Selektoren umgeschrieben wird. Ohne das wuerde die UI-Regression bei vielen Steps brechen, weil das Skript Bundle-spezifische DOM-Patterns prueft (`Watchlist Alerts`-Panel-Marker, gear-Icons, Alpaca-Settings-`Back to Dashboard`, etc.). Auch noch offen: Alpaca-Page (Account/Positions/Orders), Watchlist-Alert-Settings-UI (Popup/Push/Min-Prio/Min-Score) bewusst nicht gebaut, weil sie nur ueber API-Pfad konfigurierbar bleibt bis Frontend-Swap; News-Detail-Page; Watchlist-Item-Tag-Update via PUT.

- Datum: 2026-05-07
  Kontext: Nach Alembic-Einfuehrung sollte der Frontend-Quellstand-Wiederaufbau gestartet werden. Strategie: Parallel-Aufbau unter `src/frontend/`, Production weiter aus `src/frontend-dist`, Swap erst nach Feature-Paritaet damit UI-Regression nicht bricht.
  Erledigt: Vite/React 19/TS/Tailwind-Scaffold unter `src/frontend/` angelegt. `package.json` mit react-router-dom 7, @tanstack/react-query 5, zod, tailwindcss/postcss/autoprefixer; `vite.config.ts` mit `/api`- und `/ws`-Proxy auf `http://127.0.0.1:18090`; `tsconfig.json` als Project-References-Setup; `tailwind.config.js` mit `bergt-green`-Brandfarbe (zu kalibrieren); `index.html` mit `dark`-Klasse als Default. App-Skelett: `main.tsx` (StrictMode + BrowserRouter + QueryClientProvider + AuthProvider), `App.tsx` mit Routen `/login`, `/register`, geschuetzte Routen `/`, `/watchlists`, `/alerts` unter `Layout`. `auth/AuthContext.tsx` mit Token-Storage in `localStorage` (Keys `access_token`/`refresh_token`), automatischem `/api/auth/me`-Fetch und MFA-Pfad. `api/client.ts` mit Refresh-Logik (versucht einmal `/api/auth/refresh` bei 401 und replayt) und typisierter `ApiError`. Pages: `LoginPage` (E-Mail/Passwort/MFA-Code), `RegisterPage` (Bestaetigung-Validierung), `DashboardPage` (Stat-Karten ueber `useQuery`), `WatchlistsPage` (List+Create+Asset-Labels+Tags), `AlertsPage` (CRUD fuer Alert-Regeln, Open-Event-Liste mit Severity-Badges, Acknowledge). `vite-env.d.ts` mit CSS-Modul-Deklaration. CI: neue Stufen `Install frontend source dependencies` und `Build frontend source` in `ci.yml` und `publish.yml` als Bitrot-Gate.
  Verifikation: `npm install` -> 143 Pakete, 0 Vulnerabilities. `npm run build` -> tsc clean, Vite Build erfolgreich (293 KB JS, 91 KB gzipped; 12 KB CSS, 3 KB gzipped). Production-Stack laeuft unveraendert ueber `src/frontend-dist`-Bundle weiter; UI-Regression unveraendert.
  Offen: Fehlende Bundle-Flows in echten Komponenten nachziehen: Scanner, Symbol-Analyse mit Provider-Research-Panel, Alpaca (Account/Positions/Orders/Bars), Settings (Profile, Alpaca-Config, Watchlist-Alert-Settings), Admin (User-Management, Backups, Export/Import), News-Ticker, Tracked-Assets-Sektion, Provider-Coverage-Sektion. Sobald Paritaet steht: `ops/docker/frontend.Dockerfile` auf Vite-Multi-Stage-Build umstellen und `src/frontend-dist` entfernen.

- Datum: 2026-05-07
  Kontext: Nach erfolgreicher Codex-Uebergabe und Alert-Rule-Migration sollte der Phase-0-Restpunkt "DB-Migrationen" aus `docs/admin/project-plan.md` als naechstes geschlossen werden, vor dem groesseren Frontend-Quellstand-Wiederaufbau.
  Erledigt: Alembic als Hard-Dependency aufgenommen (`alembic==1.14.0` in `src/backend/requirements.txt`). Scaffolding angelegt: `src/backend/alembic.ini` (Logging-Setup, leeres SQL-Url-Default, `prepend_sys_path = .`), `src/backend/alembic/env.py` (uebernimmt `DATABASE_URL` aus `app.database`, importiert `app.models` damit autogenerate alle Tabellen sieht, mit `compare_type=True`), `src/backend/alembic/script.py.mako`. Anschliessend `alembic revision --autogenerate -m 'initial schema'` per docker-run gegen leere SQLite generiert und als `src/backend/alembic/versions/0001_initial_schema.py` (revision `16389c42c243`) im Repo abgelegt; deckt alle 10 Tabellen inkl. Indizes ab. `app/database.py::init_db` umgestellt: importiert alle Modelle damit `Base.metadata` vollstaendig ist, ruft dann smart `alembic stamp head` (wenn `users` existiert aber `alembic_version` nicht) oder `alembic upgrade head` (sonst). `tests/test_alembic_init.py` mit zwei Subprocess-isolierten Szenarien hinzugefuegt (Fresh-DB-Upgrade und Pre-Alembic-Stamp-Pfad), damit Modul-Reload nicht die SQLAlchemy-Mapper-Registry pollutiert.
  Verifikation: `bash ops/automation/build.sh` -> beide Images gebaut. `bash ops/automation/test.sh` -> 31 Tests OK (29 alte plus 2 neue Alembic-Tests). `SKIP_BUILD=1 bash tests/run-api-regression.sh` -> komplett gruen; alembic upgrade head laeuft beim Startup gegen leere Postgres erfolgreich. Manueller Stamp-Pfad-Check via `docker run` mit pre-populated SQLite hat sauber gestempelt (revision `16389c42c243`) und das wiederholte init_db ist idempotent.
  Offen: Frontend-Quellstand unter `src/frontend/` als Vite/React/TS/Tailwind-Projekt aufbauen, Auth/Layout/Watchlist/Dashboard und Alert-Rule-UI als erste echte Komponente; danach Frontend-Dockerfile auf Vite-Build umstellen.

- Datum: 2026-05-07
  Kontext: Uebergabe von Codex an Claude; Projekt sollte komplett verstanden, fortgefuehrt und der divergente Sandbox-Stand `/root/trading-bot-v2-work` migriert werden. Vom Nutzer freigegebene Arbeitsweise: voll automatischer Sync nach `origin/main` und Docker Hub inkl. Release-Tags nach Rehearsal, Frontend-Strategie umstellen auf echten React-Quellstand-Wiederaufbau, drei Verbesserungen direkt einpflegen (security-review als Standardschritt, `CLAUDE.md`, Pre-commit-Hook gegen Secret-Leaks).
  Erledigt: Vollstaendige Projektanalyse mit Architekturvisualisierung. `CLAUDE.md` + `.githooks/pre-commit` (Hook gegen `.env.local`/AWS-/GitHub-/Slack-Token/Private-Key-Bloecke/High-Entropy-Zuweisungen) angelegt und mit AWS-Key- und Private-Key-Sample verifiziert. Anschliessend persistente Alert-Domaene aus dem `trading-bot-v2-work`-WIP migriert: neue Tabellen `alert_rules` + `alert_events` mit den Regeltypen `provider_move`, `news_sentiment`, `signal_direction` und `tag_priority`; neue API-Pfade `GET/POST /api/alerts/rules`, `PUT/DELETE /api/alerts/rules/{id}`, `GET /api/alerts` (Auswertung mit `evaluate_alert_rules`), `GET /api/alerts/events`, `POST /api/alerts/events/{id}/ack`; `evaluate_alert_rules` an `-v2`'s `build_watchlist_alert_payload(db, user, record, ...)`-Signatur angeglichen, damit Alert-Settings/Notification-Plan koexistieren; Backup/Export/Import decken `alert_rules`/`alert_events` mit ab; offene Events werden pro Regel deduplziert, bis sie acknowledged sind; Snooze-Logik beruecksichtigt tz-naive Werte als UTC.
  Verifikation: Python-Syntaxcheck aller Backend-Dateien gruen. `bash ops/automation/build.sh` -> Backend- und Frontend-Image lokal gebaut. `bash ops/automation/test.sh` -> 29 Tests OK. `SKIP_BUILD=1 bash tests/run-api-regression.sh` -> komplett gruen inkl. neuer Sektionen `alert rule create ok`, `alert rule list ok`, `alert evaluation event ok`, `alert event list ok`, `alert event ack ok`, `acknowledged alert event list ok` plus `alert_rules`/`alert_events`-Coverage in Backup-Download und Export. `CHROME_BIN=/usr/bin/google-chrome SKIP_BUILD=1 bash tests/run-ui-regression.sh` -> erster Lauf scheiterte transient an dem dokumentierten Yahoo-429-Pfad, direkter Wiederholungslauf war komplett gruen (alle UI-Schritte inkl. `ui_watchlist_alert_management ok` und `ui_symbol_research ok`). Manuelle Security-Pass auf den 646-Zeilen-Backend-Diff: alle neuen Endpunkte unter `Depends(get_current_user)` mit `user_id`-Filter; Allowlist-Validierung fuer `rule_type`/`direction`; ORM-only ohne Raw-SQL; `payload_json`-Deserialisierung mit `JSONDecodeError`-Fallback; keine HIGH/MEDIUM-Findings.
  Offen: Sandbox `/root/trading-bot-v2-work` nach erfolgreichem Push loeschen; Frontend-Anbindung fuer Alert-Regeln/-Events steht aus und wird mit dem neuen React-Quellstand mit aufgebaut; Alembic-Migrationen als naechster Phase-0-Restpunkt.

- Datum: 2026-05-07
  Kontext: Nach Push-/VAPID-Haertung sollten echte lokale Ziel-VAPID-Werte gesetzt, der nicht-invasive Smoke gefahren und danach ein expliziter Release mit Upgrade-/Restore-Rehearsal erstellt werden.
  Erledigt: Gitignorierte `.env.local` wurde mit neu erzeugtem VAPID-Keypair, `VAPID_CLAIMS_SUB=mailto:admin@nexuspulsetrade.com` und `REQUIRE_VAPID_SECRETS=true` befuellt; Datei steht auf Modus `600`, Werte wurden nicht ausgegeben. `bash tests/run-push-config-smoke.sh` validierte die Zielkonfiguration erfolgreich. Annotierter Tag `v2026.05.07-1` wurde auf Commit `878fcff` gesetzt und gepusht; GitHub Actions `publish #21` lief erfolgreich und publizierte `dbergt/trading-bot-backend:2026.05.07-1` (`sha256:835f50167496e5bc0fd6e83bdea86bed386590fe88cf71506d759db1380aa4bf`) sowie `dbergt/trading-bot-frontend:2026.05.07-1` (`sha256:f66fe7516f6764bf8a69bd1b920250895013521c73ab6b978165d6846c813d12`).
  Verifikation: `IMAGE_TAG=2026.05.07-1 bash tests/run-upgrade-rehearsal.sh` lief erfolgreich durch: initialer Deploy, Datenanlage, Upgrade ueber bestehenden Datenbestand, Pre-Upgrade-PostgreSQL-Dump, App-Snapshot und Dump-Restore in einen frischen Stack. Upgrade-Record `state/runtime/deployments/deployment-20260507T120020Z.env`; Pre-Upgrade-Dump `/tmp/trading-bot-v2-upgrade-rehearsal-20260507135544-76885/primary/backups/postgres-20260507T120020Z-pre-upgrade-2026.05.07-1.sql`; App-Snapshot `/tmp/trading-bot-v2-upgrade-rehearsal-20260507135544-76885/primary/backups/backup-20260507T120027Z-pre-upgrade-2026.05.07-1.json`.
  Offen: Release-/Rehearsal-Status committen und pushen; danach weitere Phase-1-Produktarbeit oder optional Live-Smoke mit gesetztem Alpha-Vantage-Key gegen `2026.05.07-1`.

- Datum: 2026-05-07
  Kontext: Resume `trading-bot-v2`; nach Release `2026.05.05-1` sollte die produktive Push-/VAPID-Konfiguration ohne Code-Defaults gehaertet und ein Smoke-Test ohne echte Nutzergeraete gebaut werden.
  Erledigt: Backend-Defaults fuer VAPID Public/Private Key entfernt; `PushService.validate_configuration()` prueft vollstaendige Keypaare, Claims-Subjekt, Public/Private-Match und erzwingt VAPID bei `APP_ENV=production` oder `REQUIRE_VAPID_SECRETS=true`. Web-Push-Versand wird ohne lokale VAPID-Konfiguration uebersprungen statt mit geteilten Defaults zu senden. Neuer oeffentlicher Endpoint `/api/auth/push/config` liefert Browsern nur `configured` und `publicKey`; das rekonstruierte Frontend-Bundle holt den Public Key dort ab und enthaelt den alten eingebetteten Key nicht mehr. `.env.example`, `.env.local.example`, Compose und Doku beschreiben `APP_ENV`, `REQUIRE_VAPID_SECRETS` und die VAPID-Zielkonfiguration. Neuer Smoke `tests/run-push-config-smoke.sh` validiert echte Zielkonfiguration oder mit `GENERATE_TEST_VAPID=1` ein disposable Keypair, ohne Push-Subscriptions oder externe Push-Endpunkte zu kontaktieren.
  Verifikation: `bash ops/automation/build.sh`, `bash ops/automation/test.sh` (29 Tests OK), `GENERATE_TEST_VAPID=1 bash tests/run-push-config-smoke.sh`, `SKIP_BUILD=1 bash tests/run-api-regression.sh` und `SKIP_BUILD=1 bash tests/run-ui-regression.sh` erfolgreich. Ein UI-Zwischenlauf scheiterte transient erst am bestehenden `symbol research panel`-Wait mit Yahoo-429s im Backendlog, ein weiterer Startversuch an einem Docker-Compose-Startfehler; der direkte Wiederholungslauf war vollstaendig gruen. Commit `21b970a` wurde nach `main` gepusht; GitHub Actions `ci #24`, `publish #19` und `codeql #30` liefen erfolgreich.
  Offen: Fuer echte produktive Push-Zustellung Zielumgebungs-VAPID-Werte setzen und `bash tests/run-push-config-smoke.sh` gegen diese Konfiguration fahren; danach optional Release-Tag mit Upgrade-/Restore-Rehearsal oder weitere Phase-1-Produktarbeit.

- Datum: 2026-05-05
  Kontext: Der Gesamtstand, der Phasenplan und die Sicherheits-/Betriebsleitplanken sollen dauerhaft im Projekt verankert werden.
  Erledigt: Neue kanonische Plan-Datei `docs/admin/project-plan.md` angelegt. Sie dokumentiert Release `v2026.05.05-1`, Phasenposition, Sicherheitsachsen, Architekturachsen, naechste Prioritaeten und Fertigstellungsregeln. README, Roadmap, Release-Doku, Runbook und Security-Doku wurden auf den aktuellen validierten Stand und den naechsten Fokus Push-/VAPID-Haertung aktualisiert; `state/decisions.md` haelt die neue Plan-Verankerung als Entscheidung fest.
  Offen: Naechster Umsetzungsschritt bleibt produktive Push-/VAPID-Haertung mit nicht-invasivem Smoke-Test.

- Datum: 2026-05-05
  Kontext: Nach erfolgreichem Push-Alert-Dispatcher soll ein expliziter Release-Tag gebaut und der Docker-Hub-Upgrade-/Restore-Pfad validiert werden.
  Erledigt: Annotierter Git-Tag `v2026.05.05-1` wurde auf Commit `ec48455` gesetzt und gepusht. GitHub Actions `publish #16` fuer den Tag lief erfolgreich und synchronisierte die versionierten Docker-Hub-Images. `IMAGE_TAG=2026.05.05-1 bash tests/run-upgrade-rehearsal.sh` lief erfolgreich: initialer Deploy, Datenanlage, Upgrade ueber bestehenden Datenbestand, Pre-Upgrade-PostgreSQL-Dump, App-Snapshot und Dump-Restore in einen frischen Stack. Upgrade-Record: `state/runtime/deployments/deployment-20260505T202750Z.env`; Backend-Digest `sha256:9ba0eecf4a1ace9259705191b500fc2b4d0183145076cc34f1702dfabcc4e272`; Frontend-Digest `sha256:973882f6813f9efe7c7f32bbbdccfa4ba7c30c8d4552a4526daf0cb0636159fb`.
  Offen: Produktive Push-/VAPID-Konfiguration ohne Code-Defaults erzwingen und einen Push-Konfigurations-Smoke-Test bauen, der keine echten Nutzergeraete belaestigt.

- Datum: 2026-05-05
  Kontext: Nach dem Watchlist-Alert-Management soll die serverseitige periodische/deduplizierte Alert-Ausloesung umgesetzt werden.
  Erledigt: Gemeinsamer Watchlist-Alert-Payload-Aufbau fuer API und Dispatcher eingefuehrt; neuer Background-Dispatcher wertet Watchlists mit aktivem `pushEnabled` periodisch aus und sendet Web-Push fuer `notification.pushEligible` Alerts. Erfolgreiche Push-Zustellungen werden in `watchlist_alert_deliveries` mit stabilem Alert-Key gespeichert und innerhalb des konfigurierbaren Dedupe-Fensters nicht erneut gesendet. `PushService` meldet erfolgreiche Zustellzahlen zurueck; Backup/Export/Import sichern die Delivery-Historie. Unit-Test deckt stabile Dedupe-Keys ab, API-Regression prueft die neue Backup-/Export-Flaeche.
  Offen: Lokalen UI-Regressionslauf fuer den neuen Backend-Stand noch ausfuehren, danach Commit/Push und GitHub Actions beobachten. Naechster Produktschritt danach: expliziter Release-Tag mit Upgrade-/Restore-Rehearsal oder produktive Push-/VAPID-Haertung.

- Datum: 2026-04-26
  Kontext: Nach dem Symbol-Research-Schnitt soll Phase 1 weiter in echtes Nutzer-Alert-/Popup-Management gehen.
  Erledigt: `watchlist_alert_settings` speichert pro Nutzer/Watchlist Alert-Aktivierung, Popup-Schalter, Push-Bereitschaft, Mindestprioritaet und Mindestscore; neue Endpunkte `/api/watchlists/{id}/alert-settings` lesen/schreiben diese Settings. `/api/watchlists/{id}/alerts` liefert jetzt `alertSettings`, `notificationPlan` sowie `notification.popupEligible`/`pushEligible` pro Alert-Item, und Backup/Export/Import decken die Settings ab. Das Dashboard zeigt ein `Alert Management`-Panel im Watchlist-Bereich; In-App-Popups werden nur noch fuer popup-eligible High-Priority-Alerts ausgelöst. API-Regression prueft Settings, Notification-Plan und Backup/Export; UI-Regression bestaetigt `ui_watchlist_alert_management ok`.
  Offen: Nach Push den GitHub-Actions-Publish-Lauf beobachten; danach als naechster Schritt serverseitige periodische/deduplizierte Alert-Ausloesung oder expliziten Release-Tag mit Upgrade-/Restore-Rehearsal fahren.

- Datum: 2026-04-26
  Kontext: Phase 1 soll wie besprochen weitergezogen werden: der ETF-/Krypto-Providerpfad soll aus Watchlist/Alerts in eine echte Symbol-Research-Flaeche wandern.
  Erledigt: Neuer Endpunkt `/api/research/{symbol}` liefert normalisierte Assetdaten, Providerstatus, Quote, Provider-Research, Fundamentals und News; fuer beobachtete Symbole nutzt der Endpunkt Watchlist-Namen als Klassifizierungsfallback, damit ETFs wie `VOO` auch ohne sofort verfuegbare externe Metadaten korrekt als ETF laufen. `src/frontend-dist/ui-patches.js` rendert auf `/analysis/<symbol>` jetzt ein `Provider Research`-Panel mit Providerstatus, Kurs/Move, History-Abdeckung, ETF-Research, Top-Holdings, Headlines und Stock-Fundamentals. API-Regression prueft Crypto- und ETF-Research-Kontext; UI-Regression bestaetigt `ui_symbol_research ok`.
  Offen: Nach Push den GitHub-Actions-Publish-Lauf beobachten; danach als naechster Phase-1-Schnitt echte Nutzer-Alerts/Popup-Alert-Management aus dem vorhandenen Watchlist-Alert-Feed bauen oder einen expliziten Release-Tag mit Upgrade-/Restore-Rehearsal fahren.

- Datum: 2026-04-26
  Kontext: Lokale API-Keys und private Zugangsdaten muessen beim Wiedereinstieg nicht jedes Mal erneut zusammengesucht und eingetragen werden.
  Erledigt: `ops/automation/env.sh` fuehrt jetzt einen einheitlichen Ladevorgang fuer `.env` plus die gitignorierte Override-Datei `.env.local` ein; `ops/automation/deploy.sh`, `ops/automation/start.sh`, `ops/automation/stop.sh`, `ops/automation/logs.sh` und das Upgrade-Rehearsal laden dieselben lokalen Overrides; der Wrapper normalisiert Runtime-Pfade auf absolute Projektpfade und adoptiert bei Bedarf einen alten PostgreSQL-Datenstand aus `ops/docker/state/runtime/postgres`, damit der Wechsel vom alten Raw-Compose-Pfad keinen Restart-Fehler erzeugt; `README.md` und `docs/admin/runbook.md` dokumentieren `.env.local.example` als dauerhafte Ablage fuer private Keys.
  Offen: Die echten Live-Secrets muessen nur noch einmalig in `.env.local` hinterlegt werden; danach soll der lokale Betriebsweg ohne erneute Neueingabe funktionieren.

- Datum: 2026-04-12
  Kontext: Der Nutzer hat Alpaca-Key/Secret und danach den Alpha-Vantage-Key in die aktive `.env` eingetragen; der Live-Smoke sollte weiterlaufen, wurde dann aber fuer spaeter unterbrochen.
  Erledigt: Die fruehere echte `.env` wurde nach `/root/trading-bot-v2-work/.env` kopiert, Modus `600` gesetzt und als durch `.gitignore` ignoriert bestaetigt. `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` und `ALPHA_VANTAGE_API_KEY` sind in der aktiven `.env` vorhanden, ohne Werte auszugeben. `tests/run-alpha-vantage-live-smoke.sh` wurde korrigiert, damit Shell-Overrides wie `IMAGE_TAG=sha-d4939da591ec` Vorrang vor `.env` haben, Alpha-Vantage-Requests Free-Tier-freundlich gepaced werden und die MarketDataService-Pruefung den Provider-Helper statt den YFinance-Fallback nutzt. Der Live-Test erreichte Alpha Vantage; `VOO` kam bis History/ETF-Profil durch, `BTC/USD` scheiterte mit `BTC/USD returned too little Alpha Vantage history`.
  Offen: Ein gezielter Inspect der `DIGITAL_CURRENCY_DAILY`-Antwortstruktur fuer `BTC/USD` wurde vom Nutzer bewusst abgebrochen und ist der naechste Resume-Punkt. Dabei keinen API-Key ausgeben; nur HTTP-Status, Top-Level-Keys, Warn-/Fehlermeldungen und Serienanzahl protokollieren.

- Datum: 2026-04-12
  Kontext: Nach Klaerung der Phase sollte exakt mit dem empfohlenen Pfad fortgesetzt werden: zuerst Rehearsal des veroeffentlichten SHA-Stands, danach Phase-1-Liveprovider.
  Erledigt: `IMAGE_TAG=sha-d4939da591ec bash /root/trading-bot-v2-work/tests/run-upgrade-rehearsal.sh` lief erfolgreich durch. Geprueft wurden Docker-Hub-Pull der Backend-/Frontend-Images, initialer Deploy, Datenanlage, Upgrade ueber bestehenden Datenbestand, Pre-Upgrade-PostgreSQL-Dump, App-Snapshot und Dump-Restore in einen frischen Stack. Upgrade-Record: `state/runtime/deployments/deployment-20260412T155353Z.env`. `tests/run-alpha-vantage-live-smoke.sh` wurde als wiederholbare Liveprobe fuer `VOO` und `BTC/USD` angelegt, in Runbook/Release-Doku verlinkt und mit `bash -n` sowie bewusstem Missing-Key-Abbruch geprueft.
  Offen: Lokal ist weiter kein `ALPHA_VANTAGE_API_KEY` gesetzt. Sobald ein echter Key in `.env` oder der Umgebung liegt, `IMAGE_TAG=sha-d4939da591ec bash tests/run-alpha-vantage-live-smoke.sh` ausfuehren und die realen Providerantworten bewerten.

- Datum: 2026-04-12
  Kontext: Resume ueber `resume trading-bot-v2`; der letzte Handover zeigte noch den Docker-Hub-Login in GitHub Actions als externen Blocker.
  Erledigt: `state/current-focus.md`, `state/project-status.md` und `state/chat/session-log.md` wurden wie vereinbart zuerst gelesen. Der aktuelle GitHub-Actions-Stand wurde nachgezogen: `publish`-Run `#6` auf `main` (`d4939da`, Start `2026-03-27 11:16:30 UTC`, Ende `2026-03-27 11:19:43 UTC`) lief vollstaendig erfolgreich durch Build, Test, API-Regression, UI-Regression, Docker-Hub-Secret-Pruefung, Login sowie `sha-d4939da591ec`- und `latest`-Sync. Docker-Pulls fuer `dbergt/trading-bot-backend:sha-d4939da591ec` (`sha256:4650bcd75afbd953471bd10144a085cedeb30bc90324677a6ba3d98cb6d6d377`) und `dbergt/trading-bot-frontend:sha-d4939da591ec` (`sha256:4c6d0ccfa13717d1f2effeabad32106f3eedc298396c3602e550b38f37cc289e`) wurden lokal bestaetigt. Die bestehenden Compose-Ergaenzungen fuer `PASSWORD_RESET_BASE_URL`, `SMTP_*` und `ENABLE_INSECURE_DEBUG_RESET_TOKENS` wurden in den Handoff-Stand uebernommen; `docker compose -f ops/docker/compose.yaml config` validiert die Konfiguration.
  Offen: Kein aktueller Docker-Hub-Login-Blocker mehr. Naechster sinnvoller Schritt ist ein expliziter Release-Tag plus Upgrade-/Restore-Rehearsal fuer einen deploybaren Stand oder weiterer Phase-1-Produktschnitt, insbesondere echte ETF-/Krypto-Providerpfade mit gesetztem `ALPHA_VANTAGE_API_KEY`.

- Datum: 2026-03-27
  Kontext: Resume-Handover wurde ausgefuehrt; der externe Publish-Blocker sollte auf den neuesten GitHub-Actions-Stand gezogen und im Workflow klarer benannt werden.
  Erledigt: Oeffentliches GitHub-API/HTML fuer die `publish`-Runs `#4` und `#5` wurde geprueft. Der aktuellste Run `#5` auf `main` (`87e4196`, Start `2026-03-27 09:05:13 UTC`, Ende `2026-03-27 09:07:36 UTC`) lief erneut durch Build, Test, API-Regression und UI-Regression und scheiterte weiter nur bei `Log in to Docker Hub`; die sichtbare Fehlermeldung lautet `Username and password required`, was auf fehlende oder leere Repository-Secrets `DOCKERHUB_USERNAME` und/oder `DOCKERHUB_TOKEN` hindeutet. `.github/workflows/publish.yml` validiert fehlende Docker-Hub-Secrets jetzt explizit vor `docker/login-action`; `docs/admin/release.md`, `state/current-focus.md` und `state/project-status.md` wurden auf den neuen Stand gebracht.
  Offen: GitHub-Repository-Secrets `DOCKERHUB_USERNAME` und `DOCKERHUB_TOKEN` im Repo-UI setzen oder rotieren, optional `DOCKERHUB_NAMESPACE` abgleichen, danach echten `publish`-Run erneut beobachten.

- Datum: 2026-03-27
  Kontext: Der Nutzer will nach Rechner-Neustarts mit einem Minimalprompt nahtlos fortsetzen, und der zuletzt angestossene `publish`-Run soll als echter Wiedereinstiegspunkt dokumentiert werden.
  Erledigt: Neues Resume-Protokoll in `state/current-focus.md` angelegt; kuenftiger Minimalprompt ist `resume trading-bot-v2`, worauf zuerst `state/current-focus.md`, `state/project-status.md` und `state/chat/session-log.md` gelesen werden sollen. Der zuletzt gepruefte GitHub-Actions-`publish`-Run `#4` fuer Commit `4233762` wurde nachgezogen: Build, Test, API-Regression und UI-Regression liefen im Runner erfolgreich durch; der Fehlschlag lag erst im Step `Log in to Docker Hub`.
  Offen: Naechster fachlicher Blocker ist nicht mehr der Codepfad, sondern die Docker-Hub-Anmeldung in GitHub Actions; beim Wiedereinstieg zuerst Repository-Secrets `DOCKERHUB_USERNAME` und `DOCKERHUB_TOKEN` pruefen und danach den `publish`-Run erneut beobachten.

- Datum: 2026-03-26
  Kontext: Phase 1 soll nach dem ersten echten GitHub-Actions-`publish`-Run mit einem echten ETF-/Krypto-Providerpfad im Backend und sichtbarer UI-Anbindung fortgesetzt werden.
  Erledigt: Der letzte `publish`-Run `#3` auf `main` (`13f5c1d`, 2026-03-23 22:11:49 UTC) wurde zuerst geprueft und als reiner Workflow-Blocker identifiziert: er brach sofort im Step `Run build hook` ab, weil die direkt ausgefuehrten Shellskripte kein Exec-Bit trugen; die betroffenen Shellskripte unter `ops/automation/*.sh` und `tests/*.sh` werden im aktuellen Git-Stand nun executable gemacht. Fachlich liefert `src/backend/app/alpha_vantage_service.py` jetzt einen optionalen Alpha-Vantage-Pfad fuer ETF-Profile/Holdings, ETF-/Krypto-Tageshistorien und providergebundene ETF-/Krypto-News; `src/backend/app/services.py`, `src/backend/app/main.py` und `src/backend/app/watchlist_alerts.py` reichen diese Daten jetzt fuer Watchlists, Alerts, Analyse-Fallbacks und Scanner-Snapshots durch. `src/frontend-dist/ui-patches.js` rendert auf Dashboard-Tracked-Asset- und Alert-Karten jetzt sichtbare Provider-Pills und ETF-/Krypto-Metadaten, und `tests/run-ui-regression.mjs` seedet dafuer explizit `VOO` und `BTC/USD`. Neue Unit-Tests in `tests/test_alpha_vantage_service.py` und erweiterte Service-/Regressionstests validieren den Pfad; die containerisierten API- und UI-Regressionen gegen den frischen lokalen Build liefen erfolgreich durch.
  Offen: Lokal ist kein `ALPHA_VANTAGE_API_KEY` gesetzt, daher wurde der neue Pfad hier mit sichtbarem `provider.status=unavailable` statt echter Liveantworten verifiziert; der naechste echte `main`-Push sollte jetzt live in GitHub Actions beobachtet werden, um sowohl den Exec-Bit-Fix als auch den automatischen Docker-Hub-Sync im Runner zu bestaetigen.
- Datum: 2026-03-23
  Kontext: Git-Sync und Docker-Hub-Sync sollen kuenftig ohne manuellen Nachlauf passieren.
  Erledigt: Git-Remote laeuft jetzt lokal ueber SSH; `.github/workflows/publish.yml` publiziert auf jedem Push nach `main` automatisch `latest` plus `sha-<commit>` fuer Backend und Frontend und publiziert auf Git-Tags `v*` weiterhin den entsprechenden Release-Tag; `README.md`, `docs/admin/release.md` und `state/decisions.md` dokumentieren den neuen Automatikpfad und die dafuer benoetigten Docker-Hub-Secrets.
  Offen: Der neue GitHub-Actions-Pfad sollte nach dem naechsten echten `main`-Push einmal im Runner beobachtet werden, damit der automatische Docker-Hub-Sync mit den hinterlegten Secrets auch live bestaetigt ist.

- Datum: 2026-03-23
  Kontext: Die lokale Git-Anbindung des rekonstruierten Projekts soll an das vorhandene GitHub-Repository angeschlossen werden.
  Erledigt: Lokales Repository unter `/codex/trading-bot-v2` ist vorhanden; `origin` zeigt auf `https://github.com/dannybergt/trading-bot-v2.git`; das Remote-Repository war leer und wurde nun mit dem lokalen Initial-Commit `93cc39c` befuellt; `main` trackt jetzt sauber `origin/main`; der initiale Token ohne Workflow-Berechtigung wurde serverseitig abgewiesen, danach wurde mit einem Token inklusive Workflow-Recht der Push erfolgreich wiederholt; die temporaere Token-Datei `/tmp/github-token` wurde anschliessend wieder entfernt.
  Offen: Keine unmittelbaren Git-Anbindungsblocker mehr.

- Datum: 2026-03-23
  Kontext: Arbeitsmodus fuer dieses Repository konkretisiert.
  Erledigt: Sinnvolle Aenderungen sollen ab jetzt jeweils direkt committed und nach Moeglichkeit sofort nach `origin/main` gepusht werden.
  Offen: Pushes ueber HTTPS brauchen weiterhin eine verfuegbare GitHub-Authentifizierung auf diesem System.

- Datum: 2026-03-23
  Kontext: Der naechste fachliche Schritt soll den ETF-/Krypto-Providerpfad entlasten, damit Watchlist-Alerts nicht doppelt News/Fundamentals ziehen und ETF-Werte auch ohne sofort verfuegbare Provider-Metadaten sauber in Watchlists klassifiziert werden.
  Erledigt: `src/backend/app/services.py` cached YFinance-Fundamentals und Watchlist-News jetzt mit TTL, ueberspringt Krypto-Fundamentals komplett und erlaubt `get_stock_data(..., include_news=False, include_fundamentals=False)` fuer schlankere Alert-Pfade; `src/backend/app/main.py` nutzt diese entlastete Variante jetzt im Watchlist-Alert-Feed und im Auto-Scanner ohne unnoetige Fundamentals-Last; `src/backend/app/asset_metadata.py` kann ETFs jetzt auch aus expliziten Fallback-/Watchlist-Namen wie `Vanguard S&P 500 ETF` erkennen; neue Unit-Tests in `tests/test_market_data_service.py` pruefen Cache- und Skip-Verhalten, `tests/test_asset_metadata.py` deckt den ETF-Fallback ab, und `tests/run-api-regression.sh` validiert den erweiterten Watchlist-Pfad jetzt auch mit einem ETF-Eintrag; containerisierte Unit-Tests und die isolierte API-Regression gegen den frischen lokalen Build liefen erfolgreich.
  Offen: Der Providerpfad ist jetzt robuster und billiger, aber noch kein echter breiter ETF-/Krypto-Livefeed; naechster Produktschritt bleibt echte Providerabdeckung fuer ETFs/Krypto-News/-Bars statt nur besserer Fallback- und Cache-Strategie.

- Datum: 2026-03-23
  Kontext: Phase-1-Metadaten und Watchlist-Tags sollen im rekonstruerten Frontend sichtbar werden, ohne auf die langsamere Alert-Berechnung zu blockieren.
  Erledigt: `src/frontend-dist/ui-patches.js` erweitert das bestehende Dashboard-Panel `Watchlist Alerts` um eine `Tracked Assets`-Sektion mit Assetklassen-Mix, Top-Tags, Exchange-/Market-Metadaten und symbolbezogenen Analyse-/Trade-Drilldowns; News- und Tracked-Asset-Daten werden jetzt getrennt vom Alert-Feed gecacht und bereits im Teilzustand gerendert, damit Ticker, Asset-Mix und Tag-Summary auch bei spaeter eintreffendem `/api/watchlists/{id}/alerts` sichtbar bleiben; `tests/run-ui-regression.mjs` seedet im isolierten Stack Watchlist-Tags per API und validiert Asset-Mix, Tag-Summary und Tracked-Asset-Karten erfolgreich; der komplette UI-Lauf gegen den lokalen Build lief erfolgreich auf Alternativports `18190/18194`.
  Offen: Der Patch bleibt eine Bundle-Nachruestung; naechster sinnvoller Produktschritt ist jetzt der Live-Daten-/Providerpfad fuer ETFs und Krypto sowie spaeter die Ueberfuehrung in echten Frontend-Quellstand.

- Datum: 2026-03-20
  Kontext: Im ausgelieferten Frontend sind Dashboard-Shortcut und Alpaca-Settings-Navigation fuer Nutzer missverstaendlich.
  Erledigt: Produktions-Bundle um `src/frontend-dist/ui-patches.js` erweitert und in `index.html` eingebunden; Dashboard versieht die beiden Zahnrad-Shortcuts jetzt mit getrennten Titeln/Iconografie fuer Account Settings vs. User Administration; die Alpaca-/Settings-Seite erhaelt einen sichtbaren `Back to Dashboard`-Button mit explizitem Sprung auf `/`; `tests/run-ui-regression.mjs` prueft diese Punkte rollenbewusst, ist gegen ein Chrome-Cleanup-Race beim Entfernen des temporaeren Browserprofils gehaertet und wurde erfolgreich sowohl gegen einen bestehenden Nicht-Admin-Stack als auch im isolierten Fresh-Stack mit Admin-Shortcut validiert.
  Offen: Nach jedem kuenftigen Frontend-Image-Refresh muss validiert werden, dass der Patch weiter geladen wird oder kontrolliert in echten Frontend-Quellstand ueberfuehrt wurde.

- Datum: 2026-03-20
  Kontext: Phase 1 soll nicht nur Backend-Endpunkte liefern, sondern Watchlist-News und priorisierte Alerts sichtbar in die UI bringen.
  Erledigt: `src/frontend-dist/ui-patches.js` erweitert das rekonstruierte Bundle jetzt um ein Dashboard-Panel `Watchlist Alerts`, das die aktive Watchlist aus dem vorhandenen Select liest, `/api/watchlists/{id}/alerts` und `/api/watchlists/{id}/news` rollenbewusst nachlaedt, priorisierte Signal-/News-Kandidaten anzeigt und den unteren `Live News`-Ticker mit beobachteten Watchlist-News speist; Alert-Karten bieten jetzt Drilldown nach Analyse/Trade/Story, neue High-Priority-Alerts koennen als deduplizierte Toast-Popups auftauchen, und die Insights werden periodisch aktualisiert; `tests/run-ui-regression.mjs` validiert die neue Flaeche inklusive Drilldown-CTA im Dashboard; Low-Level-Regression gegen den Hauptstack und der isolierte Fresh-Stack-Lauf waren erfolgreich.
  Offen: Der Patch ist weiter eine Bundle-Nachruestung; mittelfristig gehoert diese UI in echten Frontend-Quellstand, inklusive echter In-App-Navigation, Popup-Alert-Management und laufender Aktualisierung ohne DOM-Patch-Layer.

- Datum: 2026-03-20
  Kontext: Es fehlt ein kontrollierter Erstzugang fuer Benutzerverwaltung und Admin-Funktionen.
  Erledigt: Startup bootstrapt jetzt optional einen initialen Admin aus `INITIAL_ADMIN_EMAIL` und `INITIAL_ADMIN_PASSWORD`; `INITIAL_ADMIN_MFA_ENABLED=false` erlaubt den ersten Login ohne MFA; API-Regression prueft den Seed-Admin-Lifecycle, und containerisierte Unit-Tests decken die Bootstrap-Logik ab.
  Offen: Im laufenden Haupt-Stack muessen noch echte Bootstrap-Credentials in `.env` gesetzt und der Stack neu gestartet werden, damit dieser Pfad ausserhalb der Tests aktiv ist.

- Datum: 2026-03-20
  Kontext: Watchlist-News nicht nur aggregieren, sondern fuer spaetere Popups und Alerts priorisiert nutzbar machen.
  Erledigt: neues Backend-Modul fuer Watchlist-Alert-Priorisierung aus Signal-, News- und Tag-Kontext eingefuehrt; Endpunkt `/api/watchlists/{id}/alerts` liefert pro beobachtetem Wert priorisierte Alert-Kandidaten mit Signal-/News-Snapshot; `ops/automation/test.sh` fuehrt jetzt host-seitige Unit-Tests aus; API-Regression prueft den neuen Alert-Feed mit.
  Offen: dieselbe Priorisierung muss spaeter ins Frontend bzw. in laufende Popup-/Ticker-Flaechen ueberfuehrt und mit belastbareren Live-News/Livedaten gespeist werden.

- Datum: 2026-03-20
  Kontext: Phase 1 nicht nur mit Metadaten beginnen, sondern Watchlists fachlich mit Tags und News weiterziehen.
  Erledigt: `watchlist_item_tags`-Tabelle eingefuehrt; Watchlist-API um Tags sowie Krypto-taugliche Item-Update/Delete-Pfade erweitert; aggregierter Endpunkt `/api/watchlists/{id}/news` mit Assetmetadaten, Tags und News-Sentiment gebaut; Backup-Export/-Import um Watchlist-Tags erweitert; API-Regression gegen frisch gebaute Images erfolgreich.
  Offen: die neuen Watchlist-Daten muessen noch im Frontend sichtbar werden; News/Signals sollen spaeter priorisiert und in Alerts/Popups ueberfuehrt werden.

- Datum: 2026-03-20
  Kontext: Das Produktziel wieder an die Roadmap binden und nicht in weiterer Plattformpolitur stecken bleiben.
  Erledigt: erste echte Phase-1-Scheibe umgesetzt; zentrale Assetklassifizierung fuer `stock`/`etf`/`crypto` eingefuehrt; Suche, Scanner und Analyse liefern jetzt normalisierte Assetmetadaten; Suchfallback fuer symbolbasierte Queries ohne Alpaca-Assetcache ergaenzt; API-Regression um Analyse-, Such- und Scanner-Metadaten erweitert und erfolgreich gegen frisch gebaute Images ausgefuehrt.
  Offen: naechste fachliche Schritte sind UI-Nutzung dieser Metadaten, News-Bindung und breitere Live-Datenabdeckung fuer Phase 1.

- Datum: 2026-03-20
  Kontext: Logging- und Auditierbarkeits-Haertung fuer den rekonstruierten Backend-Stand fortsetzen.
  Erledigt: JSON-Logging um Request-Kontext erweitert; HTTP-Middleware schreibt `X-Request-ID`, Methode, Pfad, Client-IP, Status und Laufzeit in strukturierte Logs; Audit-Logs fuer Auth-, Mail- und Push-Pfade redigieren identifizierende Werte jetzt auf IDs/Fingerprints; schlanker Unittest fuer Formatter/Context/Fingerprint wurde ergaenzt.
  Offen: dieselbe Telemetrie-Qualitaet fuer Background-Jobs und WebSockets nachziehen sowie produktive VAPID-Secrets ohne Code-Defaults erzwingen.

- Datum: 2026-03-18
  Kontext: Docker-Hub-Repositories fuer das Trading-Projekt identifizieren und lokal unter `/codex` synchronisieren.
  Erledigt: `dbergt/trading-bot-frontend` und `dbergt/trading-bot-backend` verifiziert, Images auf Aktualitaet geprueft, Projekt unter `/codex/trading-bot-v2` rekonstruiert.
  Offen: Originalen Frontend-Quellstand beschaffen und Publish-Namensschema bereinigen.

- Datum: 2026-03-18
  Kontext: Tiefenanalyse des Tools und Ableitung eines Entwicklungsplans.
  Erledigt: Architektur, API-Flaeche, Auth, Persistenz, Sicherheitslage und Betriebsgrenzen dokumentiert.
  Offen: priorisierte Umsetzung der Security- und Architekturmassnahmen.

- Datum: 2026-03-18
  Kontext: Phase-1-Sicherheitshaertung im Backend.
  Erledigt: JWT ohne unsicheren Fallback erzwungen, CORS auf explizite Origins umgestellt, Alpaca-Secrets verschluesselt gespeichert, Passwort-Reset-Tokens gehasht, Login- und Reset-Rate-Limits eingebaut.
  Offen: produktive Reset-Zustellung, pro-User-Watchlists, strukturierte Logging- und Telemetriehaertung.

- Datum: 2026-03-18
  Kontext: Watchlist-Persistenz von globalem JSON auf pro-User-Datenbankmodell umstellen.
  Erledigt: neue Tabellen fuer Watchlists und Watchlist-Items eingefuehrt, Default-Watchlists pro User seeding-basiert, Watchlist- und Scanner-Endpunkte auf DB-Persistenz umgestellt.
  Offen: automatische Migration alter `watchlists.json`-Inhalte in die neuen Tabellen.

- Datum: 2026-03-18
  Kontext: Produktziel auf vollwertige Trading-Workstation ausweiten.
  Erledigt: Zielbild, Phasenmodell, Datenanbieter-Stack und Plattformanforderungen in `docs/admin/product-roadmap.md` festgehalten.
  Offen: Anbieterwahl finalisieren und mit Phase 0 (Backups, Export/Import, Docker-Hub-Sync) beginnen.

- Datum: 2026-03-18
  Kontext: Plattformfundament fuer Backups, Export/Import und PostgreSQL-Ready-Betrieb.
  Erledigt: `DATABASE_URL`-Abstraktion, PostgreSQL-Service im Compose, Backup-Scheduler, Admin-Endpunkte fuer Export/Import/Backup/Download sowie Backup-Service-Modul umgesetzt.
  Offen: echte Runtime-Pruefung mit installierten Dependencies und dauerhafter Docker-Hub-Multi-Image-Sync.

- Datum: 2026-03-18
  Kontext: Vollstaendige Fortsetzungsfaehigkeit fuer spaetere Sitzungen sicherstellen.
  Erledigt: exakter Handover-Stand in `state/handover-2026-03-18.md` dokumentiert; Wiedereinstieg, offener Punktestand und Prioritaeten festgehalten.
  Offen: naechste Sitzung soll direkt mit Runtime-Validierung und anschliessendem Produktausbau fortsetzen.

- Datum: 2026-03-18
  Kontext: Im dokumentierten Wiedereinstieg die Browser-/UI-Regression als echten CI-/Publish-Gate umsetzen.
  Erledigt: `tests/run-ui-regression.sh` fuehrt den Compose-Stack isoliert aus, wartet auf Health, startet die Browserprobe und schreibt Artefakte; `ci.yml` und `publish.yml` fuehren die UI-Regression nun inklusive Artefakt-Upload aus.
  Offen: GitHub-Lauf mit echten Runnern beobachten und die UI-Probe spaeter um weitere Kernfluesse erweitern.

- Datum: 2026-03-18
  Kontext: Den Multi-Image-Docker-Hub-Sync lokal technisch absichern, ohne sofort einen echten Push auszufuehren.
  Erledigt: `ops/automation/sync-components.sh` unterstuetzt jetzt `DRY_RUN=1` und `SKIP_BUILD=1` fuer einen lokalen Publish-Vorabtest mit vorhandenen Images.
  Offen: echten Push gegen Docker Hub mit realen Secrets einmal kontrolliert ausfuehren.

- Datum: 2026-03-18
  Kontext: Den GitHub-Publish-Workflow fuer einen sicheren Vorabtest vorbereiten.
  Erledigt: `publish.yml` unterstuetzt jetzt `workflow_dispatch` mit `dry_run=true`, ueberspringt dann Docker-Login/Push und nutzt vorhandene lokale Images statt doppelt zu bauen.
  Offen: Dry-Run in GitHub Actions einmal ausfuehren und anschliessend einen echten Publish-Lauf pruefen.

- Datum: 2026-03-18
  Kontext: Den offenen Produktpunkt fuer produktive Passwort-Reset-Zustellung abschliessen.
  Erledigt: Passwort-Reset verschickt nun SMTP-Mails an einen konfigurierbaren Frontend-Link; `.env.example` dokumentiert `PASSWORD_RESET_BASE_URL` und `SMTP_*`; die API-Regression prueft jetzt auch Reset-Request, Confirm und Re-Login.
  Offen: SMTP-Konfiguration einmal mit echter Mail-Infrastruktur pruefen und Logging spaeter weiter strukturieren.

- Datum: 2026-03-18
  Kontext: Die neue Passwort-Reset-Mailzustellung nicht nur im Code, sondern auch zur Laufzeit verifizieren.
  Erledigt: `tests/run-password-reset-email-smoke.sh` startet einen lokalen SMTP-Capture-Server im Docker-Testnetz und prueft Reset-Mail, Link-Extraktion, Confirm und Re-Login erfolgreich end to end.
  Offen: denselben Pfad spaeter gegen einen echten externen SMTP-/Mail-Provider pruefen.

- Datum: 2026-03-18
  Kontext: Den vorbereiteten Multi-Image-Docker-Hub-Publish jetzt real ausfuehren.
  Erledigt: `SKIP_BUILD=1 bash ops/automation/sync-components.sh` hat beide Images erfolgreich nach Docker Hub gepusht:
  `dbergt/trading-bot-backend:latest` -> `sha256:6ccd0f476169e184d30c80b7dacdb8f99b6fee65e92f98c8c7a722205052bf84`,
  `dbergt/trading-bot-frontend:latest` -> `sha256:201169e45e11e6edc2fade078cda4d93dfff509dd65d6a42394b7def31fe7167`.
  Offen: denselben Pfad noch einmal kontrolliert in GitHub Actions mit den echten Secrets ausfuehren und die Governance-Frage des Zwei-Image-Modells finalisieren.

- Datum: 2026-03-18
  Kontext: Den lokalen Fortsetzungsstand nach dem Docker-Hub-Publish erneut runtime-validieren.
  Erledigt: aktueller Quellstand neu gebaut; `tests/run-api-regression.sh` repariert, weil der Export-Test nach bewusst angelegtem Zusatznutzer faelschlich weiter `1` Benutzer erwartete; API-Regression und UI-Regression danach erneut erfolgreich ausgefuehrt.
  Offen: ein echter getaggter Docker-Hub-Release plus `deploy.sh`-basiertes Upgrade-Rehearsal bleibt der naechste externe Validierungsschritt; lokal ist der aktuelle Stand wieder gruen.

- Datum: 2026-03-18
  Kontext: Verlustfreien Docker-Hub-Only-Deploy- und Upgrade-Pfad festziehen.
  Erledigt: Compose auf parametrisierte Docker-Hub-Image-Refs umgestellt; persistente Runtime-Daten aus dem Quellbaum nach `state/runtime/...` verlagert; `ops/automation/deploy.sh` fuer Deploy/Upgrade mit Pre-Upgrade-Backup, automatischem Rollback-Versuch und Deployment-Record umgesetzt; Release- und Betriebsdoku auf Docker-Hub-only ausgerichtet.
  Offen: den Pfad jetzt mit einem explizit getaggten Release und einem echten Upgrade-Fall gegen vorhandene Daten proben.

- Datum: 2026-03-18
  Kontext: Den neuen Docker-Hub-Release- und Deploy-Pfad technisch verifizieren.
  Erledigt: `SKIP_BUILD=1 DRY_RUN=1 IMAGE_TAG=2026.03.18-testdeploy bash ops/automation/sync-components.sh` lief erfolgreich und schrieb `state/releases/2026.03.18-testdeploy.env`; isolierter Docker-Hub-Deploy-Smoke-Test via `ops/automation/deploy.sh` auf temporaeren Runtime-Pfaden und eigenen Ports lief ebenfalls erfolgreich und schrieb `state/runtime/deployments/deployment-20260318T211121Z.env`.
  Offen: naechster echter Betriebscheck ist nun ein Upgrade ueber bereits vorhandene Daten inklusive Pre-Upgrade-Dump und Restore-Test.

- Datum: 2026-03-18
  Kontext: Den naechsten Betriebscheck als vollstaendiges Upgrade-/Restore-Rehearsal gegen einen echten Docker-Hub-Release fahren.
  Erledigt: explizite Releases `2026.03.18-1` und danach der Fix-Release `2026.03.18-2` wurden nach Docker Hub gepusht; `tests/run-upgrade-rehearsal.sh` wurde fuer initialen Deploy, Datenanlage, Upgrade ueber bestehenden Datenbestand, Pre-Upgrade-Dump, App-Snapshot und Dump-Restore gebaut; der Restore-Blocker im Legacy-Watchlist-Migrationspfad wurde behoben; das vollstaendige Rehearsal lief fuer `2026.03.18-2` erfolgreich durch.
  Offen: denselben Rehearsal-Pfad kuenftig fuer jeden neuen Release-Tag erneut fahren; Frontend-Quellstand und weitere Produktarbeit bleiben offen.

- Datum: 2026-04-14
  Kontext: Resume `trading-bot-v2`; offenen Alpha-Vantage-BTC-Live-Smoke-Blocker abschliessen.
  Erledigt: `DIGITAL_CURRENCY_DAILY` fuer `BTC/USD` ohne API-Key-Ausgabe inspiziert; Live-Antwort nutzt generische OHLC-Keys (`1. open`, `2. high`, `3. low`, `4. close`) statt der alten waehrungsspezifischen Keys. `AlphaVantageService` akzeptiert jetzt beide Formen, und `tests/test_alpha_vantage_service.py` deckt die generische BTC-Form ab. Focus-Test, lokaler Backend-Image-Build, `BACKEND_IMAGE=trading-bot-v2-backend:local bash tests/run-alpha-vantage-live-smoke.sh` und `bash ops/automation/test.sh` liefen erfolgreich.
  Offen: Fix committen, nach `main` pushen, GitHub-Actions-Publish fuer den neuen `sha-<commit>`-Stand beobachten und danach den Upgrade-/Restore-Rehearsal-Pfad fuer diesen Stand fahren.

- Datum: 2026-04-14
  Kontext: Parserfix veroeffentlichen und Rehearsal fuer den neuen Docker-Hub-Stand fahren.
  Erledigt: Commit `f826304` wurde nach `main` gepusht; GitHub Actions `ci`, `publish` und `codeql` liefen erfolgreich. `IMAGE_TAG=sha-f826304a7850 bash tests/run-alpha-vantage-live-smoke.sh` lief gegen das veroeffentlichte Backend-Image erfolgreich. Das erste Upgrade-Rehearsal scheiterte wegen gesetzter `INITIAL_ADMIN_*`-Werte in der lokalen `.env`; `ops/automation/deploy.sh` und `tests/run-upgrade-rehearsal.sh` wurden daraufhin so gehaertet, dass isolierte Rehearsal-Stacks den Bootstrap-Admin deaktivieren. Der zweite Lauf `IMAGE_TAG=sha-f826304a7850 bash tests/run-upgrade-rehearsal.sh` lief erfolgreich durch; Upgrade-Record `state/runtime/deployments/deployment-20260414T192521Z.env`.
  Offen: Script-/Doku-Follow-up committen und pushen; danach wieder Phase-1-Produktschnitt fuer ETF-/Krypto-Daten weiterziehen.

- Datum: 2026-04-15
  Kontext: Resume `trading-bot-v2`; gepushten Start-/Stop-Follow-up pruefen und ETF-/Krypto-Providerdaten weiter ins Dashboard/Alerting ziehen.
  Erledigt: GitHub Actions fuer `9c2f2b` geprueft; `publish` run `24423017757`, `ci` run `24423017764` und `codeql` run `24423017762` liefen erfolgreich. Danach wurde ein Provider-Coverage-Produktschnitt umgesetzt: Watchlist-Alerts bekommen `providerContext`, Provider-Live-Status/Moves/Research/History fliessen in das Alert-Ranking ein, Alert-Summaries melden Provider-Coverage-Kennzahlen, und das Dashboard zeigt eine neue `Provider Coverage`-Sektion fuer ETF-/Krypto-Werte. API- und UI-Regressionen pruefen den neuen Kontext. Commit `df6f0fa` wurde nach `main` gepusht; `publish` run `24461808225`, `ci` run `24461808223` und `codeql` run `24461808224` liefen erfolgreich. Der Publish-Run synchronisierte `sha-df6f0fa13a5d` und `latest`.
  Verifikation: `docker build -f ops/docker/backend.Dockerfile -t trading-bot-v2-backend:local .`, `bash ops/automation/test.sh`, `SKIP_BUILD=1 bash tests/run-api-regression.sh` und `bash tests/run-ui-regression.sh` liefen erfolgreich.
  Offen: Fuer den naechsten expliziten Release-Tag den Upgrade-/Restore-Rehearsal-Pfad fahren oder den ETF-/Krypto-Livepfad weiter in Research-/Dashboard-Flaechen und echte Nutzer-Alerts ausrollen.
