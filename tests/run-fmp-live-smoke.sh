#!/usr/bin/env bash
# Live smoke for the FMP fundamentals adapter.
#
# Skips entirely (exit 2) if FMP_API_KEY is not configured. The key value is
# never echoed; only metadata about the responses is printed. Designed to be
# safe to run from CI runners that have FMP_API_KEY in their secret store.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"
OVERRIDE_VARS=()

capture_overrides() {
  local name backup_name
  for name in \
    FMP_API_KEY \
    DOCKERHUB_NAMESPACE \
    BACKEND_IMAGE_NAME \
    IMAGE_TAG \
    BACKEND_IMAGE; do
    if [[ -v "${name}" ]]; then
      OVERRIDE_VARS+=("${name}")
      backup_name="__OVERRIDE_${name}"
      printf -v "${backup_name}" '%s' "${!name}"
    fi
  done
}

restore_overrides() {
  local name backup_name
  for name in "${OVERRIDE_VARS[@]}"; do
    backup_name="__OVERRIDE_${name}"
    printf -v "${name}" '%s' "${!backup_name}"
    export "${name}"
    unset "${backup_name}"
  done
}

capture_overrides
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi
restore_overrides

if [[ -z "${FMP_API_KEY:-}" ]]; then
  echo "FMP_API_KEY is required for the FMP live smoke test." >&2
  echo "Set it in the environment or in ${ENV_FILE}; the key value is never printed." >&2
  exit 2
fi

export FMP_API_KEY

DOCKERHUB_NAMESPACE="${DOCKERHUB_NAMESPACE:-dbergt}"
BACKEND_IMAGE_NAME="${BACKEND_IMAGE_NAME:-trading-bot-backend}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BACKEND_IMAGE="${BACKEND_IMAGE:-docker.io/${DOCKERHUB_NAMESPACE}/${BACKEND_IMAGE_NAME}:${IMAGE_TAG}}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command: docker" >&2
  exit 1
fi

echo "FMP live smoke image: ${BACKEND_IMAGE}"
echo "Checking live profile + ratios + key-metrics + news for AAPL"

docker run --rm -i \
  -e FMP_API_KEY \
  "${BACKEND_IMAGE}" \
  python - <<'PY'
import json
from typing import Any

from app.fmp_service import FmpService

service = FmpService()
if not service.configured:
    raise SystemExit("FmpService is not configured (FMP_API_KEY missing inside container)")

profile = service.get_profile("AAPL")
if not profile or not profile.get("companyName"):
    raise SystemExit("AAPL profile did not return live FMP data")

key_metrics = service.get_key_metrics("AAPL")
if not key_metrics:
    raise SystemExit("AAPL key-metrics returned empty")

ratios = service.get_ratios("AAPL")
if not ratios:
    raise SystemExit("AAPL ratios returned empty")

news = service.get_news("AAPL", limit=3)
if not isinstance(news, list):
    raise SystemExit("AAPL news returned a non-list")

normalized = service.normalized_ticker_info("AAPL")
required = {"shortName", "sector", "marketCap"}
missing = required - normalized.keys()
if missing:
    raise SystemExit(f"normalized_ticker_info missing fields: {sorted(missing)}")

# ETF holdings sanity check on VOO; allowed to be empty on free tier so we
# only fail if the call itself errors.
holdings = service.get_etf_holdings("VOO")
if not isinstance(holdings, list):
    raise SystemExit("VOO ETF holdings returned a non-list")

print(json.dumps({
    "profile_name": profile.get("companyName"),
    "sector": profile.get("sector"),
    "marketCap_present": profile.get("mktCap") is not None,
    "key_metrics_present": bool(key_metrics),
    "ratios_present": bool(ratios),
    "news_items": len(news),
    "voo_holdings": len(holdings),
    "normalized_keys": sorted(normalized.keys()),
}, sort_keys=True))
PY
