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

IGNORED=(
  # ecdsa: pulled by python-jose; no fixed release exists. The Minerva timing
  # attack needs ECDSA signing — JWTs here are HS256 only (auth.py) and jose
  # uses the cryptography backend.
  PYSEC-2026-1325
  # msgpack 1.0.3: pinned by alpaca-trade-api 3.2.0 (latest). Unpacker crash
  # after an error on untrusted input; only the Alpaca market-data stream
  # feeds it (TLS to Alpaca).
  PYSEC-2026-3625
  # urllib3 <2: pinned by alpaca-trade-api 3.2.0. Decompression-chain,
  # streaming-decompression and redirect-header advisories; every outbound
  # call goes to fixed provider hosts, and requests handles redirects itself
  # (strips Authorization across hosts). Ends with the move to alpaca-py.
  PYSEC-2026-1999
  PYSEC-2026-1998
  PYSEC-2026-1994
  PYSEC-2026-1996
  PYSEC-2026-141
)

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
