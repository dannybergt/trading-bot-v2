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

- Lockfile committed, Versionen gepinnt, Renovate/Dependabot: _…_
- Images mit Tag + Digest, Non-Root: _…_

## KI-/LLM-Funktionen (falls vorhanden)

- Prompt-Injection: _Nutzer-/RAG-/Tool-Text ist Daten, nie Anweisung_
- Keine Kundendaten an externe APIs ohne Freigabe (§13/§17)

## Datenschutz

- Personenbezogene Daten: _welche, warum, wie lange_ (Datenminimierung)

## Meldung von Schwachstellen

_Kontakt / Verfahren._
