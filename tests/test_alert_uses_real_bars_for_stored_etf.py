"""Der Alarm eines ETF-Eintrags darf nicht auf Platzhalterdaten ruhen.

Anlass (Review 2026-08-11, Befund W1): sobald der Alarm-Pfad die Einstufung des
Eintrags benutzte statt sie ueber die Stammdaten nachzuschaerfen, fiel ein
ETF-Eintrag ohne aussagekraeftigen Namen auf `_generate_mock_data` zurueck —
Alpaca liefert nichts, Alpha Vantage wird fuer die Klasse `stock` gar nicht
gefragt, und der yfinance-Fallback greift bei `interval="1h"` nicht. Die Folge
ist nicht kosmetisch: die Empfehlung wird auf `HOLD`/`0.0` gezwungen, der
`priorityScore` faellt, und der Alarm kann dadurch unter die Schwelle des
Nutzers rutschen und **gar nicht mehr zugestellt** werden.

Die Bedingung wird hier hergestellt, nicht unterstellt: kein Alpaca, Alpha
Vantage antwortet, der Anzeigename gibt keinen Hinweis, Intervall `1h`.
"""
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services import MarketDataService  # noqa: E402


class _AlphaVantageAntwortet:
    """Wie das Original: liefert Historie nur fuer `etf` und `crypto`."""

    def is_configured(self):
        return True

    def get_history_df(self, symbol, asset_class, *, limit=100):
        if asset_class not in {"etf", "crypto"}:
            return pd.DataFrame()
        closes = [500.0 + index for index in range(60)]
        return pd.DataFrame(
            {
                "Open": closes,
                "High": [value + 1.0 for value in closes],
                "Low": [value - 1.0 for value in closes],
                "Close": closes,
                "Volume": [1000.0] * 60,
            },
            index=pd.date_range("2026-05-01", periods=60, freq="D"),
        )

    def get_provider_snapshot(self, symbol, asset_class):
        return None

    def get_news_payload(self, symbol, asset_class, *, limit=15):
        return None


class _Predictor:
    is_trained = True

    def train(self, df):
        return {"accuracy": 0.9, "features": []}

    def predict_next_movement(self, df, *, user=None):
        return {"direction": "UP", "confidence": 0.9}


ETF_OHNE_NAMENSHINWEIS = {
    "symbol": "VOO",
    "name": "Altersvorsorge",
    "tags": [],
    "assetClass": "etf",  # gespeichert, nicht geraten
    "assetLabel": "ETF",
    "market": "equity",
    "exchange": None,
    "type": "ETF",
    "isCrypto": False,
    "provider": {},
}


class AlertRestsOnRealBarsTests(unittest.TestCase):
    def _analyse(self, profil):
        service = MarketDataService(alpha_vantage_service=_AlphaVantageAntwortet())
        service._predictor_cache["VOO"] = {
            "predictor": _Predictor(),
            "metadata": None,
            "expires_at": float("inf"),
        }
        with patch.object(service, "get_market_news", return_value={}):
            return service.get_stock_data(
                "VOO",
                period="1mo",
                interval="1h",
                include_news=False,
                include_fundamentals=False,
                asset_profile=profil,
            )

    def test_stored_etf_class_reaches_the_provider_history(self):
        payload = self._analyse(dict(ETF_OHNE_NAMENSHINWEIS))

        self.assertFalse(
            payload["synthetic"],
            "der Alarm ruht auf Platzhalterdaten — die Empfehlung wird auf HOLD "
            "gezwungen und der Eintrag kann unter die Zustellschwelle fallen",
        )
        self.assertEqual(payload["asset"]["assetClass"], "etf")
        self.assertEqual(payload["prediction"]["direction"], "UP")

    def test_the_gap_is_real_when_the_class_is_wrong(self):
        # Gegenprobe: mit falscher Einstufung faellt derselbe Eintrag auf
        # Platzhalter zurueck. Ohne diesen Fall waere oben nicht zu erkennen,
        # ob die gespeicherte Klasse ueberhaupt den Unterschied macht.
        falsch = dict(ETF_OHNE_NAMENSHINWEIS)
        falsch["assetClass"] = "stock"
        falsch["isCrypto"] = False

        payload = self._analyse(falsch)

        self.assertTrue(payload["synthetic"])
        self.assertEqual(payload["prediction"]["direction"], "HOLD")


if __name__ == "__main__":
    unittest.main()
