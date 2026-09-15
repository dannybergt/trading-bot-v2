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

## Not-Aus

_Was stoppt den Dienst sofort, ohne Daten zu verlieren?_

## Allokierte Ressourcen

_Ports, Container-Prefix, Volumes, Networks — Abgleich mit `STATE.md` (§3)._
