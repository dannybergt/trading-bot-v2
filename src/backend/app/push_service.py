import json
import logging
from sqlalchemy.orm import Session
from pywebpush import webpush, WebPushException
import os

from app.logging_config import fingerprint_value
from app.models import PushSubscription

logger = logging.getLogger(__name__)

# Generated VAPID Keys
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "BM8ekAJjHq4qv1Hiaf6lzA1naNCYkmuuXkH0aLRY3puP6yrn7zaRBwXdb5VPiSdQvKIRe-nXMTTpJR_NEutRAbc")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "sAjfmg15jfqbTtasBTFKZ-RLTLyi6f_d--V6S-sx1mY")
VAPID_CLAIMS = {
    "sub": "mailto:admin@nexuspulsetrade.com"
}

class PushService:
    @staticmethod
    def send_notification_to_user(db: Session, user_id: int, payload: dict):
        """Send a push notification to all devices for a given user."""
        subscriptions = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
        PushService.send_to_subscriptions(subscriptions, payload, db)

    @staticmethod
    def broadcast_notification(db: Session, payload: dict):
        """Send a push notification to all users in the system."""
        subscriptions = db.query(PushSubscription).all()
        PushService.send_to_subscriptions(subscriptions, payload, db)

    @staticmethod
    def send_to_subscriptions(subscriptions, payload: dict, db: Session):
        """Helper to iterate and send web push to subscription rows."""
        payload_data = json.dumps(payload)
        
        expired_subs = []
        for sub in subscriptions:
            subscription_fingerprint = fingerprint_value(sub.endpoint)
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {
                    "p256dh": sub.p256dh,
                    "auth": sub.auth
                }
            }
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=payload_data,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=VAPID_CLAIMS
                )
                logger.info(
                    "web_push_sent",
                    extra={"subscription_fingerprint": subscription_fingerprint},
                )
            except WebPushException as ex:
                logger.error(
                    "web_push_failed",
                    extra={
                        "subscription_fingerprint": subscription_fingerprint,
                        "status_code": getattr(ex.response, "status_code", None),
                        "error": str(ex),
                    },
                )
                # If the push service rejects it as expired/unsubscribed (404/410), we clean up
                if ex.response and ex.response.status_code in [404, 410]:
                    expired_subs.append(sub)
            except Exception:
                logger.exception(
                    "web_push_unexpected_error",
                    extra={"subscription_fingerprint": subscription_fingerprint},
                )

        # Clean up unsubscribed devices
        if expired_subs:
            for es in expired_subs:
                db.delete(es)
            db.commit()
            logger.info("web_push_expired_subscriptions_cleaned count=%s", len(expired_subs))
