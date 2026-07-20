#!/usr/bin/env bash
#
# Pre-merge verification runbook for a feature branch.
#
# Runs the full mandated gate chain on a host that HAS Docker + network (and,
# for the UI gate, Chrome) — NOT on a sandbox without network and NOT on the
# BC-KI01 deploy node. nexainer/watchtower deploy `main`/`latest` UNGATED onto
# the production Postgres volume, so every gate here must be green BEFORE a
# merge to `main`; once it is published there is no controlled rollback point.
#
# Gate chain (aborts on the first failure):
#   1. build.sh                       — build :local backend + frontend images
#   2. test.sh                        — unit + syntax (incl. the alembic drift gate)
#   3. run-api-regression.sh          — API contract regression
#   4. run-ui-regression.sh           — UI regression (needs Chrome)
#   5. run-upgrade-rehearsal.sh       — migration + backup/restore on a real
#                                       Postgres volume, using the freshly built
#                                       :local images (pre-publish rehearsal)
#
# Opt-outs (logged, never silent):
#   SKIP_UI=1         skip the UI regression (e.g. host without Chrome)
#   SKIP_REHEARSAL=1  skip the upgrade rehearsal (NOT recommended for
#                     persistence/migration changes)
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"

CURRENT_STEP="(none)"
trap 'echo; echo "❌ VERIFY FAILED at step: ${CURRENT_STEP}"; echo "   Fix the cause, do NOT merge to main."; exit 1' ERR

step() {
  CURRENT_STEP="$1"
  echo
  echo "======================================================================"
  echo "▶ ${CURRENT_STEP}"
  echo "======================================================================"
}

branch="$(git -C "${PROJECT_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
commit="$(git -C "${PROJECT_ROOT}" rev-parse --short HEAD 2>/dev/null || echo '?')"
echo "Verifying branch '${branch}' @ ${commit}"

# --- Port preflight (multi-agent discipline: warn, NEVER kill) ---------------
step "Port preflight (18090/18094 devstack, 181xx regression/rehearsal)"
occupied="$(docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -E '180[89]|181[0-9]{2}' || true)"
if [[ -n "${occupied}" ]]; then
  echo "⚠ Ports in use by other stacks — do NOT kill them. Re-run with shifted"
  echo "  ports if a gate fails on a bind conflict (BACKEND_PORT/FRONTEND_PORT,"
  echo "  PRIMARY_*/RESTORE_* — see state/current-focus.md):"
  echo "${occupied}"
else
  echo "Relevant ports free."
fi

# --- Gate 1: build -----------------------------------------------------------
step "1/5 build.sh (build :local images)"
bash ops/automation/build.sh

# --- Gate 2: unit + syntax ---------------------------------------------------
step "2/5 test.sh (unit + syntax + alembic drift gate)"
bash ops/automation/test.sh

# --- Gate 3: API regression --------------------------------------------------
step "3/5 run-api-regression.sh"
SKIP_BUILD=1 bash tests/run-api-regression.sh

# --- Gate 4: UI regression ---------------------------------------------------
if [[ "${SKIP_UI:-0}" == "1" ]]; then
  echo
  echo "⏭ 4/5 run-ui-regression.sh SKIPPED (SKIP_UI=1) — UI gate NOT verified."
else
  step "4/5 run-ui-regression.sh (needs Chrome)"
  SKIP_BUILD=1 bash tests/run-ui-regression.sh
fi

# --- Gate 5: migration rehearsal against a real Postgres volume --------------
if [[ "${SKIP_REHEARSAL:-0}" == "1" ]]; then
  echo
  echo "⏭ 5/5 run-upgrade-rehearsal.sh SKIPPED (SKIP_REHEARSAL=1) — migration"
  echo "   NOT rehearsed. Not recommended when persistence/schema changed."
else
  step "5/5 run-upgrade-rehearsal.sh (pre-publish, :local images)"
  # SKIP_PULL=1: the images were just built locally and are not on a registry.
  IMAGE_TAG=local \
    SKIP_PULL=1 \
    BACKEND_IMAGE_REF=trading-bot-v2-backend:local \
    FRONTEND_IMAGE_REF=trading-bot-v2-frontend:local \
    bash tests/run-upgrade-rehearsal.sh
fi

trap - ERR
echo
echo "======================================================================"
echo "✅ ALL GATES GREEN for '${branch}' @ ${commit}"
[[ "${SKIP_UI:-0}" == "1" ]] && echo "   (UI regression was skipped)"
[[ "${SKIP_REHEARSAL:-0}" == "1" ]] && echo "   (upgrade rehearsal was skipped)"
echo "Safe to merge to main (--ff-only) and push → publish.yml → nexainer deploy."
echo "======================================================================"
