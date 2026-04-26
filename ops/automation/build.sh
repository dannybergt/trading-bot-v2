#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${PROJECT_ROOT}/ops/automation/env.sh"

load_project_env "${PROJECT_ROOT}"
export_runtime_paths "${PROJECT_ROOT}"
prepare_runtime_dirs "${PROJECT_ROOT}"

docker build \
  -f "${PROJECT_ROOT}/ops/docker/backend.Dockerfile" \
  -t trading-bot-v2-backend:local \
  "${PROJECT_ROOT}"

docker build \
  -f "${PROJECT_ROOT}/ops/docker/frontend.Dockerfile" \
  -t trading-bot-v2-frontend:local \
  "${PROJECT_ROOT}"

echo "Built trading-bot-v2-backend:local and trading-bot-v2-frontend:local"
