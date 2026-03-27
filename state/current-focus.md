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

- Letzter relevanter Commit auf `main`: `4233762` (`Add ETF/crypto provider path and fix publish scripts`)
- Letzter gepruefter GitHub-Actions-`publish`-Run: `#4`
- Run-Link: `https://github.com/dannybergt/trading-bot-v2/actions/runs/23618225010`
- Run-Zeitpunkt: Start `2026-03-26 21:11:17 UTC`, Ende `2026-03-26 21:13:42 UTC`
- Ergebnis: Build/Test/API/UI im Runner gruen; Fehlschlag erst bei `Log in to Docker Hub`

## Aktueller Fokus

- Nicht mehr am Build-Hook oder an den Regressionen arbeiten; diese Huerde ist fuer den aktuellen Stand bereits genommen.
- Als naechstes den Docker-Hub-Login im GitHub-`publish`-Workflow reparieren:
  - Repository-Secrets `DOCKERHUB_USERNAME` und `DOCKERHUB_TOKEN` pruefen
  - optional `DOCKERHUB_NAMESPACE` gegen den erwarteten Namespace abgleichen
  - danach erneut echten `main`-Push oder manuellen `publish`-Lauf beobachten

## Wichtiger Kontext

- Der neue ETF-/Krypto-Providerpfad ist bereits implementiert und lokal verifiziert.
- Lokal ist kein `ALPHA_VANTAGE_API_KEY` gesetzt; deshalb wurde der Pfad hier mit sichtbarem `provider.status=unavailable` verifiziert.
- Die Resume-Formel ist absichtlich kurz; ein nacktes Codewort ohne Dateipfad ist nicht robust genug, weil Sitzungen nicht verlaesslich fortleben.
