# Projektstatus

## Stand

- Status: Plattformbasis mit validiertem PostgreSQL-Laufzeitpfad, Bootstrap-Superadmin ohne initialen MFA-Zwang, produktivem Passwort-Reset-Delivery-Pfad, Backup/Export/Import/Download-Adminpfaden, gehaertetem Scheduler, request-korreliertem strukturiertem Backend-Logging sowie mehreren Phase-1-Lieferungen fuer Assetklassifizierung, Watchlist-Tags, Watchlist-News-Bindung, priorisierten Watchlist-Alerts, deren sichtbare Dashboard-Nutzung und jetzt einem echten optionalen Alpha-Vantage-Providerpfad fuer ETFs und Krypto umgesetzt
- Letzte Aktualisierung: 2026-04-12
- Aktive Arbeit: API- und UI-Regression sind als Gates verankert; der verlustfreie Docker-Hub-Deploy-/Upgrade-Pfad ist fuer Release `2026.03.18-2` durchgeprobt, HTTP-Logs tragen Request-ID und redaktierte Audit-Felder, Phase 1 liefert jetzt normalisierte Assetmetadaten, Watchlist-Tags, aggregierte Watchlist-News und einen priorisierten Alert-Feed fuer Watchlists, das Dashboard zeigt Asset-Mix, Top-Tags, Tracked-Asset-Metadaten und providergebundene ETF-/Krypto-Snapshots an; der automatische GitHub-Actions-Publish-Pfad ist mit echten Docker-Hub-Secrets live bestaetigt, sodass der Fokus wieder auf explizite Release-/Upgrade-Rehearsals oder weiteren Phase-1-Produktschnitt wechseln kann

## Gesichert verifiziert

