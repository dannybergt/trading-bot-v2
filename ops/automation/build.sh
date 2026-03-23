#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

mkdir -p \
  "${PROJECT_ROOT}/state/runtime/backend-data" \
  "${PROJECT_ROOT}/state/runtime/backups" \
  "${PROJECT_ROOT}/state/runtime/postgres"

# The backend container runs as a non-root user, so bind-mounted runtime paths
# must already be writable on the host before `docker compose up`.
chmod 0777 \
  "${PROJECT_ROOT}/state/runtime/backend-data" \
  "${PROJECT_ROOT}/state/runtime/backups" \
  "${PROJECT_ROOT}/state/runtime/postgres"

docker build \
  -f "${PROJECT_ROOT}/ops/docker/backend.Dockerfile" \
  -t trading-bot-v2-backend:local \
  "${PROJECT_ROOT}"

docker build \
  -f "${PROJECT_ROOT}/ops/docker/frontend.Dockerfile" \
  -t trading-bot-v2-frontend:local \
  "${PROJECT_ROOT}"

echo "Built trading-bot-v2-backend:local and trading-bot-v2-frontend:local"
