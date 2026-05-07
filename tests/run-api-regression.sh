#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${RUN_ID:-$(date +%Y%m%d%H%M%S)-$$}"
TEST_ROOT="${TEST_ROOT:-/tmp/trading-bot-v2-api-regression-${RUN_ID}}"
NETWORK_NAME="${NETWORK_NAME:-trading-bot-v2-api-regression-${RUN_ID}}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-trading-bot-v2-api-postgres-${RUN_ID}}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-trading-bot-v2-api-backend-${RUN_ID}}"

BACKEND_IMAGE="${BACKEND_IMAGE:-trading-bot-v2-backend:local}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:17-alpine}"
POSTGRES_DB="${POSTGRES_DB:-trading_bot_v2_regression}"
POSTGRES_USER="${POSTGRES_USER:-trading}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-trading-change-me}"
BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-5}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-adminpass123}"
JWT_SECRET="${JWT_SECRET:-12345678901234567890123456789012}"
APP_ENCRYPTION_KEY="${APP_ENCRYPTION_KEY:-abcdefghijklmnopqrstuvwx12345678}"

DATA_DIR="${TEST_ROOT}/data"
BACKUP_DIR="${TEST_ROOT}/backups"
LOG_DIR="${TEST_ROOT}/logs"
POSTGRES_DATA_DIR="${TEST_ROOT}/postgres"
POSTGRES_LOG="${LOG_DIR}/postgres.log"
BACKEND_LOG="${LOG_DIR}/backend.log"

cleanup() {
  set +e
  docker rm -f "${BACKEND_CONTAINER}" "${POSTGRES_CONTAINER}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK_NAME}" >/dev/null 2>&1 || true
}

wait_for_postgres() {
  local attempts=0
  until docker run --rm --network "${NETWORK_NAME}" "${POSTGRES_IMAGE}" \
    pg_isready -h "${POSTGRES_CONTAINER}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if (( attempts >= 30 )); then
      echo "PostgreSQL did not become ready in time" >&2
      docker logs "${POSTGRES_CONTAINER}" >"${POSTGRES_LOG}" 2>&1 || true
      cat "${POSTGRES_LOG}" >&2 || true
      return 1
    fi
    sleep 1
  done
}

wait_for_backend() {
  local attempts=0
  until docker run --rm -i --network "${NETWORK_NAME}" "${BACKEND_IMAGE}" python - <<'PY' >/dev/null 2>&1
import requests

response = requests.get("http://backend:8000/api/health", timeout=5)
response.raise_for_status()
payload = response.json()
assert payload["status"] == "healthy"
PY
  do
    attempts=$((attempts + 1))
    if (( attempts >= 30 )); then
      echo "Backend did not become ready in time" >&2
      docker logs "${BACKEND_CONTAINER}" >"${BACKEND_LOG}" 2>&1 || true
      cat "${BACKEND_LOG}" >&2 || true
      return 1
    fi
    sleep 1
  done
}

assert_scheduled_backups() {
  sleep $((BACKUP_INTERVAL_SECONDS + 2))

  local scheduled_count
  scheduled_count=$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'backup-*-scheduled.json' | wc -l | tr -d ' ')
  if [[ "${scheduled_count}" == "0" ]]; then
    echo "Expected at least one scheduled backup in ${BACKUP_DIR}" >&2
    docker logs "${BACKEND_CONTAINER}" >"${BACKEND_LOG}" 2>&1 || true
    cat "${BACKEND_LOG}" >&2 || true
    return 1
  fi

  docker logs "${BACKEND_CONTAINER}" >"${BACKEND_LOG}" 2>&1 || true
  if grep -E "Scheduled backup failed|Task exception was never retrieved" "${BACKEND_LOG}" >/dev/null 2>&1; then
    echo "Unexpected backup scheduler failure detected" >&2
    cat "${BACKEND_LOG}" >&2
    return 1
  fi
}

trap cleanup EXIT