- `dbergt/trading-bot-frontend:latest` und `dbergt/trading-bot-backend:latest` sind am 2026-03-18 lokal verifiziert und aktuell
- interner Compose-Name in beiden Images: `trading-bot-v2`
- Backend-Quellcode konnte aus dem Image extrahiert werden
- Frontend liegt aktuell nur als Build-Artefakt vor
- Handover fuer naechste Sitzung liegt in `state/handover-2026-03-18.md`
- isolierter PostgreSQL-Lauf mit aktuellem Backend-Quellstand wurde erfolgreich geprueft
- Admin-Endpunkte fuer Backup-Liste, manuelles Backup, Export, Import und Backup-Download wurden im Docker-Testnetz erfolgreich geprueft
- Scanner-Leerlauf-Busy-Loop wurde behoben
- Build-Automation bereitet nun beschreibbare Bind-Mount-Verzeichnisse fuer den nicht-root Backend-Container vor
- Backup-Scheduler bricht bei Schreibfehlern nicht mehr als Task ab
- reproduzierbares Skript `tests/run-api-regression.sh` fuehrt die verifizierten API-Laufzeitproben automatisiert aus
- API-Regression prueft jetzt auch Passwort-Reset-Request, Token-Confirm und Re-Login
- Startup kann jetzt einen initialen Admin aus `INITIAL_ADMIN_EMAIL` und `INITIAL_ADMIN_PASSWORD` bootstrappen; mit `INITIAL_ADMIN_MFA_ENABLED=false` ist der erste Admin-Login ohne MFA moeglich
- Export-Pruefung der API-Regression wurde korrigiert: nach dem explizit angelegten zweiten Benutzer validiert der Test jetzt die erwarteten exportierten E-Mail-Adressen statt eines veralteten `users == 1`-Annahmefehlers
- frischer lokaler Build des aktuellen Quellstands wurde erfolgreich ausgefuehrt
- API-Regression lief nach der Testkorrektur erneut erfolgreich gegen die frisch gebauten lokalen Images
- UI-Regression lief anschliessend erneut erfolgreich gegen den frisch gebauten Compose-Stack
- ausgeliefertes Frontend-Bundle wurde um einen gezielten DOM-Patch erweitert: Dashboard-Shortcuts fuer Account Settings und User Administration tragen jetzt klar getrennte Icons/Titel, und die Alpaca-/Settings-Seite hat einen sichtbaren `Back to Dashboard`-Button
- UI-Regression prueft diese beiden Navigationsdetails jetzt explizit, behandelt bereits laufende Nicht-Admin-Stacks rollenbewusst und validiert den Admin-Shortcut im isolierten Fresh-Stack weiterhin verpflichtend; zusaetzlich ist der Lauf gegen ein Headless-Chrome-Cleanup-Race beim Entfernen des temporaren Profils gehaertet
- das rekonstruierte Frontend zeigt jetzt erste Phase-1-Produktdaten direkt im Dashboard: ein neues `Watchlist Alerts`-Panel rendert priorisierte Alert-Kandidaten aus `/api/watchlists/{id}/alerts`, und der bisher generische Footer-Ticker wird mit beobachteten Watchlist-News aus `/api/watchlists/{id}/news` gespeist
- derselbe Dashboard-Patch liefert jetzt auch echte Interaktion: Alert-Karten haben Drilldown-Aktionen fuer Analyse/Trade/News, neue High-Priority-Alerts koennen als deduplizierte Toast-Popups erscheinen, und die Watchlist-Insights werden periodisch aktualisiert
- derselbe Dashboard-Patch nutzt jetzt auch `trackedAssets` sichtbar: eine neue `Tracked Assets`-Sektion zeigt Assetklassen-Mix, Top-Tags, Exchange-/Market-Metadaten und pro Symbol Analyse-/Trade-Drilldowns direkt im Dashboard
- Watchlist-News und Tracked-Asset-Metadaten werden im UI jetzt getrennt vom langsameren Alert-Feed gecacht und bereits im Teilzustand gerendert; dadurch bleiben Ticker, Asset-Mix und Tag-Summary auch dann sichtbar, wenn `/api/watchlists/{id}/alerts` noch laeuft oder partiell spaeter eintrifft
- `tests/run-ui-regression.mjs` seedet im isolierten Stack jetzt Watchlist-Tags per API und validiert Asset-Mix, Top-Tags und Tracked-Asset-Karten erfolgreich; der komplette UI-Lauf war gegen den lokalen Build auf Alternativports `18190/18194` erfolgreich
- `MarketDataService` cached YFinance-Fundamentals und Watchlist-News jetzt mit TTL, ueberspringt Krypto-Fundamentals komplett und vermeidet im Watchlist-Alert-Pfad doppelte News-/Fundamentals-Fetches; dadurch werden ETFs/Krypto im Backend robuster behandelt und Alert-Latenz/Ratelimit-Druck sinkt
- ETF-Klassifizierung greift jetzt auch aus expliziten Watchlist-Namen wie `Vanguard S&P 500 ETF`, selbst wenn kein externer Provider gerade Metadaten liefert
- API-Regression deckt jetzt neben dem Krypto-Watchlist-Pfad auch einen ETF-Watchlist-Eintrag mit Tags, News-Tracking und Alert-Priorisierung ab; der komplette isolierte Lauf gegen den frischen lokalen Build war erfolgreich
- Compose nutzt fuer persistente Backend-Runtime-Daten jetzt standardmaessig `state/runtime/backend-data` statt eines Pfads im Quellbaum
- `ops/automation/deploy.sh` deployt und upgraded jetzt direkt aus Docker Hub, erstellt vor Upgrades Sicherungen und schreibt den aktiven Rollout-Stand nach `state/runtime/deployments/current.env`
- `ops/automation/sync-components.sh` schreibt fuer getaggte Releases jetzt lokale Release-Metadaten unter `state/releases/<IMAGE_TAG>.env`
- versionierter Docker-Hub-Release-Dry-Run mit `IMAGE_TAG=2026.03.18-testdeploy` wurde erfolgreich ausgefuehrt
- Git-Remote `origin` ist lokal per SSH erreichbar; `publish.yml` synchronisiert Pushes nach `main` jetzt fuer Backend und Frontend automatisch nach Docker Hub als `latest` plus `sha-<commit>` und publiziert Git-Tags `v*` als versionierte Release-Tags
- isolierter Docker-Hub-Deploy-Smoke-Test gegen temporaere Runtime-Pfade und eigene Ports lief erfolgreich durch; Deployment-Record wurde unter `state/runtime/deployments/deployment-20260318T211121Z.env` geschrieben
- `tests/run-upgrade-rehearsal.sh` prueft jetzt initialen Docker-Hub-Deploy, Datenanlage, Upgrade ueber bestehenden Datenbestand, Pre-Upgrade-PostgreSQL-Dump, App-Snapshot und Dump-Restore in einen frischen Stack
- Docker-Hub-Release `2026.03.18-2` wurde erfolgreich gepusht:
  - `dbergt/trading-bot-backend:2026.03.18-2` -> `sha256:29cb70ebac978e0a90e9f95b605638e7894391d21ad0123d2cd6d46536986f82`
  - `dbergt/trading-bot-frontend:2026.03.18-2` -> `sha256:201169e45e11e6edc2fade078cda4d93dfff509dd65d6a42394b7def31fe7167`
