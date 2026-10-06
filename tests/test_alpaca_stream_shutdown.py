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


if __name__ == "__main__":
    unittest.main()