mkdir -p "${DATA_DIR}" "${BACKUP_DIR}" "${LOG_DIR}" "${POSTGRES_DATA_DIR}"
chmod 0777 "${DATA_DIR}" "${BACKUP_DIR}" "${LOG_DIR}"

echo "Regression artifacts: ${TEST_ROOT}"

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  echo "Building current local images"
  bash "${PROJECT_ROOT}/ops/automation/build.sh"
fi

echo "Creating isolated Docker network ${NETWORK_NAME}"
docker network create "${NETWORK_NAME}" >/dev/null

echo "Starting isolated PostgreSQL container"
docker run -d \
  --name "${POSTGRES_CONTAINER}" \
  --network "${NETWORK_NAME}" \
  -e POSTGRES_DB="${POSTGRES_DB}" \
  -e POSTGRES_USER="${POSTGRES_USER}" \
  -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  -v "${POSTGRES_DATA_DIR}:/var/lib/postgresql/data" \
  "${POSTGRES_IMAGE}" >/dev/null

wait_for_postgres

echo "Starting isolated backend container"
docker run -d \
  --name "${BACKEND_CONTAINER}" \
  --network "${NETWORK_NAME}" \
  --network-alias backend \
  -e DATA_DIR=/app/data \
  -e BACKUP_DIR=/app/backups \
  -e DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_CONTAINER}:5432/${POSTGRES_DB}" \
  -e JWT_SECRET="${JWT_SECRET}" \
  -e APP_ENCRYPTION_KEY="${APP_ENCRYPTION_KEY}" \
  -e INITIAL_ADMIN_EMAIL="${ADMIN_EMAIL}" \
  -e INITIAL_ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
  -e INITIAL_ADMIN_MFA_ENABLED=false \
  -e ALLOWED_ORIGINS="http://127.0.0.1:18094,http://localhost:18094" \
  -e BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS}" \
  -e ENABLE_INSECURE_DEBUG_RESET_TOKENS=true \
  -v "${DATA_DIR}:/app/data" \
  -v "${BACKUP_DIR}:/app/backups" \
  "${BACKEND_IMAGE}" >/dev/null

wait_for_backend

echo "Running API regression probe"
docker run --rm -i --network "${NETWORK_NAME}" "${BACKEND_IMAGE}" python - <<PY
import io
import json
import requests

base = "http://backend:8000"
email = "${ADMIN_EMAIL}"
password = "${ADMIN_PASSWORD}"

health = requests.get(f"{base}/api/health", timeout=30)
health.raise_for_status()
assert health.json()["status"] == "healthy"
print("health ok")

login = requests.post(
    f"{base}/api/auth/login",
    json={"email": email, "password": password},
    timeout=30,
)
login.raise_for_status()
login_payload = login.json()
headers = {"Authorization": f"Bearer {login_payload['access_token']}"}
assert login_payload["mfa_required"] is False
print("bootstrap admin login ok")

me = requests.get(f"{base}/api/auth/me", headers=headers, timeout=30)
me.raise_for_status()
me_payload = me.json()
assert me_payload["email"] == email
assert me_payload["is_admin"] is True
assert me_payload["mfa_enabled"] is False
print("bootstrap admin profile ok")

push_config = requests.get(f"{base}/api/auth/push/config", timeout=30)
push_config.raise_for_status()
push_config_payload = push_config.json()
assert push_config_payload["configured"] is False
assert push_config_payload["publicKey"] is None
print("push config unavailable ok")

password_reset_request = requests.post(
    f"{base}/api/auth/password-reset/request",
    json={"email": email},
    timeout=30,
)
password_reset_request.raise_for_status()
reset_request_payload = password_reset_request.json()
reset_token = reset_request_payload.get("debug_reset_token")
assert reset_token
assert reset_request_payload["message"].startswith("If the email exists")
print("password reset request ok")

password_reset_confirm = requests.post(
    f"{base}/api/auth/password-reset/confirm",
    json={"token": reset_token, "new_password": "new-adminpass123"},
    timeout=30,
)
password_reset_confirm.raise_for_status()
assert password_reset_confirm.json()["message"] == "Password has been reset successfully"
print("password reset confirm ok")

