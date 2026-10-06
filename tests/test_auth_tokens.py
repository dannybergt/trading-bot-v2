"""JWT access/refresh tokens: what decode_token and get_current_user accept.

The forged tokens are built by hand (base64url + HMAC), not with the JWT
library under test, so each case still holds when the library is swapped
(python-jose -> PyJWT, ADR 2026-10-06) and turns red if a check is lost:
signature, algorithm allow-list (incl. alg=none), expiry, token type.
"""
import base64
import hashlib
import hmac
import json
import os
import time
import unittest

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import auth
from app.database import Base
from app.models import User


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _forge(payload: dict, *, secret: str | None = None, alg: str = "HS256") -> str:
    header = _b64(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    body = _b64(json.dumps(payload).encode())
    signing_input = f"{header}.{body}".encode("ascii")
    if alg == "none":
        return f"{header}.{body}."
    digest = {"HS256": hashlib.sha256, "HS384": hashlib.sha384, "HS512": hashlib.sha512}[alg]
    key = (secret if secret is not None else auth.JWT_SECRET).encode()
    return f"{header}.{body}.{_b64(hmac.new(key, signing_input, digest).digest())}"


def _claims(**overrides) -> dict:
    claims = {"sub": "1", "email": "a@example.com", "type": "access", "exp": int(time.time()) + 3600}
    claims.update(overrides)
    return claims


class DecodeTokenTests(unittest.TestCase):
    def test_issued_access_token_round_trips(self):
        payload = auth.decode_token(auth.create_access_token(7, "u@example.com"))
        self.assertEqual(payload["sub"], "7")
        self.assertEqual(payload["email"], "u@example.com")
        self.assertEqual(payload["type"], "access")
        self.assertIsInstance(payload["exp"], int)
        self.assertGreater(payload["exp"], time.time() + 23 * 3600)

    def test_issued_refresh_token_round_trips(self):
        payload = auth.decode_token(auth.create_refresh_token(7))
        self.assertEqual(payload["sub"], "7")
        self.assertEqual(payload["type"], "refresh")
        self.assertGreater(payload["exp"], time.time() + 6 * 86400)

    def test_issued_token_is_hs256(self):
        header = auth.create_access_token(1, "a@example.com").split(".")[0]
        header += "=" * (-len(header) % 4)
        self.assertEqual(json.loads(base64.urlsafe_b64decode(header))["alg"], "HS256")

    def test_token_signed_like_before_the_swap_still_decodes(self):
        # Tokens minted by python-jose before the deploy: plain HS256 with an
        # integer exp. Sessions must survive the library change.
        self.assertEqual(auth.decode_token(_forge(_claims()))["sub"], "1")

    def test_expired_token_is_rejected(self):
        self.assertIsNone(auth.decode_token(_forge(_claims(exp=int(time.time()) - 10))))

    def test_wrong_secret_is_rejected(self):
        self.assertIsNone(auth.decode_token(_forge(_claims(), secret="x" * 32)))

    def test_tampered_payload_is_rejected(self):
        header, _, signature = _forge(_claims()).split(".")
        body = _b64(json.dumps(_claims(sub="2")).encode())
        self.assertIsNone(auth.decode_token(f"{header}.{body}.{signature}"))

    def test_alg_none_is_rejected(self):
        self.assertIsNone(auth.decode_token(_forge(_claims(), alg="none")))

    def test_other_hmac_algorithm_is_rejected(self):
        # Correct secret, valid signature, but not the one allowed algorithm.
        self.assertIsNone(auth.decode_token(_forge(_claims(), alg="HS512")))

    def test_non_string_subject_is_rejected(self):
        self.assertIsNone(auth.decode_token(_forge(_claims(sub=1))))

    def test_garbage_is_rejected(self):
        for token in ("", "abc", "a.b.c", "....", _forge(_claims())[:-4]):
            with self.subTest(token=token):
                self.assertIsNone(auth.decode_token(token))


class GetCurrentUserTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)()
        self.user = User(email="u@example.com", hashed_password="x", is_active=True)
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _call(self, token: str):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        return auth.get_current_user(creds, self.db)

    def _assert_401(self, token: str):
        with self.assertRaises(HTTPException) as ctx:
            self._call(token)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_valid_access_token_returns_user(self):
        self.assertEqual(self._call(auth.create_access_token(self.user.id, self.user.email)).id, self.user.id)

    def test_refresh_token_is_not_an_access_token(self):
        self._assert_401(auth.create_refresh_token(self.user.id))

    def test_expired_token_is_401(self):
        self._assert_401(_forge(_claims(sub=str(self.user.id), exp=int(time.time()) - 10)))

    def test_forged_signature_is_401(self):
        self._assert_401(_forge(_claims(sub=str(self.user.id)), secret="y" * 32))

    def test_alg_none_is_401(self):
        self._assert_401(_forge(_claims(sub=str(self.user.id)), alg="none"))


if __name__ == "__main__":
    unittest.main()
