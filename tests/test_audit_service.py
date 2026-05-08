"""Audit-service tests.

Drives the helper against an in-memory SQLite so we exercise the real
SQLAlchemy round-trip plus the fingerprint hashing. The point of
audit-log is reliability under failure, so the swallow-and-warn path
also gets explicit coverage.
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import audit_service
from app.database import Base
from app.models import AuditEvent, User


class AuditServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = Session()
        self.user = User(email="alice@example.com", hashed_password="x", is_active=True)
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_log_event_persists_and_fingerprints_actor(self):
        event = audit_service.log_event(
            self.db,
            user_id=self.user.id,
            action=audit_service.ACTION_AUTH_LOGIN,
            actor_email="alice@example.com",
            ip_address="192.168.1.1",
            user_agent="pytest/1.0",
            details={"mfa_used": True},
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.action, "auth.login")
        self.assertEqual(event.user_id, self.user.id)
        # Email fingerprint is short and stable
        self.assertIsNotNone(event.actor_fingerprint)
        self.assertEqual(16, len(event.actor_fingerprint))
        # Same email yields the same fingerprint
        again = audit_service.log_event(
            self.db,
            user_id=self.user.id,
            action=audit_service.ACTION_AUTH_LOGIN,
            actor_email="alice@example.com",
        )
        self.assertEqual(event.actor_fingerprint, again.actor_fingerprint)
        # Different emails diverge
        self.assertNotEqual(
            event.actor_fingerprint,
            audit_service._fingerprint("bob@example.com"),
        )

    def test_log_event_fingerprints_ip_and_user_agent(self):
        event = audit_service.log_event(
            self.db,
            user_id=self.user.id,
            action=audit_service.ACTION_AUTH_LOGIN,
            ip_address="10.0.0.1",
            user_agent="Mozilla/5.0",
        )
        self.assertIsNotNone(event.ip_fingerprint)
        self.assertIsNotNone(event.user_agent_fingerprint)
        self.assertEqual(16, len(event.ip_fingerprint))

    def test_log_event_serializes_details_as_json(self):
        event = audit_service.log_event(
            self.db,
            user_id=self.user.id,
            action=audit_service.ACTION_PAPER_ORDER_PLACE,
            resource_type="paper_order",
            resource_id=42,
            details={"symbol": "AAPL", "side": "buy", "qty": 10},
        )
        self.assertEqual("42", event.resource_id)
        self.assertEqual("paper_order", event.resource_type)
        self.assertIn("AAPL", event.details_json)

    def test_log_event_returns_none_on_db_failure(self):
        # Inject a stub session whose `add` raises. log_event must
        # swallow the failure and return None — the audit trail must
        # never block the request path.
        from unittest.mock import MagicMock

        broken = MagicMock()
        broken.add.side_effect = RuntimeError("simulated DB failure")
        broken.rollback = MagicMock()
        result = audit_service.log_event(
            broken,
            user_id=self.user.id,
            action="test.failure",
        )
        self.assertIsNone(result)
        broken.rollback.assert_called_once()

    def test_serialize_event_returns_dict_payload(self):
        event = audit_service.log_event(
            self.db,
            user_id=self.user.id,
            action=audit_service.ACTION_AUTH_LOGIN,
            actor_email="alice@example.com",
            details={"mfa_used": False},
        )
        payload = audit_service.serialize_event(event)
        self.assertEqual("auth.login", payload["action"])
        self.assertEqual({"mfa_used": False}, payload["details"])
        self.assertIn("createdAt", payload)

    def test_failed_login_can_be_logged_without_user_id(self):
        # No user_id (failed-login attempt against an unknown email)
        event = audit_service.log_event(
            self.db,
            action=audit_service.ACTION_AUTH_LOGIN_FAILED,
            outcome="failure",
            actor_email="ghost@example.com",
            details={"reason": "invalid_credentials"},
        )
        self.assertIsNotNone(event)
        self.assertIsNone(event.user_id)
        self.assertIsNotNone(event.actor_fingerprint)
        self.assertEqual("failure", event.outcome)


if __name__ == "__main__":
    unittest.main()