login_after_reset = requests.post(
    f"{base}/api/auth/login",
    json={"email": email, "password": "new-adminpass123"},
    timeout=30,
)
login_after_reset.raise_for_status()
login_after_reset_payload = login_after_reset.json()
headers = {"Authorization": f"Bearer {login_after_reset_payload['access_token']}"}
assert login_after_reset_payload["mfa_required"] is False
print("login after reset ok")

stock_analysis = requests.get(
    f"{base}/api/stock/AAPL",
    headers=headers,
    timeout=30,
)
stock_analysis.raise_for_status()
stock_payload = stock_analysis.json()
assert stock_payload["assetClass"] == "stock"
assert stock_payload["info"]["assetClass"] == "stock"
assert stock_payload["type"] == "STOCK"
print("stock asset metadata ok")

crypto_analysis = requests.get(
    f"{base}/api/stock/BTC/USD",
    headers=headers,
    timeout=30,
)
crypto_analysis.raise_for_status()
crypto_payload = crypto_analysis.json()
assert crypto_payload["assetClass"] == "crypto"
assert crypto_payload["info"]["assetClass"] == "crypto"
assert crypto_payload["isCrypto"] is True
assert crypto_payload["provider"]["source"] == "Alpha Vantage"
assert crypto_payload["provider"]["status"] in {"live", "partial", "unavailable"}
print("crypto asset metadata ok")

crypto_research = requests.get(
    f"{base}/api/research/BTC/USD",
    headers=headers,
    timeout=30,
)
crypto_research.raise_for_status()
crypto_research_payload = crypto_research.json()
assert crypto_research_payload["assetClass"] == "crypto"
assert crypto_research_payload["provider"]["source"] == "Alpha Vantage"
assert crypto_research_payload["providerContext"]["source"] == "Alpha Vantage"
assert crypto_research_payload["providerContext"]["status"] in {"live", "partial", "unavailable"}
assert "quote" in crypto_research_payload
assert "news" in crypto_research_payload
print("crypto research context ok")

search_crypto = requests.get(
    f"{base}/api/search/BTC/USD",
    headers=headers,
    timeout=30,
)
search_crypto.raise_for_status()
search_payload = search_crypto.json()
assert isinstance(search_payload, list) and search_payload
assert search_payload[0]["assetClass"] == "crypto"
assert search_payload[0]["type"] == "CRYPTO"
print("search asset metadata ok")

scanner = requests.get(f"{base}/api/scanner", headers=headers, timeout=30)
scanner.raise_for_status()
scanner_payload = scanner.json()
assert isinstance(scanner_payload, list) and scanner_payload
assert scanner_payload[0]["assetClass"] == "stock"
assert "type" in scanner_payload[0]
print("scanner asset metadata ok")

create_watchlist = requests.post(
    f"{base}/api/watchlists",
    headers=headers,
    json={"name": "Macro Radar"},
    timeout=30,
)
create_watchlist.raise_for_status()
watchlist_payload = create_watchlist.json()
watchlist_id = watchlist_payload["id"]
print("watchlist create ok")

watchlist_add_item = requests.post(
    f"{base}/api/watchlists/{watchlist_id}/items",
    headers=headers,
    json={"symbol": "BTC/USD", "name": "Bitcoin", "tags": ["Crypto", "Momentum", "crypto"]},
    timeout=30,
)
watchlist_add_item.raise_for_status()
watchlist_add_payload = watchlist_add_item.json()
watchlist_item = next(item for item in watchlist_add_payload["items"] if item["symbol"] == "BTC/USD")
assert watchlist_item["assetClass"] == "crypto"
assert watchlist_item["tags"] == ["crypto", "momentum"]
print("watchlist add tagged item ok")

