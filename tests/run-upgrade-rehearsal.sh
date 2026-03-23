#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"
EXAMPLE_ENV_FILE="${PROJECT_ROOT}/.env.example"
RUN_ID="${RUN_ID:-$(date +%Y%m%d%H%M%S)-$$}"
TEST_ROOT="${TEST_ROOT:-/tmp/trading-bot-v2-upgrade-rehearsal-${RUN_ID}}"
PRIMARY_ROOT="${TEST_ROOT}/primary"
RESTORE_ROOT="${TEST_ROOT}/restore"
PRIMARY_PROJECT="${PRIMARY_PROJECT:-trading-bot-v2-upgrade-primary-${RUN_ID}}"
RESTORE_PROJECT="${RESTORE_PROJECT:-trading-bot-v2-upgrade-restore-${RUN_ID}}"
PRIMARY_BACKEND_PORT="${PRIMARY_BACKEND_PORT:-18150}"
PRIMARY_FRONTEND_PORT="${PRIMARY_FRONTEND_PORT:-18154}"
RESTORE_BACKEND_PORT="${RESTORE_BACKEND_PORT:-18160}"
RESTORE_FRONTEND_PORT="${RESTORE_FRONTEND_PORT:-18164}"
DEPLOYMENTS_DIR="${PROJECT_ROOT}/state/runtime/deployments"
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
    IMAGE_TAG \
    DOCKERHUB_NAMESPACE \
    BACKEND_IMAGE_NAME \
    FRONTEND_IMAGE_NAME \
    BACKEND_IMAGE_REF \
    FRONTEND_IMAGE_REF \
    PRIMARY_BACKEND_PORT \
    PRIMARY_FRONTEND_PORT \
    RESTORE_BACKEND_PORT \
    RESTORE_FRONTEND_PORT \
    PRIMARY_PROJECT \
    RESTORE_PROJECT \
    TEST_ROOT \
    ADMIN_EMAIL \
    ADMIN_PASSWORD \
    MEMBER_EMAIL \
    MEMBER_PASSWORD \
    CUSTOM_WATCHLIST_NAME \
    CUSTOM_SYMBOL; do
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

compose_for_stack() {
  local stack_name="$1"
  shift

  local compose_project_name backend_port frontend_port host_data_dir host_backup_dir host_postgres_dir
  if [[ "${stack_name}" == "primary" ]]; then
    compose_project_name="${PRIMARY_PROJECT}"
    backend_port="${PRIMARY_BACKEND_PORT}"
    frontend_port="${PRIMARY_FRONTEND_PORT}"
    host_data_dir="${PRIMARY_ROOT}/backend-data"
    host_backup_dir="${PRIMARY_ROOT}/backups"
    host_postgres_dir="${PRIMARY_ROOT}/postgres"
  else
    compose_project_name="${RESTORE_PROJECT}"
    backend_port="${RESTORE_BACKEND_PORT}"
    frontend_port="${RESTORE_FRONTEND_PORT}"
    host_data_dir="${RESTORE_ROOT}/backend-data"
    host_backup_dir="${RESTORE_ROOT}/backups"
    host_postgres_dir="${RESTORE_ROOT}/postgres"
  fi

  COMPOSE_PROJECT_NAME="${compose_project_name}" \
  BACKEND_PORT="${backend_port}" \
  FRONTEND_PORT="${frontend_port}" \
  HOST_DATA_DIR="${host_data_dir}" \
  HOST_BACKUP_DIR="${host_backup_dir}" \
  HOST_POSTGRES_DATA_DIR="${host_postgres_dir}" \
  BACKEND_IMAGE_REF="${BACKEND_IMAGE_REF}" \
  FRONTEND_IMAGE_REF="${FRONTEND_IMAGE_REF}" \
  docker compose \
    --project-directory "${PROJECT_ROOT}" \
    --env-file "${LOADED_ENV_FILE}" \
    -f "${PROJECT_ROOT}/ops/docker/compose.yaml" \
    "$@"
}

