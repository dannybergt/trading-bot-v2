# Current Focus

## Resume Codeword

Wenn der Nutzer nur dies schreibt:

`resume trading-bot-v2`

dann zuerst in genau dieser Reihenfolge lesen:

1. `state/current-focus.md`
2. `state/project-status.md`
3. `state/chat/session-log.md`

und danach ohne Rueckfragen an der unten beschriebenen Stelle fortsetzen.

## Stand Beim Letzten Handover

- Aktueller Release-Stand: `v2026.05.05-1` auf Commit `ec48455` (`Dispatch watchlist push alerts`) ist gepusht, GitHub-Actions-`publish` run `#16` lief erfolgreich und synchronisierte die versionierten Docker-Hub-Tags.
- Docker-Hub-Rehearsal fuer `IMAGE_TAG=2026.05.05-1` lief erfolgreich: initialer Deploy, Datenanlage, Upgrade ueber bestehenden Datenbestand, Pre-Upgrade-PostgreSQL-Dump, App-Snapshot und Dump-Restore in einen frischen Stack.
- Rehearsal-Artefakte: Deployment-Record `state/runtime/deployments/deployment-20260505T202750Z.env`; Backend-Digest `sha256:9ba0eecf4a1ace9259705191b500fc2b4d0183145076cc34f1702dfabcc4e272`; Frontend-Digest `sha256:973882f6813f9efe7c7f32bbbdccfa4ba7c30c8d4552a4526daf0cb0636159fb`.
- Gesamtplan-Verankerung: `docs/admin/project-plan.md` beschreibt aktuellen Release, Phasenposition, Sicherheitsachsen, Architekturachsen und Prioritaeten; README, Roadmap, Release- und Security-Doku wurden darauf ausgerichtet.
- Aktueller lokaler Security-Stand: produktive Push-/VAPID-Konfiguration wurde ohne Code-Defaults gehaertet; Backend und Frontend nutzen keine eingebetteten Default-VAPID-Keys mehr.
- Neue Backend-Pfade:
  - `PushService.validate_configuration()` prueft `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIMS_SUB` und erzwingt sie bei `APP_ENV=production` oder `REQUIRE_VAPID_SECRETS=true`
  - `/api/auth/push/config` liefert Browsern nur `configured` und den oeffentlichen VAPID-Key
  - Web-Push-Versand wird bei fehlender lokaler VAPID-Konfiguration uebersprungen statt mit geteilten Defaults zu senden
- Neuer Smoke: `tests/run-push-config-smoke.sh`; Standardmodus validiert echte Zielkonfiguration ohne Nutzergeraete zu benachrichtigen, `GENERATE_TEST_VAPID=1` prueft den Parser mit einem disposable Keypair.
- Verifikation: `bash ops/automation/build.sh`, `bash ops/automation/test.sh`, `GENERATE_TEST_VAPID=1 bash tests/run-push-config-smoke.sh`, `SKIP_BUILD=1 bash tests/run-api-regression.sh`, `SKIP_BUILD=1 bash tests/run-ui-regression.sh`; ein UI-Zwischenlauf scheiterte transient am bekannten externen Daten-/Navigationspfad, der direkte Wiederholungslauf war gruen.
- Naechster sinnvoller Schritt: VAPID-Haertung committen, nach `main` pushen und GitHub Actions beobachten.

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

## Aktueller Fokus

- Nicht mehr am Build-Hook, an den Regressionen oder am Docker-Hub-Login arbeiten; diese Huerden sind fuer den aktuellen Stand genommen.
- Der automatische GitHub-Actions-Publish-Pfad ist mit echten Secrets live bestaetigt.
- Der veroeffentlichte `sha-d4939da591ec`-Stand ist durch ein Upgrade-/Restore-Rehearsal als deploybar bestaetigt; der neuere Parserfix-Stand `sha-f826304a7850` ist ebenfalls live-smoke- und upgrade-/restore-validiert.
- Der Alpha-Vantage-BTC-Liveblocker ist behoben: `DIGITAL_CURRENCY_DAILY` liefert fuer `BTC/USD` aktuell generische OHLC-Keys (`1. open`, `2. high`, `3. low`, `4. close`) statt der alten waehrungsspezifischen Keys; der Parser akzeptiert jetzt beide Formen.
- Das Upgrade-Rehearsal ignoriert fuer seine isolierten Wegwerf-Stacks jetzt reale `INITIAL_ADMIN_*`-Werte aus `.env`, damit eine lokale Zielumgebungs-Konfiguration den Test-Admin-Seed nicht entprivilegiert.
- Naechster sinnvoller Schritt ist:
  - VAPID-Haertung pushen und GitHub Actions beobachten
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