- vollstaendiges Docker-Hub-Upgrade-/Restore-Rehearsal fuer `2026.03.18-2` lief erfolgreich durch; der Upgrade-Record liegt unter `state/runtime/deployments/deployment-20260318T213234Z.env`
- GitHub-Repository `https://github.com/dannybergt/trading-bot-v2.git` ist jetzt initial befuellt; lokales `main` trackt `origin/main`
- der Restore-Blocker im Legacy-Watchlist-Migrationspfad wurde behoben: bei nicht-SQLite-Datenbanken wird der SQLite-Migrationspfad nun sauber uebersprungen statt den Startup zu crashen
- Backend-Logging fuehrt jetzt pro HTTP-Request eine `X-Request-ID`, schreibt strukturierte Request-Metadaten in JSON-Logs und redigiert identifizierende Audit-Werte wie E-Mail-Adressen und Push-Endpoints auf Fingerprints
- Suche, Scanner und Analyse liefern jetzt normalisierte Assetmetadaten (`assetClass`, `assetLabel`, `type`, `market`, `exchange`, `isCrypto`)
- Assetklassifizierung deckt aktuell `stock`, `etf` und `crypto` ab und nutzt Provider-Metadaten mit heuristischen Fallbacks fuer symbolbasierte Anfragen
- Scanner haelt Watchlist-Eintraege auch ohne Live-Bars sichtbar und gibt dabei trotzdem Assetmetadaten zurueck
- API-Regression prueft jetzt Analyse-, Such- und Scanner-Metadaten fuer Stock- und Krypto-Pfade mit dem frisch gebauten lokalen Image erfolgreich
- Watchlist-Items koennen jetzt normalisierte Tags speichern; Add/Update/Delete unterstuetzen auch Krypto-Symbole mit `/` im Symbolpfad
- neuer Endpunkt `/api/watchlists/{id}/news` bindet News pro Watchlist aggregiert an beobachtete Werte, Tags und Assetmetadaten
- neuer Endpunkt `/api/watchlists/{id}/alerts` priorisiert Watchlist-Eintraege aus Signal-, News- und Tag-Kontext als Backend-Basis fuer spaetere Alerts/Popups
- Backup-Export/-Import deckt Watchlist-Item-Tags jetzt mit ab
- API-Regression prueft Watchlist-Tags, Krypto-Item-Management und Watchlist-News-Bindung erfolgreich gegen den isolierten Docker-Stack
- containerisierte Unit-Tests decken jetzt Assetmetadaten, Logging und Alert-Priorisierung ab; API-Regression prueft den neuen Watchlist-Alert-Feed mit
- containerisierte Unit-Tests decken jetzt auch den Bootstrap-Admin-Pfad ab; API-Regression meldet sich mit dem initial gesaeten Admin an
- `tests/run-password-reset-email-smoke.sh` verifiziert die Passwort-Reset-Zustellung lokal ueber einen SMTP-Capture-Server im Docker-Testnetz
- CI und Publish fuehren das API-Regressionsskript jetzt als Gate vor weiterem Build/Push aus
- Compose-Gesamtlauf mit Frontend wurde erfolgreich geprueft
- Frontend-Nginx liefert SPA-Routen aus und proxyt `/api` sowie `/ws` korrekt an das Backend
- `tests/run-ui-regression.sh` startet einen isolierten Stack, fuehrt die Browser-Regression aus und sammelt Artefakte/Logs
- CI und Publish fuehren das UI-Regressionsskript jetzt als Gate vor weiterem Build/Push aus
- `ops/automation/sync-components.sh` unterstuetzt jetzt lokalen Dry-Run und Wiederverwendung vorhandener Images fuer einen technischen Publish-Vorabtest ohne Registry-Push
- `publish.yml` unterstuetzt nun auch einen manuellen `workflow_dispatch`-Dry-Run ohne Docker-Hub-Login/Pushausfuehrung und vermeidet doppelte Builds im Sync-Schritt
- letzter beobachteter GitHub-Actions-`publish`-Run `#3` auf `main` (`13f5c1d`, 2026-03-23 22:11:49 UTC) scheiterte sofort im Step `Run build hook`; Ursache war kein fachlicher Testfehler, sondern fehlende Exec-Bits auf den direkt im Workflow aufgerufenen Shellskripten
- Shellskripte unter `ops/automation/*.sh` und `tests/*.sh`, die im Workflow direkt ausgefuehrt werden, sind jetzt im Git-Stand als executable markiert, damit der naechste echte `publish`-Run nicht erneut am Build-Hook stoppt
- neuer Backend-Pfad `src/backend/app/alpha_vantage_service.py` liefert optional Alpha-Vantage-basierte ETF-Profile/Holdings, ETF-/Krypto-Tageshistorien und providergebundene ETF-/Krypto-News; `MarketDataService` nutzt diese Daten jetzt fuer Watchlists, Alerts, Analyse-Fallbacks und Scanner-Snapshots
- Watchlist-`trackedAssets`, Alert-Items und `/api/stock/{symbol}` tragen fuer ETFs/Krypto jetzt normalisierte Providerdaten (`provider.status/source/quote/research`), sodass die UI den Unterschied zwischen aktivem Livepfad und fehlender Provider-Konfiguration sichtbar machen kann
- das rekonstruierte Frontend zeigt im Dashboard jetzt auch Alpha-Vantage-gebundene ETF-/Krypto-Metadaten direkt auf den `Tracked Assets`- und Alert-Karten; `tests/run-ui-regression.mjs` seedet dafuer jetzt explizit `VOO` und `BTC/USD` und validiert die Provider-Bindung sichtbar
- containerisierte Unit-Tests plus isolierte API- und UI-Regression gegen den frischen lokalen Build liefen am 2026-03-26 mit dem neuen ETF-/Krypto-Providerpfad erfolgreich durch
- der nachfolgende GitHub-Actions-`publish`-Run `#4` auf `main` (`4233762`, Start 2026-03-26 21:11:17 UTC, Ende 2026-03-26 21:13:42 UTC) lief bereits durch Build, Test, API-Regression und UI-Regression sauber durch und scheiterte erst im Step `Log in to Docker Hub`
- der aktuellste beobachtete GitHub-Actions-`publish`-Run `#5` auf `main` (`87e4196`, Start 2026-03-27 09:05:13 UTC, Ende 2026-03-27 09:07:36 UTC) bestaetigte denselben Stand erneut: alle Gates gruen, danach Fehler `Username and password required` im Docker-Hub-Login
- `.github/workflows/publish.yml` prueft fehlende Docker-Hub-Secrets jetzt explizit vor `docker/login-action`, damit kuenftige Fehlstarts im Runner eindeutiger benannt werden
- der nachfolgende GitHub-Actions-`publish`-Run `#6` auf `main` (`d4939da`, Start 2026-03-27 11:16:30 UTC, Ende 2026-03-27 11:19:43 UTC) lief vollstaendig erfolgreich durch: Build, Test, API-Regression, UI-Regression, Docker-Hub-Secret-Pruefung, Docker-Hub-Login, `sha-d4939da591ec`-Sync und `latest`-Sync
- Docker-Hub-Image-Pulls fuer den Actions-Publish-Stand wurden am 2026-04-12 lokal bestaetigt:
  - `dbergt/trading-bot-backend:sha-d4939da591ec` -> `sha256:4650bcd75afbd953471bd10144a085cedeb30bc90324677a6ba3d98cb6d6d377`
  - `dbergt/trading-bot-frontend:sha-d4939da591ec` -> `sha256:4c6d0ccfa13717d1f2effeabad32106f3eedc298396c3602e550b38f37cc289e`
