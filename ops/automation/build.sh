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

# Version metadata baked into both images (ENV + OCI labels). Derived from git
# so CI and local builds carry the exact commit; overridable via env.
GIT_SHA="${GIT_SHA:-$(git -C "${PROJECT_ROOT}" rev-parse --short=12 HEAD 2>/dev/null || echo unknown)}"
BUILD_TIME="${BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
APP_VERSION="${APP_VERSION:-$(git -C "${PROJECT_ROOT}" describe --tags --always 2>/dev/null || echo dev)}"
echo "Build version: ${APP_VERSION} (${GIT_SHA}) @ ${BUILD_TIME}"

docker build \
  -f "${PROJECT_ROOT}/ops/docker/backend.Dockerfile" \
  --build-arg GIT_SHA="${GIT_SHA}" \
  --build-arg BUILD_TIME="${BUILD_TIME}" \
  --build-arg APP_VERSION="${APP_VERSION}" \
  -t trading-bot-v2-backend:local \
  "${PROJECT_ROOT}"

docker build \
  -f "${PROJECT_ROOT}/ops/docker/frontend.Dockerfile" \
  --build-arg GIT_SHA="${GIT_SHA}" \
  --build-arg BUILD_TIME="${BUILD_TIME}" \
  --build-arg APP_VERSION="${APP_VERSION}" \
  -t trading-bot-v2-frontend:local \
  "${PROJECT_ROOT}"

echo "Built trading-bot-v2-backend:local and trading-bot-v2-frontend:local"
