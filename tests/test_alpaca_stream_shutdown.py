"""SIGTERM must end the backend promptly even if the Alpaca SDK never returns.

`stream.run` blocks until the SDK ends its websocket loops, and on `stop()`
the SDK does not always do that (reconnect loop after a failed auth, pending
close handshakes). When that blocking call sat in the event loop's default
executor, the interpreter joined its non-daemon thread at exit and the
container only ended through SIGKILL after the stop timeout.

The test runs the start/stop cycle in a child interpreter with an SDK stand-in
whose `run` never returns and whose `stop` does nothing, and requires the child
to exit on its own. It is red when the stream thread is not a daemon.
"""
import subprocess
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent

CHILD = """
import asyncio, os, sys, threading
os.environ["ALPACA_API_KEY"] = "k"
os.environ["ALPACA_SECRET_KEY"] = "s"
import alpaca_trade_api.stream as sdk

class NeverEnds:
    def __init__(self, *a, **kw): pass
    def subscribe_trades(self, *a): pass
    def subscribe_bars(self, *a): pass
    def run(self): threading.Event().wait()
    def stop(self): pass

sdk.Stream = NeverEnds
from app.alpaca_stream import AlpacaStreamService

async def main():
    service = AlpacaStreamService()
    await service.start()
    await asyncio.sleep(0.2)
    await service.stop()

asyncio.run(main())
print("child-main-done")
"""


class AlpacaStreamShutdownTest(unittest.TestCase):
    def test_process_exits_although_the_sdk_run_never_returns(self):
        try:
            result = subprocess.run(
                [sys.executable, "-c", CHILD],
                cwd=BACKEND_ROOT,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            self.fail("process still alive 20 s after stop(): the stream thread blocks interpreter exit")
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertIn("child-main-done", result.stdout)


class AlpacaStreamRunFailureTest(unittest.TestCase):
    def test_exception_from_run_is_logged_with_the_start_failed_event(self):
        # Without the wrapper the exception ends the daemon thread and reaches
        # threading.excepthook (plain stderr), not the structured log.
        import asyncio
        import os
        from unittest.mock import patch

        os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
        os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")
        sys.path.insert(0, str(BACKEND_ROOT))
        from app import alpaca_stream

        class Boom:
            def __init__(self, *a, **kw):
                pass

            def subscribe_trades(self, *a):
                pass

            def subscribe_bars(self, *a):
                pass

            def run(self):
                raise RuntimeError("stream ended with an error")

        async def start():
            service = alpaca_stream.AlpacaStreamService()
            service.api_key, service.secret_key = "k", "s"
            await service.start()
            service._thread.join(timeout=5)
            self.assertFalse(service._thread.is_alive())

        with patch.object(alpaca_stream, "Stream", Boom), \
             self.assertLogs("app.alpaca_stream", level="ERROR") as logs:
            asyncio.run(start())
        self.assertTrue(any("alpaca_stream_start_failed" in line for line in logs.output))
        self.assertTrue(any("stream ended with an error" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