- vollstaendiges Docker-Hub-Upgrade-/Restore-Rehearsal fuer `sha-d4939da591ec` lief am 2026-04-12 erfolgreich durch; geprueft wurden initialer Deploy, Datenanlage, Upgrade ueber bestehenden Datenbestand, Pre-Upgrade-PostgreSQL-Dump, App-Snapshot und Dump-Restore in einen frischen Stack
- der zugehoerige Upgrade-Record liegt unter `state/runtime/deployments/deployment-20260412T155353Z.env`
- die SMTP-/Passwort-Reset-Variablen aus `.env.example` werden nun auch im Compose-Backend-Service durchgereicht, damit `PASSWORD_RESET_BASE_URL`, `SMTP_*` und `ENABLE_INSECURE_DEBUG_RESET_TOKENS` im lokalen Compose-Lauf wirksam werden
- `tests/run-alpha-vantage-live-smoke.sh` prueft bei gesetztem `ALPHA_VANTAGE_API_KEY` echte Alpha-Vantage-Snapshots fuer `VOO` und `BTC/USD` sowie deren Durchreichung ueber `MarketDataService`
- Passwort-Reset kann jetzt ueber SMTP an einen konfigurierbaren Frontend-Reset-Link zugestellt werden
- SMTP-Reset-Zustellung wurde lokal erfolgreich gegen einen Testserver inklusive Link-Extraktion, Confirm und Re-Login verifiziert
- Docker-Hub-Publish wurde lokal erfolgreich ausgefuehrt:
  - `dbergt/trading-bot-backend:latest` -> `sha256:6ccd0f476169e184d30c80b7dacdb8f99b6fee65e92f98c8c7a722205052bf84`
  - `dbergt/trading-bot-frontend:latest` -> `sha256:201169e45e11e6edc2fade078cda4d93dfff509dd65d6a42394b7def31fe7167`
