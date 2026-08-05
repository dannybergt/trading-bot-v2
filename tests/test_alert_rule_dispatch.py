"""Alarmregeln: Preisziele und die Auswertung im Hintergrund.

Der Anlass (2026-08-05): `evaluate_alert_rules` hatte genau einen Aufrufer —
den HTTP-Handler von `GET /api/alerts`. Eine Regel feuerte damit ausschliesslich,
wenn der Nutzer die Alarmseite oeffnete. Wer sie nicht oeffnete, bekam nie ein
Ereignis, und eine Benachrichtigung ausserhalb der Anwendung erst recht nicht.
Die Alarmfunktion war auf dem Papier fertig und in der Praxis wirkungslos.

Dazu fehlte der naheliegendste Regeltyp ueberhaupt: ein Preisziel. Der Kurs
liegt laengst im Alert-Payload; es war schlicht nie verdrahtet.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main
from app.database import Base
from app.models import AlertRule, User, Watchlist


def _rule(rule_type: str, threshold: float | None) -> AlertRule:
    return AlertRule(
        user_id=1,
        watchlist_id="wl-1",
        symbol="AAPL",
        rule_type=rule_type,
        threshold_value=threshold,
        enabled=True,
    )


def _alert_item(price: float | None, currency: str = "USD") -> dict:
    return {
        "symbol": "AAPL",
        "providerContext": {
            "price": price,
            "currency": currency,
            "source": "alpaca",
            "changePercent": 0.0,
        },
    }


class PriceTargetRuleTests(unittest.TestCase):
    def test_price_above_fires_at_and_over_the_threshold(self):
        payload = main.build_alert_event_payload(_rule("price_above", 150.0), _alert_item(151.25))
        self.assertIsNotNone(payload)
        self.assertEqual("high", payload["severity"])
        self.assertEqual(150.0, payload["trigger"]["threshold"])
        self.assertEqual(151.25, payload["trigger"]["price"])
        # Die Meldung muss den Wert mit Einheit tragen (UX-Direktive).
        self.assertIn("151.25 USD", payload["message"])
        self.assertIn("150.00 USD", payload["message"])

        exact = main.build_alert_event_payload(_rule("price_above", 150.0), _alert_item(150.0))
        self.assertIsNotNone(exact, "die Schwelle selbst muss ausloesen, nicht erst darueber")

    def test_price_above_stays_quiet_below_the_threshold(self):
        self.assertIsNone(
            main.build_alert_event_payload(_rule("price_above", 150.0), _alert_item(149.99))
        )

    def test_price_below_fires_at_and_under_the_threshold(self):
        payload = main.build_alert_event_payload(_rule("price_below", 100.0), _alert_item(97.5))
        self.assertIsNotNone(payload)
        self.assertLess(payload["trigger"]["distancePct"], 0)
        self.assertIsNone(
            main.build_alert_event_payload(_rule("price_below", 100.0), _alert_item(100.01))
        )

    def test_missing_price_or_threshold_never_fires(self):
        """Kein Kurs, kein Alarm — und schon gar keine erfundene Zahl."""
        self.assertIsNone(
            main.build_alert_event_payload(_rule("price_above", 150.0), _alert_item(None))
        )
        self.assertIsNone(
            main.build_alert_event_payload(_rule("price_above", None), _alert_item(150.0))
        )

    def test_rule_types_are_accepted_by_the_api_whitelist(self):
        self.assertIn("price_above", main.ALERT_RULE_TYPES)
        self.assertIn("price_below", main.ALERT_RULE_TYPES)


class BackgroundEvaluationTests(unittest.TestCase):
    """Die Regeln muessen auch feuern, wenn niemand die Seite oeffnet."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)()

        self.user = User(email="alice@example.com", hashed_password="x", is_active=True)
        self.db.add(self.user)
        self.db.commit()
        self.watchlist = Watchlist(id="wl-1", user_id=self.user.id, name="Core")
        self.db.add(self.watchlist)
        self.db.add(
            AlertRule(
                user_id=self.user.id,
                watchlist_id="wl-1",
                symbol="AAPL",
                rule_type="price_above",
                threshold_value=150.0,
                enabled=True,
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_all_users_with_enabled_rules_are_evaluated(self):
        with mock.patch.object(main, "evaluate_alert_rules", return_value=[]) as evaluated:
            created = main.evaluate_alert_rules_for_all_users(self.db)

        self.assertEqual(0, created)
        evaluated.assert_called_once()
        self.assertEqual(self.user.id, evaluated.call_args.args[1].id)

    def test_inactive_users_are_skipped(self):
        self.user.is_active = False
        self.db.commit()
        with mock.patch.object(main, "evaluate_alert_rules", return_value=[]) as evaluated:
            main.evaluate_alert_rules_for_all_users(self.db)
        evaluated.assert_not_called()

    def test_disabled_rules_do_not_pull_a_user_into_the_cycle(self):
        self.db.query(AlertRule).update({AlertRule.enabled: False})
        self.db.commit()
        with mock.patch.object(main, "evaluate_alert_rules", return_value=[]) as evaluated:
            main.evaluate_alert_rules_for_all_users(self.db)
        evaluated.assert_not_called()

    def test_one_failing_user_does_not_stop_the_others(self):
        """Sonst nimmt ein einzelner Provider-Ausfall alle Alarme mit."""
        second = User(email="bob@example.com", hashed_password="x", is_active=True)
        self.db.add(second)
        self.db.commit()
        self.db.add(
            AlertRule(
                user_id=second.id,
                watchlist_id="wl-1",
                symbol="MSFT",
                rule_type="price_below",
                threshold_value=10.0,
                enabled=True,
            )
        )
        self.db.commit()

        calls = []

        def flaky(db, user):
            calls.append(user.id)
            if user.id == self.user.id:
                raise RuntimeError("provider exploded")
            return []

        with mock.patch.object(main, "evaluate_alert_rules", side_effect=flaky):
            main.evaluate_alert_rules_for_all_users(self.db)

        self.assertEqual(2, len(calls), "der zweite Nutzer muss trotzdem drankommen")

    def test_created_events_are_pushed(self):
        """Ohne Zustellung bliebe das Ereignis liegen, bis jemand nachsieht."""
        event = mock.Mock(id=7, title="AAPL price target", message="hit", symbol="AAPL")
        with mock.patch.object(main, "evaluate_alert_rules", return_value=[event]):
            with mock.patch.object(main.PushService, "send_notification_to_user") as push:
                created = main.evaluate_alert_rules_for_all_users(self.db)

        self.assertEqual(1, created)
        push.assert_called_once()
        payload = push.call_args.args[2]
        self.assertEqual("AAPL price target", payload["title"])
        self.assertEqual("/analysis/AAPL", payload["url"])

    def test_a_failing_push_does_not_lose_the_event(self):
        event = mock.Mock(id=7, title="t", message="m", symbol="AAPL")
        with mock.patch.object(main, "evaluate_alert_rules", return_value=[event]):
            with mock.patch.object(
                main.PushService,
                "send_notification_to_user",
                side_effect=RuntimeError("no subscription"),
            ):
                created = main.evaluate_alert_rules_for_all_users(self.db)

        self.assertEqual(
            1, created, "das Ereignis zaehlt auch dann, wenn die Zustellung scheitert"
        )


if __name__ == "__main__":
    unittest.main()