deploy_stack() {
  local stack_name="$1"
  local backend_port frontend_port host_data_dir host_backup_dir host_postgres_dir

  if [[ "${stack_name}" == "primary" ]]; then
    backend_port="${PRIMARY_BACKEND_PORT}"
    frontend_port="${PRIMARY_FRONTEND_PORT}"
    host_data_dir="${PRIMARY_ROOT}/backend-data"
    host_backup_dir="${PRIMARY_ROOT}/backups"
    host_postgres_dir="${PRIMARY_ROOT}/postgres"
  else
    backend_port="${RESTORE_BACKEND_PORT}"
    frontend_port="${RESTORE_FRONTEND_PORT}"
    host_data_dir="${RESTORE_ROOT}/backend-data"
    host_backup_dir="${RESTORE_ROOT}/backups"
    host_postgres_dir="${RESTORE_ROOT}/postgres"
  fi

  TRACK_CURRENT_DEPLOYMENT=0 \
  COMPOSE_PROJECT_NAME="$([[ "${stack_name}" == "primary" ]] && echo "${PRIMARY_PROJECT}" || echo "${RESTORE_PROJECT}")" \
  BACKEND_PORT="${backend_port}" \
  FRONTEND_PORT="${frontend_port}" \
  HOST_DATA_DIR="${host_data_dir}" \
  HOST_BACKUP_DIR="${host_backup_dir}" \
  HOST_POSTGRES_DATA_DIR="${host_postgres_dir}" \
  IMAGE_TAG="${IMAGE_TAG}" \
  BACKEND_IMAGE_REF="${BACKEND_IMAGE_REF}" \
  FRONTEND_IMAGE_REF="${FRONTEND_IMAGE_REF}" \
  ENV_FILE="${LOADED_ENV_FILE}" \
  bash "${PROJECT_ROOT}/ops/automation/deploy.sh"
}

cleanup() {
  set +e
  compose_for_stack primary -p "${PRIMARY_PROJECT}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  compose_for_stack restore -p "${RESTORE_PROJECT}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  if [[ "${KEEP_TEST_ROOT:-0}" != "1" ]]; then
    rm -rf "${TEST_ROOT}" >/dev/null 2>&1 || true
  fi
}

