#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_IMAGE="${BACKEND_IMAGE:-trading-bot-v2-backend:local}"

load_env_file() {
  local candidate="$1"
  if [[ ! -f "${candidate}" ]]; then
    return 0
  fi

  set -a
  # shellcheck disable=SC1090
  source "${candidate}"
  set +a
}

load_env_file "${ENV_FILE:-${PROJECT_ROOT}/.env}"
load_env_file "${ENV_LOCAL_FILE:-${PROJECT_ROOT}/.env.local}"

if [[ "${GENERATE_TEST_VAPID:-0}" == "1" ]]; then
  docker run --rm -i "${BACKEND_IMAGE}" python - <<'PY'
import base64
import os

from py_vapid import Vapid

from app.push_service import PushService


def encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


vapid = Vapid()
vapid.generate_keys()
private_numbers = vapid.private_key.private_numbers()
public_numbers = vapid.public_key.public_numbers()
os.environ["VAPID_PRIVATE_KEY"] = encode_base64url(
    int(private_numbers.private_value).to_bytes(32, "big")
)
os.environ["VAPID_PUBLIC_KEY"] = encode_base64url(
    b"\x04"
    + int(public_numbers.x).to_bytes(32, "big")
    + int(public_numbers.y).to_bytes(32, "big")
)
os.environ["VAPID_CLAIMS_SUB"] = "mailto:smoke@example.com"

PushService.validate_configuration(require_config=True)
print("push config smoke ok: generated disposable VAPID pair validates")
PY
  exit 0
fi

missing=()
for key in VAPID_PUBLIC_KEY VAPID_PRIVATE_KEY VAPID_CLAIMS_SUB; do
  if [[ -z "${!key:-}" ]]; then
    missing+=("${key}")
  fi
done

if (( ${#missing[@]} )); then
  printf 'Missing required push config for smoke: %s\n' "${missing[*]}" >&2
  printf 'Set VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY and VAPID_CLAIMS_SUB in .env.local or the environment.\n' >&2
  printf 'For a parser-only dry run, use GENERATE_TEST_VAPID=1.\n' >&2
  exit 1
fi

docker run --rm -i \
  --env VAPID_PUBLIC_KEY \
  --env VAPID_PRIVATE_KEY \
  --env VAPID_CLAIMS_SUB \
  --env REQUIRE_VAPID_SECRETS=true \
  "${BACKEND_IMAGE}" \
  python - <<'PY'
from app.push_service import PushService

PushService.validate_configuration(require_config=True)
print("push config smoke ok: configured VAPID pair validates")
PY
