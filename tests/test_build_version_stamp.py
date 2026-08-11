"""Der Versionsstempel muss den gebauten Baum beschreiben, nicht HEAD.

Hintergrund: `build.sh` stempelte `git describe`/`rev-parse HEAD` in beide
Images. Gebaut wird aber der **Arbeitsbaum**. Weicht er vom Commit ab, behauptet
das Image einen Commit, der so nie gebaut wurde — in den Verifikationslaeufen
vom 2026-08-05, -06 und -07 stand deshalb der Commit von `main` im
Abschlussbanner, obwohl ein ungetesteter Arbeitsbaum geprueft wurde. Der Punkt
stand seit dem 2026-08-05 als offen im STATE.

Geprueft wird das **Verhalten**, nicht der Quelltext: `ops/automation/version.sh`
laeuft gegen ein vorgetaeuschtes `git`, dessen Antworten der Test bestimmt. Das
Testimage hat kein echtes `git`, und ein Docker-Build je Fall waere zu teuer —
der Stub stellt die Bedingung her, statt sie zu unterstellen.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_SH = REPO_ROOT / "ops" / "automation" / "version.sh"

FAKE_GIT = """#!/usr/bin/env bash
# Vorgetaeuschtes git. Die Antworten steuert der Test ueber Umgebungsvariablen.
for arg in "$@"; do
  case "$arg" in
    status)   printf '%s' "${FAKE_GIT_STATUS:-}"; [[ -n "${FAKE_GIT_STATUS:-}" ]] && echo; exit 0 ;;
    rev-parse) echo "${FAKE_GIT_SHA:-abcdef123456}"; exit 0 ;;
    describe) echo "${FAKE_GIT_DESCRIBE:-v1.2.3-4-gabcdef1}"; exit 0 ;;
  esac
done
exit 0
"""

FAKE_GIT_MISSING = """#!/usr/bin/env bash
exit 127
"""


class BuildVersionStampTests(unittest.TestCase):
    def _stamp(self, *, git_body=FAKE_GIT, env=None):
        """Sourct version.sh mit gestubbtem git und liefert (APP_VERSION, GIT_SHA)."""
        if not VERSION_SH.exists():
            self.skipTest(f"{VERSION_SH} nicht eingehaengt")
        with tempfile.TemporaryDirectory() as tmp:
            stub_dir = Path(tmp) / "bin"
            stub_dir.mkdir()
            stub = stub_dir / "git"
            stub.write_text(git_body)
            stub.chmod(0o755)

            run_env = {
                "PATH": f"{stub_dir}:{os.environ.get('PATH', '')}",
                "PROJECT_ROOT": str(REPO_ROOT),
                "HOME": tmp,
            }
            run_env.update(env or {})

            result = subprocess.run(
                ["bash", "-c", f'source "{VERSION_SH}"; printf "%s\\n%s\\n" "$APP_VERSION" "$GIT_SHA"'],
                capture_output=True,
                text=True,
                env=run_env,
                timeout=30,
            )
            self.assertEqual(
                result.returncode, 0, f"version.sh scheiterte: {result.stderr.strip()}"
            )
            lines = result.stdout.strip().splitlines()
            self.assertEqual(len(lines), 2, f"unerwartete Ausgabe: {result.stdout!r}")
            return lines[0], lines[1]

    def test_clean_tree_is_stamped_without_a_marker(self):
        version, sha = self._stamp(env={"FAKE_GIT_STATUS": ""})

        self.assertEqual(version, "v1.2.3-4-gabcdef1")
        self.assertEqual(sha, "abcdef123456")
        self.assertNotIn("dirty", version)
        self.assertNotIn("dirty", sha)

    def test_modified_tree_says_so_in_both_stamps(self):
        # Genau der Fall, der drei Verifikationslaeufe lang falsch protokolliert
        # wurde: gebaut wird der Baum, gestempelt wurde HEAD.
        version, sha = self._stamp(env={"FAKE_GIT_STATUS": " M src/backend/app/main.py"})

        self.assertTrue(
            version.endswith("-dirty"),
            f"APP_VERSION verschweigt die Abweichung vom Commit: {version}",
        )
        self.assertTrue(
            sha.endswith("-dirty"),
            f"GIT_SHA verschweigt die Abweichung vom Commit: {sha}",
        )

    def test_untracked_file_counts_as_a_deviation(self):
        # Unverfolgte Dateien landen im Build-Kontext und damit im Image.
        # Von git ignorierte Dateien listet `status --porcelain` nicht, das
        # Laufzeitverzeichnis macht den Stempel also nicht faelschlich schmutzig.
        version, sha = self._stamp(env={"FAKE_GIT_STATUS": "?? tests/neu.py"})

        self.assertTrue(version.endswith("-dirty"), version)
        self.assertTrue(sha.endswith("-dirty"), sha)

    def test_explicit_env_wins(self):
        # Die CI setzt den Stempel nicht, koennte es aber; eine gesetzte Vorgabe
        # darf nicht nachtraeglich mit einem Marker versehen werden.
        version, sha = self._stamp(
            env={
                "FAKE_GIT_STATUS": " M irgendwas",
                "APP_VERSION": "v9.9.9",
                "GIT_SHA": "0123456789ab",
            }
        )

        self.assertEqual(version, "v9.9.9")
        self.assertEqual(sha, "0123456789ab")

    def test_without_git_the_stamp_degrades_instead_of_failing(self):
        version, sha = self._stamp(git_body=FAKE_GIT_MISSING)

        self.assertEqual(version, "dev")
        self.assertEqual(sha, "unknown")

    def test_build_sh_uses_the_shared_stamp(self):
        # Ohne diese Zusage koennte build.sh seine eigene Fassung behalten und
        # alles oben waere gruen, ohne dass ein Image je richtig gestempelt wird.
        build_sh = REPO_ROOT / "ops" / "automation" / "build.sh"
        if not build_sh.exists():
            self.skipTest("build.sh nicht eingehaengt")
        source = build_sh.read_text()

        self.assertIn("ops/automation/version.sh", source)
        self.assertNotIn(
            "rev-parse --short=12 HEAD",
            source,
            "build.sh stempelt weiterhin selbst und umgeht damit den Marker",
        )


if __name__ == "__main__":
    unittest.main()
