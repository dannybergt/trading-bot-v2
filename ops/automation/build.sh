#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${PROJECT_ROOT}/ops/automation/env.sh"

load_project_env "${PROJECT_ROOT}"
export_runtime_paths "${PROJECT_ROOT}"
prepare_runtime_dirs "${PROJECT_ROOT}"

# Auto-activate the secret-blocking pre-commit hook for any developer who
# runs build.sh in a fresh clone. core.hooksPath is a per-repo .git/config
# setting and does not propagate via git clone, so we ensure it here.
if [[ -d "${PROJECT_ROOT}/.git" && -d "${PROJECT_ROOT}/.githooks" ]]; then
  current_hooks_path="$(git -C "${PROJECT_ROOT}" config --get core.hooksPath 2>/dev/null || true)"
  if [[ "${current_hooks_path}" != ".githooks" ]]; then
    git -C "${PROJECT_ROOT}" config core.hooksPath .githooks
    echo "Activated git hooks at .githooks (core.hooksPath was '${current_hooks_path:-unset}')"
  fi
fi

docker build \
  -f "${PROJECT_ROOT}/ops/docker/backend.Dockerfile" \
  -t trading-bot-v2-backend:local \
  "${PROJECT_ROOT}"

docker build \
  -f "${PROJECT_ROOT}/ops/docker/frontend.Dockerfile" \
  -t trading-bot-v2-frontend:local \
  "${PROJECT_ROOT}"

echo "Built trading-bot-v2-backend:local and trading-bot-v2-frontend:local"
