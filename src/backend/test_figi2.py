from app.figi_service import figi
print("ISIN Apple:", figi.get_ticker_by_isin("US0378331005"))
print("WKN Apple:", figi.get_ticker_by_wkn("865985"))
