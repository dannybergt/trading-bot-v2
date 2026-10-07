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
  # braces: every release is affected, no fix exists (2026-10-06). Pulled
  # only by tailwindcss 3 (devDependency, via chokidar/micromatch/fast-glob)
  # at build time; the patterns it expands are the `content` globs in our own
  # tailwind.config — no outside input, nothing of it ships in the nginx
  # image. Ends with tailwindcss 4 (ROADMAP, ADR 2026-10-06).
  # Format ID:YYYY-MM-DD. After that day the audit fails again, so the
  # exception is re-decided instead of living on (security-reviewer PR #60).
  GHSA-vfj7-8cjw-p6xm:2026-10-20
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
if "vulnerabilities" not in report:
    # Registry/network failure: never read as "nothing found".
    print("npm audit returned no report:", report.get("error", report))
    sys.exit(2)
found = {}
for name, vuln in report["vulnerabilities"].items():
    for via in vuln["via"]:
        if isinstance(via, dict):
            found.setdefault(via["url"].rsplit("/", 1)[-1], set()).add(name)
for advisory in sorted(ignored - set(found)):
    print(f"note: {advisory} is no longer reported, remove it from NPM_IGNORED")
open_ids = sorted(set(found) - ignored)
for advisory in open_ids:
    print(f"OPEN {advisory} in {', '.join(sorted(found[advisory]))}")
print(f"npm audit: {len(found)} advisories, {len(open_ids)} open, {len(set(found) & ignored)} ignored")
sys.exit(1 if open_ids else 0)
PY
