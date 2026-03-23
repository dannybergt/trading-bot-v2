# Projektstatus

## Stand

- Status: Plattformbasis mit validiertem PostgreSQL-Laufzeitpfad, Bootstrap-Superadmin ohne initialen MFA-Zwang, produktivem Passwort-Reset-Delivery-Pfad, Backup/Export/Import/Download-Adminpfaden, gehaertetem Scheduler, request-korreliertem strukturiertem Backend-Logging sowie mehreren Phase-1-Lieferungen fuer Assetklassifizierung, Watchlist-Tags, Watchlist-News-Bindung, priorisierten Watchlist-Alerts, deren sichtbare Dashboard-Nutzung und einen entlasteten ETF-/Krypto-Providerpfad umgesetzt
- Letzte Aktualisierung: 2026-03-23
- Aktive Arbeit: API- und UI-Regression sind als Gates verankert; der verlustfreie Docker-Hub-Deploy-/Upgrade-Pfad ist fuer Release `2026.03.18-2` durchgeprobt, HTTP-Logs tragen Request-ID und redaktierte Audit-Felder, Phase 1 liefert jetzt normalisierte Assetmetadaten, Watchlist-Tags, aggregierte Watchlist-News und einen priorisierten Alert-Feed fuer Watchlists, das Dashboard zeigt Asset-Mix, Top-Tags und Tracked-Asset-Metadaten jetzt auch dann schon an, wenn die langsamere Alert-Berechnung noch laeuft, und der Backend-Pfad cacht News/Fundamentals jetzt providerbewusst statt Krypto/Alerts unnoetig ueber YFinance zu jagen; naechster Fokus ist der weitere fachliche Ausbau echter Live-Daten/Provider fuer ETFs und Krypto sowie spaeter die Ueberfuehrung der Bundle-Patches in echten Frontend-Quellstand

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
- kuenftige Releases muessen denselben Upgrade-/Restore-Rehearsal-Pfad erneut bestehen

## Naechste Schritte

- denselben Rehearsal-Pfad fuer jeden neuen Release-Tag diszipliniert wiederholen
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
