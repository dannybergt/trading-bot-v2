# Trading Bot V2

Rekonstruierter lokaler Arbeitsstand des Trading-Projekts aus Docker-Hub-Images und vorhandenen lokalen Images.

Stand der Synchronisierung:

- Docker Hub: `dbergt/trading-bot-frontend:latest`, verifiziert am 18.03.2026
- Docker Hub: `dbergt/trading-bot-backend:latest`, verifiziert am 18.03.2026
- Interner Compose-/Projektname in den Images: `trading-bot-v2`
- Frontend lokal nur als ausgeliefertes Build-Bundle vorhanden
- Backend lokal mit Python-Quellcode vorhanden

## Projektbild

Das Tool ist eine AI-gestuetzte Trading-Anwendung mit:

- FastAPI-Backend fuer Marktanalyse, Scanner, Watchlists, Auth, MFA, Push und Alpaca-Integration
- priorisierter Watchlist-Alert-Feed mit Signal-, News-, Tag- und Provider-Kontext
- persistiertes Watchlist-Alert-Management und serverseitiger Watchlist-Push-Dispatcher mit Delivery-Deduplizierung
- Nginx-Frontend mit bereits gebautem Web-Bundle, SPA-Fallback sowie `/api`-/`/ws`-Proxy zum Backend
- SQLAlchemy-Persistenz mit SQLite-Fallback und PostgreSQL-Ready-Pfad fuer User, Reset-Tokens, Watchlists, Alert-Settings, Alert-Deliveries und Push-Subscriptions
- externer Datenintegration ueber Alpaca, yfinance, Alpha Vantage, FIGI/WKN/ISIN-Suche
- ML-gestuetzter Kursprognose mit `scikit-learn` und `xgboost`

Der aktuelle Gesamtstand und die Phasenposition sind in `docs/admin/project-plan.md` verankert. Aktuell vollstaendig verifizierter Release: `2026.05.05-1`.

## Lokale Struktur

- `src/backend`: aus dem Backend-Image extrahierter Quellstand
- `src/frontend-dist`: aus dem Frontend-Image extrahiertes Produktions-Bundle
- `docs/admin`: Betriebs-, Release-, Sicherheits- und Rekonstruktionsdoku
- `docs/user`: Nutzerperspektive und Grenzen
- `ops/automation`: Build-, Test-, Scan- und Sync-Skripte
- `ops/docker`: lokale Container-Artefakte fuer Backend und Frontend
- `state`: Status, Entscheidungen und Sitzungsnotizen

## Release- und Deploy-Modell

Die Distribution erfolgt ausschliesslich ueber Docker Hub:

- Backend: `dbergt/trading-bot-backend`
- Frontend: `dbergt/trading-bot-frontend`
- Pushes nach `main` synchronisieren die beiden Images automatisch ueber GitHub Actions nach Docker Hub und publizieren dabei `latest` sowie einen unveraenderlichen Commit-Tag `sha-<commit>`
- versionierte Releases bleiben zusaetzlich an explizite Git-Tags `v*` gebunden und werden als gleichlautender Docker-Hub-Tag ohne das fuehrende `v` publiziert
- produktive Upgrades sollen weiterhin ueber explizite Release-Tags verteilt werden, nicht ueber das bewegliche `latest`
- `ops/automation/sync-components.sh` publiziert beide Images und schreibt dazu ein lokales Release-Metadatenfile unter `state/releases/<tag>.env`
- `ops/automation/deploy.sh` deployt oder upgraded denselben Stand spaeter wieder aus Docker Hub und erstellt vorher Sicherungen

## Schnellstart

1. `.env.example` nach `.env` kopieren.
   Diese Datei bleibt die Basis-Konfiguration fuer Ports, Image-Tags und lokale Pfade.
2. Fuer dauerhafte private Keys und persoenliche Zugangsdaten optional `.env.local.example` nach `.env.local` kopieren und dort nur die benoetigten Zeilen entkommentieren bzw. sensible Overrides setzen.
   Die Ops-Skripte laden immer erst `.env` und danach `.env.local`; dadurch ueberlebt dein privater Key-Satz auch dann, wenn `.env` spaeter neu aus `.env.example` erzeugt oder bereinigt wird.
   Fuer einen initialen Verwaltungszugang `INITIAL_ADMIN_EMAIL` und `INITIAL_ADMIN_PASSWORD` setzen.
   `INITIAL_ADMIN_MFA_ENABLED=false` erlaubt den Erstlogin des Bootstrap-Admins ohne MFA.
   Fuer produktive Passwort-Reset-Mails muessen zusaetzlich `PASSWORD_RESET_BASE_URL`, `SMTP_HOST` und `SMTP_FROM_EMAIL` gesetzt sein.
