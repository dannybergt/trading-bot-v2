"""Guard the version string that ends up in published images.

`ops/automation/build.sh` derives APP_VERSION from `git describe --tags
--always`. With the default shallow checkout there are no tags and no history,
so describe silently falls through to its `--always` fallback and emits a bare
short SHA -- the image is then labelled `aa80510` instead of
`v2026.05.08-1-75-gaa80510`, and /api/version reports the same.

Nothing else catches this: a local build has full history, so every regression
run produces a correct version regardless of what CI does. The failure is
therefore only visible in the published artefact, which is why it went
unnoticed. These tests pin the checkout depth in the workflows that run
build.sh.
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = PROJECT_ROOT / ".github" / "workflows"

# Only workflows that actually invoke build.sh need the full history.
BUILDING_WORKFLOWS = ("ci.yml", "publish.yml")

CHECKOUT_STEP = re.compile(
    r"uses:\s*actions/checkout@[^\s]+\s*\n"
    r"(?P<body>(?:\s+.*\n)*?)"
    r"(?=\s*- name:|\Z)",
)


class WorkflowCheckoutDepthTests(unittest.TestCase):
    def test_building_workflows_run_build_script(self):
        """Anchors the premise: if build.sh moves, this guard must be revisited."""
        for name in BUILDING_WORKFLOWS:
            text = (WORKFLOW_DIR / name).read_text()
            self.assertIn("build.sh", text, f"{name} no longer runs build.sh")

    def test_checkout_fetches_full_history_and_tags(self):
        for name in BUILDING_WORKFLOWS:
            text = (WORKFLOW_DIR / name).read_text()
            matches = list(CHECKOUT_STEP.finditer(text))
            self.assertTrue(matches, f"{name} has no actions/checkout step")
            for match in matches:
                self.assertIn(
                    "fetch-depth: 0",
                    match.group("body"),
                    f"{name} checks out shallow -- git describe would fall back to a bare SHA",
                )


if __name__ == "__main__":
    unittest.main()