- Compose-Testdaten wurden nach den Verifikationen wieder bereinigt

## Offene Punkte

- Originaler Frontend-Quellstand fehlt
- Persistenz- und Migrationsstrategie ist fuer weiteres Wachstum zu schwach
- keine belastbare Test-Suite fuer Kernfluesse vorhanden
- kuenftige Release-Tags muessen denselben Upgrade-/Restore-Rehearsal-Pfad erneut bestehen
- der automatische GitHub-Actions-Publish-Pfad ist fuer `main` live bestaetigt; bei kuenftigen Workflow-Aenderungen weiter auf Secret-/Namespace-Drift achten
- lokal ist kein `ALPHA_VANTAGE_API_KEY` gesetzt; der neue Providerpfad ist damit verifiziert, faellt hier aber bewusst auf `provider.status=unavailable` fuer ETF/Krypto zurueck
- die neue Alpha-Vantage-Liveprobe ist vorbereitet, konnte aber lokal mangels `ALPHA_VANTAGE_API_KEY` noch nicht gegen echte Providerantworten laufen
- Nachtrag 2026-04-12: In der aktiven lokalen `.env` ist nun ein `ALPHA_VANTAGE_API_KEY` gesetzt. Der Live-Smoke erreicht Alpha Vantage; `VOO` kam durch, `BTC/USD` liefert im aktuellen Test aber zu wenig History. Die gezielte Analyse der BTC-Antwortstruktur wurde durch Nutzerunterbrechung noch nicht abgeschlossen.
- das Backend-Docker-Hub-Repo ist ueber die unauthentifizierte Docker-Hub-API nicht sichtbar; zur Verifikation daher `docker pull` mit lokaler Authentifizierung oder GitHub-Actions-Logs nutzen

## Naechste Schritte

- denselben Rehearsal-Pfad fuer jeden neuen Release-Tag diszipliniert wiederholen
- fuer den naechsten produktiven Stand einen expliziten Release-Tag erzeugen und danach den Upgrade-/Restore-Rehearsal-Pfad gegen diesen Tag fahren
- GitHub-Actions-`publish` bei kuenftigen `main`-Pushes weiter beobachten, aber nicht mehr als aktueller Blocker behandeln
- Alpha-Vantage-BTC-Antwortstruktur fuer `DIGITAL_CURRENCY_DAILY` ohne Key-Ausgabe pruefen, weil `BTC/USD` im Live-Smoke aktuell zu wenig History liefert
- danach den eingebauten ETF-/Krypto-Livepfad per `IMAGE_TAG=sha-d4939da591ec bash tests/run-alpha-vantage-live-smoke.sh` erneut pruefen und ggf. auf weitere UI-Flaechen ausrollen
- `current.env` nur fuer echte Zielumgebungen und nicht fuer Smoke-Staende schreiben
- Frontend-Quellstand beschaffen oder kontrolliert rekonstruieren
- die rekonstruierte Bundle-Patch-Schicht bei kuenftigen Frontend-Image-Updates mitpruefen, damit der nachgeruestete Settings-/Admin-Navigationsfix nicht verloren geht
- den neuen Watchlist-Alerts-/News-/Tracked-Assets-Patch bei kuenftigen Frontend-Image-Updates mitpruefen oder in echten Frontend-Quellstand ueberfuehren
- produktive Push-/VAPID-Secrets ohne Code-Defaults erzwingen
- Assetklassifizierung, Watchlist-Tags, News-Bindung und Alert-Priorisierung aus dem aktuellen Dashboard-Patch in weitere UI-Flows und spaeter in echten Frontend-Quellstand ueberfuehren
- echte Live-Daten-/Providerpfade fuer ETFs und Krypto weiter schliessen, damit Phase 1 nicht auf Fallback-Metadaten, gecachten Leerantworten und spaerlichen Newsfeeds stehen bleibt
- Watchlist-Alert-Feed spaeter in laufenden News-Ticker, Popups und aktive Nutzer-Alerts ueberfuehren
- Datenmodell und Migrationen professionalisieren
- verbleibende Logging-/Telemetry-Haertung fuer Background-Jobs und WebSockets nachziehen
- Phase 1 Produktausbau gem. `docs/admin/product-roadmap.md` konsequent weiterziehen
