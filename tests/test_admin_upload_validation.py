"""Admin-upload validation tests.

Hits `_read_admin_upload_json` with synthetic UploadFile-like stubs to
verify the MIME allowlist, the size cap, and the JSON-parse error path.
"""
import asyncio
import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


class _FakeUploadFile:
    """Minimal duck-typed stand-in for `fastapi.UploadFile`. The real
    class is async; we mirror that with a single `read(chunk_size)`
    coroutine that walks the underlying byte buffer."""

    def __init__(self, body: bytes, content_type: str | None = "application/json"):
        self.content_type = content_type
        self._body = body
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            chunk = self._body[self._pos:]
            self._pos = len(self._body)
            return chunk
        chunk = self._body[self._pos: self._pos + size]
        self._pos += len(chunk)
        return chunk


class AdminUploadValidationTests(unittest.TestCase):
    def setUp(self):
        from app import main as main_module
        self.main = main_module

    def _run(self, file: _FakeUploadFile):
        return asyncio.run(self.main._read_admin_upload_json(file))

    def test_application_json_payload_is_parsed(self):
        body = json.dumps({"hello": "world"}).encode("utf-8")
        file = _FakeUploadFile(body, content_type="application/json")
        payload = self._run(file)
        self.assertEqual({"hello": "world"}, payload)

    def test_octet_stream_is_accepted_as_fallback(self):
        body = json.dumps({"k": 1}).encode("utf-8")
        file = _FakeUploadFile(body, content_type="application/octet-stream")
        payload = self._run(file)
        self.assertEqual({"k": 1}, payload)

    def test_unsupported_mime_is_rejected(self):
        from fastapi import HTTPException

        body = b"<html></html>"
        file = _FakeUploadFile(body, content_type="text/html")
        with self.assertRaises(HTTPException) as ctx:
            self._run(file)
        self.assertEqual(400, ctx.exception.status_code)

    def test_oversized_upload_is_rejected(self):
        from fastapi import HTTPException

        # Cap is 50 MB by default — push past it
        oversized = b"a" * (51 * 1024 * 1024)
        file = _FakeUploadFile(oversized, content_type="application/json")
        with self.assertRaises(HTTPException) as ctx:
            self._run(file)
        self.assertEqual(413, ctx.exception.status_code)

    def test_invalid_json_is_rejected(self):
        from fastapi import HTTPException

        file = _FakeUploadFile(b"this is not json", content_type="application/json")
        with self.assertRaises(HTTPException) as ctx:
            self._run(file)
        self.assertEqual(400, ctx.exception.status_code)


if __name__ == "__main__":
    unittest.main()
