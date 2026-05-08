"""docs_service tests.

Verifies the topic listing reads markdown sources, the title +
page-mapping parsing handles the comment frontmatter, slug
sanitisation rejects path-escapes, and missing topics return None.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


def _seed_docs(directory: Path) -> None:
    (directory / "dashboard.md").write_text(
        "<!-- page: / -->\n# Dashboard\n\nWhat you see on the landing page.\n",
        encoding="utf-8",
    )
    (directory / "watchlists.md").write_text(
        "<!-- page: /watchlists -->\n# Watchlists\n\nThe symbol universe.\n",
        encoding="utf-8",
    )
    (directory / "no-page.md").write_text(
        "# Untagged\n\nNot mapped to any frontend route.\n",
        encoding="utf-8",
    )


class DocsServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.docs_dir = Path(self._tmp.name)
        _seed_docs(self.docs_dir)
        os.environ["DOCS_INAPP_DIR"] = str(self.docs_dir)
        # Force a re-import so the module-level path picks up the env
        for module_name in list(sys.modules):
            if module_name.startswith("app.docs_service"):
                del sys.modules[module_name]
        from app import docs_service  # noqa: WPS433

        docs_service.reset_caches_for_tests()
        self.docs_service = docs_service

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("DOCS_INAPP_DIR", None)

    def test_list_topics_returns_three_entries_with_titles(self):
        topics = self.docs_service.list_topics()
        slugs = {entry["slug"] for entry in topics}
        self.assertEqual({"dashboard", "watchlists", "no-page"}, slugs)
        title_by_slug = {entry["slug"]: entry["title"] for entry in topics}
        self.assertEqual("Dashboard", title_by_slug["dashboard"])
        self.assertEqual("Watchlists", title_by_slug["watchlists"])

    def test_page_to_topic_map_skips_unannotated_files(self):
        mapping = self.docs_service.get_page_to_topic_map()
        self.assertEqual("dashboard", mapping["/"])
        self.assertEqual("watchlists", mapping["/watchlists"])
        # The untagged file does not appear in the page map
        self.assertNotIn("/no-page", mapping)

    def test_get_topic_returns_full_content(self):
        topic = self.docs_service.get_topic("dashboard")
        self.assertIsNotNone(topic)
        self.assertEqual("Dashboard", topic["title"])
        self.assertIn("landing page", topic["content"])
        self.assertEqual("/", topic["page"])

    def test_get_topic_returns_none_for_missing_slug(self):
        self.assertIsNone(self.docs_service.get_topic("missing"))

    def test_get_topic_rejects_unsafe_slug(self):
        for unsafe in ("../etc/passwd", "..", "ABC", "topic/with/slash", ""):
            self.assertIsNone(self.docs_service.get_topic(unsafe))


if __name__ == "__main__":
    unittest.main()
