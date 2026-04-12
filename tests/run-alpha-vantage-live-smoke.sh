#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

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
from typing import Any

from app.alpha_vantage_service import AlphaVantageService
from app.services import MarketDataService


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


def require_live_snapshot(service: AlphaVantageService, symbol: str, asset_class: str) -> dict[str, Any]:
    snapshot = service.get_provider_snapshot(symbol, asset_class)
    compact = compact_snapshot(snapshot)
    if not snapshot:
        raise SystemExit(f"{symbol} returned no Alpha Vantage provider snapshot")
    quote = snapshot.get("quote") or {}
    history = quote.get("history") or []
    if (
        snapshot.get("source") != "Alpha Vantage"
        or snapshot.get("status") != "live"
        or quote.get("price") is None
        or not history
    ):
        raise SystemExit(f"{symbol} did not return a live Alpha Vantage snapshot: {json.dumps(compact, sort_keys=True)}")
    return compact


def require_market_data_provider(
    market_data: MarketDataService,
    symbol: str,
    asset_class: str,
) -> dict[str, Any]:
    payload = market_data.get_stock_data(
        symbol,
        period="1mo",
        interval="1d",
        include_news=False,
        include_fundamentals=False,
    )
    provider = payload.get("provider") or {}
    frame = payload.get("data")
    rows = len(frame.index) if hasattr(frame, "index") else 0
    if provider.get("source") != "Alpha Vantage" or provider.get("status") != "live":
        raise SystemExit(
            f"{symbol} MarketDataService did not propagate a live Alpha Vantage provider: "
            f"{json.dumps(compact_snapshot(provider), sort_keys=True)}"
        )
    if payload.get("asset", {}).get("assetClass") != asset_class:
        raise SystemExit(f"{symbol} asset class mismatch: {payload.get('asset')}")
    if rows < 2:
        raise SystemExit(f"{symbol} returned too few market data rows: {rows}")
    return {
        "symbol": symbol,
        "providerStatus": provider.get("status"),
        "rows": rows,
        "lastUpdated": provider.get("lastUpdated"),
    }


service = AlphaVantageService()
if not service.is_configured():
    raise SystemExit("AlphaVantageService is not configured")

market_data = MarketDataService(alpha_vantage_service=service)
checks = []
for symbol, asset_class in (("VOO", "etf"), ("BTC/USD", "crypto")):
    checks.append({"symbol": symbol, "snapshot": require_live_snapshot(service, symbol, asset_class)})
    checks.append({"symbol": symbol, "marketData": require_market_data_provider(market_data, symbol, asset_class)})

print(json.dumps({"status": "ok", "checks": checks}, indent=2, sort_keys=True))
PY
