# TESTING — trading-bot-v2

> Skelett aus agent-baseline (AGENTS.md §7). Der `test-runner` nutzt das Kommando aus
> „Ausführen"; der `test-engineer` schreibt die Zeilen, die in „Pflichtfälle" noch fehlen.

## Ausführen

```bash
make test            # gesamte Suite
make test ARGS=…     # gezielt
```

## Struktur

| Ebene | Wo | Was |
|---|---|---|
| Unit | `tests/unit/` | Geschäftslogik |
| Integration | `tests/integration/` | Endpunkte, Repositories, Migrationen (Up → Down → Up) |
| E2E / Browser | `tests/e2e/` | Golden Path + mindestens ein Edge Case |

## Pflichtfälle (§7) — je Zeile: vorhanden / offen

- [ ] Auth/RBAC: jede Rolle, jede geschützte Route, fremdes Objekt → 403/404
- [ ] Fehlerfälle: ungültige, leere, zu große Eingaben
- [ ] Rate-Limit / Validation
- [ ] Migration Up → Down → Up auf leerer DB
- [ ] Externe Abhängigkeit weg (Timeout, 5xx)
- [ ] Zeit: UTC, Zeitzonengrenze (§11)
- [ ] Persistenz: Neustart, zweiter Nutzer, abgelaufene Sitzung — Bedingung herstellen, nicht unterstellen

## Negativkontrollen

_Jeder Schutz hat einen Test, der rot ist, wenn der Schutz fehlt. Liste der Nachweise._

## Nachweis am laufenden System

Zielkatalog: `docs/verification/zielkatalog.md` — Maßstab für den `verifier` (`/verify`).
