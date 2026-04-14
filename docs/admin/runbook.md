# Runbook

## Zweck

Betriebsanleitung fuer den lokal rekonstruierten Trading-Bot-V2-Stand.

## Komponenten

- `backend`: FastAPI, Uvicorn, PostgreSQL/SQLAlchemy, Alpaca-/Marktdatenlogik
- `frontend`: Nginx mit statischem Produktions-Bundle, SPA-Fallback und Proxy auf `/api` sowie `/ws`
- `postgres`: primäre Persistenz fuer User, Watchlists, Settings und Backup-Importe

## Start

1. `.env` aus `.env.example` erzeugen und Secrets setzen.
   Fuer einen Bootstrap-Superadmin `INITIAL_ADMIN_EMAIL` und `INITIAL_ADMIN_PASSWORD` setzen.
   Optional fuer den Erstaufbau: `INITIAL_ADMIN_MFA_ENABLED=false`, damit sich der Bootstrap-Admin ohne OTP anmelden und weitere Konten anlegen kann.
   Fuer produktive Passwort-Reset-Mails zusaetzlich `PASSWORD_RESET_BASE_URL`, `SMTP_HOST`, `SMTP_PORT` und `SMTP_FROM_EMAIL` konfigurieren.
2. aktuellen Docker-Hub-Stand starten:
   - `bash ops/automation/start.sh`
3. Health pruefen:
   - Backend ueber Frontend-Proxy: `http://127.0.0.1:18094/api/health`
   - Backend direkt: `http://127.0.0.1:18090/api/health`
   - Frontend: `http://127.0.0.1:18094/login`

`start.sh` setzt ohne weitere Angabe `IMAGE_TAG=latest`, zieht Backend und Frontend frisch von Docker Hub und ruft danach den normalen Deploy-/Upgrade-Pfad auf. Fuer einen festen Stand:

- `IMAGE_TAG=sha-92cefb3138e6 bash ops/automation/start.sh`
- `IMAGE_TAG=2026.03.18-2 bash ops/automation/start.sh`

## Docker-Hub-Deploy

1. in `.env` fuer produktive Rollouts einen expliziten `IMAGE_TAG` setzen
2. `bash ops/automation/deploy.sh`
3. das Skript:
   - erstellt vor Upgrades einen PostgreSQL-Dump
   - erstellt bei laufendem Backend zusaetzlich einen App-Snapshot
   - deployed `backend` und `frontend` aus Docker Hub ohne lokalen Neu-Build
   - schreibt den aktiven Rollout unter `state/runtime/deployments/current.env`
   - mit `TRACK_CURRENT_DEPLOYMENT=0` kann ein isolierter Smoke-Deploy den Alias `current.env` unberuehrt lassen
4. Health pruefen:
   - Backend: `/api/health`
   - Frontend: `/login`

## Stop

- `bash ops/automation/stop.sh`

Das stoppt und entfernt nur Container/Netzwerk des Compose-Stacks. Persistente Daten unter `state/runtime` bleiben erhalten.

## Logs

- `docker compose --env-file .env -f ops/docker/compose.yaml logs -f backend`
- `docker compose --env-file .env -f ops/docker/compose.yaml logs -f frontend`
- `docker compose --env-file .env -f ops/docker/compose.yaml logs -f postgres`

## Regression

- reproduzierbare Backend-API-Laufzeitprobe:
  - `bash tests/run-api-regression.sh`
- reproduzierbare SMTP-Laufzeitprobe fuer Passwort-Reset:
  - `bash tests/run-password-reset-email-smoke.sh`
- reproduzierbare Browser/UI-Laufzeitprobe:
  - `bash tests/run-ui-regression.sh`
- reproduzierbare Upgrade-/Restore-Laufzeitprobe ueber Docker Hub:
  - `IMAGE_TAG=2026.03.18-1 bash tests/run-upgrade-rehearsal.sh`
- reproduzierbare Alpha-Vantage-Liveprobe fuer ETF-/Krypto-Providerdaten:
  - `ALPHA_VANTAGE_API_KEY=... IMAGE_TAG=sha-d4939da591ec bash tests/run-alpha-vantage-live-smoke.sh`
- Low-Level-Browserprobe gegen bereits laufenden Stack:
  - `node tests/run-ui-regression.mjs`
- gepruefte Pfade:
  - Health
  - Register/Login
  - Passwort-Reset-Request und Passwort-Reset-Confirm
  - Watchlist-Alert-Feed mit Priorisierung aus Signal, News und Tags
  - SMTP-Zustellung des Reset-Links an einen Testserver
  - Backup-Liste/Create/Download
  - Export
  - Import
  - Backup-Restore
  - Alpha-Vantage-Live-Snapshots fuer `VOO` und `BTC/USD`, wenn ein echter Provider-Key gesetzt ist
  - geplanter Scheduler-Backup mit Schreibprobe
  - SPA-Routen `/login` und `/register`
  - UI-Registrierung
  - UI-Navigation auf `/settings`
  - Token-Persistenz im Browser

## Datenhaltung

- PostgreSQL-Daten liegen unter `state/runtime/postgres`
- sonstige Backend-Runtime-Daten liegen unter `state/runtime/backend-data`
- Backup-Dateien liegen unter `state/runtime/backups`
- Legacy-/Fallback-Dateien unter `src/backend/data` sind nicht mehr Zielbild
- beim Startup wird ein Watchlist-Migrationspfad fuer alte `watchlists.json`-Bestände ausgefuehrt

## Backup

- automatisch ueber Scheduler im Backend, Intervall via `BACKUP_INTERVAL_SECONDS`
- manuell per Admin-Endpunkt:
  - `POST /api/admin/backups`
- auflisten:
  - `GET /api/admin/backups`
- herunterladen:
  - `GET /api/admin/backups/{filename}`
- Voll-Export:
  - `GET /api/admin/export`

## Restore

1. Backup-Datei ueber Admin-Endpunkt hochladen:
   - `POST /api/admin/backups/import`
   - oder `POST /api/admin/import`
2. Backend-Health und Admin-Login pruefen
3. Watchlists, Nutzer und Push-Subscriptions stichprobenartig verifizieren

## Monitoring

- Health: `GET /api/health`
- besonders beobachtungsbeduerftig:
  - fehlerhafte Bootstrap-Admin-Konfiguration (`INITIAL_ADMIN_*`) beim Startup
  - Scanner-Fehler
  - Alpaca-Verbindungsfehler
  - SMTP-Fehler im Passwort-Reset-Delivery-Pfad
  - Push-Versandfehler
  - ML-Training-/Prediction-Exceptions
  - fehlgeschlagene Backup-Laeufe
  - PostgreSQL-Health und Disk-Wachstum im Backup-Verzeichnis

## Rollback

- Image-basiert: auf vorherige Digests zurueckgehen
- Docker-Hub-basiert bevorzugt ueber vorherigen `IMAGE_TAG` plus `bash ops/automation/deploy.sh`
- datenbasiert: Backup ueber Admin-Import wiederherstellen
- Achtung: formale DB-Migrationskette ist noch nicht vollstaendig auf Alembic o.a. umgestellt
