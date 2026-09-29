"""Push endpoints are user-controlled outbound URLs; only browser push services pass.

The server POSTs every alert to the stored endpoint and reads the answer, so an
unchecked endpoint is an SSRF into the private network and an unbounded
decompression target for urllib3 <2 (ADR 2026-09-29).
"""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
if BACKEND.exists():
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from pydantic import ValidationError  # noqa: E402

from app import push_service  # noqa: E402
from app.auth_routes import PushSubscriptionRequest  # noqa: E402
from app.push_service import PushService, is_allowed_push_endpoint  # noqa: E402

ALLOWED = (
    "https://fcm.googleapis.com/fcm/send/abc:def",
    "https://updates.push.services.mozilla.com/wpush/v2/gAAAA",
    "https://web.push.apple.com/QGx0",
    "https://wns2-par02p.notify.windows.com/w/?token=x",
)
REFUSED = (
    "http://fcm.googleapis.com/fcm/send/abc",  # not https
    "https://10.0.0.5/push",  # private network
    "https://backend:8000/api/health",  # compose service name
    "https://fcm.googleapis.com.evil.example/x",  # suffix trick
    "https://evilnotify.windows.com/x",  # suffix without the dot
    "https://user@fcm.googleapis.com/x",  # userinfo
    "https://fcm.googleapis.com:8443/x",  # other port
    "https://fcm.googleapis.com:99999/x",  # invalid port
    "file:///etc/passwd",
    "",
)


class PushEndpointAllowlistTests(unittest.TestCase):
    def test_browser_push_services_pass(self):
        for url in ALLOWED:
            with self.subTest(url=url):
                self.assertTrue(is_allowed_push_endpoint(url))

    def test_other_urls_are_refused(self):
        for url in REFUSED:
            with self.subTest(url=url):
                self.assertFalse(is_allowed_push_endpoint(url))

    def test_subscribe_schema_refuses_a_private_endpoint(self):
        with self.assertRaises(ValidationError):
            PushSubscriptionRequest(endpoint="https://10.0.0.5/push", p256dh="k", auth="a")
        ok = PushSubscriptionRequest(endpoint=ALLOWED[0], p256dh="k", auth="a")
        self.assertEqual(ALLOWED[0], ok.endpoint)

    def test_subscribe_schema_caps_field_lengths(self):
        with self.assertRaises(ValidationError):
            PushSubscriptionRequest(endpoint=ALLOWED[0] + "x" * 2100, p256dh="k", auth="a")
        with self.assertRaises(ValidationError):
            PushSubscriptionRequest(endpoint=ALLOWED[0], p256dh="k" * 300, auth="a")

    def test_stored_row_with_a_foreign_endpoint_is_never_contacted(self):
        rows = [
            SimpleNamespace(endpoint="http://169.254.169.254/latest", p256dh="k", auth="a"),
            SimpleNamespace(endpoint=ALLOWED[0], p256dh="k", auth="a"),
        ]
        config = {"configured": True, "private_key": "p", "claims": {"sub": "mailto:x@example.com"}}
        with mock.patch.object(push_service, "validate_vapid_configuration", return_value=config), \
                mock.patch.object(push_service, "webpush") as sent:
            count = PushService.send_to_subscriptions(rows, {"title": "t"}, db=mock.Mock())
        self.assertEqual(1, count)
        self.assertEqual(1, sent.call_count)
        self.assertEqual(ALLOWED[0], sent.call_args.kwargs["subscription_info"]["endpoint"])
        self.assertEqual(10, sent.call_args.kwargs["timeout"])


if __name__ == "__main__":
    unittest.main()
