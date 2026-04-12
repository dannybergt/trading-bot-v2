#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"
OVERRIDE_VARS=()

capture_overrides() {
  local name backup_name
  for name in \
    ALPHA_VANTAGE_API_KEY \
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

if [[ -z "${ALPHA_VANTAGE_API_KEY:-}" ]]; then
  echo "ALPHA_VANTAGE_API_KEY is required for the Alpha Vantage live smoke test." >&2
  echo "Set it in the environment or in ${ENV_FILE}; the key value is never printed." >&2
  exit 2
fi

export ALPHA_VANTAGE_API_KEY

DOCKERHUB_NAMESPACE="${DOCKERHUB_NAMESPACE:-dbergt}"
BACKEND_IMAGE_NAME="${BACKEND_IMAGE_NAME:-trading-bot-backend}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BACKEND_IMAGE="${BACKEND_IMAGE:-docker.io/${DOCKERHUB_NAMESPACE}/${BACKEND_IMAGE_NAME}:${IMAGE_TAG}}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command: docker" >&2
  exit 1
fi

echo "Alpha Vantage live smoke image: ${BACKEND_IMAGE}"
echo "Checking live provider snapshots for VOO and BTC/USD"

docker run --rm -i \
  -e ALPHA_VANTAGE_API_KEY \
  "${BACKEND_IMAGE}" \
  python - <<'PY'
import json
import time
from typing import Any

from app.alpha_vantage_service import AlphaVantageService
from app.services import MarketDataService

REQUEST_PAUSE_SECONDS = 1.25


def compact_snapshot(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return payload
    quote = payload.get("quote") or {}
    research = payload.get("research") or {}
    return {
        "status": payload.get("status"),
        "source": payload.get("source"),
        "assetClass": payload.get("assetClass"),
        "reason": payload.get("reason"),
        "lastUpdated": payload.get("lastUpdated"),
        "price": quote.get("price"),
        "historyPoints": len(quote.get("history") or []),
        "topHoldings": len(research.get("topHoldings") or []),
        "topSectors": len(research.get("topSectors") or []),
    }


def pause_for_free_tier() -> None:
    time.sleep(REQUEST_PAUSE_SECONDS)


def require_history(service: AlphaVantageService, symbol: str, asset_class: str) -> dict[str, Any]:
    frame = service.get_history_df(symbol, asset_class, limit=30)
    if frame.empty or len(frame.index) < 2:
        raise SystemExit(f"{symbol} returned too little Alpha Vantage history")
    latest_close = frame.iloc[-1].get("Close")
    if latest_close is None:
        raise SystemExit(f"{symbol} Alpha Vantage history is missing latest close")
    return {
        "status": "live",
        "source": "Alpha Vantage",
        "assetClass": asset_class,
        "rows": len(frame.index),
        "latestClose": round(float(latest_close), 4),
        "lastUpdated": frame.index[-1].isoformat() + "Z",
    }


def require_etf_profile(service: AlphaVantageService, symbol: str) -> dict[str, Any]:
    payload = service._request(  # Reuses the same cache key get_provider_snapshot uses.
        f"alpha-profile:etf:{symbol}",
        15 * 60,
        function="ETF_PROFILE",
        symbol=symbol,
    )
    if not payload or payload.get("_warning"):
        raise SystemExit(
            f"{symbol} ETF_PROFILE did not return live Alpha Vantage data: "
            f"{json.dumps(payload, sort_keys=True)}"
        )
    return {
        "symbol": symbol,
        "status": "live",
        "source": "Alpha Vantage",
        "netAssetsPresent": payload.get("net_assets") not in (None, ""),
        "holdings": len(payload.get("holdings") or []),
        "sectors": len(payload.get("sectors") or []),
    }


service = AlphaVantageService()
if not service.is_configured():
    raise SystemExit("AlphaVantageService is not configured")

checks = [
    {"symbol": "VOO", "history": require_history(service, "VOO", "etf")},
]
pause_for_free_tier()
checks.append({"symbol": "VOO", "profile": require_etf_profile(service, "VOO")})
pause_for_free_tier()
checks.append({"symbol": "BTC/USD", "history": require_history(service, "BTC/USD", "crypto")})

market_data = MarketDataService(alpha_vantage_service=service)
for symbol, asset_class in (("VOO", "etf"), ("BTC/USD", "crypto")):
    profile = {"symbol": symbol, "assetClass": asset_class}
    snapshot = market_data.get_provider_snapshot(symbol, asset_profile=profile)
    history = market_data.get_provider_history_df(symbol, asset_profile=profile, limit=30)
    if not snapshot or snapshot.get("status") != "live" or snapshot.get("source") != "Alpha Vantage":
        raise SystemExit(
            f"{symbol} MarketDataService did not expose a live provider snapshot: "
            f"{json.dumps(compact_snapshot(snapshot), sort_keys=True)}"
        )
    if history.empty or len(history.index) < 2:
        raise SystemExit(f"{symbol} MarketDataService returned too little provider history")
    checks.append({"symbol": symbol, "marketDataSnapshot": compact_snapshot(snapshot)})

print(json.dumps({"status": "ok", "checks": checks}, indent=2, sort_keys=True))
PY
