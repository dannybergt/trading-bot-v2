# OPERATIONS — trading-bot-v2

> Skelett aus agent-baseline (AGENTS.md §8). Für den, der den Dienst um drei Uhr nachts betreibt,
> ohne ihn gebaut zu haben. Der `ops-reviewer` prüft bei jeder Compose-/Dockerfile-Änderung, ob
> das hier noch stimmt.

## Start / Stop / Neustart

```bash
docker compose up -d           # Preflight: Ports aus STATE.md frei?
docker compose stop            # Volumes bleiben in jedem Fall erhalten
docker compose restart <dienst>
```

## Health

- `/healthz` — lebt · `/readyz` — kann bedienen (DB, Queue erreichbar)
- Compose-`healthcheck` je Dienst; `docker ps` zeigt `(healthy)`

## Logs und Metriken

- `docker logs --since 1h trading-bot-v2-api` — JSON, UTC, `request_id`
- Metriken: `/metrics` (Prometheus) — _intern, nicht öffentlich_
- Alarme/SLOs: _Quelle, Schwellen, wer wird benachrichtigt_

## Backup / Restore

- Backup: _was, wohin (anderes Laufwerk als die Volumes), wann (UTC)_
- Restore: _Kommandos wörtlich, Reihenfolge (Dienst stoppen → einspielen → starten)_
- Restore-Probe: _Intervall, letzter Nachweis_

## Deploy

- Mechanismus: _Watchtower-Label / CI / Hand_; Image-Tag + Digest in Compose
- Migration beim Start: _ja/nein; Rollback-Reihenfolge: erst `downgrade`, dann altes Image_
- **CI rot im Schritt „Dependency audit"** (auch ohne eigene Dependency-Aenderung): eine neue
  Advisory ist erschienen. Fertig, wenn der Schritt gruen ist, durch eines von beiden:
  Version in `src/backend/requirements.txt` bzw. per `npm audit fix` im Lockfile heben, oder —
  nur wenn kein Fix existiert oder ein Pin ihn blockiert — die ID mit Grund in
  `ops/automation/deps-audit.sh` eintragen und die Entscheidung in `state/decisions.md` festhalten.
  Ein Ausfall von PyPI/OSV/npm zeigt sich als Installations- oder Netzfehler, nicht als Fund —
  dann den Lauf wiederholen.
  npm-Ausnahmen stehen als `ID:YYYY-MM-DD` und verfallen absichtlich: ab dem Folgetag ist der
  Schritt rot (`EXPIRED or undated npm ignore`), bis neu entschieden ist (Fix oder neues Datum mit Grund).
- **Dependabot-PR macht `tests/test_alpaca_dependency_override.py` rot** (meist `pip check`): der
  Bump verletzt eine Grenze von `alpaca-trade-api` (installiert `--no-deps`, ADR 2026-10-06). Bump
  ablehnen und die Grenze als `ignore` in `.github/dependabot.yml` eintragen; den Test nie lockern.
- **Rueckweg nach einem schlechten Deploy** (Watchtower rollt nicht zurueck): auf BC-KI01 in
  `/data/trading-bot-v2/.env` `IMAGE_TAG=sha-<vorheriger Commit, 12 Zeichen>` setzen, dann
  `docker compose up -d backend` (bzw. `frontend`). Fertig: Container `healthy`, `/api/health` 200.

## Not-Aus

_Was stoppt den Dienst sofort, ohne Daten zu verlieren?_

## Allokierte Ressourcen

_Ports, Container-Prefix, Volumes, Networks — Abgleich mit `STATE.md` (§3)._
