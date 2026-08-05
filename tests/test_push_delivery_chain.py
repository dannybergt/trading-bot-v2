"""Guard die Push-Kette vom Service Worker bis zum Endpunkt.

Der Anlass (2026-08-05): die Serverseite war seit Phase 4 vollstaendig —
VAPID-Pruefung beim Start, Watchlist-Dispatcher, Scanner-Push, Paper-Fill-Push.
Im gesamten Frontend gab es dazu **keinen einzigen** `pushManager`-Aufruf und
keinen `push`-Handler im Service Worker. Jede gesendete Benachrichtigung lief
ins Leere, und kein Test hat es gemerkt, weil beide Haelften fuer sich
betrachtet in Ordnung waren.

Genau das prueft diese Datei: nicht die Haelften, sondern dass sie sich
treffen. Ein Push-Endpunkt ohne Empfaenger ist ein toter Pfad, egal wie gruen
die Serverseite ist.
"""
import json
import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = PROJECT_ROOT / "src" / "frontend" / "src"
FRONTEND_ROOT = PROJECT_ROOT / "src" / "frontend"
SERVICE_WORKER = FRONTEND_ROOT / "public" / "push-sw.js"
VITE_CONFIG = FRONTEND_ROOT / "vite.config.ts"


def _frontend_sources() -> str:
    parts = []
    for path in FRONTEND_SRC.rglob("*.ts*"):
        if path.suffix in {".ts", ".tsx"} and "node_modules" not in path.parts:
            parts.append(path.read_text())
    return "\n".join(parts)


class PushReceiverExistsTests(unittest.TestCase):
    def test_service_worker_handles_push_and_click(self):
        self.assertTrue(
            SERVICE_WORKER.exists(),
            "es gibt keinen Push-Handler im Service Worker -- der Server "
            "verschickt dann Benachrichtigungen, die niemand entgegennimmt",
        )
        source = SERVICE_WORKER.read_text()
        self.assertIn('addEventListener("push"', source)
        self.assertIn('addEventListener("notificationclick"', source)
        self.assertIn("showNotification", source)

    def test_service_worker_is_wired_into_the_build(self):
        """Eine Datei unter public/ landet nicht von allein im Service Worker."""
        config = VITE_CONFIG.read_text()
        self.assertRegex(
            config,
            r"importScripts:\s*\[\s*[\"']/push-sw\.js[\"']",
            "push-sw.js wird nicht in den generierten Service Worker "
            "eingehaengt -- die Handler liegen dann ungenutzt herum",
        )

    def test_frontend_subscribes_via_the_push_manager(self):
        source = _frontend_sources()
        self.assertIn("pushManager.subscribe", source)
        self.assertIn("applicationServerKey", source)
        self.assertIn("Notification.requestPermission", source)

    def test_frontend_calls_both_push_endpoints(self):
        """Der oeffentliche Schluessel wird geholt, das Abo gemeldet."""
        source = _frontend_sources()
        self.assertIn("/api/auth/push/config", source)
        self.assertIn("/api/auth/push/subscribe", source)

    def test_subscribe_payload_matches_the_backend_schema(self):
        """Die drei Feldnamen aus PushSubscriptionRequest, nicht zwei davon."""
        # Die Quelle wird ueber den Import geholt, nicht ueber einen geratenen
        # Pfad: im Test-Container liegt das Paket unter /app/app, im Checkout
        # unter src/backend/app. Ein fest verdrahteter Pfad haette zudem
        # denselben Fallback zerschossen, auf den sich mehrere andere Tests
        # verlassen (sie haengen src/backend an sys.path, sobald es existiert).
        import inspect

        from app import auth_routes

        schema_source = inspect.getsource(auth_routes)
        match = re.search(
            r"class PushSubscriptionRequest\(BaseModel\):(.*?)\n\n", schema_source, re.S
        )
        self.assertIsNotNone(match, "PushSubscriptionRequest nicht gefunden")
        fields = re.findall(r"^\s{4}(\w+):", match.group(1), re.M)
        self.assertEqual({"endpoint", "p256dh", "auth"}, set(fields))

        subscribe_source = (FRONTEND_SRC / "push" / "subscribe.ts").read_text()
        for field in fields:
            self.assertIn(
                f"{field}:",
                subscribe_source,
                f"das Abo-Feld {field} fehlt in der Nutzlast des Clients",
            )

    def test_permission_is_never_requested_unprompted(self):
        """Ein ungefragter Dialog ist der schnellste Weg zu 'dauerhaft blockiert'.

        `Notification.requestPermission` darf nur in einem Klickpfad stehen,
        nicht in einem Effekt beim Seitenaufruf. Geprueft wird deshalb, dass
        die zustandslesende Funktion ihn nicht aufruft.
        """
        subscribe_source = (FRONTEND_SRC / "push" / "subscribe.ts").read_text()
        read_state = re.search(
            r"export async function readPushState\(.*?\n\}", subscribe_source, re.S
        )
        self.assertIsNotNone(read_state)
        self.assertNotIn(
            "requestPermission",
            read_state.group(0),
            "readPushState loest einen Berechtigungsdialog aus, obwohl es nur "
            "den Zustand lesen soll",
        )


class PushNotificationCopyTests(unittest.TestCase):
    def test_notification_settings_are_translated_in_both_languages(self):
        for lang in ("en", "de"):
            data = json.loads((FRONTEND_SRC / "i18n" / f"{lang}.json").read_text())
            block = data["settings"]["notifications"]
            self.assertIn("title", block)
            self.assertIn("enable", block)
            # Der abgelehnte und der unkonfigurierte Fall brauchen eine eigene
            # Erklaerung -- sonst steht dort "irgendwas ging schief".
            self.assertIn("denied", block["state"])
            self.assertIn("unconfigured", block["state"])


if __name__ == "__main__":
    unittest.main()
