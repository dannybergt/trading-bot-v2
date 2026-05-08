"""Data-quality service tests.

Drives the report builder against synthetic research/stock payloads
and verifies the per-field confidence labels, the overall reduction,
the static upgrade-hint rules, and the provider catalogue's
configured-state detection.
"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app import data_quality_service as dq  # noqa: E402


def _full_research_payload() -> dict:
    return {
        "fundamentals": {
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "marketCap": 3_000_000_000_000,
            "trailingPE": 28.5,
            "fmp_source": True,
        },
        "researchDepth": {
            "rating": {"rating": "S+"},
            "estimates": [{"date": "2026"}],
            "cashflow": [{"date": "2025"}],
            "debt": [{"date": "2025"}],
        },
        "researchSignals": {
            "insiderTrades": [{"date": "2026-04-01"}],
            "institutionalHoldings": [{"holder": "Vanguard"}],
            "earningsSurprises": [{"date": "2026-02-01"}],
            "upcomingEarnings": {"date": "2026-08-01"},
        },
        "earningsCalls": [{"date": "2026-Q1"}, {"date": "2025-Q4"}],
        "optionsFlow": {
            "expiry": "2026-06-21",
            "totalCallVolume": 1500,
            "totalPutVolume": 1200,
        },
        "socialSentiment": {
            "combined": {"totalMessages": 25},
        },
        "news": {
            "items": [{"title": "x"}, {"title": "y"}, {"title": "z"}],
            "provider": "Alpaca + FMP",
        },
        "macroContext": {
            "vix": {"value": 14.5},
            "yield10y": {"value": 4.1},
            "dxy": {"value": 105.2},
        },
    }


def _stock_payload(rows: int = 130) -> dict:
    return {
        "chart_data": [{"close": 100 + i} for i in range(rows)],
        "provider": {"source": "Alpaca", "status": "live"},
    }


class DataQualityServiceTests(unittest.TestCase):
    def test_full_payload_yields_high_overall(self):
        report = dq.evaluate_symbol_data_quality(
            symbol="AAPL",
            asset_class="stock",
            research_payload=_full_research_payload(),
            stock_payload=_stock_payload(),
        )
        self.assertEqual("high", report["overall"])
        self.assertEqual([], report["upgradeHints"])
        keys = {field["key"] for field in report["fields"]}
        # Stock-specific fields are present, crypto-specific is not
        self.assertIn("price_history", keys)
        self.assertIn("research_depth", keys)
        self.assertIn("options_flow", keys)
        self.assertNotIn("crypto_metrics", keys)

    def test_empty_research_yields_low_overall_and_upgrade_hints(self):
        # No FMP key set in the test env → hints should fire
        os.environ.pop("FMP_API_KEY", None)
        report = dq.evaluate_symbol_data_quality(
            symbol="AAPL",
            asset_class="stock",
            research_payload={},
            stock_payload={"chart_data": [], "provider": None},
        )
        self.assertEqual("low", report["overall"])
        # FMP-Starter hint must surface when its three fields are missing
        labels = [hint["label"] for hint in report["upgradeHints"]]
        self.assertTrue(any("FMP" in label for label in labels))

    def test_crypto_asset_class_omits_options_and_includes_crypto_metrics(self):
        payload = _full_research_payload()
        payload["cryptoMetrics"] = {"marketCapUsd": 1_300_000_000_000}
        # provider snapshot live for crypto
        payload["provider"] = {"status": "live"}
        report = dq.evaluate_symbol_data_quality(
            symbol="BTC/USD",
            asset_class="crypto",
            research_payload=payload,
            stock_payload=_stock_payload(),
        )
        keys = {f["key"] for f in report["fields"]}
        self.assertIn("crypto_metrics", keys)
        self.assertNotIn("options_flow", keys)

    def test_provider_catalogue_marks_configured_state(self):
        os.environ["FMP_API_KEY"] = "test-key"
        try:
            catalogue = dq.get_provider_catalogue()
            fmp = next(item for item in catalogue if item["key"] == "fmp")
            self.assertTrue(fmp["configured"])
            yfinance = next(item for item in catalogue if item["key"] == "yfinance")
            self.assertTrue(yfinance["configured"])  # No env flag → always configured
        finally:
            os.environ.pop("FMP_API_KEY", None)

    def test_overall_reduction_thresholds(self):
        # 5 full out of 6 → high (5/6 ≈ 83%)
        fields = (
            [{"key": str(i), "confidence": dq.FULL, "provider": "x"} for i in range(5)]
            + [{"key": "missing", "confidence": dq.MISSING, "provider": "x"}]
        )
        self.assertEqual("high", dq._overall_confidence(fields))

        # 2 full + 3 partial out of 6 → medium (5/6 ≈ 83% combined)
        fields = (
            [{"key": "a", "confidence": dq.FULL, "provider": "x"}, {"key": "b", "confidence": dq.FULL, "provider": "x"}]
            + [{"key": str(i), "confidence": dq.PARTIAL, "provider": "x"} for i in range(3)]
            + [{"key": "missing", "confidence": dq.MISSING, "provider": "x"}]
        )
        self.assertEqual("medium", dq._overall_confidence(fields))

        # 1 full + 1 partial out of 5 → low (2/5 = 40%)
        fields = (
            [{"key": "a", "confidence": dq.FULL, "provider": "x"}]
            + [{"key": "b", "confidence": dq.PARTIAL, "provider": "x"}]
            + [{"key": str(i), "confidence": dq.MISSING, "provider": "x"} for i in range(3)]
        )
        self.assertEqual("low", dq._overall_confidence(fields))


if __name__ == "__main__":
    unittest.main()
