"""Guard that the German and English bundles stay structurally identical.

A missing key does not crash i18next -- it renders the key path itself, so a
half-translated page looks merely odd rather than broken and survives review.
That is exactly how seven pages stayed untranslated until 2026-07-26.

The ui-regression checks a handful of visible headings; this pins the whole key
tree, which is the part that scales as namespaces get added.
"""
import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = PROJECT_ROOT / "src" / "frontend" / "src" / "i18n"


def _load(name: str) -> dict:
    path = I18N_DIR / name
    assert path.exists(), f"{path} is missing"
    return json.loads(path.read_text())


def _key_paths(node, prefix: str = "") -> set[str]:
    """Flatten to dotted paths. Lists are compared by length, not by content:
    the entries are translated prose and must differ between languages."""
    if isinstance(node, dict):
        paths: set[str] = set()
        for key, value in node.items():
            paths |= _key_paths(value, f"{prefix}.{key}" if prefix else key)
        return paths
    if isinstance(node, list):
        return {f"{prefix}[{len(node)}]"}
    return {prefix}


class I18nBundleTests(unittest.TestCase):
    def setUp(self):
        self.de = _load("de.json")
        self.en = _load("en.json")

    def test_key_trees_are_identical(self):
        de_paths = _key_paths(self.de)
        en_paths = _key_paths(self.en)
        missing_in_de = sorted(en_paths - de_paths)
        missing_in_en = sorted(de_paths - en_paths)
        self.assertEqual(
            ([], []),
            (missing_in_de, missing_in_en),
            f"bundle drift -- missing in de.json: {missing_in_de[:20]}, "
            f"missing in en.json: {missing_in_en[:20]}",
        )

    def test_emptiness_is_symmetric(self):
        """A value blank in one language but filled in the other is drift.

        Blank in BOTH is legitimate and deliberately allowed: some inputs have
        no placeholder for certain rule types, and inventing copy there would
        change the UI rather than translate it.
        """

        def flatten(node, prefix="", out=None):
            out = {} if out is None else out
            if isinstance(node, dict):
                for key, value in node.items():
                    flatten(value, f"{prefix}.{key}" if prefix else key, out)
            elif isinstance(node, str):
                out[prefix] = node
            return out

        de_flat = flatten(self.de)
        en_flat = flatten(self.en)
        asymmetric = sorted(
            key
            for key in de_flat.keys() & en_flat.keys()
            if bool(de_flat[key].strip()) != bool(en_flat[key].strip())
        )
        self.assertEqual([], asymmetric, f"blank in one language only: {asymmetric[:20]}")

    def test_guided_tour_namespace_is_complete(self):
        """The guided run addresses every step by key; a gap would render a raw path."""
        expected_steps = {
            "basics",
            "findSymbol",
            "readAnalysis",
            "watchlist",
            "alert",
            "paperTrade",
            "autoExecution",
        }
        for name, bundle in (("de.json", self.de), ("en.json", self.en)):
            with self.subTest(bundle=name):
                tour = bundle.get("tour")
                self.assertIsNotNone(tour, f"{name} has no `tour` namespace")
                self.assertEqual(expected_steps, set(tour["steps"]))
                for step_id, step in tour["steps"].items():
                    self.assertTrue(step.get("label"), f"{name}: {step_id} has no label")
                    self.assertTrue(step.get("cta"), f"{name}: {step_id} has no cta")
                    self.assertTrue(
                        step.get("watchFor"), f"{name}: {step_id} has no watchFor entries"
                    )


if __name__ == "__main__":
    unittest.main()
