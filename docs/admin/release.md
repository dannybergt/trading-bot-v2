# Release

## Status

Lokaler Build, versionierter Docker-Hub-Publish und Docker-Hub-Deploy/Upgrade sind technisch angelegt. Der operative Zielpfad ist jetzt ausdruecklich: Docker Hub als einzige Ablage und als Distribution Point. Pushes nach `main` synchronisieren die Images zusaetzlich automatisch ueber GitHub Actions nach Docker Hub.

## Aktuelle Registry-Situation

- lokaler Projektordner: `trading-bot-v2`
- Docker-Hub-Repositories:
  - `dbergt/trading-bot-backend`
  - `dbergt/trading-bot-frontend`
- Release-Disziplin:
  - `main` publiziert automatisch `latest` plus einen unveraenderlichen `sha-<commit>`-Tag fuer Backend und Frontend
  - Git-Tags `v*` publizieren den gleichlautenden Docker-Hub-Release-Tag ohne fuehrendes `v`
  - keine produktiven Upgrades ueber ein schwebendes `latest`
  - fuer Releases immer explizite Tags verwenden, z. B. `2026.03.18-1`
  - aktuell vollstaendig verifizierter Release: `2026.03.18-2`

## Build

- lokal beide Komponenten bauen:
  - `ops/automation/build.sh`

## Test

- Mindestpruefung:
  - `ops/automation/test.sh`
  - `bash tests/run-api-regression.sh`
  - `bash tests/run-password-reset-email-smoke.sh`
  - `bash tests/run-ui-regression.sh`
  - `IMAGE_TAG=2026.03.18-1 bash tests/run-upgrade-rehearsal.sh`
  - optional mit echtem Provider-Key:
    `ALPHA_VANTAGE_API_KEY=... IMAGE_TAG=sha-d4939da591ec bash tests/run-alpha-vantage-live-smoke.sh`
  - optional `node tests/run-ui-regression.mjs` gegen bereits laufenden Stack
  - optional manuell `docker compose -f ops/docker/compose.yaml up --build`

## Scan

- `ops/automation/scan.sh`

## Publish

- GitHub-Automation:
  - `.github/workflows/publish.yml` laeuft automatisch auf Push nach `main` sowie auf Git-Tags `v*`
  - der Workflow fuehrt vor dem Push `build`, `test`, API-Regression und UI-Regression als Gates aus
  - `main` erzeugt automatisch `latest` und `sha-<commit>`
  - `v2026.03.18-3` erzeugt automatisch den Docker-Hub-Tag `2026.03.18-3`
  - benoetigte Repository-Secrets:
    - `DOCKERHUB_USERNAME`
    - `DOCKERHUB_TOKEN`
    - optional `DOCKERHUB_NAMESPACE`, sonst gilt der Wert aus `.env.example`
  - wenn der Step `Log in to Docker Hub` bzw. die neue Secret-Pruefung mit `Username and password required` oder `Missing Docker Hub secrets` fehlschlaegt, sind `DOCKERHUB_USERNAME` und/oder `DOCKERHUB_TOKEN` im GitHub-Repository fehlend oder leer; in `Settings -> Secrets and variables -> Actions` setzen oder rotieren und danach den `publish`-Run erneut starten

- Multi-Image-Sync lokal:
  - `bash ops/automation/sync-components.sh`
- technischer Vorabtest ohne Registry-Push:
  - `SKIP_BUILD=1 DRY_RUN=1 bash ops/automation/sync-components.sh`
- Voraussetzung fuer echte Pushes:
  - lokales `docker login` gegen Docker Hub mit dem Ziel-Account
- Gate vor dem Docker-Hub-Push:
  - `ops/automation/build.sh`
  - `ops/automation/test.sh`
  - `SKIP_BUILD=1 bash tests/run-api-regression.sh`
  - `SKIP_BUILD=1 bash tests/run-ui-regression.sh`
- nuetzliche lokale Schalter fuer den Sync-Pfad:
  - `SKIP_BUILD=1` nutzt bereits vorhandene lokale Images statt neu zu bauen
  - `DRY_RUN=1` taggt bzw. baut nur und fuehrt keinen `docker push` aus
- nach jedem Publish schreibt `ops/automation/sync-components.sh` ein Release-Metadatenfile:
  - `state/releases/<IMAGE_TAG>.env`
- empfohlenes Release-Beispiel:
  - `IMAGE_TAG=2026.03.18-1 bash ops/automation/sync-components.sh`
  - fuer den aktuell validierten Stand:
    `IMAGE_TAG=2026.03.18-2 bash ops/automation/sync-components.sh`

## Deploy und Upgrade

- aus Docker Hub deployen oder upgraden:
  - `IMAGE_TAG=2026.03.18-1 bash ops/automation/deploy.sh`
- kompletter Upgrade-/Restore-Probelauf:
  - `IMAGE_TAG=2026.03.18-1 bash tests/run-upgrade-rehearsal.sh`
  - aktuell erfolgreich verifiziert:
    `IMAGE_TAG=2026.03.18-2 bash tests/run-upgrade-rehearsal.sh`
  - aktueller Actions-Publish-Stand erfolgreich verifiziert:
    `IMAGE_TAG=sha-d4939da591ec bash tests/run-upgrade-rehearsal.sh`
- Verhalten des Deploy-Skripts:
  - zieht Backend- und Frontend-Images aus Docker Hub
  - erstellt vor einem Upgrade einen PostgreSQL-Dump
  - erstellt, wenn das Backend laeuft, zusaetzlich einen App-Snapshot
  - rollt den Compose-Stack ohne Neu-Build aus
  - wartet auf Backend-Health und Frontend-Login-Route
  - schreibt den aktiven Rollout-Stand nach `state/runtime/deployments/current.env`
  - versucht bei Fehlschlag automatisch den Ruecksprung auf die vorherigen Image-Refs
- fuer isolierte Smoke- oder Rehearsal-Deployments:
  - `TRACK_CURRENT_DEPLOYMENT=0` verhindert das Ueberschreiben von `state/runtime/deployments/current.env`

## Rollback

- primaerer Ruecksprungpfad:
  - `state/runtime/deployments/current.env` bzw. das vorherige Deployment-Record lesen
  - vorherigen `IMAGE_TAG` wieder setzen
  - `bash ops/automation/deploy.sh`
- datenbasierter Ruecksprung:
  - PostgreSQL-Dump aus `state/runtime/backups`
  - oder App-Snapshot per Admin-Import

## Persistenzregel

- keine produktiven Runtime-Daten unter `src/` ablegen
- persistente Host-Pfade liegen unter `state/runtime/...`
- Compose-Upgrades duerfen Volumes und Host-Bind-Mounts nicht loeschen
