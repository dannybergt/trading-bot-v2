import pandas as pd
import ta

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate technical indicators for the given dataframe.
    Expects DataFrame with columns: 'Open', 'High', 'Low', 'Close', 'Volume'
    """
    df = df.copy()
    
    # RSI
    df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
    
    # MACD
    macd = ta.trend.MACD(df['Close'])
    df['MACD_12_26_9'] = macd.macd()
    df['MACDs_12_26_9'] = macd.macd_signal()
    df['MACDh_12_26_9'] = macd.macd_diff()
    
    # Bollinger Bands
    indicator_bb = ta.volatility.BollingerBands(close=df['Close'], window=20, window_dev=2)
    df['BBU_20_2.0'] = indicator_bb.bollinger_hband()
    df['BBL_20_2.0'] = indicator_bb.bollinger_lband()
    df['BBM_20_2.0'] = indicator_bb.bollinger_mavg()
    
    # SMA / EMA
    df['SMA_20'] = ta.trend.sma_indicator(df['Close'], window=20)
    df['SMA_50'] = ta.trend.sma_indicator(df['Close'], window=50)
    df['SMA_100'] = ta.trend.sma_indicator(df['Close'], window=100)
    df['SMA_200'] = ta.trend.sma_indicator(df['Close'], window=200)
    df['EMA_12'] = ta.trend.ema_indicator(df['Close'], window=12)
    df['EMA_26'] = ta.trend.ema_indicator(df['Close'], window=26)
    
    # ATR (Average True Range)
    df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
    
    # Stochastic Oscillator
    stoch = ta.momentum.StochasticOscillator(df['High'], df['Low'], df['Close'], window=14, smooth_window=3)
    df['STOCH_K'] = stoch.stoch()
    df['STOCH_D'] = stoch.stoch_signal()

    # VWAP (cumulative volume-weighted average price). On daily series this is
    # a running session-style VWAP across the full window; for intraday with a
    # real session boundary the chart layer can reset by date if needed.
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3.0
    cumulative_volume = df['Volume'].cumsum().replace(0, pd.NA)
    df['VWAP'] = (typical_price * df['Volume']).cumsum() / cumulative_volume

    return df

def detect_patterns(df: pd.DataFrame) -> list:
    """
    Detect candlestick patterns in the last few candles.
    """
    patterns = []
    if len(df) < 3:
        return patterns
    
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    
    body_curr = abs(curr['Close'] - curr['Open'])
    body_prev = abs(prev['Close'] - prev['Open'])
    range_curr = curr['High'] - curr['Low']
    
    # Bullish Engulfing
    if (prev['Close'] < prev['Open']) and \
       (curr['Close'] > curr['Open']) and \
       (curr['Close'] > prev['Open']) and \
       (curr['Open'] < prev['Close']):
        patterns.append({'name': 'Bullish Engulfing', 'signal': 'buy', 'timestamp': str(curr.name)})
    
    # Bearish Engulfing
    if (prev['Close'] > prev['Open']) and \
       (curr['Close'] < curr['Open']) and \
       (curr['Open'] > prev['Close']) and \
       (curr['Close'] < prev['Open']):
        patterns.append({'name': 'Bearish Engulfing', 'signal': 'sell', 'timestamp': str(curr.name)})
    
    # Hammer (small body at top, long lower shadow)
    if range_curr > 0:
        lower_shadow = min(curr['Open'], curr['Close']) - curr['Low']
        upper_shadow = curr['High'] - max(curr['Open'], curr['Close'])
        if lower_shadow > 2 * body_curr and upper_shadow < body_curr * 0.5 and body_curr > 0:
            patterns.append({'name': 'Hammer', 'signal': 'buy', 'timestamp': str(curr.name)})
    
    # Shooting Star (small body at bottom, long upper shadow)
    if range_curr > 0:
        lower_shadow = min(curr['Open'], curr['Close']) - curr['Low']
        upper_shadow = curr['High'] - max(curr['Open'], curr['Close'])
        if upper_shadow > 2 * body_curr and lower_shadow < body_curr * 0.5 and body_curr > 0:
            patterns.append({'name': 'Shooting Star', 'signal': 'sell', 'timestamp': str(curr.name)})
    
    # Doji (very small body relative to range)
    if range_curr > 0 and body_curr / range_curr < 0.1:
        patterns.append({'name': 'Doji', 'signal': 'neutral', 'timestamp': str(curr.name)})
    
    # Morning Star (3-candle bullish reversal)
    body_prev2 = abs(prev2['Close'] - prev2['Open'])
    if (prev2['Close'] < prev2['Open']) and \
       (body_prev < body_prev2 * 0.3) and \
       (curr['Close'] > curr['Open']) and \
       (curr['Close'] > (prev2['Open'] + prev2['Close']) / 2):
        patterns.append({'name': 'Morning Star', 'signal': 'buy', 'timestamp': str(curr.name)})
    
    # Evening Star (3-candle bearish reversal)
    if (prev2['Close'] > prev2['Open']) and \
       (body_prev < body_prev2 * 0.3) and \
       (curr['Close'] < curr['Open']) and \
       (curr['Close'] < (prev2['Open'] + prev2['Close']) / 2):
        patterns.append({'name': 'Evening Star', 'signal': 'sell', 'timestamp': str(curr.name)})
    
    return patterns
