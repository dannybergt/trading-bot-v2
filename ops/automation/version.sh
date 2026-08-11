#!/usr/bin/env bash
# Versionsstempel fuer die gebauten Images. Wird von build.sh gesourct.
#
# Warum das ein eigenes Skript ist: der Stempel ist eine *Aussage ueber das
# Artefakt* ("dieses Image ist Commit X"). Bis 2026-08-11 war sie unwahr,
# sobald der Arbeitsbaum vom Commit abwich — gebaut wird der Baum, gestempelt
# wurde HEAD. In den Verifikationslaeufen vom 2026-08-05, -06 und -07 stand
# deshalb der Commit von `main` im Abschlussbanner, obwohl ein ungetesteter
# Arbeitsbaum geprueft wurde. Hier getrennt, damit die Logik ohne Docker-Build
# pruefbar ist (tests/test_build_version_stamp.py).
#
# Setzt: APP_VERSION, GIT_SHA. Beide sind per Environment ueberschreibbar
# (die CI setzt sie nicht, dort ist der Checkout sauber).

VERSION_SH_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# Abweichung vom Commit: geaenderte *und* unverfolgte Dateien zaehlen, denn
# beide landen im Build-Kontext. Von git ignorierte Dateien listet
# `status --porcelain` nicht — Artefakt- und Laufzeitverzeichnisse machen den
# Stempel also nicht faelschlich schmutzig.
VERSION_SH_DIRTY=""
if [[ -n "$(git -C "${VERSION_SH_ROOT}" status --porcelain 2>/dev/null)" ]]; then
  VERSION_SH_DIRTY="-dirty"
fi

GIT_SHA="${GIT_SHA:-$(git -C "${VERSION_SH_ROOT}" rev-parse --short=12 HEAD 2>/dev/null || echo unknown)${VERSION_SH_DIRTY}}"
APP_VERSION="${APP_VERSION:-$(git -C "${VERSION_SH_ROOT}" describe --tags --always 2>/dev/null || echo dev)${VERSION_SH_DIRTY}}"
BUILD_TIME="${BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
