"""npm decision in ops/automation/deps-audit.sh: fail closed on every odd input.

The evaluator is the Python block of the script (between <<'PY' and PY); it
is run here as-is on hand-written npm reports. Exit 0 = clean, 1 = open
advisory or expired/undated ignore, 2 = no usable report.
"""
import datetime
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "automation" / "deps-audit.sh"
ADVISORY = "GHSA-vfj7-8cjw-p6xm"
FOUND = {"vulnerabilities": {"braces": {"via": [{"url": "https://github.com/advisories/" + ADVISORY}]}}}


def _evaluator() -> str:
    text = SCRIPT.read_text()
    start = text.index("<<'PY'\n") + len("<<'PY'\n")
    return text[start:text.index("\nPY\n", start)]


def _date(days: int) -> str:
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


class NpmFilterTests(unittest.TestCase):
    def _run(self, raw: str, *ignores: str) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "npm.json"
            report.write_text(raw)
            code = Path(tmp) / "eval.py"
            code.write_text(_evaluator())
            return subprocess.run(
                [sys.executable, "-I", str(code), str(report), *ignores],
                capture_output=True,
                text=True,
                timeout=30,
            ).returncode

    def test_valid_ignore_passes(self):
        self.assertEqual(self._run(json.dumps(FOUND), f"{ADVISORY}:{_date(1)}"), 0)

    def test_ignore_valid_through_its_last_day(self):
        self.assertEqual(self._run(json.dumps(FOUND), f"{ADVISORY}:{_date(0)}"), 0)

    def test_expired_undated_or_bad_date_fails(self):
        for entry in (f"{ADVISORY}:{_date(-1)}", ADVISORY, f"{ADVISORY}:bogus"):
            with self.subTest(entry=entry):
                self.assertEqual(self._run(json.dumps(FOUND), entry), 1)

    def test_open_advisory_fails(self):
        self.assertEqual(self._run(json.dumps(FOUND)), 1)

    def test_string_via_with_own_entry_is_followed(self):
        report = {"vulnerabilities": {**FOUND["vulnerabilities"], "micromatch": {"via": ["braces"]}}}
        self.assertEqual(self._run(json.dumps(report), f"{ADVISORY}:{_date(1)}"), 0)
        self.assertEqual(self._run(json.dumps(report)), 1)

    def test_clean_report_passes(self):
        self.assertEqual(self._run(json.dumps({"vulnerabilities": {}})), 0)

    def test_no_usable_report_is_exit_2(self):
        for raw in (
            "",
            "not json",
            "[]",
            "null",
            '"text"',
            "42",
            '{"error": {"code": "E"}}',
            '{"vulnerabilities": {}, "error": {"code": "E"}}',
            '{"vulnerabilities": []}',
            '{"vulnerabilities": null}',
            '{"vulnerabilities": {"braces": {"via": "GHSA-x"}}}',
            '{"vulnerabilities": {"braces": {}}}',
            '{"vulnerabilities": {"braces": {"via": ["micromatch"]}}}',
        ):
            with self.subTest(raw=raw):
                self.assertEqual(self._run(raw, f"{ADVISORY}:{_date(1)}"), 2)


if __name__ == "__main__":
    unittest.main()
