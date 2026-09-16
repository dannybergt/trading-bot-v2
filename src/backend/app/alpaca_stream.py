import os
import asyncio
import logging
from datetime import datetime, timezone
from alpaca_trade_api.stream import Stream
from .websocket_manager import manager

logger = logging.getLogger(__name__)


def _iso_timestamp(value):
    """ISO 8601 (UTC) for whatever the SDK hands over as a timestamp.

    Stream trades arrive as `pd.Timestamp`, stream bars as a raw integer
    of nanoseconds since the epoch (alpaca-trade-api 3.2.0 converts the
    msgpack time only for `Trade`, not for `Bar`). The old
    `.isoformat()` call raised on every bar and the SDK logged
    "error during websocket communication" once per symbol per minute
    (deployed instance, 2026-09-16)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1_000_000_000, tz=timezone.utc).isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class AlpacaStreamService:
    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY", "")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        self.base_url = "https://paper-api.alpaca.markets" 
        # Note: the stream URL is automatically derived by the SDK, usually wss://stream.data.alpaca.markets/v2/iex
        
        self.stream = None
        self.symbols_to_track = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"] # We can make this dynamic later
        self.loop = None
        
    async def start(self):
        """Initialize and start the Alpaca WebSocket stream."""
        if not self.api_key or not self.secret_key:
            logger.error("Alpaca API keys missing. Cannot start stream.")
            return

        try:
            # We use 'iex' feed for the free tier, 'sip' for paid.
            # Using data_feed='iex' is safer for the free paper trading accounts.
            self.stream = Stream(
                self.api_key,
                self.secret_key,
                base_url=self.base_url,
                data_feed='iex'
            )
            
            # Register handlers
            self.stream.subscribe_trades(self.trade_callback, *self.symbols_to_track)
            self.stream.subscribe_bars(self.bar_callback, *self.symbols_to_track)
            
            logger.info("alpaca_stream_started symbols=%s", ",".join(self.symbols_to_track))
            
            # This is a blocking call, so we must run it in an executor in the background
            self.loop = asyncio.get_running_loop()
            await self.loop.run_in_executor(None, self.stream.run)
            
        except Exception:
            logger.exception("alpaca_stream_start_failed")

    async def trade_callback(self, t):
        """Callback for real-time trades."""
        # Note: Alpaca callback functions might run in a separate thread.
        # We need to ensure we broadcast safely in the main async loop.
        data = {
            "type": "trade",
            "symbol": t.symbol,
            "price": t.price,
            "size": t.size,
            "time": _iso_timestamp(getattr(t, "timestamp", None))
        }
        
        # Broadcast to all connected web UI clients
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast_json(data), self.loop)

    async def bar_callback(self, b):
        """Callback for real-time bars (1-minute aggregations typically)."""
        data = {
            "type": "bar",
            "symbol": b.symbol,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
            "time": _iso_timestamp(getattr(b, "timestamp", None))
        }
        
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast_json(data), self.loop)

    async def stop(self):
        """Stop the stream."""
        if self.stream:
            self.stream.stop()
            logger.info("Alpaca stream stopped.")

alpaca_stream = AlpacaStreamService()
