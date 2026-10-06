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
- Restore der App-Daten (Datei aus `/api/admin/export` oder `/api/admin/backups/<name>`; Dienste bleiben an, der Import läuft in einer Transaktion — bei einem Fehler bleibt der Bestand unverändert, Datei korrigieren und wiederholen):

  ```bash
  # TOKEN = access_token aus POST /api/auth/login (Admin-Konto), in der Shell gesetzt, nicht ins Log
  curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
    -F "file=@backup.json;type=application/json" \
    "http://localhost:${FRONTEND_PORT:-18094}/api/admin/backups/import"   # Antwort {"status":"restored",...}
  ```

  Fertig, wenn alles davon stimmt: (1) Antwort 200 (400 = abgewiesen, nichts geändert; 413 = Datei über 50 MiB; 504 = Ablauf im Runbook „Restore“); (2) `GET /api/admin/audit-events?action=backup.restore&limit=1` zeigt ein Event ohne `outcome: failure` (bei `/api/admin/import`: `action=backup.import`); (3) `curl -fsS http://localhost:${FRONTEND_PORT:-18094}/api/health` antwortet 200; (4) `jq '.data.users | length' backup.json` ist gleich `GET /api/admin/export | jq '.data.users | length'` (gleiche Zählung für `watchlists`).
- Restore-Probe: _Intervall, letzter Nachweis_
- Größengrenze App-Restore (`POST /api/admin/import`, `/api/admin/backups/import` über den Frontend-Port): Datei bis 50 MiB (`ADMIN_UPLOAD_MAX_BYTES`, Code-Default — `docker-compose.yml` reicht die Variable nicht durch; Backend antwortet darüber 413 mit JSON), nginx lässt diese zwei Pfade nur per POST mit Bearer-Token bis 51 MiB durch, wartet 300 s (`frontend.nginx.conf`, Ablauf in `docs/admin/runbook.md` „Restore“), jeden anderen API-Aufruf bis 1 MB. Wer `ADMIN_UPLOAD_MAX_BYTES` hebt, hebt `client_max_body_size` im Upload-Block mit — sonst endet der Restore an nginx mit einer HTML-413-Seite.

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

## Not-Aus

_Was stoppt den Dienst sofort, ohne Daten zu verlieren?_

## Allokierte Ressourcen

_Ports, Container-Prefix, Volumes, Networks — Abgleich mit `STATE.md` (§3)._
