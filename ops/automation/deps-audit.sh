#!/usr/bin/env bash
# Dependency audit for the shipped backend image and the frontend lockfile.
#
# Fails on any advisory that is not listed below. Every ignore names the
# package that pins the vulnerable version and why it is not reachable here;
# remove the line as soon as the pin is gone (ADR 2026-09-29).
#
#   BACKEND_IMAGE=trading-bot-v2-backend:local bash ops/automation/deps-audit.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_IMAGE="${BACKEND_IMAGE:-trading-bot-v2-backend:local}"
PIP_AUDIT_VERSION="2.10.1"

# Empty since 2026-10-06: python-jose (and its ecdsa) replaced by PyJWT,
# alpaca-trade-api installed --no-deps so urllib3/msgpack are no longer held
# back (ADR 2026-10-06). A new entry needs the pinning package, why the code
# path is not reachable, and the condition that removes it.
IGNORED=()

ignore_args=()
for id in "${IGNORED[@]}"; do
  ignore_args+=(--ignore-vuln "${id}")
done

echo "pip-audit ${PIP_AUDIT_VERSION} against ${BACKEND_IMAGE} (installed packages)"
# Throwaway container; pip-audit lives in its own venv so its dependencies are
# not part of the audit — the audited site-packages is exactly what the image
# ships.
docker run --rm -e PIP_AUDIT_VERSION="${PIP_AUDIT_VERSION}" "${BACKEND_IMAGE}" sh -c '
  set -e
  python -m venv /tmp/pip-audit
  /tmp/pip-audit/bin/pip install --no-cache-dir -q "pip-audit==${PIP_AUDIT_VERSION}"
  site="$(python -c "import sysconfig; print(sysconfig.get_paths()[\"purelib\"])")"
  /tmp/pip-audit/bin/pip-audit --progress-spinner off --path "${site}" "$@"
' sh "${ignore_args[@]}"

echo "npm audit against src/frontend/package-lock.json"
(cd "${PROJECT_ROOT}/src/frontend" && npm audit --audit-level=low)
