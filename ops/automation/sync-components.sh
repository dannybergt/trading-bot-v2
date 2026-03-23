#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
EXAMPLE_ENV_FILE="${PROJECT_ROOT}/.env.example"
RELEASES_DIR="${PROJECT_ROOT}/state/releases"
DRY_RUN="${DRY_RUN:-0}"
SKIP_BUILD="${SKIP_BUILD:-0}"
SOURCE_BACKEND_IMAGE="${SOURCE_BACKEND_IMAGE:-trading-bot-v2-backend:local}"
SOURCE_FRONTEND_IMAGE="${SOURCE_FRONTEND_IMAGE:-trading-bot-v2-frontend:local}"
OVERRIDE_VARS=()

capture_overrides() {
  local name backup_name
  for name in \
    DOCKERHUB_NAMESPACE \
    BACKEND_IMAGE_NAME \
    FRONTEND_IMAGE_NAME \
    IMAGE_TAG \
    DRY_RUN \
    SKIP_BUILD \
    SOURCE_BACKEND_IMAGE \
    SOURCE_FRONTEND_IMAGE; do
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

load_env() {
  local candidate="$1"
  if [[ ! -f "${candidate}" ]]; then
    return 1
  fi

  # shellcheck disable=SC1090
  source "${candidate}"
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

ensure_local_image() {
  local image_ref="$1"
  local image_id
  if ! image_id="$(docker image inspect --format '{{.Id}}' "${image_ref}" 2>&1)"; then
    if [[ -n "${image_id}" ]]; then
      echo "${image_id}" >&2
    fi
    echo "Required local image is missing: ${image_ref}" >&2
    exit 1
  fi
}

build_or_tag_image() {
  local local_ref="$1"
  local target_ref="$2"
  local dockerfile_path="$3"

  if [[ "${SKIP_BUILD}" == "1" ]]; then
    ensure_local_image "${local_ref}"
    echo "Tagging ${local_ref} as ${target_ref}"
    docker tag "${local_ref}" "${target_ref}"
    return 0
  fi

  echo "Building ${target_ref}"
  docker build -f "${dockerfile_path}" -t "${target_ref}" "${PROJECT_ROOT}"
}

image_repo_digests() {
  local image_ref="$1"
  docker image inspect --format '{{join .RepoDigests ","}}' "${image_ref}" 2>/dev/null || true
}

capture_overrides
if ! load_env "${ENV_FILE}" && ! load_env "${EXAMPLE_ENV_FILE}"; then
  echo "Missing .env or .env.example in ${PROJECT_ROOT}" >&2
  exit 1
fi
restore_overrides

require_command docker

: "${DOCKERHUB_NAMESPACE:?DOCKERHUB_NAMESPACE is required}"
: "${BACKEND_IMAGE_NAME:?BACKEND_IMAGE_NAME is required}"
: "${FRONTEND_IMAGE_NAME:?FRONTEND_IMAGE_NAME is required}"
: "${IMAGE_TAG:=latest}"

BACKEND_REF="docker.io/${DOCKERHUB_NAMESPACE}/${BACKEND_IMAGE_NAME}:${IMAGE_TAG}"
FRONTEND_REF="docker.io/${DOCKERHUB_NAMESPACE}/${FRONTEND_IMAGE_NAME}:${IMAGE_TAG}"

echo "Sync mode: $([[ "${DRY_RUN}" == "1" ]] && echo "dry-run" || echo "push")"
echo "Build mode: $([[ "${SKIP_BUILD}" == "1" ]] && echo "reuse-local-images" || echo "docker-build")"
echo "Backend target: ${BACKEND_REF}"
echo "Frontend target: ${FRONTEND_REF}"

build_or_tag_image \
  "${SOURCE_BACKEND_IMAGE}" \
  "${BACKEND_REF}" \
  "${PROJECT_ROOT}/ops/docker/backend.Dockerfile"

build_or_tag_image \
  "${SOURCE_FRONTEND_IMAGE}" \
  "${FRONTEND_REF}" \
  "${PROJECT_ROOT}/ops/docker/frontend.Dockerfile"

echo "Prepared image refs:"
docker image inspect \
  --format '{{join .RepoTags ", "}}' \
  "${BACKEND_REF}" \
  "${FRONTEND_REF}"

if [[ "${DRY_RUN}" == "1" ]]; then
  mkdir -p "${RELEASES_DIR}"
  cat >"${RELEASES_DIR}/${IMAGE_TAG}.env" <<EOF
CREATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
IMAGE_TAG=${IMAGE_TAG}
BACKEND_IMAGE_REF=${BACKEND_REF}
FRONTEND_IMAGE_REF=${FRONTEND_REF}
BACKEND_REPO_DIGESTS=$(image_repo_digests "${BACKEND_REF}")
FRONTEND_REPO_DIGESTS=$(image_repo_digests "${FRONTEND_REF}")
PUBLISH_MODE=dry-run
EOF
  echo "Dry run complete. No push was performed."
  exit 0
fi

echo "Pushing ${BACKEND_REF}"
docker push "${BACKEND_REF}"

echo "Pushing ${FRONTEND_REF}"
docker push "${FRONTEND_REF}"

mkdir -p "${RELEASES_DIR}"
cat >"${RELEASES_DIR}/${IMAGE_TAG}.env" <<EOF
CREATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
IMAGE_TAG=${IMAGE_TAG}
BACKEND_IMAGE_REF=${BACKEND_REF}
FRONTEND_IMAGE_REF=${FRONTEND_REF}
BACKEND_REPO_DIGESTS=$(image_repo_digests "${BACKEND_REF}")
FRONTEND_REPO_DIGESTS=$(image_repo_digests "${FRONTEND_REF}")
PUBLISH_MODE=push
EOF

echo "Multi-image sync complete"
