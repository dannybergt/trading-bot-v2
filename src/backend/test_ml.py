from app.services import MarketDataService
from app.alpaca_service import AlpacaService
import warnings
warnings.filterwarnings("ignore")

def test_ml():
    alpaca = AlpacaService()
    service = MarketDataService(alpaca)
    
    print("Fetching data and running ML ...")
    result = service.get_stock_data("AAPL", period="1y", interval="1d")
    
    # Check if prediction is non-null and valid
    prediction = result.get('prediction', None)
    
    if prediction:
        print(f"Prediction Success: {prediction}")
    else:
        print("Prediction is None.")

if __name__ == "__main__":
    test_ml()
