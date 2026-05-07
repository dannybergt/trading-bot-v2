import base64
import os
import unittest

from py_vapid import Vapid

from app.push_service import PushConfigurationError, PushService


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _generate_vapid_pair() -> tuple[str, str]:
    vapid = Vapid()
    vapid.generate_keys()
    private_numbers = vapid.private_key.private_numbers()
    public_numbers = vapid.public_key.public_numbers()
    private_key = _encode_base64url(int(private_numbers.private_value).to_bytes(32, "big"))
    public_key = _encode_base64url(
        b"\x04"
        + int(public_numbers.x).to_bytes(32, "big")
        + int(public_numbers.y).to_bytes(32, "big")
    )
    return public_key, private_key


class PushServiceConfigurationTests(unittest.TestCase):
    def setUp(self):
        self._saved_env = {
            "APP_ENV": os.environ.get("APP_ENV"),
            "ENVIRONMENT": os.environ.get("ENVIRONMENT"),
            "REQUIRE_VAPID_SECRETS": os.environ.get("REQUIRE_VAPID_SECRETS"),
            "VAPID_PUBLIC_KEY": os.environ.get("VAPID_PUBLIC_KEY"),
            "VAPID_PRIVATE_KEY": os.environ.get("VAPID_PRIVATE_KEY"),
            "VAPID_CLAIMS_SUB": os.environ.get("VAPID_CLAIMS_SUB"),
        }
        for key in self._saved_env:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_missing_vapid_keys_leave_push_unconfigured_for_local_runs(self):
        status = PushService.validate_configuration()

        self.assertFalse(status["configured"])
        self.assertFalse(status["required"])
        self.assertFalse(PushService.is_configured())

    def test_missing_vapid_keys_fail_when_required(self):
        os.environ["REQUIRE_VAPID_SECRETS"] = "true"

        with self.assertRaises(PushConfigurationError):
            PushService.validate_configuration()

    def test_missing_vapid_keys_fail_in_production(self):
        os.environ["APP_ENV"] = "production"

        with self.assertRaises(PushConfigurationError):
            PushService.validate_configuration()

    def test_valid_vapid_pair_is_accepted(self):
        public_key, private_key = _generate_vapid_pair()
        os.environ["VAPID_PUBLIC_KEY"] = public_key
        os.environ["VAPID_PRIVATE_KEY"] = private_key
        os.environ["VAPID_CLAIMS_SUB"] = "mailto:alerts@example.com"

        status = PushService.validate_configuration(require_config=True)

        self.assertTrue(status["configured"])
        self.assertTrue(status["required"])
        self.assertEqual(status["public_key"], public_key)
        self.assertEqual(status["claims"], {"sub": "mailto:alerts@example.com"})

    def test_partial_or_mismatched_vapid_configuration_fails(self):
        public_key, private_key = _generate_vapid_pair()
        os.environ["VAPID_PUBLIC_KEY"] = public_key
        os.environ["VAPID_CLAIMS_SUB"] = "mailto:alerts@example.com"

        with self.assertRaises(PushConfigurationError):
            PushService.validate_configuration()

        other_public_key, _ = _generate_vapid_pair()
        os.environ["VAPID_PRIVATE_KEY"] = private_key
        os.environ["VAPID_PUBLIC_KEY"] = other_public_key

        with self.assertRaises(PushConfigurationError):
            PushService.validate_configuration()


if __name__ == "__main__":
    unittest.main()
