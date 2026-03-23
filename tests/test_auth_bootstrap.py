import os
import unittest

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import ensure_initial_admin, verify_password
from app.database import Base
from app.models import User


class InitialAdminBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)()
        self._saved_env = {
            "INITIAL_ADMIN_EMAIL": os.environ.get("INITIAL_ADMIN_EMAIL"),
            "INITIAL_ADMIN_PASSWORD": os.environ.get("INITIAL_ADMIN_PASSWORD"),
            "INITIAL_ADMIN_MFA_ENABLED": os.environ.get("INITIAL_ADMIN_MFA_ENABLED"),
        }

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_ensure_initial_admin_creates_admin_without_mfa_by_default(self):
        os.environ["INITIAL_ADMIN_EMAIL"] = "superadmin@example.com"
        os.environ["INITIAL_ADMIN_PASSWORD"] = "super-secret-123"
        os.environ.pop("INITIAL_ADMIN_MFA_ENABLED", None)

        user = ensure_initial_admin(self.session)

        self.assertIsNotNone(user)
        self.assertEqual(user.email, "superadmin@example.com")
        self.assertTrue(user.is_admin)
        self.assertFalse(user.mfa_enabled)
        self.assertTrue(verify_password("super-secret-123", user.hashed_password))

    def test_ensure_initial_admin_promotes_existing_user(self):
        existing = User(
            email="admin@example.com",
            hashed_password="old-hash",
            is_admin=False,
            is_active=False,
            mfa_enabled=True,
            mfa_secret="SECRET",
        )
        self.session.add(existing)
        self.session.commit()

        os.environ["INITIAL_ADMIN_EMAIL"] = "admin@example.com"
        os.environ["INITIAL_ADMIN_PASSWORD"] = "replacement-123"
        os.environ["INITIAL_ADMIN_MFA_ENABLED"] = "false"

        user = ensure_initial_admin(self.session)

        self.assertEqual(user.id, existing.id)
        self.assertTrue(user.is_admin)
        self.assertTrue(user.is_active)
        self.assertFalse(user.mfa_enabled)
        self.assertIsNone(user.mfa_secret)
        self.assertTrue(verify_password("replacement-123", user.hashed_password))

    def test_partial_initial_admin_configuration_fails_fast(self):
        os.environ["INITIAL_ADMIN_EMAIL"] = "admin@example.com"
        os.environ.pop("INITIAL_ADMIN_PASSWORD", None)

        with self.assertRaises(RuntimeError):
            ensure_initial_admin(self.session)


if __name__ == "__main__":
    unittest.main()