3. aktuellen Docker-Hub-Stand starten:
   - `bash ops/automation/start.sh`
4. Frontend im Browser oeffnen:
   - `http://127.0.0.1:18094/login`
5. Backend-Health ueber den Frontend-Proxy pruefen:
   - `http://127.0.0.1:18094/api/health`
6. Stack stoppen, ohne Runtime-Daten zu loeschen:
   - `bash ops/automation/stop.sh`

`start.sh` nutzt standardmaessig Docker Hub `latest`. Ein expliziter Stand bleibt moeglich:

- `IMAGE_TAG=sha-92cefb3138e6 bash ops/automation/start.sh`
- `IMAGE_TAG=2026.05.05-1 bash ops/automation/start.sh`

## Docker-Hub-Deploy

1. in `.env` einen expliziten Release-Tag setzen, z. B. `IMAGE_TAG=2026.05.05-1`
2. optional direkte Image-Refs setzen oder aus Namespace, Image-Namen und Tag ableiten lassen
3. `bash ops/automation/deploy.sh`
4. der Deploy-Pfad erstellt vor einem Upgrade automatisch einen PostgreSQL-Dump und, wenn das Backend bereits laeuft, einen App-Snapshot in `state/runtime/backups`
5. der ausgerollte Stand wird unter `state/runtime/deployments/current.env` protokolliert

## GitHub-Automation

- sinnvolle Aenderungen werden lokal committed und nach `origin/main` gepusht
- der Workflow `.github/workflows/publish.yml` baut, testet und synchronisiert auf jedem Push nach `main` automatisch beide Docker-Hub-Images
- fuer jeden `main`-Push entstehen:
  - `docker.io/<namespace>/trading-bot-backend:latest`
  - `docker.io/<namespace>/trading-bot-frontend:latest`
  - `docker.io/<namespace>/trading-bot-backend:sha-<commit>`
  - `docker.io/<namespace>/trading-bot-frontend:sha-<commit>`
- fuer Release-Tags `v2026.05.05-1` entstehen die versionierten Docker-Hub-Tags `2026.05.05-1`
- dafuer muessen in GitHub Actions mindestens `DOCKERHUB_USERNAME` und `DOCKERHUB_TOKEN` als Repository-Secrets gesetzt sein; `DOCKERHUB_NAMESPACE` ist optional und faellt sonst auf `.env.example` zurueck

## Regressionstest

- API-Laufzeitprobe fuer Auth, Backup, Export, Import und Download:
  - `bash tests/run-api-regression.sh`
- SMTP-Smoke-Test fuer produktive Passwort-Reset-Zustellung:
  - `bash tests/run-password-reset-email-smoke.sh`
- Browser/UI-Laufzeitprobe mit eigenem Stack-Start, Login, Register und Settings:
  - `bash tests/run-ui-regression.sh`
- Upgrade-Rehearsal fuer Docker-Hub-Deploy, Pre-Upgrade-Dump und Dump-Restore:
  - `IMAGE_TAG=2026.05.05-1 bash tests/run-upgrade-rehearsal.sh`
- Low-Level-Browserprobe gegen bereits laufenden Stack:
  - `node tests/run-ui-regression.mjs`

## Lokaler Betrieb

- Stack starten:
  - `bash ops/automation/start.sh`
- Stack stoppen:
  - `bash ops/automation/stop.sh`
- Live-Logs ansehen:
  - `bash ops/automation/logs.sh backend`
  - `bash ops/automation/logs.sh frontend`
  - `bash ops/automation/logs.sh postgres`

## Prioritaeten

- produktive Push-/VAPID-Konfiguration je Zielumgebung mit `REQUIRE_VAPID_SECRETS=true` erzwingen und per `tests/run-push-config-smoke.sh` validieren
- DB-Migrationspfad fuer PostgreSQL-first professionalisieren
- Provider- und Live-Datenabdeckung weiter ausbauen
- Frontend-Quellstand statt nur Build-Artefakt beschaffen oder rekonstruieren
- getaggte Docker-Hub-Releases und Deploy-/Upgrade-Rehearsals diszipliniert fahren
- strukturierte Logging-/Telemetrie-Haertung nachziehen
