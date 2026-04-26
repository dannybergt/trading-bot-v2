#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_ROOT}/ops/docker/compose.yaml}"
DEPLOY_STATE_DIR="${PROJECT_ROOT}/state/runtime/deployments"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
AUTO_ROLLBACK="${AUTO_ROLLBACK:-1}"
TRACK_CURRENT_DEPLOYMENT="${TRACK_CURRENT_DEPLOYMENT:-1}"
OVERRIDE_VARS=()
# shellcheck disable=SC1091
source "${PROJECT_ROOT}/ops/automation/env.sh"

capture_overrides() {
  local name backup_name
  for name in \
    DOCKERHUB_NAMESPACE \
    BACKEND_IMAGE_NAME \
    FRONTEND_IMAGE_NAME \
    IMAGE_TAG \
    BACKEND_IMAGE_REF \
    FRONTEND_IMAGE_REF \
    HOST_DATA_DIR \
    HOST_BACKUP_DIR \
    HOST_POSTGRES_DATA_DIR \
    BACKEND_PORT \
    FRONTEND_PORT \
    INITIAL_ADMIN_EMAIL \
    INITIAL_ADMIN_PASSWORD \
    INITIAL_ADMIN_MFA_ENABLED \
    COMPOSE_PROJECT_NAME \
    AUTO_ROLLBACK \
    TRACK_CURRENT_DEPLOYMENT; do
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

resolve_host_path() {
  local path_value="$1"
  if [[ "${path_value}" = /* ]]; then
    printf '%s\n' "${path_value}"
    return 0
  fi

  printf '%s/%s\n' "${PROJECT_ROOT}" "${path_value#./}"
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

sanitize_label() {
  printf '%s' "$1" | tr '/:@ ' '____'
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

compose() {
  docker compose \
    --project-directory "${PROJECT_ROOT}" \
    -f "${COMPOSE_FILE}" \
    "$@"
}

get_service_container_id() {
  compose ps -q "$1" 2>/dev/null || true
}

get_service_image_ref() {
  local service="$1"
  local container_id
  container_id="$(get_service_container_id "${service}")"
  if [[ -z "${container_id}" ]]; then
    return 0
  fi
  docker inspect --format '{{.Config.Image}}' "${container_id}"
}

get_service_image_id() {
  local service="$1"
  local container_id
  container_id="$(get_service_container_id "${service}")"
  if [[ -z "${container_id}" ]]; then
    return 0
  fi
  docker inspect --format '{{.Image}}' "${container_id}"
}

create_application_backup() {
  local label="$1"
  compose exec -T \
    -e BACKUP_LABEL="${label}" \
    backend \
    python -c 'import os; from app.backup_service import BackupService; from app.database import SessionLocal; db = SessionLocal(); path = BackupService.create_backup(db, label=os.environ["BACKUP_LABEL"]); db.close(); print(path.name)'
}

create_postgres_dump() {
  local output_file="$1"
  compose exec -T postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >"${output_file}"
}

write_deployment_record() {
  local status="$1"
  local rollback_status="$2"
  local record_file="$3"

  cat >"${record_file}" <<EOF
DEPLOYED_AT=${TIMESTAMP}
DEPLOY_STATUS=${status}
ROLLBACK_STATUS=${rollback_status}
IMAGE_TAG=${IMAGE_TAG}
TARGET_BACKEND_IMAGE_REF=${TARGET_BACKEND_IMAGE_REF}
TARGET_FRONTEND_IMAGE_REF=${TARGET_FRONTEND_IMAGE_REF}
ACTIVE_BACKEND_IMAGE_REF=${ACTIVE_BACKEND_IMAGE_REF}
ACTIVE_FRONTEND_IMAGE_REF=${ACTIVE_FRONTEND_IMAGE_REF}
PREVIOUS_BACKEND_IMAGE_REF=${PREVIOUS_BACKEND_IMAGE_REF}
PREVIOUS_FRONTEND_IMAGE_REF=${PREVIOUS_FRONTEND_IMAGE_REF}
ACTIVE_BACKEND_IMAGE_ID=${ACTIVE_BACKEND_IMAGE_ID}
ACTIVE_FRONTEND_IMAGE_ID=${ACTIVE_FRONTEND_IMAGE_ID}
PRE_UPGRADE_APP_BACKUP=${PRE_UPGRADE_APP_BACKUP}
PRE_UPGRADE_POSTGRES_DUMP=${PRE_UPGRADE_POSTGRES_DUMP}
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-trading-bot-v2}
BACKEND_PORT=${BACKEND_PORT:-18090}
FRONTEND_PORT=${FRONTEND_PORT:-18094}
HOST_DATA_DIR=${HOST_DATA_DIR}
HOST_BACKUP_DIR=${HOST_BACKUP_DIR}
HOST_POSTGRES_DATA_DIR=${HOST_POSTGRES_DATA_DIR}
EOF

  if [[ "${TRACK_CURRENT_DEPLOYMENT}" == "1" ]]; then
    cp "${record_file}" "${DEPLOY_STATE_DIR}/current.env"
  fi
}

LOADED_ENV_FILE=""
LOADED_ENV_LOCAL_FILE=""
capture_overrides
load_project_env "${PROJECT_ROOT}"
restore_overrides

require_command docker
require_command curl

: "${DOCKERHUB_NAMESPACE:?DOCKERHUB_NAMESPACE is required}"
: "${BACKEND_IMAGE_NAME:?BACKEND_IMAGE_NAME is required}"
: "${FRONTEND_IMAGE_NAME:?FRONTEND_IMAGE_NAME is required}"
: "${IMAGE_TAG:=latest}"

HOST_DATA_DIR="$(resolve_host_path "${HOST_DATA_DIR:-state/runtime/backend-data}")"
HOST_BACKUP_DIR="$(resolve_host_path "${HOST_BACKUP_DIR:-state/runtime/backups}")"
HOST_POSTGRES_DATA_DIR="$(resolve_host_path "${HOST_POSTGRES_DATA_DIR:-state/runtime/postgres}")"
TARGET_BACKEND_IMAGE_REF="${BACKEND_IMAGE_REF:-docker.io/${DOCKERHUB_NAMESPACE}/${BACKEND_IMAGE_NAME}:${IMAGE_TAG}}"
TARGET_FRONTEND_IMAGE_REF="${FRONTEND_IMAGE_REF:-docker.io/${DOCKERHUB_NAMESPACE}/${FRONTEND_IMAGE_NAME}:${IMAGE_TAG}}"

export HOST_DATA_DIR HOST_BACKUP_DIR HOST_POSTGRES_DATA_DIR
export BACKEND_IMAGE_REF="${TARGET_BACKEND_IMAGE_REF}"
export FRONTEND_IMAGE_REF="${TARGET_FRONTEND_IMAGE_REF}"

mkdir -p \
  "${HOST_DATA_DIR}" \
  "${HOST_BACKUP_DIR}" \
  "${HOST_POSTGRES_DATA_DIR}" \
  "${DEPLOY_STATE_DIR}"

chmod 0777 \
  "${HOST_DATA_DIR}" \
  "${HOST_BACKUP_DIR}" \
  "${HOST_POSTGRES_DATA_DIR}"

PREVIOUS_BACKEND_IMAGE_REF="$(get_service_image_ref backend)"
PREVIOUS_FRONTEND_IMAGE_REF="$(get_service_image_ref frontend)"
PRE_UPGRADE_APP_BACKUP=""
PRE_UPGRADE_POSTGRES_DUMP=""
ACTIVE_BACKEND_IMAGE_REF=""
ACTIVE_FRONTEND_IMAGE_REF=""
ACTIVE_BACKEND_IMAGE_ID=""
ACTIVE_FRONTEND_IMAGE_ID=""
ROLLBACK_STATUS="not-needed"

echo "Deploying backend image: ${TARGET_BACKEND_IMAGE_REF}"
echo "Deploying frontend image: ${TARGET_FRONTEND_IMAGE_REF}"

if [[ -n "$(get_service_container_id postgres)" ]]; then
  PRE_UPGRADE_POSTGRES_DUMP="${HOST_BACKUP_DIR}/postgres-${TIMESTAMP}-pre-upgrade-$(sanitize_label "${IMAGE_TAG}").sql"
  echo "Creating PostgreSQL dump: ${PRE_UPGRADE_POSTGRES_DUMP}"
  create_postgres_dump "${PRE_UPGRADE_POSTGRES_DUMP}"
fi

if [[ -n "$(get_service_container_id backend)" ]]; then
  echo "Creating application snapshot backup"
  PRE_UPGRADE_APP_BACKUP="$(create_application_backup "pre-upgrade-$(sanitize_label "${IMAGE_TAG}")")"
fi

echo "Pulling Docker Hub images"
docker pull "${TARGET_BACKEND_IMAGE_REF}"
docker pull "${TARGET_FRONTEND_IMAGE_REF}"

if compose up -d --no-build \
  && wait_for_http "http://127.0.0.1:${BACKEND_PORT:-18090}/api/health" "Backend health endpoint" \
  && wait_for_http "http://127.0.0.1:${FRONTEND_PORT:-18094}/login" "Frontend login route"; then
  ACTIVE_BACKEND_IMAGE_REF="$(get_service_image_ref backend)"
  ACTIVE_FRONTEND_IMAGE_REF="$(get_service_image_ref frontend)"
  ACTIVE_BACKEND_IMAGE_ID="$(get_service_image_id backend)"
  ACTIVE_FRONTEND_IMAGE_ID="$(get_service_image_id frontend)"
  RECORD_FILE="${DEPLOY_STATE_DIR}/deployment-${TIMESTAMP}.env"
  write_deployment_record "success" "${ROLLBACK_STATUS}" "${RECORD_FILE}"
  echo "Deployment succeeded"
  echo "Deployment record: ${RECORD_FILE}"
  exit 0
fi

echo "Deployment failed" >&2

if [[ "${AUTO_ROLLBACK}" == "1" && -n "${PREVIOUS_BACKEND_IMAGE_REF}" && -n "${PREVIOUS_FRONTEND_IMAGE_REF}" ]]; then
  echo "Attempting rollback to previous images" >&2
  export BACKEND_IMAGE_REF="${PREVIOUS_BACKEND_IMAGE_REF}"
  export FRONTEND_IMAGE_REF="${PREVIOUS_FRONTEND_IMAGE_REF}"
  if compose up -d --no-build \
    && wait_for_http "http://127.0.0.1:${BACKEND_PORT:-18090}/api/health" "Backend health endpoint after rollback" \
    && wait_for_http "http://127.0.0.1:${FRONTEND_PORT:-18094}/login" "Frontend login route after rollback"; then
    ROLLBACK_STATUS="successful"
  else
    ROLLBACK_STATUS="failed"
  fi
else
  ROLLBACK_STATUS="skipped"
fi

ACTIVE_BACKEND_IMAGE_REF="$(get_service_image_ref backend)"
ACTIVE_FRONTEND_IMAGE_REF="$(get_service_image_ref frontend)"
ACTIVE_BACKEND_IMAGE_ID="$(get_service_image_id backend)"
ACTIVE_FRONTEND_IMAGE_ID="$(get_service_image_id frontend)"
RECORD_FILE="${DEPLOY_STATE_DIR}/deployment-${TIMESTAMP}.env"
write_deployment_record "failed" "${ROLLBACK_STATUS}" "${RECORD_FILE}"

echo "Deployment record: ${RECORD_FILE}" >&2
exit 1
