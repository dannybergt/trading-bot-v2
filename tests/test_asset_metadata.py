import unittest

from app.asset_metadata import (
    build_asset_profile,
    canonicalize_symbol,
    infer_asset_class,
    is_plausible_symbol_query,
    to_yfinance_symbol,
)


class AssetMetadataTests(unittest.TestCase):
    def test_infer_asset_class_from_alpaca_crypto_asset(self):
        asset = {"symbol": "BTC/USD", "asset_class": "crypto", "name": "Bitcoin"}
        self.assertEqual(infer_asset_class("BTC/USD", asset=asset), "crypto")

    def test_infer_asset_class_from_etf_attribute(self):
        asset = {
            "symbol": "QQQ",
            "asset_class": "us_equity",
            "attributes": ["etf"],
            "name": "Invesco QQQ Trust",
        }
        self.assertEqual(infer_asset_class("QQQ", asset=asset), "etf")

    def test_infer_asset_class_from_symbol_fallback(self):
        self.assertEqual(infer_asset_class("BTC-USD"), "crypto")
        self.assertEqual(infer_asset_class("AAPL"), "stock")

    def test_build_asset_profile_returns_normalized_fields(self):
        profile = build_asset_profile("BTC-USD", fallback_name="Bitcoin")
        self.assertEqual(profile["symbol"], "BTC/USD")
        self.assertEqual(profile["assetClass"], "crypto")
        self.assertEqual(profile["assetLabel"], "Crypto")
        self.assertEqual(profile["type"], "CRYPTO")
        self.assertTrue(profile["isCrypto"])

    def test_build_asset_profile_uses_fallback_name_for_etf_hint(self):
        profile = build_asset_profile("VOO", fallback_name="Vanguard S&P 500 ETF")
        self.assertEqual(profile["assetClass"], "etf")
        self.assertEqual(profile["assetLabel"], "ETF")
        self.assertEqual(profile["type"], "ETF")
        self.assertFalse(profile["isCrypto"])

    def test_symbol_helpers_normalize_crypto_pairs(self):
        self.assertEqual(canonicalize_symbol("btc-usd"), "BTC/USD")
        self.assertEqual(to_yfinance_symbol("BTC/USD"), "BTC-USD")
        self.assertTrue(is_plausible_symbol_query("BTC/USD"))
        self.assertFalse(is_plausible_symbol_query("APPLE INC"))


if __name__ == "__main__":
    unittest.main()
