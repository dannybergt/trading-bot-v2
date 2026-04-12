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

- Letzter relevanter Commit auf `main`: `d4939da` (`Clarify Docker Hub secret failure path`)
- Letzter gepruefter GitHub-Actions-`publish`-Run: `#6`
- Run-Link: `https://github.com/dannybergt/trading-bot-v2/actions/runs/23643694566`
- Run-Zeitpunkt: Start `2026-03-27 11:16:30 UTC`, Ende `2026-03-27 11:19:43 UTC`
- Ergebnis: Build/Test/API/UI, `Validate Docker Hub secrets`, `Log in to Docker Hub`, `Sync primary image tag` und `Sync latest image tag` liefen erfolgreich durch
- Docker-Hub-Nachweis:
  - `docker pull dbergt/trading-bot-backend:sha-d4939da591ec` erfolgreich, Digest `sha256:4650bcd75afbd953471bd10144a085cedeb30bc90324677a6ba3d98cb6d6d377`
  - `docker pull dbergt/trading-bot-frontend:sha-d4939da591ec` erfolgreich, Digest `sha256:4c6d0ccfa13717d1f2effeabad32106f3eedc298396c3602e550b38f37cc289e`
- Upgrade-/Restore-Rehearsal fuer `IMAGE_TAG=sha-d4939da591ec` lief am `2026-04-12` erfolgreich durch:
  - initialer Docker-Hub-Deploy, Datenanlage, Upgrade ueber Bestand, PostgreSQL-Dump, App-Snapshot und Dump-Restore in frischem Stack
  - Deployment-Record: `state/runtime/deployments/deployment-20260412T155353Z.env`

## Aktueller Fokus

- Nicht mehr am Build-Hook, an den Regressionen oder am Docker-Hub-Login arbeiten; diese Huerden sind fuer den aktuellen Stand genommen.
- Der automatische GitHub-Actions-Publish-Pfad ist mit echten Secrets live bestaetigt.
- Der veroeffentlichte `sha-d4939da591ec`-Stand ist durch ein Upgrade-/Restore-Rehearsal als deploybar bestaetigt.
- Naechster sinnvoller Schritt ist Phase 1 weiterziehen:
  - echten `ALPHA_VANTAGE_API_KEY` in einer Zielumgebung setzen
  - `IMAGE_TAG=sha-d4939da591ec bash tests/run-alpha-vantage-live-smoke.sh` ausfuehren
  - ETF-/Krypto-Livepfade gegen reale Providerantworten validieren
  - danach ETF-/Krypto-News, Bars und Research-Daten breiter in Alerts/Dashboard ausrollen

## Wichtiger Kontext

- Der neue ETF-/Krypto-Providerpfad ist bereits implementiert und lokal verifiziert.
- Lokal ist kein `ALPHA_VANTAGE_API_KEY` gesetzt; deshalb wurde der Pfad hier mit sichtbarem `provider.status=unavailable` verifiziert.
- `tests/run-alpha-vantage-live-smoke.sh` ist vorbereitet und bricht ohne gesetzten Key bewusst ab, ohne den Key-Wert auszugeben.
- `.github/workflows/publish.yml` meldet fehlende Docker-Hub-Secrets jetzt explizit vor `docker/login-action`; beim letzten echten Lauf waren die benoetigten Secrets gesetzt und gueltig.
- Die Docker-Hub-Frontend-Tags sind ueber die oeffentliche API sichtbar. Das Backend-Repo ist ueber die unauthentifizierte Docker-Hub-API nicht sichtbar, aber der Pull mit lokaler Docker-Authentifizierung funktioniert.
- Die Resume-Formel ist absichtlich kurz; ein nacktes Codewort ohne Dateipfad ist nicht robust genug, weil Sitzungen nicht verlaesslich fortleben.
