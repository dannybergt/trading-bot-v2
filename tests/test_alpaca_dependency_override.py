"""alpaca-trade-api runs with urllib3 2.x and msgpack 1.2 (installed --no-deps).

The SDK declares urllib3<2 and msgpack==1.0.3; both carry advisories. The
image installs it --no-deps (src/backend/requirements-alpaca.txt, ADR
2026-10-06). These tests hold the assumptions that make that safe: the SDK
never imports urllib3 itself, its REST client works over requests/urllib3 2,
and its stream decoder handles msgpack 1.2 timestamps. Remove together with
requirements-alpaca.txt when the code moves to alpaca-py.
"""
import json
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import metadata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = PROJECT_ROOT / "ops" / "docker" / "backend.Dockerfile"


def _version(name: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", metadata.version(name))[:3])


class InstalledVersionsTests(unittest.TestCase):
    def test_urllib3_is_at_least_2_8(self):
        self.assertGreaterEqual(_version("urllib3"), (2, 8, 0))

    def test_msgpack_is_at_least_1_2_1(self):
        self.assertGreaterEqual(_version("msgpack"), (1, 2, 1))

    def test_python_jose_is_gone(self):
        with self.assertRaises(metadata.PackageNotFoundError):
            metadata.version("python-jose")

    def test_dockerfile_installs_alpaca_without_deps_after_requirements(self):
        text = DOCKERFILE.read_text()
        main = text.find("-r requirements.txt")
        nodeps = text.find("--no-deps -r requirements-alpaca.txt")
        self.assertGreater(main, -1)
        self.assertGreater(nodeps, main)


# The only two conflicts --no-deps is allowed to leave behind. --no-deps also
# hides every other SDK bound from the resolver (websockets<11, PyYAML==6.0.1,
# deprecation==2.1.0, aiohttp<4, websocket-client<2); a Dependabot bump past
# one of them would install fine and break the SDK only at runtime.
ALLOWED_CONFLICT = re.compile(r"^alpaca-trade-api \S+ has requirement (urllib3|msgpack)[^A-Za-z0-9_.-]")


class PipCheckTests(unittest.TestCase):
    def test_pip_check_reports_only_the_two_intended_conflicts(self):
        result = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        unexpected = [line for line in lines if not ALLOWED_CONFLICT.match(line)]
        self.assertEqual(unexpected, [], result.stdout + result.stderr)
        # Guard against a pip check that silently stopped reporting: with the
        # SDK installed the two intended conflicts must be there.
        self.assertEqual(len(lines), 2, result.stdout + result.stderr)


class SdkDoesNotUseUrllib3Tests(unittest.TestCase):
    def test_no_direct_urllib3_import(self):
        import alpaca_trade_api

        package = Path(alpaca_trade_api.__file__).parent
        offenders = [
            str(path.relative_to(package))
            for path in package.rglob("*.py")
            if re.search(r"^\s*(import|from)\s+urllib3", path.read_text(), re.MULTILINE)
        ]
        self.assertEqual(offenders, [])


class _AccountHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        body = json.dumps({"id": "acc-1", "status": "ACTIVE", "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class RestOverUrllib3TwoTests(unittest.TestCase):
    def test_get_account_through_sdk(self):
        import alpaca_trade_api as tradeapi

        server = HTTPServer(("127.0.0.1", 0), _AccountHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            api = tradeapi.REST("key", "secret", f"http://127.0.0.1:{server.server_port}", api_version="v2")
            account = api.get_account()
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(account.id, "acc-1")
        self.assertEqual(account._raw["path"], "/v2/account")


class StreamDecodeWithMsgpackTwoTests(unittest.TestCase):
    def test_trade_and_bar_frames_decode(self):
        import msgpack
        from alpaca_trade_api.stream import DataStream

        from app.alpaca_stream import _iso_timestamp

        ts = msgpack.Timestamp(seconds=1_790_000_000, nanoseconds=123_000_000)
        frame = msgpack.packb([
            {"T": "t", "S": "SPY", "p": 500.5, "s": 10, "t": ts},
            {"T": "b", "S": "SPY", "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 100, "t": ts},
        ])
        stream = DataStream("key", "secret", "https://paper-api.alpaca.markets", raw_data=False)
        trade_msg, bar_msg = msgpack.unpackb(frame)

        trade = stream._cast("t", trade_msg)
        bar = stream._cast("b", bar_msg)

        self.assertEqual((trade.symbol, trade.price, trade.size), ("SPY", 500.5, 10))
        self.assertEqual((bar.symbol, bar.close, bar.volume), ("SPY", 1.5, 100))
        # Same instant either way; the SDK hands trades over in exchange time
        # (America/New_York) and bars as epoch nanoseconds.
        expected = datetime(2026, 9, 21, 14, 13, 20, 123000, tzinfo=timezone.utc)
        self.assertEqual(datetime.fromisoformat(_iso_timestamp(trade.timestamp)), expected)
        self.assertEqual(datetime.fromisoformat(_iso_timestamp(bar.timestamp)), expected)


if __name__ == "__main__":
    unittest.main()
