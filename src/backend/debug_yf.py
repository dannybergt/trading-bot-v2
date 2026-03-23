
import yfinance as yf
import pandas as pd

print("Testing yfinance...")
try:
    ticker = yf.Ticker("AAPL")
    print("Ticker object created.")
    
    # Try fetching info
    print("Fetching info...")
    try:
        info = ticker.info
        print(f"Info keys: {list(info.keys())[:5]}")
    except Exception as e:
        print(f"Info fetch failed: {e}")

    # Try fetching history
    print("Fetching history (1mo)...")
    df = ticker.history(period="1mo")
    
    if df.empty:
        print("DataFrame is empty!")
    else:
        print(f"Success! Rows: {len(df)}")
        print(df.head())
        
except Exception as e:
    print(f"Major error: {e}")

print("Done.")
