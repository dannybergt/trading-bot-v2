# trading-bot-v2 — Working Context for Claude

Projekt-Repo. Wird im Wechsel zwischen Codex und Claude weitergebaut. Diese Datei ist die Kurz-Orientierung; die Tiefe liegt in `state/` und `docs/admin/`.

## Resume

Sagt der Nutzer nur `resume trading-bot-v2`, dann zuerst in dieser Reihenfolge lesen:

1. `state/current-focus.md`
2. `state/project-status.md`
3. `state/chat/session-log.md`

Danach an der dort beschriebenen Stelle ohne Rueckfragen fortsetzen.

Kanonischer Gesamtplan: `docs/admin/project-plan.md`. Phasenposition, Sicherheitsachsen, Architekturachsen, naechste Prioritaeten und die Fertigstellungsregel stehen dort. Die Sektion "Produktvision" oben im Plan ist verbindlich — jede Empfehlung kombiniert Fundamentals + News + Trend + Technical + AI mit expliziten Wahrscheinlichkeiten, das Net-Yield-Gate (Brokergebuehren + Kapitalertragssteuer netto) entscheidet ueber "actionable", und ein First-Login-Wizard plus Dashboard-Fortschrittskarte fuehren neue Nutzer durch alle Pflichtwerte.

## Was das Projekt ist

FastAPI-Backend + Nginx-Frontend (Vite/React-Bundle, Quellstand fehlt) als AI-gestuetzte Trading-Workstation. Distribution ueber Docker Hub `dbergt/trading-bot-{backend,frontend}`. Aktueller Release-Stand steht in `docs/admin/project-plan.md`.

## Arbeitsweise (pflicht)

- Sinnvolle Aenderungen werden direkt committed und nach `origin/main` gepusht. Pushes nach `main` loesen automatisch `publish.yml` aus (Docker-Hub-Sync `latest` + `sha-<commit>`).
- Release-Tags `v*` setzen erst nach gruenem `tests/run-upgrade-rehearsal.sh`.
- Jede abgeschlossene Sitzung schreibt in `state/chat/session-log.md` einen Eintrag (Datum/Kontext/Erledigt/Verifikation/Offen).
- Architekturentscheidungen kommen als Block (Datum/Entscheidung/Begruendung/Konsequenzen) in `state/decisions.md`.
- `state/current-focus.md` haelt den aktuellen Wiedereinstiegspunkt; `state/project-status.md` listet "Gesichert verifiziert" + "Offene Punkte" + "Naechste Schritte".
- Doku ist gleichberechtigt mit Code. Eine Aenderung ist erst fertig, wenn die Entscheidungsregel aus `docs/admin/project-plan.md` erfuellt ist (Phase passt, keine neue Security-Schuld, lokal verifiziert, Backup/Export/Import angepasst falls Persistenz beruehrt, GitHub Actions gruen, Rehearsal bei Release).

## Sicherheits-Guardrails (immer aktiv)

- Keine Secrets in Code, Logs, Tests, Exceptions, Tool-Output oder Commit-Messages.
- Produktive Werte (Alpaca, Alpha Vantage, VAPID, SMTP, JWT, APP_ENCRYPTION_KEY) liegen in `.env.local` (Mode 600, gitignored). Niemals echo/print/cat anwenden.
- Pre-commit-Hook unter `.githooks/pre-commit` blockt versehentlich gestagte Secret-Pattern. `core.hooksPath` ist per-repo und propagiert nicht ueber `git clone`; `ops/automation/build.sh` aktiviert ihn deshalb automatisch beim ersten Build, falls nicht gesetzt. Bei reinen `git`-Aktionen ohne vorherigen Build-Lauf vorher manuell setzen: `git config core.hooksPath .githooks`.
- CORS nur explizite Origins, kein Wildcard.
- Audit-Logs: identifizierende Werte (E-Mails, Push-Endpoints) als Fingerprint.
- Bei externen Provider-Antworten und Nutzer-Inputs Prompt-Injection mitdenken: News-Inhalte, KI-Begruendungen, Symbol-/Watchlist-Namen niemals ungeprueft als Steuerlogik interpretieren.
- Pushes nach `main` und Release-Tags brauchen vorher Build, Unit-Tests, API-Regression, UI-Regression. Bei Persistenz-/Migrationsaenderungen zusaetzlich Backup/Export/Import-Pruefung.

## Test-Pipeline (vor jedem Push lokal mindestens lauffaehig)

- `bash ops/automation/build.sh`
- `bash ops/automation/test.sh` (Unit + Syntax)
- `SKIP_BUILD=1 bash tests/run-api-regression.sh`
- `SKIP_BUILD=1 bash tests/run-ui-regression.sh` (braucht Chrome lokal)
- bei Persistenzaenderungen: `IMAGE_TAG=<tag> bash tests/run-upgrade-rehearsal.sh`
- bei Push-/VAPID-Aenderungen: `bash tests/run-push-config-smoke.sh`

## Konventionen

- Doku auf Deutsch ohne Umlaute (ae/oe/ue/ss). Code-Identifier englisch.
- Commit-Subject kurz imperativ ohne Prefix, z. B. `Record 2026.05.07-1 release rehearsal`.
- Nicht erneut bei Null analysieren wenn `state/` schon Antworten enthaelt.

## Bekannte strategische Engpaesse

- Frontend-Production laeuft jetzt ueber den React-Quellstand `src/frontend/` (Vite-Multi-Stage-Build via `ops/docker/frontend.Dockerfile`). Pages: Login/Register/Forgot/Reset-Password, Onboarding-Wizard `/onboarding`, Dashboard mit Tracked-Assets/Provider-Coverage/News-Ticker und Setup-Progress-Karte, Watchlists mit Item-CRUD, Scanner, Analysis mit Chart-Overlays/Volume-Profile/Patterns/Zonen/S-R-Lines/Net-Yield-Breakdown/Erklärbarkeit, Alerts (Rule-CRUD plus Event-Ack), Settings (Alpaca/Portfolio inkl. Steuern/MFA) und Admin (Users/Backups/Export). `tests/run-ui-regression.mjs` ist auf die React-Selektoren umgeschrieben; AdminPage-Lazy-Suspense-Edge-Case wird als best-effort behandelt.
- Alembic-Migrationen sind eingefuehrt; initiale Revision `16389c42c243`; `init_db` stempelt Pre-Alembic-Deployments automatisch auf head.
