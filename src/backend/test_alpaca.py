import sys
sys.path.append('/app')
from app.alpaca_service import AlpacaService

alpaca = AlpacaService()
print("==== NEWS ====")
try:
    news = alpaca.get_news("AAPL")
    print(news)
except Exception as e:
    print("NEWS ERROR:", e)

print("==== BARS ====")
try:
    bars = alpaca.get_bars_df("AAPL", limit=5)
    print(bars)
except Exception as e:
    print("BARS ERROR:", e)
