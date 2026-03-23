import alpaca_trade_api as tradeapi
import logging
import os
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)

class AlpacaService:
    def __init__(self, api_key=None, secret_key=None, paper=True):
        # Allow passing specific keys or fallback to environment (system default)
        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        self.base_url = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        
        self.api = None
        if self.api_key and self.secret_key:
            self.connect()

    def connect(self):
        try:
            self.api = tradeapi.REST(
                self.api_key, 
                self.secret_key, 
                self.base_url, 
                api_version='v2'
            )
            logger.info("alpaca_connected base_url=%s", self.base_url)
        except Exception:
            logger.exception("alpaca_connect_failed base_url=%s", self.base_url)
            self.api = None

    def get_account(self):
        if not self.api:
            return None
        try:
            return self.api.get_account()
        except Exception:
            logger.exception("alpaca_account_fetch_failed")
            return None

    def get_portfolio_history(self, period="1M", timeframe="1D"):
        if not self.api: return None
        try:
            # period: 1D, 1W, 1M, 3M, 1A, all
            # timeframe: 1Min, 5Min, 15Min, 1H, 1D
            return self.api.get_portfolio_history(period=period, timeframe=timeframe)._raw
        except Exception:
            logger.exception("alpaca_portfolio_history_fetch_failed period=%s timeframe=%s", period, timeframe)
            return None

    def get_activities(self, limit=100):
        if not self.api: return []
        try:
            # activity_types="FILL" gets executed orders
            activities = self.api.get_activities(activity_types="FILL", direction="desc")
            return [a._raw for a in activities[:limit]]
        except Exception:
            logger.exception("alpaca_activities_fetch_failed limit=%s", limit)
            return []

    def get_bars(self, symbol, timeframe='1Day', limit=100):
        """
        Fetch historical bars as list of dicts.
        timeframe: 1Min, 1Hour, 1Day
        """
        try:
            bars = self.get_bars_df(symbol, timeframe, limit)
            if bars.empty: return []
            
            # Format for frontend
            data = []
            for index, row in bars.iterrows():
                # Alpaca data is returned with UTC time index
                data.append({
                    'time': index.strftime('%Y-%m-%d %H:%M:%S'),
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['volume']
                })
            return data
        except Exception:
            logger.exception("alpaca_bars_fetch_failed symbol=%s timeframe=%s limit=%s", symbol, timeframe, limit)
            return []

    def get_bars_df(self, symbol, timeframe='1Day', limit=100):
        """
        Fetch historical bars and return as a Pandas DataFrame formatted for analysis.
        timeframe: 1Min, 1Hour, 1Day
        """
        if not self.api:
            return pd.DataFrame()
            
        try:
            # Map timeframe
            tf_map = {
                '1Min': '1Min', '5Min': '5Min', '15Min': '15Min',
                '1Hour': '1Hour', '1Day': '1Day', '1Week': '1Week', '1Month': '1Month'
            }
            mapped_tf = tf_map.get(timeframe, '1Day')

            # Calculate start date based on limit to fetch enough points
            # Ensure we get enough trading days
            days_back = limit * 2 if mapped_tf == '1Day' else limit
            if mapped_tf == '1Week': days_back = limit * 10
            elif mapped_tf == '1Month': days_back = limit * 35
            
            start = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            
            # Check if this is a Crypto symbol
            is_crypto = '/' in symbol

            if is_crypto:
                bars = self.api.get_crypto_bars(symbol, mapped_tf, start=start, limit=limit).df
            else:
                bars = self.api.get_bars(symbol, mapped_tf, start=start, limit=limit, adjustment='all').df
                
            if bars.empty:
                return pd.DataFrame()

            # The returned df has columns: open, high, low, close, volume, trade_count, vwap
            # rename for analysis
            bars.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            }, inplace=True)
            
            # Keep only the symbol data (if index is MultiIndex)
            if isinstance(bars.index, pd.MultiIndex):
                bars = bars.xs(symbol, level=1)
                
            # Convert index to localized/unlocalized easily digestable stamp
            bars.index = bars.index.tz_convert('UTC').tz_localize(None)

            return bars
        except Exception:
            logger.exception("alpaca_bars_df_fetch_failed symbol=%s timeframe=%s limit=%s", symbol, timeframe, limit)
            return pd.DataFrame()

    def get_news(self, symbol, limit=10):
        """Fetch market news from Alpaca."""
        if not self.api: return []
        try:
            # list_news is available in modern alpaca-trade-api
            news = self.api.get_news(symbol, limit=limit)
            return [n._raw for n in news]
        except Exception:
            logger.exception("alpaca_news_fetch_failed symbol=%s limit=%s", symbol, limit)
            return []

    _assets_cache = []
    _assets_cache_time = 0

    def get_all_assets(self):
        """Fetch and cache all active US equity assets from Alpaca."""
        if not self.api: return []
        
        now = datetime.now().timestamp()
        # Cache for 24 hours
        if self._assets_cache and (now - self._assets_cache_time < 86400):
            return self._assets_cache
            
        try:
            equities = self.api.list_assets(status='active', asset_class='us_equity')
            try:
                crypto = self.api.list_assets(status='active', asset_class='crypto')
            except Exception:
                logger.exception("alpaca_crypto_assets_fetch_failed")
                crypto = []
                
            assets = equities + crypto
            self._assets_cache = [a._raw for a in assets]
            self._assets_cache_time = now
            return self._assets_cache
        except Exception:
            logger.exception("alpaca_assets_fetch_failed")
            return []

    def submit_order(self, symbol, qty, side, type='market', time_in_force='gtc'):
        if not self.api:
            return None
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type=type,
                time_in_force=time_in_force
            )
            return order
        except Exception:
            logger.exception("alpaca_order_submit_failed symbol=%s side=%s qty=%s", symbol, side, qty)
            return None
