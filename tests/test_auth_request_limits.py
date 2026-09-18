"""Grenzen am Auth-Body und am Registrieren.

Die Login-Sperre ist auf die getippte E-Mail geschluesselt, vor jeder
Kontenpruefung. Ohne Laengengrenze bestimmt der Aufrufer, was der Prozess
haelt: drei Logins mit je 200 kB "Adresse" hielten 600 kB (security-reviewer
2026-09-18, HOCH, Vorbestand seit dem ersten Limiter). RFC 5321 erlaubt 254
Zeichen — mehr ist kein Login-Versuch. Und Registrieren ist offen: jedes
Konto ist ein Anteil an der Backtest-Warteschlange, also zaehlt es je Adresse.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import auth_routes  # noqa: E402


class AuthBodyLimitTests(unittest.TestCase):
    def test_email_and_password_are_bounded_at_the_boundary(self):
        for model, field in (
            (auth_routes.LoginRequest, "email"),
            (auth_routes.RegisterRequest, "email"),
            (auth_routes.PasswordResetRequest, "email"),
        ):
            with self.subTest(model=model.__name__):
                payload = {"email": "a" * 300, "password": "p" * 12}
                with self.assertRaises(ValidationError):
                    model(**payload)
                payload["email"] = "a" * auth_routes.EMAIL_MAX_LENGTH
                model(**payload)  # die Grenze selbst ist erlaubt
        with self.assertRaises(ValidationError):
            auth_routes.LoginRequest(email="a@b.c", password="p" * 2000)
        with self.assertRaises(ValidationError):
            auth_routes.PasswordResetConfirm(token="t" * 600, new_password="p" * 12)


class RegisterLimitTests(unittest.TestCase):
    def setUp(self):
        auth_routes._RATE_LIMITS["register"].reset()
        self.addCleanup(auth_routes._RATE_LIMITS["register"].reset)

    def _request(self, host):
        request = MagicMock()
        request.client.host = host
        return request

    def test_sixth_registration_from_one_address_is_refused(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        req = auth_routes.RegisterRequest(email="new@example.com", password="p" * 12)
        with patch.object(auth_routes, "seed_default_watchlists"), \
             patch.object(auth_routes.audit_service, "log_event"), \
             patch.object(auth_routes, "hash_password", return_value="x"):
            for _ in range(auth_routes._RATE_LIMITS["register"].limit):
                auth_routes.register(req, self._request("203.0.113.9"), db=db)
            with self.assertRaises(HTTPException) as caught:
                auth_routes.register(req, self._request("203.0.113.9"), db=db)
            self.assertEqual(429, caught.exception.status_code)
            # Eine andere Adresse ist unbeeinflusst.
            auth_routes.register(req, self._request("203.0.113.10"), db=db)


if __name__ == "__main__":
    unittest.main()
