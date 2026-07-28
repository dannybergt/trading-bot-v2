"""Guard the frontend nginx serving configuration.

The frontend container is not the outermost hop in production: an Apache
reverse proxy terminates TLS for the public domain and forwards to this nginx.
That makes every response header nginx *omits* a header the upstream proxy is
free to invent.

The concrete case this pins: nginx served `text/html` with no charset, so
Apache appended its own default (`charset=ISO-8859-1`). The HTTP header
outranks the document's `<meta charset="UTF-8">`, which means the public domain
declared a different encoding than the internal port for the very same bytes.

These tests pin the serving guarantees that are only observable through the
proxy, and would otherwise regress unnoticed on the internal port.
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NGINX_CONF = PROJECT_ROOT / "ops" / "docker" / "frontend.nginx.conf"


def _conf_text() -> str:
    assert NGINX_CONF.exists(), f"{NGINX_CONF} is missing"
    return NGINX_CONF.read_text()


class FrontendNginxConfTests(unittest.TestCase):
    def test_charset_is_declared_as_utf8(self):
        """Without an explicit charset the upstream proxy picks one for us."""
        conf = _conf_text()
        match = re.search(r"^\s*charset\s+([^;]+);", conf, re.MULTILINE)
        self.assertIsNotNone(
            match,
            "frontend.nginx.conf declares no charset -- an upstream reverse "
            "proxy will substitute its own default (Apache uses ISO-8859-1)",
        )
        self.assertEqual(match.group(1).strip().lower(), "utf-8")

    def test_charset_is_not_disabled(self):
        """`charset off` would reintroduce the exact gap this guards."""
        self.assertIsNone(
            re.search(r"^\s*charset\s+off\s*;", _conf_text(), re.MULTILINE),
            "charset must not be turned off",
        )

    def test_spa_fallback_still_present(self):
        """If the premise breaks, this guard should say so instead of passing.

        The charset only matters because nginx serves the SPA shell itself.
        Should the fallback ever move elsewhere, this file needs revisiting
        rather than staying quietly green.
        """
        self.assertIn("try_files $uri $uri/ /index.html;", _conf_text())


if __name__ == "__main__":
    unittest.main()
