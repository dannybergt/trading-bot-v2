"""Der Stammdatenabruf, den der Aufrufer ausgeschlossen hatte.

Hintergrund: `get_stock_data` schaerft die Anlageklasse nach, indem es die
Stammdaten holt — yfinance `.info`, der teuerste Aufruf dieses Dienstes und
derjenige, der unter Drosselung `429` liefert und bis zum Wall-Clock-Limit
haengt. Das lief auch dann, wenn der Aufrufer `include_fundamentals=False`
gesetzt hatte. Gemessen am 2026-08-11 im Alarm-Pfad: vier Aufrufe pro
Aktien-Symbol, darunter dieser.

Geprueft wird getrennt:
  1. mit mitgegebenem Profil faellt der Stammdatenabruf weg,
  2. die mitgegebene Einstufung wird auch nicht still ueberschrieben,
  3. ohne mitgegebenes Profil bleibt die Nachschaerfung erhalten — die
     Hintergrundschleifen haben kein Profil zur Hand und niemand wartet dort
     vor einem Bildschirm,
  4. der Alarm-Pfad gibt das Profil ueberhaupt mit. Ohne (4) waeren (1) bis (3)
     gruen und trotzdem wirkungslos.
"""
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services import MarketDataService  # noqa: E402


ETF_PROFILE = {
    "symbol": "VOO",
    "name": "Vanguard S&P 500 ETF",
    "assetClass": "etf",
    "assetLabel": "ETF",
    "market": "equity",
    "exchange": "NYSEARCA",
    "type": "ETF",
    "isCrypto": False,
}

STOCK_PROFILE = {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "assetClass": "stock",
    "assetLabel": "Stock",
    "market": "equity",
    "exchange": "NASDAQ",
    "type": "STOCK",
    "isCrypto": False,
}


class _FakePredictor:
    is_trained = True

    def train(self, df):
        return {"accuracy": 0.0, "features": []}

    def predict_next_movement(self, df, *, user=None):
        return {"direction": "HOLD", "confidence": 0.0}


def _service_without_providers(symbol: str) -> MarketDataService:
    """Dienst ohne Anbieter; der Predictor kommt aus dem Cache, damit der Lauf
    nicht ueber die Plattenpersistenz geht."""
    service = MarketDataService()
    service._predictor_cache[symbol] = {
        "predictor": _FakePredictor(),
        "metadata": None,
        "expires_at": float("inf"),
    }
    return service


class CallerProfileTests(unittest.TestCase):
    def test_supplied_profile_skips_the_fundamentals_lookup(self):
        # Das Profil muss hier auf `stock` lauten: nur dann greift die
        # Nachschaerfung ueberhaupt. Mit einem ETF-Profil waere der Fall auch
        # ohne den Schutz gruen — er wuerde nichts belegen.
        service = _service_without_providers("AAPL")

        with patch.object(service, "get_ticker_info", return_value={}) as ticker_info, patch.object(
            service, "get_provider_history_df", return_value=pd.DataFrame()
        ), patch.object(service, "get_yfinance_history_df", return_value=pd.DataFrame()):
            service.get_stock_data(
                "AAPL",
                period="1mo",
                interval="1h",
                include_news=False,
                include_fundamentals=False,
                asset_profile=dict(STOCK_PROFILE),
            )

        ticker_info.assert_not_called()

    def test_supplied_profile_is_not_silently_overwritten(self):
        # Auch wenn die Stammdaten geholt werden (Kennzahlen), bleibt die
        # Einstufung die des Aufrufers — sonst weicht die Klasse im Ergebnis
        # von der ab, die der Nutzer in der Karte sieht.
        service = _service_without_providers("VOO")

        with patch.object(
            service, "get_ticker_info", return_value={"quoteType": "EQUITY", "trailingPE": 21.5}
        ), patch.object(service, "get_provider_history_df", return_value=pd.DataFrame()), patch.object(
            service, "get_yfinance_history_df", return_value=pd.DataFrame()
        ):
            payload = service.get_stock_data(
                "VOO",
                period="1mo",
                interval="1d",
                include_news=False,
                include_fundamentals=True,
                asset_profile=dict(ETF_PROFILE),
            )

        self.assertEqual(payload["asset"]["assetClass"], "etf")
        self.assertEqual(payload["info"]["assetClass"], "etf")
        self.assertEqual(payload["info"]["shortName"], "Vanguard S&P 500 ETF")

    def test_without_a_supplied_profile_the_refinement_stays(self):
        # Zusage fuer die Hintergrundschleifen (Auto-Scanner, ML-Retrain): sie
        # haben kein Profil zur Hand, und fuer sie war der Aufruf nie das
        # Problem — dort wartet niemand vor einem Bildschirm.
        service = _service_without_providers("VOO")

        with patch.object(
            service, "get_ticker_info", return_value={"quoteType": "ETF", "shortName": "Vanguard S&P 500 ETF"}
        ) as ticker_info, patch.object(
            service, "get_provider_history_df", return_value=pd.DataFrame()
        ), patch.object(service, "get_yfinance_history_df", return_value=pd.DataFrame()):
            payload = service.get_stock_data(
                "VOO",
                period="1mo",
                interval="1h",
                include_news=False,
                include_fundamentals=False,
            )

        ticker_info.assert_called()
        self.assertEqual(payload["asset"]["assetClass"], "etf")


class AlertRequestPathTests(unittest.TestCase):
    """Der stille Rueckweg: das Profil ist ein Schluesselwort-Argument mit
    Default. Gibt der Endpunkt es nicht mit, greift nichts von alledem."""

    def test_alert_payload_hands_the_tracked_profile_to_the_analysis(self):
        from app import main as app_main

        record = MagicMock()
        record.id = "wl_profile"
        item = MagicMock()
        item.id = 1
        record.items = [item]

        tracked = {
            "symbol": "VOO",
            "name": "Vanguard S&P 500 ETF",
            "tags": [],
            "assetClass": "etf",
            "assetLabel": "ETF",
            "market": "equity",
            "exchange": "NYSEARCA",
            "type": "ETF",
            "isCrypto": False,
            "provider": {},
        }
        seen: list = []

        def record_call(symbol, **kwargs):
            seen.append(kwargs.get("asset_profile"))
            return {}

        with patch.object(app_main, "get_or_create_watchlist_alert_setting", return_value=MagicMock()), \
             patch.object(app_main, "serialize_tracked_watchlist_item", return_value=tracked), \
             patch.object(app_main, "apply_alert_notifications", return_value={"popupCount": 0, "pushCount": 0}), \
             patch.object(app_main.service, "get_stock_data", side_effect=record_call), \
             patch.object(app_main.service, "get_market_news", return_value={}):
            app_main.build_watchlist_alert_payload(MagicMock(), MagicMock(), record)

        self.assertEqual(
            seen,
            [tracked],
            "der Alarm-Pfad analysiert ohne das Profil des Eintrags — der "
            "Stammdatenabruf pro Symbol bleibt damit bestehen",
        )


if __name__ == "__main__":
    unittest.main()
