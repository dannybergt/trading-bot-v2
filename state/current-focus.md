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
- Der Alpha-Vantage-BTC-Liveblocker ist lokal behoben: `DIGITAL_CURRENCY_DAILY` liefert fuer `BTC/USD` aktuell generische OHLC-Keys (`1. open`, `2. high`, `3. low`, `4. close`) statt der alten waehrungsspezifischen Keys; der Parser akzeptiert jetzt beide Formen.
- Naechster sinnvoller Schritt ist den Fix in einen neuen unveraenderlichen Stand ueberfuehren:
  - Commit fuer Parserfix und Handoff-Doku erstellen
  - Push nach `main` beobachten, bis GitHub Actions den neuen `sha-<commit>`-Stand nach Docker Hub synchronisiert
  - danach `IMAGE_TAG=sha-<commit> bash tests/run-upgrade-rehearsal.sh` fuer den neuen Stand fahren
  - anschliessend ETF-/Krypto-News, Bars und Research-Daten breiter in Alerts/Dashboard ausrollen

## Wichtiger Kontext

- Der neue ETF-/Krypto-Providerpfad ist bereits implementiert und lokal verifiziert.
- In `/root/trading-bot-v2-work/.env` ist ein `ALPHA_VANTAGE_API_KEY` gesetzt; Werte wurden nicht ausgegeben und duerfen auch kuenftig nicht geloggt werden.
- `tests/run-alpha-vantage-live-smoke.sh` bricht ohne gesetzten Key bewusst ab, ohne den Key-Wert auszugeben.
- Der bereits veroeffentlichte Docker-Hub-Stand `sha-d4939da591ec` enthaelt den BTC-Parserfix noch nicht; Live-Smokes fuer diesen alten Stand koennen bei `BTC/USD` weiter am History-Parsing scheitern.
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
- Beim naechsten Resume nicht mehr die BTC-Struktur untersuchen; naechster sinnvoller Schritt ist Commit/Push und danach Release-/Upgrade-Rehearsal fuer den neuen `sha-<commit>`-Stand.
