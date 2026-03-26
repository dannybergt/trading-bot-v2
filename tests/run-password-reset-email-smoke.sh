#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${RUN_ID:-$(date +%Y%m%d%H%M%S)-$$}"
TEST_ROOT="${TEST_ROOT:-/tmp/trading-bot-v2-password-reset-email-${RUN_ID}}"
NETWORK_NAME="${NETWORK_NAME:-trading-bot-v2-password-reset-email-${RUN_ID}}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-trading-bot-v2-reset-postgres-${RUN_ID}}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-trading-bot-v2-reset-backend-${RUN_ID}}"
SMTP_CONTAINER="${SMTP_CONTAINER:-trading-bot-v2-reset-smtp-${RUN_ID}}"

BACKEND_IMAGE="${BACKEND_IMAGE:-trading-bot-v2-backend:local}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:17-alpine}"
POSTGRES_DB="${POSTGRES_DB:-trading_bot_v2_reset_smoke}"
POSTGRES_USER="${POSTGRES_USER:-trading}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-trading-change-me}"
APP_EMAIL="${APP_EMAIL:-admin@example.com}"
APP_PASSWORD="${APP_PASSWORD:-adminpass123}"
RESET_PASSWORD="${RESET_PASSWORD:-new-adminpass123}"
JWT_SECRET="${JWT_SECRET:-12345678901234567890123456789012}"
APP_ENCRYPTION_KEY="${APP_ENCRYPTION_KEY:-abcdefghijklmnopqrstuvwx12345678}"
PASSWORD_RESET_BASE_URL="${PASSWORD_RESET_BASE_URL:-https://app.example/reset-password}"
SMTP_FROM_EMAIL="${SMTP_FROM_EMAIL:-noreply@example.com}"

DATA_DIR="${TEST_ROOT}/data"
BACKUP_DIR="${TEST_ROOT}/backups"
LOG_DIR="${TEST_ROOT}/logs"
POSTGRES_DATA_DIR="${TEST_ROOT}/postgres"
SMTP_LOG="${LOG_DIR}/smtp.log"
BACKEND_LOG="${LOG_DIR}/backend.log"

cleanup() {
  set +e
  docker logs "${SMTP_CONTAINER}" >"${SMTP_LOG}" 2>&1 || true
  docker logs "${BACKEND_CONTAINER}" >"${BACKEND_LOG}" 2>&1 || true
  docker rm -f "${BACKEND_CONTAINER}" "${SMTP_CONTAINER}" "${POSTGRES_CONTAINER}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK_NAME}" >/dev/null 2>&1 || true
}

wait_for_postgres() {
  local attempts=0
  until docker run --rm --network "${NETWORK_NAME}" "${POSTGRES_IMAGE}" \
    pg_isready -h "${POSTGRES_CONTAINER}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if (( attempts >= 30 )); then
      echo "PostgreSQL did not become ready in time" >&2
      docker logs "${POSTGRES_CONTAINER}" >"${LOG_DIR}/postgres.log" 2>&1 || true
      cat "${LOG_DIR}/postgres.log" >&2 || true
      return 1
    fi
    sleep 1
  done
}

wait_for_backend() {
  local attempts=0
  until docker run --rm -i --network "${NETWORK_NAME}" "${BACKEND_IMAGE}" python - <<'PY' >/dev/null 2>&1
import requests

response = requests.get("http://backend:8000/api/health", timeout=5)
response.raise_for_status()
assert response.json()["status"] == "healthy"
PY
  do
    attempts=$((attempts + 1))
    if (( attempts >= 30 )); then
      echo "Backend did not become ready in time" >&2
      docker logs "${BACKEND_CONTAINER}" >"${BACKEND_LOG}" 2>&1 || true
      cat "${BACKEND_LOG}" >&2 || true
      return 1
    fi
    sleep 1
  done
}

wait_for_smtp() {
  local attempts=0
  until docker run --rm -i --network "${NETWORK_NAME}" "${BACKEND_IMAGE}" python - <<'PY' >/dev/null 2>&1
import socket

with socket.create_connection(("smtp", 1025), timeout=5):
    pass
PY
  do
    attempts=$((attempts + 1))
    if (( attempts >= 30 )); then
      echo "SMTP test server did not become ready in time" >&2
      docker logs "${SMTP_CONTAINER}" >"${SMTP_LOG}" 2>&1 || true
      cat "${SMTP_LOG}" >&2 || true
      return 1
    fi
    sleep 1
  done
}

wait_for_reset_token() {
  local attempts=0
  while (( attempts < 30 )); do
    docker logs "${SMTP_CONTAINER}" >"${SMTP_LOG}" 2>&1 || true
    local token
    token="$(python3 - <<PY
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import quopri
import re

raw_text = Path("${SMTP_LOG}").read_text(encoding="utf-8", errors="ignore")
text = quopri.decodestring(raw_text.encode("utf-8")).decode("utf-8", errors="ignore")
for match in re.finditer(r"https?://[^\\s<>\"]+", text):
    url = match.group(0).rstrip(".)")
    if "/reset-password" not in url:
        continue
    token = parse_qs(urlsplit(url).query).get("token", [None])[0]
    if token:
        print(token)
        break
PY
)"
    if [[ -n "${token}" ]]; then
      printf '%s\n' "${token}"
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 1
  done

  echo "Password reset email did not appear in SMTP logs" >&2
  cat "${SMTP_LOG}" >&2 || true
  return 1
}

