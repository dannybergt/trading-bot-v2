import numpy as np
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

def compute_volume_profile(df: pd.DataFrame, *, bins: int = 24) -> dict:
    """Bin OHLCV history by close price and sum the volume per bin.

    Returns a list of `{priceLow, priceHigh, volume}` plus the point-of-control
    (the bin with the most traded volume). The point of control is the price
    level that traders most-revisited inside the timeframe — useful as a
    natural support/resistance level even before the explicit detection layer
    in wave 4.
    """
    empty = {"bins": [], "minPrice": None, "maxPrice": None, "totalVolume": 0.0,
             "pointOfControl": None, "pointOfControlVolume": 0.0}
    if df.empty or "Close" not in df.columns or "Volume" not in df.columns:
        return empty

    prices = df["Close"].dropna()
    if prices.empty:
        return empty

    volumes = df["Volume"].reindex(prices.index).fillna(0.0)
    min_price = float(prices.min())
    max_price = float(prices.max())
    if not np.isfinite(min_price) or not np.isfinite(max_price) or max_price <= min_price:
        return {**empty, "minPrice": min_price, "maxPrice": max_price,
                "totalVolume": float(volumes.sum())}

    edges = np.linspace(min_price, max_price, bins + 1)
    indices = np.clip(np.searchsorted(edges, prices.to_numpy(), side="right") - 1, 0, bins - 1)
    bin_volumes = np.zeros(bins, dtype=float)
    np.add.at(bin_volumes, indices, volumes.to_numpy(dtype=float))

    poc_idx = int(np.argmax(bin_volumes))
    poc_price = float((edges[poc_idx] + edges[poc_idx + 1]) / 2)

    bin_data = [
        {
            "priceLow": float(edges[i]),
            "priceHigh": float(edges[i + 1]),
            "volume": float(bin_volumes[i]),
        }
        for i in range(bins)
    ]

    return {
        "bins": bin_data,
        "minPrice": min_price,
        "maxPrice": max_price,
        "totalVolume": float(bin_volumes.sum()),
        "pointOfControl": poc_price,
        "pointOfControlVolume": float(bin_volumes[poc_idx]),
    }


def detect_support_resistance(df: pd.DataFrame, *, lookback: int = 5, max_levels: int = 6,
                                tolerance_pct: float = 0.5) -> list[dict]:
    """Detect horizontal support/resistance levels via swing-pivot clustering.

    A point is a swing high if its High exceeds the High of every candle in
    the surrounding `lookback` window on both sides; a swing low symmetrically
    on Low. Pivots within `tolerance_pct` of the same price collapse into one
    level whose `strength` counts how many original pivots clustered there.

    Returns a list sorted by strength (descending), capped at `max_levels`.
    Each entry contains:
      - price: representative price for the level
      - kind: "support" | "resistance"
      - strength: cluster size
      - lastTouch: ISO timestamp of the most recent contributing pivot
    """
    levels: list[dict] = []
    if df.empty or len(df) < lookback * 2 + 1:
        return levels
    if "High" not in df.columns or "Low" not in df.columns:
        return levels

    highs = df["High"].to_numpy(dtype=float)
    lows = df["Low"].to_numpy(dtype=float)
    timestamps = df.index

    pivots: list[tuple[str, float, object]] = []  # (kind, price, timestamp)
    for idx in range(lookback, len(df) - lookback):
        left_high = highs[idx - lookback : idx]
        right_high = highs[idx + 1 : idx + lookback + 1]
        if highs[idx] > left_high.max() and highs[idx] > right_high.max():
            pivots.append(("resistance", float(highs[idx]), timestamps[idx]))
        left_low = lows[idx - lookback : idx]
        right_low = lows[idx + 1 : idx + lookback + 1]
        if lows[idx] < left_low.min() and lows[idx] < right_low.min():
            pivots.append(("support", float(lows[idx]), timestamps[idx]))

    if not pivots:
        return levels

    # Cluster pivots within tolerance into representative levels.
    pivots.sort(key=lambda item: item[1])
    clusters: list[dict] = []
    for kind, price, ts in pivots:
        absorbed = False
        for cluster in clusters:
            if abs(price - cluster["price"]) / max(cluster["price"], 1e-9) * 100 <= tolerance_pct:
                cluster["prices"].append(price)
                cluster["touches"].append(ts)
                cluster["price"] = sum(cluster["prices"]) / len(cluster["prices"])
                cluster["kinds"].add(kind)
                absorbed = True
                break
        if not absorbed:
            clusters.append({
                "price": price,
                "prices": [price],
                "kinds": {kind},
                "touches": [ts],
            })

    # Strength = touch count; ties break by recency.
    for cluster in clusters:
        last_touch = max(cluster["touches"])
        if hasattr(last_touch, "isoformat"):
            last_touch_iso = last_touch.isoformat()
        else:
            last_touch_iso = str(last_touch)
        primary_kind = "resistance" if "resistance" in cluster["kinds"] else "support"
        # If the cluster has both kinds it's a flip-zone; surface as resistance
        # when above current price, support when below.
        levels.append({
            "price": round(float(cluster["price"]), 4),
            "kind": primary_kind,
            "strength": len(cluster["touches"]),
            "lastTouch": last_touch_iso,
            "isFlipZone": len(cluster["kinds"]) > 1,
        })

    levels.sort(key=lambda item: (item["strength"], item["lastTouch"]), reverse=True)
    return levels[:max_levels]


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
