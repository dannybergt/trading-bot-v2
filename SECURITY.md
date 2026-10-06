# SECURITY — trading-bot-v2

> Skelett aus agent-baseline (AGENTS.md §6). Was hier steht, prüft der `security-reviewer` vor
> jedem PR mit Auth-, Eingabe-, Endpunkt-, Upload-, Zahlungs-, Abhängigkeits- oder KI-Bezug.

## Authentifizierung und Autorisierung

- Verfahren: _Sessions / JWT / OAuth — MFA-fähig?_
- Passwort-Hashing: _Argon2id / bcrypt / scrypt_
- Rollen und serverseitige Prüfung: _Tabelle Rolle → erlaubte Aktionen; testbar in `tests/`_

## Eingaben und Ausgaben

- Validierung an Systemgrenzen: _wo, womit_
- Output-Encoding / CSP: _…_
- Uploads: _Typ, Größe, Inhalt geprüft?_
- SSRF: _Allowlist für ausgehende URLs_

## Secrets und Logging

- Secrets nur über ENV (`.env.example` vollständig, `.env` in `.gitignore`/`.dockerignore`)
- Nicht geloggt: Passwörter, Tokens, Session-IDs, PII, volle Request-Bodies (§6.4)

## Abhängigkeiten und Container

- Lockfile committed, Versionen gepinnt, Renovate/Dependabot: Backend `src/backend/requirements.txt`
  (jede direkte Abhaengigkeit `==`; transitive sind nicht gelockt — Deckel, Abloesung durch
  `pip-compile`/`uv lock`, sobald ein transitiver Sprung einen Build bricht), Frontend `src/frontend/package-lock.json`; `pip`/`setuptools`
  im Image gepinnt (`ops/docker/backend.Dockerfile`). Dependabot woechentlich fuer Actions, pip, npm.
- Audit blockiert CI: `ops/automation/deps-audit.sh` (pip-audit auf die site-packages des
  gebauten Images, `npm audit --audit-level=low` auf das Lockfile). Jede Ausnahme steht mit
  Grund im Skript; Stand 2026-10-06: keine Ausnahme. `alpaca-trade-api` wird mit `--no-deps`
  aus `src/backend/requirements-alpaca.txt` installiert, damit urllib3/msgpack nicht an seinen
  veralteten Pins haengen; JWT ueber PyJWT statt python-jose — ADR 2026-10-06.
- Ausgehende URLs: nur feste Anbieter-Hosts; einzige nutzergesteuerte URL ist der Web-Push-Endpunkt,
  begrenzt auf die Push-Dienste der Browser (`push_service.is_allowed_push_endpoint`, beim Abonnieren
  und beim Senden).
- Images mit Tag + Digest, Non-Root: _…_

## KI-/LLM-Funktionen (falls vorhanden)

- Prompt-Injection: _Nutzer-/RAG-/Tool-Text ist Daten, nie Anweisung_
- Keine Kundendaten an externe APIs ohne Freigabe (§13/§17)

## Datenschutz

- Personenbezogene Daten: _welche, warum, wie lange_ (Datenminimierung)

## Meldung von Schwachstellen

_Kontakt / Verfahren._
