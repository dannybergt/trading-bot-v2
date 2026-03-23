import os
import asyncio
import logging
from alpaca_trade_api.stream import Stream
from .websocket_manager import manager

logger = logging.getLogger(__name__)

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
            "time": t.timestamp.isoformat() if hasattr(t, 'timestamp') and t.timestamp else None
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
            "time": b.timestamp.isoformat() if hasattr(b, 'timestamp') and b.timestamp else None
        }
        
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast_json(data), self.loop)

    async def stop(self):
        """Stop the stream."""
        if self.stream:
            self.stream.stop()
            logger.info("Alpaca stream stopped.")

alpaca_stream = AlpacaStreamService()
