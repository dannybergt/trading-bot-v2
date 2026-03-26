#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "Deprecated wrapper: forwarding to ops/automation/sync-components.sh"
exec bash "${PROJECT_ROOT}/ops/automation/sync-components.sh" "$@"
