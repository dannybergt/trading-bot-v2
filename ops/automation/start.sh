#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Daily operator start: use Docker Hub latest unless a specific IMAGE_TAG is
# intentionally supplied by the caller.
export IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "Starting Trading Bot V2 from Docker Hub tag: ${IMAGE_TAG}"
bash "${PROJECT_ROOT}/ops/automation/deploy.sh"

echo
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT:-18094}/login"
echo "API health via frontend: http://127.0.0.1:${FRONTEND_PORT:-18094}/api/health"
echo "Backend direct health: http://127.0.0.1:${BACKEND_PORT:-18090}/api/health"
