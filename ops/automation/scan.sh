#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "Scanning for obvious insecure defaults"
rg -n "dev-secret-change-in-production-please|allow_origins=\\[\"\\*\"\\]|print\\(|except Exception" \
  "${PROJECT_ROOT}/src/backend" || true

echo "Scanning for extracted bytecode and caches"
find "${PROJECT_ROOT}/src/backend" \( -name "__pycache__" -o -name "*.pyc" \) -print || true

echo "Scan complete"
