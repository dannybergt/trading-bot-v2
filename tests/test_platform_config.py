"""Platform-configuration service tests.

Covers the operator-managed-keys path:
  * encrypt/decrypt round-trip via the same Fernet wrapper used for Alpaca
  * DB > env > None precedence
  * 60s in-memory cache + explicit invalidate()
  * allow-list enforcement (set/delete rejects unmanaged keys)
  * list_status diagnostic shape
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import platform_config
from app.database import Base
from app.models import PlatformConfiguration, User  # noqa: F401 — register models


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return Session()


class PlatformConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        platform_config.invalidate()
        # Don't leak between tests — clear the targeted env var bag
        for key in platform_config.MANAGED_KEYS:
            os.environ.pop(key, None)

    def test_managed_keys_locked_to_allowlist(self):
        self.assertIn("ALPHA_VANTAGE_API_KEY", platform_config.MANAGED_KEYS)
        self.assertNotIn("JWT_SECRET", platform_config.MANAGED_KEYS)
        self.assertNotIn("APP_ENCRYPTION_KEY", platform_config.MANAGED_KEYS)
        self.assertNotIn("POSTGRES_PASSWORD", platform_config.MANAGED_KEYS)

    def test_set_then_get_roundtrip(self):
        db = _make_session()
        platform_config.set_value(db, "ALPHA_VANTAGE_API_KEY", "av-secret-1", updated_by_user_id=None)
        db.commit()
        self.assertEqual(
            platform_config.get_value(db, "ALPHA_VANTAGE_API_KEY"),
            "av-secret-1",
        )

    def test_stored_value_is_encrypted_at_rest(self):
        db = _make_session()
        platform_config.set_value(db, "FMP_API_KEY", "fmp-secret-xyz", updated_by_user_id=None)
        db.commit()
        row = db.query(PlatformConfiguration).filter_by(key="FMP_API_KEY").one()
        self.assertTrue(row.encrypted_value.startswith("enc:"))
        self.assertNotIn("fmp-secret-xyz", row.encrypted_value)

    def test_db_value_wins_over_env(self):
        db = _make_session()
        os.environ["ALPHA_VANTAGE_API_KEY"] = "env-value"
        try:
            platform_config.set_value(db, "ALPHA_VANTAGE_API_KEY", "db-value", updated_by_user_id=None)
            db.commit()
            self.assertEqual(
                platform_config.get_value(db, "ALPHA_VANTAGE_API_KEY"),
                "db-value",
            )
        finally:
            os.environ.pop("ALPHA_VANTAGE_API_KEY", None)

    def test_env_fallback_when_no_db_row(self):
        db = _make_session()
        os.environ["FMP_API_KEY"] = "env-only"
        try:
            self.assertEqual(
                platform_config.get_value(db, "FMP_API_KEY"),
                "env-only",
            )
        finally:
            os.environ.pop("FMP_API_KEY", None)

    def test_unconfigured_returns_none(self):
        db = _make_session()
        self.assertIsNone(platform_config.get_value(db, "TWELVE_DATA_API_KEY"))

    def test_delete_falls_back_to_env(self):
        db = _make_session()
        platform_config.set_value(db, "FRED_API_KEY", "db-fred", updated_by_user_id=None)
        db.commit()
        os.environ["FRED_API_KEY"] = "env-fred"
        try:
            self.assertEqual(platform_config.get_value(db, "FRED_API_KEY"), "db-fred")
            removed = platform_config.delete_value(db, "FRED_API_KEY")
            db.commit()
            self.assertTrue(removed)
            self.assertEqual(platform_config.get_value(db, "FRED_API_KEY"), "env-fred")
        finally:
            os.environ.pop("FRED_API_KEY", None)

    def test_set_rejects_unmanaged_key(self):
        db = _make_session()
        with self.assertRaises(ValueError):
            platform_config.set_value(db, "JWT_SECRET", "evil", updated_by_user_id=None)

    def test_delete_rejects_unmanaged_key(self):
        db = _make_session()
        with self.assertRaises(ValueError):
            platform_config.delete_value(db, "JWT_SECRET")

    def test_invalidate_drops_specific_key(self):
        db = _make_session()
        platform_config.set_value(db, "COINGECKO_API_KEY", "v1", updated_by_user_id=None)
        db.commit()
        self.assertEqual(platform_config.get_value(db, "COINGECKO_API_KEY"), "v1")
        # Mutate directly without invalidate() — the cache should still hold v1
        row = db.query(PlatformConfiguration).filter_by(key="COINGECKO_API_KEY").one()
        from app.auth import encrypt_secret

        row.encrypted_value = encrypt_secret("v2")
        db.commit()
        self.assertEqual(platform_config.get_value(db, "COINGECKO_API_KEY"), "v1")
        platform_config.invalidate("COINGECKO_API_KEY")
        self.assertEqual(platform_config.get_value(db, "COINGECKO_API_KEY"), "v2")

    def test_list_status_shape(self):
        db = _make_session()
        platform_config.set_value(db, "ALPHA_VANTAGE_API_KEY", "dbval", updated_by_user_id=None)
        db.commit()
        os.environ["FMP_API_KEY"] = "envval"
        try:
            status = {item.key: item for item in platform_config.list_status(db)}
        finally:
            os.environ.pop("FMP_API_KEY", None)
        self.assertEqual(status["ALPHA_VANTAGE_API_KEY"].source, "db")
        self.assertTrue(status["ALPHA_VANTAGE_API_KEY"].configured)
        self.assertEqual(status["FMP_API_KEY"].source, "env")
        self.assertTrue(status["FMP_API_KEY"].configured)
        self.assertEqual(status["TWELVE_DATA_API_KEY"].source, "unconfigured")
        self.assertFalse(status["TWELVE_DATA_API_KEY"].configured)
        # No raw value field — verify by inspecting the dataclass shape
        self.assertFalse(hasattr(status["ALPHA_VANTAGE_API_KEY"], "value"))

    def test_empty_string_treated_as_none(self):
        db = _make_session()
        os.environ["ALPHA_VANTAGE_API_KEY"] = ""
        try:
            self.assertIsNone(platform_config.get_value(db, "ALPHA_VANTAGE_API_KEY"))
        finally:
            os.environ.pop("ALPHA_VANTAGE_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
