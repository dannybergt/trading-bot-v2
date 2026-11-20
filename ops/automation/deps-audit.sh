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

# pip: empty since 2026-10-06:python-jose (and its ecdsa) replaced by PyJWT,
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

NPM_IGNORED=(
  # Format ID:YYYY-MM-DD. After that day the audit fails again, so the
  # exception is re-decided instead of living on (security-reviewer PR #60).
  # braces (GHSA-vfj7-8cjw-p6xm, until 2026-11-06) is no longer reported
  # (2026-11-20) and was removed.
  # glob GHSA-3g3m-2fjr-6pw4 and minimatch GHSA-g3hv-75wg-m249 (moderate,
  # 2026-11-20): pulled only by workbox-build 7.4.1 (vite-plugin-pwa,
  # devDependency) at build time; the patterns are the globPatterns of our own
  # vite config, no outside input, nothing of it ships in the nginx image
  # (dist/ holds only the generated sw.js). Fixed releases are majors
  # (glob 14, minimatch 11) that workbox-build does not accept. Way out: a
  # workbox-build release on the fixed majors. Next decision by 2026-12-04.
  GHSA-3g3m-2fjr-6pw4:2026-12-04
  GHSA-g3hv-75wg-m249:2026-12-04
)

echo "npm audit against src/frontend/package-lock.json"
npm_json="$(mktemp)"
trap 'rm -f "${npm_json}"' EXIT
# Exit code is non-zero whenever anything is found; the decision is made on
# the JSON below. The readable report is printed for the log.
(cd "${PROJECT_ROOT}/src/frontend" && npm audit --json > "${npm_json}") || true
(cd "${PROJECT_ROOT}/src/frontend" && npm audit --audit-level=low) || true
python3 - "${npm_json}" "${NPM_IGNORED[@]}" <<'PY'
import datetime
import json
import sys

try:
    report = json.load(open(sys.argv[1]))
except json.JSONDecodeError:
    # npm crashed without (valid) output: same as no report.
    print("npm audit returned no readable JSON")
    sys.exit(2)
if not isinstance(report, dict):
    # Valid JSON but not a report object ([] / null / a string): no report.
    print(f"npm audit returned JSON that is not a report object ({type(report).__name__})")
    sys.exit(2)
ignored = set()
expired = []
for entry in sys.argv[2:]:
    advisory, _, until = entry.partition(":")
    try:
        valid = datetime.date.fromisoformat(until) >= datetime.date.today()
    except ValueError:
        valid = False
    if not valid:
        expired.append(entry)
    ignored.add(advisory)
if expired:
    for entry in expired:
        print(f"EXPIRED or undated npm ignore: {entry} (decide again: fix, or a new date with reason)")
    sys.exit(1)
if "error" in report or not isinstance(report.get("vulnerabilities"), dict):
    # Registry/network failure or a shape npm 10 does not write: never read
    # as "nothing found".
    print("npm audit returned no report:", report.get("error", "no vulnerabilities object"))
    sys.exit(2)
vulnerabilities = report["vulnerabilities"]
found = {}
for name, vuln in vulnerabilities.items():
    via_list = vuln.get("via") if isinstance(vuln, dict) else None
    if not isinstance(via_list, list):
        print(f"npm audit: unexpected via for {name}")
        sys.exit(2)
    for via in via_list:
        if isinstance(via, dict):
            found.setdefault(via["url"].rsplit("/", 1)[-1], set()).add(name)
        elif via not in vulnerabilities:
            # A string via names another vulnerable package, which must have
            # its own entry; otherwise the report is incomplete.
            print(f"npm audit: {name} via {via} without own entry")
            sys.exit(2)
for advisory in sorted(ignored - set(found)):
    print(f"note: {advisory} is no longer reported, remove it from NPM_IGNORED")
open_ids = sorted(set(found) - ignored)
for advisory in open_ids:
    print(f"OPEN {advisory} in {', '.join(sorted(found[advisory]))}")
print(f"npm audit: {len(found)} advisories, {len(open_ids)} open, {len(set(found) & ignored)} ignored")
sys.exit(1 if open_ids else 0)
PY
