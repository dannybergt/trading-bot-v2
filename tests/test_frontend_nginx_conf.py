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
# Checkout layout first, backend image layout (/app/app/main.py) second.
BACKEND_MAIN = next(
    (
        path
        for path in (
            PROJECT_ROOT / "src" / "backend" / "app" / "main.py",
            PROJECT_ROOT / "app" / "main.py",
        )
        if path.exists()
    ),
    None,
)
ADMIN_UPLOAD_PATHS = ("/api/admin/import", "/api/admin/backups/import")
MULTIPART_HEADROOM = 1024 * 1024


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


def _size_to_bytes(value: str) -> int:
    """nginx size syntax: bare bytes, or a k/m/g suffix (case-insensitive)."""
    match = re.fullmatch(r"(\d+)([kKmMgG]?)", value.strip())
    assert match, f"unparseable nginx size {value!r}"
    factor = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[match.group(2).lower()]
    return int(match.group(1)) * factor


def _server_level_body_limit(conf: str) -> int:
    """client_max_body_size outside any location block (nginx default 1m)."""
    depth = 0
    limit = "1m"
    for line in conf.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if depth == 1:
            match = re.match(r"client_max_body_size\s+([^;]+);", stripped)
            if match:
                limit = match.group(1)
        depth += stripped.count("{") - stripped.count("}")
    return _size_to_bytes(limit)


def _location_blocks(conf: str) -> list[tuple[str, str]]:
    """(matcher, body) for each location block; the conf nests no deeper."""
    return [
        (m.group(1).strip(), m.group(2))
        for m in re.finditer(r"^\s*location\s+([^{]+)\{(.*?)^\s*\}", conf, re.MULTILINE | re.DOTALL)
    ]


def _location_for(conf: str, uri: str) -> tuple[str, str]:
    """The block nginx picks for a normalised `uri`: exact match, then regex,
    then the longest prefix (no prefix here uses ^~)."""
    blocks = _location_blocks(conf)
    for matcher, body in blocks:
        if matcher.startswith("=") and matcher[1:].strip() == uri:
            return matcher, body
    for matcher, body in blocks:
        if matcher.startswith("~"):
            pattern = matcher.lstrip("~*").strip()
            flags = re.IGNORECASE if matcher.startswith("~*") else 0
            if re.search(pattern, uri, flags):
                return matcher, body
    prefixes = [(m, b) for m, b in blocks if not m.startswith(("~", "="))]
    matcher, body = max(
        ((m, b) for m, b in prefixes if uri.startswith(m)), key=lambda item: len(item[0])
    )
    return matcher, body


def _backend_admin_upload_cap() -> int:
    assert BACKEND_MAIN is not None, "backend main.py not found"
    match = re.search(
        r'ADMIN_UPLOAD_MAX_BYTES\s*=\s*int\(os\.getenv\("ADMIN_UPLOAD_MAX_BYTES",\s*str\(([^)]+)\)\)\)',
        BACKEND_MAIN.read_text(),
    )
    assert match, "ADMIN_UPLOAD_MAX_BYTES default not found in main.py"
    expr = match.group(1)
    assert re.fullmatch(r"[\d\s*]+", expr), f"unexpected cap expression {expr!r}"
    value = 1
    for factor in expr.split("*"):
        value *= int(factor)
    return value


