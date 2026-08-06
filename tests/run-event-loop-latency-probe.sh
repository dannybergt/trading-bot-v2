#!/usr/bin/env bash
# Weist nach, dass die Hintergrundschleifen die Anfragen nicht mehr anhalten.
#
# Die Bedingung wird **hergestellt**, nicht unterstellt: der Scanner-Erstlauf
# wird per ENV auf wenige Sekunden vorgezogen, eine Watchlist mit mehreren
# Symbolen gefuellt, und waehrend der Zyklus laeuft (Provider-HTTP, DB,
# ML-Training) wird `/api/health` gepingt — ein Endpunkt ohne jede
# Provider-Arbeit. Bleibt der langsam, steht der Event-Loop.
#
# Messwert vor dem Fix (2026-08-06): bis zu 21,7 s auf `/api/health`.
#
#   bash tests/run-event-loop-latency-probe.sh
#   MAX_HEALTH_SECONDS=2.0 bash tests/run-event-loop-latency-probe.sh
#
# Negativkontrolle: dieselbe Sonde gegen ein Image vom Stand vor dem Fix
# muss die Grenze reissen. Ohne diesen Gegenlauf sagt ein gruenes Ergebnis
# hier nichts.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${RUN_ID:-$(date +%Y%m%d%H%M%S)-$$}"
IMAGE="${BACKEND_IMAGE:-trading-bot-v2-backend:local}"
NETWORK="tbv2-loopprobe-${RUN_ID}"
POSTGRES="tbv2-loopprobe-pg-${RUN_ID}"
BACKEND="tbv2-loopprobe-be-${RUN_ID}"

# Obergrenze fuer eine Anfrage an einen Endpunkt, der nichts tut. Grosszuegig
# gewaehlt: es geht nicht um Millisekunden, sondern um den Unterschied
# zwischen "antwortet" und "der Server steht".
MAX_HEALTH_SECONDS="${MAX_HEALTH_SECONDS:-3.0}"
PROBE_SECONDS="${PROBE_SECONDS:-75}"

ADMIN_EMAIL="loopprobe-${RUN_ID}@example.com"
# Gleiche Form wie in `run-api-regression.sh`: ueberschreibbar, und der
# Secret-Scan des pre-commit-Hooks greift bei einer literalen Zuweisung.
ADMIN_PASSWORD="${ADMIN_PASSWORD:-loopprobe123}"
JWT_SECRET="${JWT_SECRET:-12345678901234567890123456789012}"
APP_ENCRYPTION_KEY="${APP_ENCRYPTION_KEY:-abcdefghijklmnopqrstuvwx12345678}"

cleanup() {
  docker rm -f "${BACKEND}" "${POSTGRES}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Event-Loop-Latenzsonde ${RUN_ID} (Grenze ${MAX_HEALTH_SECONDS}s)"
docker network create "${NETWORK}" >/dev/null
docker run -d --name "${POSTGRES}" --network "${NETWORK}" \
  -e POSTGRES_DB=tbv2 -e POSTGRES_USER=tbv2 -e POSTGRES_PASSWORD=loopprobe \
  postgres:16-alpine >/dev/null

for _ in $(seq 1 60); do
  docker exec "${POSTGRES}" pg_isready -U tbv2 >/dev/null 2>&1 && break
  sleep 1
done

docker run -d --name "${BACKEND}" --network "${NETWORK}" --network-alias backend \
  -e DATA_DIR=/app/data -e BACKUP_DIR=/app/backups \
  -e DATABASE_URL="postgresql+psycopg://tbv2:loopprobe@${POSTGRES}:5432/tbv2" \
  -e JWT_SECRET="${JWT_SECRET}" \
  -e APP_ENCRYPTION_KEY="${APP_ENCRYPTION_KEY}" \
  -e INITIAL_ADMIN_EMAIL="${ADMIN_EMAIL}" \
  -e INITIAL_ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
  -e INITIAL_ADMIN_MFA_ENABLED=false \
  -e LOG_LEVEL=INFO -e PYTHONUNBUFFERED=1 \
  -e AUTO_SCANNER_INITIAL_DELAY_SECONDS=8 \
  -e AUTO_SCANNER_INTERVAL_SECONDS=30 \
  -e ALERT_RULE_EVAL_INITIAL_DELAY_SECONDS=10 \
  -e PAPER_ORDER_FILL_INITIAL_DELAY_SECONDS=12 \
  "${IMAGE}" >/dev/null

for _ in $(seq 1 90); do
  docker run --rm --network "${NETWORK}" "${IMAGE}" \
    python -c "import requests;requests.get('http://backend:8000/api/health',timeout=3)" >/dev/null 2>&1 && break
  sleep 1
done

docker run --rm -i --network "${NETWORK}" \
  -e ADMIN_EMAIL="${ADMIN_EMAIL}" \
  -e ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
  -e MAX_HEALTH_SECONDS="${MAX_HEALTH_SECONDS}" \
  -e PROBE_SECONDS="${PROBE_SECONDS}" \
  "${IMAGE}" python - <<'PY'
import os
import statistics
import threading
import time

import requests

base = "http://backend:8000"
max_allowed = float(os.environ["MAX_HEALTH_SECONDS"])
probe_seconds = float(os.environ["PROBE_SECONDS"])

login = requests.post(
    f"{base}/api/auth/login",
    json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]},
    timeout=30,
)
login.raise_for_status()
headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

# Dem Scanner Arbeit geben: ohne beobachtete Symbole hat sein Zyklus nichts
# zu tun und die Sonde wuerde eine Ruhe messen, die nichts beweist.
watchlists = requests.get(f"{base}/api/watchlists", headers=headers, timeout=30).json()
watchlist_id = watchlists[0]["id"]
for symbol in ("AAPL", "MSFT", "NVDA", "TSLA", "AMZN"):
    requests.post(
        f"{base}/api/watchlists/{watchlist_id}/items",
        headers=headers,
        json={"symbol": symbol, "name": symbol},
        timeout=30,
    )
print(f"seeded 5 symbols into watchlist {watchlist_id}")

samples: list[float] = []
stop = threading.Event()


def ping() -> None:
    while not stop.is_set():
        started = time.monotonic()
        try:
            requests.get(f"{base}/api/health", timeout=120)
            samples.append(time.monotonic() - started)
        except Exception:
            samples.append(999.0)
        time.sleep(0.5)


pinger = threading.Thread(target=ping, daemon=True)
pinger.start()
time.sleep(probe_seconds)
stop.set()
pinger.join(timeout=130)

worst = max(samples) if samples else 0.0
median = statistics.median(samples) if samples else 0.0
print(
    f"health pings: {len(samples)}, median {median:.3f}s, max {worst:.2f}s "
    f"(limit {max_allowed:.1f}s)"
)
if not samples:
    raise SystemExit("no health samples taken — the probe proved nothing")
if worst > max_allowed:
    raise SystemExit(
        f"event loop blocked: /api/health took {worst:.2f}s while the background "
        f"loops were working (limit {max_allowed:.1f}s)"
    )
print("event_loop_latency ok")
PY

echo "Event-Loop-Latenzsonde bestanden"
