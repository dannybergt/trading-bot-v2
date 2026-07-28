#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

test -f "${PROJECT_ROOT}/src/backend/app/main.py"
test -f "${PROJECT_ROOT}/src/backend/requirements.txt"
test -f "${PROJECT_ROOT}/src/frontend/index.html"
test -f "${PROJECT_ROOT}/src/frontend/package.json"
test -f "${PROJECT_ROOT}/src/backend/app/migrate_watchlists.py"

for file in "${PROJECT_ROOT}"/src/backend/app/*.py; do
  python3 -c 'import pathlib, sys; path = pathlib.Path(sys.argv[1]); compile(path.read_text(), str(path), "exec")' "$file"
done

# The deployment descriptors and workflow definitions are mounted individually
# (not as a whole-repo mount) so test code never sees .env.local. They keep
# their repo-relative layout under /app, so tests resolving them via
# `parents[1]` work both here and when run directly from a checkout.
docker run --rm \
  -v "${PROJECT_ROOT}/tests:/app/tests:ro" \
  -v "${PROJECT_ROOT}/ops/docker/backend.Dockerfile:/app/ops/docker/backend.Dockerfile:ro" \
  -v "${PROJECT_ROOT}/docker-compose.yml:/app/docker-compose.yml:ro" \
  -v "${PROJECT_ROOT}/.env.example:/app/.env.example:ro" \
  -v "${PROJECT_ROOT}/.github/workflows:/app/.github/workflows:ro" \
  -v "${PROJECT_ROOT}/ops/docker/frontend.nginx.conf:/app/ops/docker/frontend.nginx.conf:ro" \
  -v "${PROJECT_ROOT}/src/frontend/src/i18n:/app/src/frontend/src/i18n:ro" \
  trading-bot-v2-backend:local \
  python -m unittest discover -s /app/tests -p 'test_*.py'

echo "Basic structure and Python syntax checks passed"
