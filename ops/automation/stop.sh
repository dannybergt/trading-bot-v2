#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"
EXAMPLE_ENV_FILE="${PROJECT_ROOT}/.env.example"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_ROOT}/ops/docker/compose.yaml}"
OVERRIDE_VARS=()

load_env() {
  local candidate="$1"
  if [[ ! -f "${candidate}" ]]; then
    return 1
  fi

  set -a
  # shellcheck disable=SC1090
  source "${candidate}"
  set +a
}

capture_overrides() {
  local name backup_name
  for name in \
    COMPOSE_PROJECT_NAME \
    HOST_DATA_DIR \
    HOST_BACKUP_DIR \
    HOST_POSTGRES_DATA_DIR \
    BACKEND_IMAGE_REF \
    FRONTEND_IMAGE_REF \
    BACKEND_PORT \
    FRONTEND_PORT; do
    if [[ -v "${name}" ]]; then
      OVERRIDE_VARS+=("${name}")
      backup_name="__OVERRIDE_${name}"
      printf -v "${backup_name}" '%s' "${!name}"
    fi
  done
}

restore_overrides() {
  local name backup_name
  for name in "${OVERRIDE_VARS[@]}"; do
    backup_name="__OVERRIDE_${name}"
    printf -v "${name}" '%s' "${!backup_name}"
    export "${name}"
    unset "${backup_name}"
  done
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

LOADED_ENV_FILE=""
capture_overrides
if load_env "${ENV_FILE}"; then
  LOADED_ENV_FILE="${ENV_FILE}"
elif load_env "${EXAMPLE_ENV_FILE}"; then
  LOADED_ENV_FILE="${EXAMPLE_ENV_FILE}"
else
  echo "Missing .env or .env.example in ${PROJECT_ROOT}" >&2
  exit 1
fi
restore_overrides

require_command docker

echo "Stopping Trading Bot V2 stack: ${COMPOSE_PROJECT_NAME:-trading-bot-v2}"
docker compose \
  --project-directory "${PROJECT_ROOT}" \
  --env-file "${LOADED_ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  down --remove-orphans

echo "Stopped. Runtime data under state/runtime was kept."
