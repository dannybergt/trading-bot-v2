#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${RUN_ID:-$(date +%Y%m%d%H%M%S)-$$}"
TEST_ROOT="${TEST_ROOT:-/tmp/trading-bot-v2-ui-regression-${RUN_ID}}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-trading-bot-v2-ui-regression-${RUN_ID}}"

BACKEND_PORT="${BACKEND_PORT:-18090}"
FRONTEND_PORT="${FRONTEND_PORT:-18094}"
POSTGRES_DB="${POSTGRES_DB:-trading_bot_v2_ui_regression}"
POSTGRES_USER="${POSTGRES_USER:-trading}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-trading-change-me}"
JWT_SECRET="${JWT_SECRET:-12345678901234567890123456789012}"
APP_ENCRYPTION_KEY="${APP_ENCRYPTION_KEY:-abcdefghijklmnopqrstuvwx12345678}"
BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-3600}"

UI_ARTIFACT_DIR="${UI_ARTIFACT_DIR:-/tmp/trading-bot-v2-ui-regression-artifacts-${RUN_ID}}"
UI_TEST_EMAIL="${UI_TEST_EMAIL:-ui-regression-${RUN_ID}@example.com}"
UI_TEST_PASSWORD="${UI_TEST_PASSWORD:-UIRegressionPass123!}"

TEST_DATA_DIR="${TEST_ROOT}/data"
TEST_BACKUP_DIR="${TEST_ROOT}/backups"
TEST_POSTGRES_DIR="${TEST_ROOT}/postgres"
ENV_FILE="${TEST_ROOT}/ui-regression.env"
LOG_DIR="${UI_ARTIFACT_DIR}/compose-logs"

compose_args=(
  --project-directory "${PROJECT_ROOT}"
  --env-file "${ENV_FILE}"
  -f "${PROJECT_ROOT}/ops/docker/compose.yaml"
  -p "${COMPOSE_PROJECT_NAME}"
)

resolve_chrome_bin() {
  if [[ -n "${CHROME_BIN:-}" ]]; then
    printf '%s\n' "${CHROME_BIN}"
    return 0
  fi

  local candidate
  for candidate in google-chrome google-chrome-stable chromium chromium-browser; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      command -v "${candidate}"
      return 0
    fi
  done

  echo "No Chrome/Chromium binary found. Set CHROME_BIN explicitly." >&2
  return 1
}

wait_for_http() {
  local url="$1"
  local description="$2"
  local attempts="${3:-60}"
  local attempt=0

  until curl -fsS "${url}" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if (( attempt >= attempts )); then
      echo "${description} did not become ready: ${url}" >&2
      return 1
    fi
    sleep 2
  done
}

dump_compose_logs() {
  mkdir -p "${LOG_DIR}"
  docker compose "${compose_args[@]}" ps >"${LOG_DIR}/compose-ps.txt" 2>&1 || true

  local service
  for service in postgres backend frontend; do
    docker compose "${compose_args[@]}" logs --no-color "${service}" >"${LOG_DIR}/${service}.log" 2>&1 || true
  done
}

cleanup() {
  set +e
  dump_compose_logs
  docker compose "${compose_args[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  if [[ "${KEEP_TEST_ROOT:-0}" != "1" ]]; then
    rm -rf "${TEST_ROOT}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

mkdir -p "${TEST_DATA_DIR}" "${TEST_BACKUP_DIR}" "${TEST_POSTGRES_DIR}" "${UI_ARTIFACT_DIR}"
chmod 0777 "${TEST_DATA_DIR}" "${TEST_BACKUP_DIR}" "${TEST_POSTGRES_DIR}"

CHROME_BIN_RESOLVED="$(resolve_chrome_bin)"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"

cat >"${ENV_FILE}" <<EOF
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}
BACKEND_PORT=${BACKEND_PORT}
FRONTEND_PORT=${FRONTEND_PORT}
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
HOST_DATA_DIR=${TEST_DATA_DIR}
HOST_BACKUP_DIR=${TEST_BACKUP_DIR}
HOST_POSTGRES_DATA_DIR=${TEST_POSTGRES_DIR}
DATABASE_URL=postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
JWT_SECRET=${JWT_SECRET}
APP_ENCRYPTION_KEY=${APP_ENCRYPTION_KEY}
ALLOWED_ORIGINS=http://127.0.0.1:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}
BACKUP_INTERVAL_SECONDS=${BACKUP_INTERVAL_SECONDS}
ENABLE_INSECURE_DEBUG_RESET_TOKENS=true
EOF

echo "UI regression artifacts: ${UI_ARTIFACT_DIR}"
echo "UI regression compose project: ${COMPOSE_PROJECT_NAME}"

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  echo "Building current local images"
  bash "${PROJECT_ROOT}/ops/automation/build.sh"
fi

echo "Starting isolated compose stack"
docker compose "${compose_args[@]}" up -d

echo "Waiting for backend health"
wait_for_http "http://127.0.0.1:${BACKEND_PORT}/api/health" "Backend health endpoint"

echo "Waiting for frontend login route"
wait_for_http "${FRONTEND_URL}/login" "Frontend login route"

echo "Running browser regression"
CHROME_BIN="${CHROME_BIN_RESOLVED}" \
FRONTEND_URL="${FRONTEND_URL}" \
UI_ARTIFACT_DIR="${UI_ARTIFACT_DIR}" \
UI_TEST_EMAIL="${UI_TEST_EMAIL}" \
UI_TEST_PASSWORD="${UI_TEST_PASSWORD}" \
node "${PROJECT_ROOT}/tests/run-ui-regression.mjs"

echo "UI regression passed"