trap cleanup EXIT

mkdir -p "${DATA_DIR}" "${BACKUP_DIR}" "${LOG_DIR}" "${POSTGRES_DATA_DIR}"
chmod 0777 "${DATA_DIR}" "${BACKUP_DIR}" "${LOG_DIR}" "${POSTGRES_DATA_DIR}"

echo "Password reset email smoke artifacts: ${TEST_ROOT}"

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  echo "Building current local images"
  bash "${PROJECT_ROOT}/ops/automation/build.sh"
fi

echo "Creating isolated Docker network ${NETWORK_NAME}"
docker network create "${NETWORK_NAME}" >/dev/null

echo "Starting isolated PostgreSQL container"
docker run -d \
  --name "${POSTGRES_CONTAINER}" \
  --network "${NETWORK_NAME}" \
  -e POSTGRES_DB="${POSTGRES_DB}" \
  -e POSTGRES_USER="${POSTGRES_USER}" \
  -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  -v "${POSTGRES_DATA_DIR}:/var/lib/postgresql/data" \
  "${POSTGRES_IMAGE}" >/dev/null

wait_for_postgres

echo "Starting test SMTP container"
docker run -d \
  --name "${SMTP_CONTAINER}" \
  --network "${NETWORK_NAME}" \
  --network-alias smtp \
  -v "${PROJECT_ROOT}/tests/smtp_capture_server.py:/tmp/smtp_capture_server.py:ro" \
  "${BACKEND_IMAGE}" \
  python /tmp/smtp_capture_server.py >/dev/null

wait_for_smtp

echo "Starting isolated backend container"
docker run -d \
  --name "${BACKEND_CONTAINER}" \
  --network "${NETWORK_NAME}" \
  --network-alias backend \
  -e DATA_DIR=/app/data \
  -e BACKUP_DIR=/app/backups \
  -e DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_CONTAINER}:5432/${POSTGRES_DB}" \
  -e JWT_SECRET="${JWT_SECRET}" \
  -e APP_ENCRYPTION_KEY="${APP_ENCRYPTION_KEY}" \
  -e ALLOWED_ORIGINS="http://127.0.0.1:18094,http://localhost:18094" \
  -e ENABLE_INSECURE_DEBUG_RESET_TOKENS=false \
  -e PASSWORD_RESET_BASE_URL="${PASSWORD_RESET_BASE_URL}" \
  -e SMTP_HOST=smtp \
  -e SMTP_PORT=1025 \
  -e SMTP_FROM_EMAIL="${SMTP_FROM_EMAIL}" \
  -e SMTP_USE_TLS=false \
  -v "${DATA_DIR}:/app/data" \
  -v "${BACKUP_DIR}:/app/backups" \
  "${BACKEND_IMAGE}" >/dev/null

wait_for_backend

echo "Creating user and requesting password reset"
docker run --rm -i --network "${NETWORK_NAME}" "${BACKEND_IMAGE}" python - <<PY
import requests

base = "http://backend:8000"
email = "${APP_EMAIL}"
password = "${APP_PASSWORD}"

register = requests.post(
    f"{base}/api/auth/register",
    json={"email": email, "password": password},
    timeout=30,
)
register.raise_for_status()
assert register.json()["email"] == email

request_reset = requests.post(
    f"{base}/api/auth/password-reset/request",
    json={"email": email},
    timeout=30,
)
request_reset.raise_for_status()
payload = request_reset.json()
assert "debug_reset_token" not in payload
assert payload["message"].startswith("If the email exists")
print("password reset request via smtp ok")
PY

RESET_TOKEN="$(wait_for_reset_token)"
echo "SMTP reset token captured"

echo "Confirming password reset from delivered email"
docker run --rm -i --network "${NETWORK_NAME}" "${BACKEND_IMAGE}" python - <<PY
import requests

base = "http://backend:8000"
email = "${APP_EMAIL}"
new_password = "${RESET_PASSWORD}"
token = "${RESET_TOKEN}"

confirm = requests.post(
    f"{base}/api/auth/password-reset/confirm",
    json={"token": token, "new_password": new_password},
    timeout=30,
)
confirm.raise_for_status()
assert confirm.json()["message"] == "Password has been reset successfully"

login = requests.post(
    f"{base}/api/auth/login",
    json={"email": email, "password": new_password},
    timeout=30,
)
login.raise_for_status()
assert login.json()["mfa_required"] is False
print("password reset email confirm ok")
PY

echo "Password reset email smoke passed"