watchlist_add_etf = requests.post(
    f"{base}/api/watchlists/{watchlist_id}/items",
    headers=headers,
    json={"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "tags": ["ETF", "Core"]},
    timeout=30,
)
watchlist_add_etf.raise_for_status()
watchlist_add_etf_payload = watchlist_add_etf.json()
watchlist_etf_item = next(item for item in watchlist_add_etf_payload["items"] if item["symbol"] == "VOO")
assert watchlist_etf_item["assetClass"] == "etf"
assert watchlist_etf_item["assetLabel"] == "ETF"
assert watchlist_etf_item["tags"] == ["core", "etf"]
print("watchlist add etf item ok")

watchlist_update_item = requests.put(
    f"{base}/api/watchlists/{watchlist_id}/items/BTC/USD",
    headers=headers,
    json={"tags": ["swing", "priority"], "name": "Bitcoin Core"},
    timeout=30,
)
watchlist_update_item.raise_for_status()
watchlist_update_payload = watchlist_update_item.json()
updated_item = next(item for item in watchlist_update_payload["items"] if item["symbol"] == "BTC/USD")
assert updated_item["name"] == "Bitcoin Core"
assert updated_item["tags"] == ["priority", "swing"]
print("watchlist update tagged item ok")

watchlists = requests.get(f"{base}/api/watchlists", headers=headers, timeout=30)
watchlists.raise_for_status()
watchlists_payload = watchlists.json()
watchlist_from_list = next(item for item in watchlists_payload if item["id"] == watchlist_id)
listed_item = next(item for item in watchlist_from_list["items"] if item["symbol"] == "BTC/USD")
listed_etf_item = next(item for item in watchlist_from_list["items"] if item["symbol"] == "VOO")
assert listed_item["assetClass"] == "crypto"
assert listed_item["tags"] == ["priority", "swing"]
assert listed_etf_item["assetClass"] == "etf"
assert listed_etf_item["tags"] == ["core", "etf"]
print("watchlist list tags ok")

watchlist_news = requests.get(
    f"{base}/api/watchlists/{watchlist_id}/news",
    headers=headers,
    params={"limit_total": 10, "limit_per_symbol": 3},
    timeout=30,
)
watchlist_news.raise_for_status()
watchlist_news_payload = watchlist_news.json()
assert watchlist_news_payload["watchlist"]["id"] == watchlist_id
assert watchlist_news_payload["summary"]["trackedSymbols"] == 2
tracked_crypto = next(item for item in watchlist_news_payload["trackedAssets"] if item["symbol"] == "BTC/USD")
tracked_etf = next(item for item in watchlist_news_payload["trackedAssets"] if item["symbol"] == "VOO")
assert tracked_crypto["tags"] == ["priority", "swing"]
assert tracked_crypto["assetClass"] == "crypto"
assert tracked_etf["assetClass"] == "etf"
assert tracked_etf["tags"] == ["core", "etf"]
assert tracked_crypto["provider"]["source"] == "Alpha Vantage"
assert tracked_crypto["provider"]["status"] in {"live", "partial", "unavailable"}
assert tracked_etf["provider"]["source"] == "Alpha Vantage"
assert tracked_etf["provider"]["status"] in {"live", "partial", "unavailable"}
print("watchlist news binding ok")

etf_research = requests.get(
    f"{base}/api/research/VOO",
    headers=headers,
    timeout=30,
)
etf_research.raise_for_status()
etf_research_payload = etf_research.json()
assert etf_research_payload["assetClass"] == "etf"
assert etf_research_payload["provider"]["source"] == "Alpha Vantage"
assert etf_research_payload["providerContext"]["source"] == "Alpha Vantage"
assert etf_research_payload["providerContext"]["status"] in {"live", "partial", "unavailable"}
assert "research" in etf_research_payload
assert "fundamentals" in etf_research_payload
print("etf research context ok")

alert_settings = requests.get(
    f"{base}/api/watchlists/{watchlist_id}/alert-settings",
    headers=headers,
    timeout=30,
)
alert_settings.raise_for_status()
alert_settings_payload = alert_settings.json()
assert alert_settings_payload["enabled"] is True
assert alert_settings_payload["toastEnabled"] is True
assert alert_settings_payload["pushEnabled"] is False
assert alert_settings_payload["minPriority"] == "high"
assert alert_settings_payload["minScore"] == 70

alert_settings_update = requests.put(
    f"{base}/api/watchlists/{watchlist_id}/alert-settings",
    headers=headers,
    json={
        "enabled": True,
        "toastEnabled": True,
        "pushEnabled": True,
        "minPriority": "low",
        "minScore": 0,
    },
    timeout=30,
)
alert_settings_update.raise_for_status()
alert_settings_update_payload = alert_settings_update.json()
assert alert_settings_update_payload["pushEnabled"] is True
assert alert_settings_update_payload["minPriority"] == "low"
assert alert_settings_update_payload["minScore"] == 0
print("watchlist alert settings ok")

watchlist_alerts = requests.get(
    f"{base}/api/watchlists/{watchlist_id}/alerts",
    headers=headers,
    params={"limit": 5, "news_limit": 2},
    timeout=60,
)
watchlist_alerts.raise_for_status()
watchlist_alerts_payload = watchlist_alerts.json()
assert watchlist_alerts_payload["watchlist"]["id"] == watchlist_id
assert watchlist_alerts_payload["summary"]["trackedSymbols"] == 2
assert watchlist_alerts_payload["summary"]["alertItems"] == 2
assert "providerLive" in watchlist_alerts_payload["summary"]
assert "providerResearch" in watchlist_alerts_payload["summary"]
assert "providerMovers" in watchlist_alerts_payload["summary"]
assert watchlist_alerts_payload["alertSettings"]["pushEnabled"] is True
assert watchlist_alerts_payload["notificationPlan"]["pushCount"] == 2
assert watchlist_alerts_payload["summary"]["popupEligible"] == 2
assert watchlist_alerts_payload["summary"]["pushEligible"] == 2
tracked_alert_crypto = next(item for item in watchlist_alerts_payload["trackedAssets"] if item["symbol"] == "BTC/USD")
tracked_alert_etf = next(item for item in watchlist_alerts_payload["trackedAssets"] if item["symbol"] == "VOO")
assert tracked_alert_crypto["tags"] == ["priority", "swing"]
assert tracked_alert_etf["assetClass"] == "etf"
assert tracked_alert_crypto["provider"]["source"] == "Alpha Vantage"
assert tracked_alert_etf["provider"]["source"] == "Alpha Vantage"
crypto_alert_item = next(item for item in watchlist_alerts_payload["items"] if item["symbol"] == "BTC/USD")
etf_alert_item = next(item for item in watchlist_alerts_payload["items"] if item["symbol"] == "VOO")
assert crypto_alert_item["assetClass"] == "crypto"
assert crypto_alert_item["tags"] == ["priority", "swing"]
assert etf_alert_item["assetClass"] == "etf"
assert etf_alert_item["tags"] == ["core", "etf"]
assert crypto_alert_item["provider"]["source"] == "Alpha Vantage"
assert etf_alert_item["provider"]["source"] == "Alpha Vantage"
assert crypto_alert_item["providerContext"]["source"] == "Alpha Vantage"
assert etf_alert_item["providerContext"]["source"] == "Alpha Vantage"
for alert_item in (crypto_alert_item, etf_alert_item):
    assert alert_item["priorityLabel"] in {"low", "medium", "high"}
    assert alert_item["alertType"] in {"signal", "news", "watchlist", "watch"}
    assert alert_item["signal"]["direction"] in {"UP", "DOWN", "HOLD"}
    assert alert_item["news"]["aggregateLabel"] in {"bullish", "bearish", "neutral"}
    assert alert_item["providerContext"]["status"] in {"live", "partial", "unavailable"}
    assert "researchAvailable" in alert_item["providerContext"]
    assert alert_item["notification"]["popupEligible"] is True
    assert alert_item["notification"]["pushEligible"] is True
print("watchlist alerts priority feed ok")

watchlist_remove_etf_item = requests.delete(
    f"{base}/api/watchlists/{watchlist_id}/items/VOO",
    headers=headers,
    timeout=30,
)
watchlist_remove_etf_item.raise_for_status()
remaining_items_after_etf_delete = watchlist_remove_etf_item.json()["items"]
assert len(remaining_items_after_etf_delete) == 1
print("watchlist etf delete ok")

watchlist_remove_item = requests.delete(
    f"{base}/api/watchlists/{watchlist_id}/items/BTC/USD",
    headers=headers,
    timeout=30,
)
watchlist_remove_item.raise_for_status()
assert watchlist_remove_item.json()["items"] == []
print("watchlist crypto delete ok")

create_user = requests.post(
    f"{base}/api/auth/admin/users",
    headers=headers,
    json={"email": "member@example.com", "password": "memberpass123", "is_admin": False},
    timeout=30,
)
create_user.raise_for_status()
member_payload = create_user.json()
member_id = member_payload["id"]
assert member_payload["email"] == "member@example.com"
assert member_payload["is_admin"] is False
print("admin create user ok")

admin_password_reset = requests.put(
    f"{base}/api/auth/admin/users/{member_id}/password",
    headers=headers,
    json={"new_password": "memberpass456", "reset_mfa": True},
    timeout=30,
)
admin_password_reset.raise_for_status()
admin_password_reset_payload = admin_password_reset.json()
assert admin_password_reset_payload["id"] == member_id
assert admin_password_reset_payload["mfa_enabled"] is False
print("admin password reset ok")

member_login = requests.post(
    f"{base}/api/auth/login",
    json={"email": "member@example.com", "password": "memberpass456"},
    timeout=30,
)
member_login.raise_for_status()
assert member_login.json()["mfa_required"] is False
print("member login after admin reset ok")

backup_list = requests.get(f"{base}/api/admin/backups", headers=headers, timeout=30)
backup_list.raise_for_status()
assert isinstance(backup_list.json()["items"], list)
print("backup list ok")

backup_create = requests.post(
    f"{base}/api/admin/backups",
    headers=headers,
    params={"label": "manual-check"},
    timeout=30,
)
backup_create.raise_for_status()
backup_filename = backup_create.json()["filename"]
assert backup_filename.endswith("-manual-check.json")
print("manual backup ok")

download = requests.get(f"{base}/api/admin/backups/{backup_filename}", headers=headers, timeout=30)
download.raise_for_status()
backup_payload = download.json()
assert backup_payload["schema_version"] == 1
assert any(
    setting["watchlist_id"] == watchlist_id and setting["push_enabled"] is True
    for setting in backup_payload["data"].get("watchlist_alert_settings", [])
)
assert isinstance(backup_payload["data"].get("watchlist_alert_deliveries"), list)
print("backup download ok")

export_state = requests.get(f"{base}/api/admin/export", headers=headers, timeout=30)
export_state.raise_for_status()
export_payload = export_state.json()
assert export_payload["schema_version"] == 1
exported_user_emails = {user["email"] for user in export_payload["data"]["users"]}
assert exported_user_emails == {email, "member@example.com"}
assert any(
    setting["watchlist_id"] == watchlist_id and setting["min_priority"] == "low"
    for setting in export_payload["data"].get("watchlist_alert_settings", [])
)
assert isinstance(export_payload["data"].get("watchlist_alert_deliveries"), list)
print("export ok")

platform_import = requests.post(
    f"{base}/api/admin/import",
    headers=headers,
    files={"file": ("snapshot.json", io.BytesIO(json.dumps(export_payload).encode("utf-8")), "application/json")},
    timeout=30,
)
platform_import.raise_for_status()
assert platform_import.json()["status"] == "imported"
print("platform import ok")

backup_import = requests.post(
    f"{base}/api/admin/backups/import",
    headers=headers,
    files={"file": ("backup.json", io.BytesIO(download.content), "application/json")},
    timeout=30,
)
backup_import.raise_for_status()
assert backup_import.json()["status"] == "restored"
print("backup import ok")
PY

assert_scheduled_backups

echo "API regression passed"
