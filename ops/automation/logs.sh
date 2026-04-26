#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_ROOT}/ops/docker/compose.yaml}"

# shellcheck disable=SC1091
source "${PROJECT_ROOT}/ops/automation/env.sh"

load_project_env "${PROJECT_ROOT}"
export_runtime_paths "${PROJECT_ROOT}"

docker compose \
  --project-directory "${PROJECT_ROOT}" \
  -f "${COMPOSE_FILE}" \
  logs -f "$@"
