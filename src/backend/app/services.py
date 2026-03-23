import copy
import logging
from time import monotonic

import pandas as pd
import yfinance as yf
from app.analysis import calculate_indicators, detect_patterns
from app.asset_metadata import build_asset_profile, canonicalize_symbol, to_yfinance_symbol
from app.sentiment import analyze_news
from app.ml_models import PricePredictor

logger = logging.getLogger(__name__)

TICKER_INFO_TTL_SECONDS = 5 * 60
NEWS_CACHE_TTL_SECONDS = 60

class MarketDataService:
    def __init__(self, alpaca_service=None):
        self.predictor = PricePredictor()
        self.alpaca = alpaca_service
        self._ticker_info_cache: dict[str, dict] = {}
        self._news_cache: dict[str, dict] = {}

    def _get_cached_payload(self, cache: dict[str, dict], key: str):
        entry = cache.get(key)
        if not entry:
            return None
        if entry["expires_at"] <= monotonic():
            cache.pop(key, None)
            return None
        return copy.deepcopy(entry["value"])

    def _set_cached_payload(self, cache: dict[str, dict], key: str, value, ttl_seconds: int):
        cache[key] = {
            "expires_at": monotonic() + ttl_seconds,
            "value": copy.deepcopy(value),
        }
        return copy.deepcopy(value)

    def get_asset_reference(self, symbol: str):
        if not self.alpaca:
            return None

        target_symbol = canonicalize_symbol(symbol)
        for asset in self.alpaca.get_all_assets():
            if canonicalize_symbol(asset.get("symbol")) == target_symbol:
                return asset
        return None

    def get_asset_profile(
        self,
        symbol: str,
        ticker_info: dict | None = None,
        fallback_name: str | None = None,
    ) -> dict:
        asset = self.get_asset_reference(symbol)
        return build_asset_profile(
            symbol,
            asset=asset,
            ticker_info=ticker_info,
            fallback_name=fallback_name,
        )

    def get_ticker_info(
        self,
        symbol: str,
        *,
        asset_profile: dict | None = None,
    ) -> dict:
        target_symbol = canonicalize_symbol(symbol)
        cached = self._get_cached_payload(self._ticker_info_cache, target_symbol)
        if cached is not None:
            return cached

        profile = asset_profile or self.get_asset_profile(symbol)
        if profile.get("isCrypto"):
            logger.debug("fundamentals_skipped_crypto symbol=%s", symbol)
            return self._set_cached_payload(self._ticker_info_cache, target_symbol, {}, TICKER_INFO_TTL_SECONDS)

        ticker_info = {}
        try:
            ticker_info = yf.Ticker(to_yfinance_symbol(symbol)).info or {}
        except Exception:
            logger.exception("fundamentals_fetch_failed symbol=%s", symbol)
            ticker_info = {}

        return self._set_cached_payload(
            self._ticker_info_cache,
            target_symbol,
            ticker_info if isinstance(ticker_info, dict) else {},
            TICKER_INFO_TTL_SECONDS,
        )
        
    def get_stock_data(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
        user=None,
        *,
        include_news: bool = True,
        include_fundamentals: bool = True,
    ):
        """
        Fetch historical data and calculate indicators.
        """
        df = pd.DataFrame()
        market_symbol = canonicalize_symbol(symbol)
        asset_profile = self.get_asset_profile(symbol)
        if self.alpaca:
            # map period/interval to alpaca args
            tf_map = {"1d": "1Day", "1h": "1Hour", "15m": "15Min", "5m": "5Min", "1wk": "1Week"}
            timeframe = tf_map.get(interval, "1Day")
            
            days_map = {"1d": 1, "5d": 5, "1mo": 22, "3mo": 66, "6mo": 260, "1y": 500, "max": 1000}
            limit = days_map.get(period, 130)
            
            if timeframe == "1Hour": limit = limit * 7
            elif timeframe == "15Min": limit = limit * 28
            elif timeframe == "5Min": limit = limit * 84
            
            df = self.alpaca.get_bars_df(market_symbol, timeframe=timeframe, limit=limit)
        
        if df.empty:
            logger.warning("market_data_empty_using_mock symbol=%s period=%s interval=%s", symbol, period, interval)
            df = self._generate_mock_data(symbol, period, interval)
            
        # Calculate Indicators
        df_analyzed = calculate_indicators(df)
        
        # Detect Patterns
        patterns = detect_patterns(df_analyzed)
        
        # Fetch News Sentiment
        if include_news:
            news_data = self.get_market_news(symbol)
        else:
            news_data = {
                "items": [],
                "aggregate_score": 0.0,
                "aggregate_label": "neutral",
            }
        sentiment_score = news_data['aggregate_score'] if news_data else 0.0

        # Fetch Fundamentals from YFinance
        tickerInfo = {}
        if include_fundamentals:
            tickerInfo = self.get_ticker_info(symbol, asset_profile=asset_profile)
            if tickerInfo:
                asset_profile = self.get_asset_profile(symbol, ticker_info=tickerInfo)
        pe_ratio = tickerInfo.get('trailingPE', 0.0)
        forward_pe = tickerInfo.get('forwardPE', 0.0)
        price_to_book = tickerInfo.get('priceToBook', 0.0)

        df_analyzed['News_Sentiment'] = sentiment_score
        df_analyzed['PE_Ratio'] = pe_ratio
        df_analyzed['Forward_PE'] = forward_pe
        df_analyzed['Price_To_Book'] = price_to_book

        # Generate Prediction (Mock training on the fly for demo)
        prediction = None
        try:
            # Train on the fetched data
            self.predictor.train(df_analyzed)
            # Predict next move
            prediction = self.predictor.predict_next_movement(df_analyzed)
            
            # Apply user-defined Target Yield threshold constraints
            if prediction and prediction.get('direction') == 'UP' and user:
                # Get the last row's Close and ATR for volatility-based upside estimation
                latest = df_analyzed.iloc[-1]
                close_price = float(latest['Close'])
                atr = float(latest.get('ATR', 0))
                
                # Estimate a reasonable upside potential using 1.5 * ATR
                expected_gain_abs = atr * 1.5
                expected_gain_pct = (expected_gain_abs / close_price) * 100
                
                # Calculate required yield from user settings
                min_yield_pct = float(user.min_target_yield)
                fee_pct = float(user.trade_fee_percent)
                fee_abs_as_pct = (float(user.trade_fee_absolute) / close_price) * 100 if close_price > 0 else 0
                
                total_required_pct = min_yield_pct + fee_pct + fee_abs_as_pct
                
                # Attach expected yield context to the prediction dict
                prediction['expected_yield_pct'] = round(expected_gain_pct, 2)
                prediction['required_yield_pct'] = round(total_required_pct, 2)
                
                if expected_gain_pct < total_required_pct:
                    prediction['direction'] = 'HOLD'
                    prediction['reason'] = f'HOLD: Expected upside ({expected_gain_pct:.2f}%) is below your target + fees ({total_required_pct:.2f}%).'
                    logger.info("prediction_buy_suppressed symbol=%s reason=%s", symbol, prediction['reason'])
                else:
                    prediction['reason'] = f'BUY: Passed target yield filter ({expected_gain_pct:.2f}% >= {total_required_pct:.2f}%).'
                    
        except Exception:
            logger.exception("market_prediction_failed symbol=%s", symbol)
            
        # Get Info (Enriched with YFinance)
        info = {
            'symbol': symbol,
            'shortName': asset_profile['name'],
            'sector': tickerInfo.get('sector', 'N/A'),
            'industry': tickerInfo.get('industry', 'N/A'),
            'marketCap': tickerInfo.get('marketCap', 0),
            'dividendYield': tickerInfo.get('dividendYield', 0),
            '52WeekHigh': tickerInfo.get('fiftyTwoWeekHigh', 0),
            '52WeekLow': tickerInfo.get('fiftyTwoWeekLow', 0),
            'trailingPE': pe_ratio,
            'forwardPE': forward_pe,
            'priceToBook': price_to_book,
            'assetClass': asset_profile['assetClass'],
            'assetLabel': asset_profile['assetLabel'],
            'market': asset_profile['market'],
            'exchange': asset_profile['exchange'],
            'type': asset_profile['type'],
            'isCrypto': asset_profile['isCrypto'],
        }

        return {
            'data': df_analyzed,
            'patterns': patterns,
            'prediction': prediction,
            'info': info,
            'asset': asset_profile,
        }

    def _generate_mock_data(self, symbol, period, interval):
        import numpy as np
        from datetime import datetime, timedelta
        
        # Determine number of points based on period/interval
        days_map = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "max": 1000}
        days = days_map.get(period, 180)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # interval map to frequency
        freq_map = {"1d": "D", "1h": "H", "15m": "15T", "5m": "5T", "1wk": "W"}
        freq = freq_map.get(interval, "D")
        
        dates = pd.date_range(start=start_date, end=end_date, freq=freq)
        n = len(dates)
        
        if n == 0:
            dates = pd.date_range(start=start_date, periods=100, freq=freq)
            n = 100
            
        # Random walk
        base_price = 150.0
        if symbol == "NVDA": base_price = 450.0
        elif symbol == "GOOGL": base_price = 140.0
        elif symbol == "MSFT": base_price = 350.0
        
        np.random.seed(42)
        returns = np.random.normal(0, 0.02, n)
        price_curve = base_price * (1 + returns).cumprod()
        
        data = {
            "Open": price_curve,
            "High": price_curve * (1 + np.abs(np.random.normal(0, 0.01, n))),
            "Low": price_curve * (1 - np.abs(np.random.normal(0, 0.01, n))),
            "Close": price_curve,
            "Volume": np.random.randint(100000, 5000000, n).astype(float)
        }
        
        df = pd.DataFrame(data, index=dates)
        return df

    def get_market_news(self, symbol: str, limit: int = 15):
        """
        Fetch news for the symbol from Alpaca and analyze sentiment.
        """
        target_symbol = canonicalize_symbol(symbol)
        cache_key = f"{target_symbol}|{int(limit)}"
        cached = self._get_cached_payload(self._news_cache, cache_key)
        if cached is not None:
            return cached

        raw_news = []
        if self.alpaca:
            try:
                raw_news = self.alpaca.get_news(target_symbol, limit=limit)
            except Exception:
                logger.exception("market_news_fetch_failed symbol=%s", symbol)

        # Normalize news items to expected format for analyze_news
        normalized = []
        for item in raw_news:
             normalized.append({
                 'title': item.get('headline', ''),
                 'summary': item.get('summary', ''),
                 'providerPublishTime': item.get('created_at', ''),
                 'url': item.get('url', ''),
                 'source': item.get('source', ''),
             })

        analyzed_news = analyze_news(normalized)

        # Calculate aggregate sentiment
        avg_score = 0
        if analyzed_news:
            avg_score = sum(item['score'] for item in analyzed_news) / len(analyzed_news)

        payload = {
            'items': analyzed_news,
            'aggregate_score': avg_score,
            'aggregate_label': 'bullish' if avg_score > 0.1 else 'bearish' if avg_score < -0.1 else 'neutral'
        }
        return self._set_cached_payload(self._news_cache, cache_key, payload, NEWS_CACHE_TTL_SECONDS)
