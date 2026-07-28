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

# The workflow definitions are mounted read-only so tests can assert on them.
# Deliberately not a whole-repo mount -- that would put .env.local inside the
# test container.
docker run --rm \
  -v "${PROJECT_ROOT}/tests:/app/tests:ro" \
  -v "${PROJECT_ROOT}/.github/workflows:/app/.github/workflows:ro" \
  trading-bot-v2-backend:local \
  python -m unittest discover -s /app/tests -p 'test_*.py'

echo "Basic structure and Python syntax checks passed"