class RequestBodyLimitTests(unittest.TestCase):
    """nginx and the backend must agree on how big an admin restore may be.

    With nginx at its 1 MB default in front of a backend that accepts 50 MiB,
    any backup above 1 MB died at the proxy with an nginx 413 page and never
    reached the backend's own check (verifier N-2, 2026-09-29).
    """

    def test_admin_uploads_pass_up_to_the_backend_cap(self):
        conf = _conf_text()
        cap = _backend_admin_upload_cap()
        for uri in ADMIN_UPLOAD_PATHS:
            matcher, body = _location_for(conf, uri)
            match = re.search(r"client_max_body_size\s+([^;]+);", body)
            self.assertIsNotNone(
                match,
                f"{uri} is served by `location {matcher}` without its own "
                "client_max_body_size -- it inherits the API default and a restore "
                "above that dies at nginx",
            )
            limit = _size_to_bytes(match.group(1))
            self.assertGreaterEqual(
                limit,
                cap + MULTIPART_HEADROOM,
                f"{uri}: nginx accepts {limit} bytes, backend accepts a {cap}-byte "
                "file plus its multipart envelope",
            )
            self.assertLessEqual(
                limit,
                cap + 2 * MULTIPART_HEADROOM,
                f"{uri}: nginx accepts {limit} bytes, far above what the backend "
                "keeps -- nginx should stop those bodies before the backend",
            )
            self.assertIn("proxy_pass http://backend:8000", body)
            self.assertIn("X-Forwarded-For", body, f"{uri} must forward the client address")

    def test_raised_limit_only_reaches_the_path_it_was_chosen_for(self):
        """nginx chooses the block by the normalised path; a proxy_pass without
        a URI forwards the client's raw path. A 51m regex block of that kind let
        `/api/watchlists/1/items/../../../admin/import` pick the upload limit
        and still reach the `{symbol:path}` route (reviewer B-1, reproduced).
        Every block above the server default is therefore an exact match whose
        proxy_pass names exactly that path."""
        conf = _conf_text()
        default = _server_level_body_limit(conf)
        raised = []
        for matcher, body in _location_blocks(conf):
            match = re.search(r"client_max_body_size\s+([^;]+);", body)
            if not match or _size_to_bytes(match.group(1)) <= default:
                continue
            raised.append(matcher)
            self.assertTrue(
                matcher.startswith("="),
                f"`location {matcher}` raises the body limit but is not an exact match",
            )
            path = matcher[1:].strip()
            target = re.search(r"proxy_pass\s+([^;]+);", body)
            self.assertIsNotNone(target, f"`location {matcher}` has no proxy_pass")
            self.assertEqual(
                target.group(1).strip(),
                f"http://backend:8000{path}",
                f"`location {matcher}` must forward exactly {path}, not the raw client path",
            )
        self.assertEqual(sorted(raised), sorted(f"= {p}" for p in ADMIN_UPLOAD_PATHS))

    def test_restore_blocks_refuse_before_buffering(self):
        """Only POST and only with a bearer token -- checked by nginx before it
        buffers up to 51 MiB (security-reviewer #1/#2). No connection limit:
        with a format-only token check it lets two anonymous slow uploads
        lock every restore out (reviewer B-2)."""
        conf = _conf_text()
        self.assertNotRegex(conf, r"(?m)^\s*limit_conn(_zone)?\s")
        for uri in ADMIN_UPLOAD_PATHS:
            matcher, body = _location_for(conf, uri)
            self.assertRegex(body, r"limit_except\s+POST\s*\{\s*deny\s+all;\s*\}")
            self.assertRegex(body, r'if\s+\(\$http_authorization\s+!~\*\s+"\^Bearer ')
            self.assertRegex(body, r"\{\s*return\s+401;\s*\}")

    def test_restore_blocks_outlast_a_slow_restore(self):
        """At the 60 s default nginx answers 504 while a 50 MiB restore keeps
        running; an operator then retries a restore that already replaced the
        data (ops-reviewer #1)."""
        conf = _conf_text()
        for uri in ADMIN_UPLOAD_PATHS:
            matcher, body = _location_for(conf, uri)
            for directive in ("proxy_read_timeout", "proxy_send_timeout"):
                match = re.search(rf"{directive}\s+(\d+)s;", body)
                self.assertIsNotNone(match, f"{uri}: {directive} missing in `location {matcher}`")
                self.assertGreaterEqual(int(match.group(1)), 300)

    def test_other_api_calls_keep_the_small_limit(self):
        conf = _conf_text()
        self.assertLessEqual(_server_level_body_limit(conf), 1024 * 1024)
        for uri in ("/api/admin/backups", "/api/auth/login", "/api/admin/import/x"):
            matcher, body = _location_for(conf, uri)
            self.assertNotIn(
                "client_max_body_size",
                body,
                f"{uri} (location {matcher}) must not get the upload limit",
            )


if __name__ == "__main__":
    unittest.main()