seed_or_verify_data() {
  local base_url="$1"
  local mode="$2"

  BASE_URL="${base_url}" \
  MODE="${mode}" \
  ADMIN_EMAIL="${ADMIN_EMAIL}" \
  ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
  MEMBER_EMAIL="${MEMBER_EMAIL}" \
  MEMBER_PASSWORD="${MEMBER_PASSWORD}" \
  CUSTOM_WATCHLIST_NAME="${CUSTOM_WATCHLIST_NAME}" \
  CUSTOM_SYMBOL="${CUSTOM_SYMBOL}" \
  python3 - <<'PY'
import json
import os
import urllib.error
import urllib.request

base = os.environ["BASE_URL"].rstrip("/")
mode = os.environ["MODE"]
admin_email = os.environ["ADMIN_EMAIL"]
admin_password = os.environ["ADMIN_PASSWORD"]
member_email = os.environ["MEMBER_EMAIL"]
member_password = os.environ["MEMBER_PASSWORD"]
custom_watchlist_name = os.environ["CUSTOM_WATCHLIST_NAME"]
custom_symbol = os.environ["CUSTOM_SYMBOL"]


def request(method, path, payload=None, headers=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{base}{path}", data=body, method=method)
    req.add_header("Accept", "application/json")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {path} failed with {exc.code}: {detail}") from exc


def login(email, password):
    payload = request(
        "POST",
        "/api/auth/login",
        {"email": email, "password": password},
    )
    token = payload["access_token"]
    return {"Authorization": f"Bearer {token}"}


if mode == "seed":
    register_payload = request(
        "POST",
        "/api/auth/register",
        {"email": admin_email, "password": admin_password},
    )
    assert register_payload["email"] == admin_email
    headers = login(admin_email, admin_password)

    created_watchlist = request(
        "POST",
        "/api/watchlists",
        {"name": custom_watchlist_name},
        headers,
    )
    request(
        "POST",
        f"/api/watchlists/{created_watchlist['id']}/items",
        {"symbol": custom_symbol, "name": "Upgrade Rehearsal Asset"},
        headers,
    )
    member_payload = request(
        "POST",
        "/api/auth/admin/users",
        {"email": member_email, "password": member_password, "is_admin": False},
        headers,
    )
    assert member_payload["email"] == member_email
    export_payload = request("GET", "/api/admin/export", headers=headers)
    exported_emails = {user["email"] for user in export_payload["data"]["users"]}
    assert exported_emails == {admin_email, member_email}
    print("seed ok")
elif mode == "verify":
    headers = login(admin_email, admin_password)
    watchlists = request("GET", "/api/watchlists", headers=headers)
    custom_watchlists = [item for item in watchlists if item["name"] == custom_watchlist_name]
    assert len(custom_watchlists) == 1
    symbols = {item["symbol"] for item in custom_watchlists[0]["items"]}
    assert custom_symbol in symbols

    export_payload = request("GET", "/api/admin/export", headers=headers)
    exported_emails = {user["email"] for user in export_payload["data"]["users"]}
    assert exported_emails == {admin_email, member_email}

    member_login = request(
        "POST",
        "/api/auth/login",
        {"email": member_email, "password": member_password},
    )
    assert member_login["mfa_required"] is False
    print("verify ok")
else:
    raise SystemExit(f"Unsupported mode: {mode}")
PY
}

restore_postgres_dump_into_stack() {
  local dump_file="$1"
  local attempts=0

  compose_for_stack restore -p "${RESTORE_PROJECT}" up -d postgres
  until compose_for_stack restore -p "${RESTORE_PROJECT}" exec -T postgres sh -lc \
    'PGPASSWORD="$POSTGRES_PASSWORD" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null'; do
    attempts=$((attempts + 1))
    if (( attempts >= 30 )); then
      echo "Restore PostgreSQL service did not become ready in time" >&2
      return 1
    fi
    sleep 2
  done

  compose_for_stack restore -p "${RESTORE_PROJECT}" exec -T postgres sh -lc \
    'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"'

  compose_for_stack restore -p "${RESTORE_PROJECT}" exec -T postgres sh -lc \
    'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' \
    < "${dump_file}"

  if ! compose_for_stack restore -p "${RESTORE_PROJECT}" up -d backend; then
    compose_for_stack restore -p "${RESTORE_PROJECT}" logs --no-color postgres backend >&2 || true
    return 1
  fi

  if ! wait_for_http "http://127.0.0.1:${RESTORE_BACKEND_PORT}/api/health" "Restore backend health endpoint"; then
    compose_for_stack restore -p "${RESTORE_PROJECT}" logs --no-color postgres backend >&2 || true
    return 1
  fi

  if ! compose_for_stack restore -p "${RESTORE_PROJECT}" up -d frontend; then
    compose_for_stack restore -p "${RESTORE_PROJECT}" logs --no-color frontend >&2 || true
    return 1
  fi

  wait_for_http "http://127.0.0.1:${RESTORE_FRONTEND_PORT}/login" "Restore frontend login route"
}

latest_deployment_record_after() {
  local marker_file="$1"
  find "${DEPLOYMENTS_DIR}" -maxdepth 1 -type f -name 'deployment-*.env' -newer "${marker_file}" | sort | tail -n 1
}

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
require_command curl
require_command python3

: "${DOCKERHUB_NAMESPACE:?DOCKERHUB_NAMESPACE is required}"
: "${BACKEND_IMAGE_NAME:?BACKEND_IMAGE_NAME is required}"
: "${FRONTEND_IMAGE_NAME:?FRONTEND_IMAGE_NAME is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required for upgrade rehearsal}"

BACKEND_IMAGE_REF="${BACKEND_IMAGE_REF:-docker.io/${DOCKERHUB_NAMESPACE}/${BACKEND_IMAGE_NAME}:${IMAGE_TAG}}"
FRONTEND_IMAGE_REF="${FRONTEND_IMAGE_REF:-docker.io/${DOCKERHUB_NAMESPACE}/${FRONTEND_IMAGE_NAME}:${IMAGE_TAG}}"
ADMIN_EMAIL="${ADMIN_EMAIL:-upgrade-admin-${RUN_ID}@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-UpgradeAdminPass123!}"
MEMBER_EMAIL="${MEMBER_EMAIL:-upgrade-member-${RUN_ID}@example.com}"
MEMBER_PASSWORD="${MEMBER_PASSWORD:-UpgradeMemberPass123!}"
CUSTOM_WATCHLIST_NAME="${CUSTOM_WATCHLIST_NAME:-Upgrade Rehearsal}"
CUSTOM_SYMBOL="${CUSTOM_SYMBOL:-TSLA}"

mkdir -p \
  "${PRIMARY_ROOT}/backend-data" \
  "${PRIMARY_ROOT}/backups" \
  "${PRIMARY_ROOT}/postgres" \
  "${RESTORE_ROOT}/backend-data" \
  "${RESTORE_ROOT}/backups" \
  "${RESTORE_ROOT}/postgres" \
  "${DEPLOYMENTS_DIR}"

trap cleanup EXIT

echo "Primary deploy project: ${PRIMARY_PROJECT}"
echo "Restore deploy project: ${RESTORE_PROJECT}"
echo "Release tag under test: ${IMAGE_TAG}"

echo "Initial Docker-Hub deploy"
deploy_stack primary
wait_for_http "http://127.0.0.1:${PRIMARY_BACKEND_PORT}/api/health" "Primary backend health endpoint"
wait_for_http "http://127.0.0.1:${PRIMARY_FRONTEND_PORT}/login" "Primary frontend login route"

echo "Seeding upgrade rehearsal data"
seed_or_verify_data "http://127.0.0.1:${PRIMARY_BACKEND_PORT}" seed

MARKER_FILE="$(mktemp)"
touch "${MARKER_FILE}"

echo "Running upgrade deploy over existing data"
deploy_stack primary

UPGRADE_RECORD="$(latest_deployment_record_after "${MARKER_FILE}")"
rm -f "${MARKER_FILE}"

if [[ -z "${UPGRADE_RECORD}" ]]; then
  echo "Upgrade deployment record was not created" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${UPGRADE_RECORD}"

if [[ -z "${PRE_UPGRADE_POSTGRES_DUMP}" || ! -s "${PRE_UPGRADE_POSTGRES_DUMP}" ]]; then
  echo "Expected pre-upgrade PostgreSQL dump was not created" >&2
  exit 1
fi

if [[ -z "${PRE_UPGRADE_APP_BACKUP}" || ! -s "${PRIMARY_ROOT}/backups/${PRE_UPGRADE_APP_BACKUP}" ]]; then
  echo "Expected pre-upgrade application snapshot backup was not created" >&2
  exit 1
fi

echo "Verifying data persistence after upgrade"
seed_or_verify_data "http://127.0.0.1:${PRIMARY_BACKEND_PORT}" verify

echo "Restoring pre-upgrade PostgreSQL dump into a fresh stack"
restore_postgres_dump_into_stack "${PRE_UPGRADE_POSTGRES_DUMP}"

echo "Verifying restored data in fresh stack"
seed_or_verify_data "http://127.0.0.1:${RESTORE_BACKEND_PORT}" verify

echo "Upgrade rehearsal passed"
echo "Upgrade deployment record: ${UPGRADE_RECORD}"
echo "Pre-upgrade PostgreSQL dump: ${PRE_UPGRADE_POSTGRES_DUMP}"
echo "Pre-upgrade app snapshot: ${PRIMARY_ROOT}/backups/${PRE_UPGRADE_APP_BACKUP}"
