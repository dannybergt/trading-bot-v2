#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck disable=SC1091
source "${PROJECT_ROOT}/ops/automation/env.sh"

# Daily operator start: use Docker Hub latest unless a specific IMAGE_TAG is
# intentionally supplied by the caller.
START_IMAGE_TAG="${IMAGE_TAG:-latest}"

load_project_env "${PROJECT_ROOT}"
export_runtime_paths "${PROJECT_ROOT}"
prepare_runtime_dirs "${PROJECT_ROOT}"
adopt_legacy_postgres_runtime_dir "${PROJECT_ROOT}" "${HOST_POSTGRES_DATA_DIR}"

export IMAGE_TAG="${START_IMAGE_TAG}"

echo "Loaded config: ${LOADED_ENV_FILE}"
if [[ -n "${LOADED_ENV_LOCAL_FILE:-}" ]]; then
  echo "Loaded local overrides: ${LOADED_ENV_LOCAL_FILE}"
fi
echo "Resolved runtime dirs:"
echo "  data: ${HOST_DATA_DIR}"
echo "  backups: ${HOST_BACKUP_DIR}"
echo "  postgres: ${HOST_POSTGRES_DATA_DIR}"
echo "Starting Trading Bot V2 from Docker Hub tag: ${IMAGE_TAG}"

bash "${PROJECT_ROOT}/ops/automation/deploy.sh"

echo
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT:-18094}/login"
echo "API health via frontend: http://127.0.0.1:${FRONTEND_PORT:-18094}/api/health"
echo "Backend direct health: http://127.0.0.1:${BACKEND_PORT:-18090}/api/health"
