import base64
import json
import logging
import os

from sqlalchemy.orm import Session
from pywebpush import webpush, WebPushException
from py_vapid import Vapid

from app.logging_config import fingerprint_value
from app.models import PushSubscription

logger = logging.getLogger(__name__)


class PushConfigurationError(RuntimeError):
    pass


def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _requires_vapid_config() -> bool:
    if _env_flag("REQUIRE_VAPID_SECRETS"):
        return True
    app_env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "")).strip().lower()
    return app_env in {"prod", "production"}


def _decode_base64url(value: str, *, label: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise PushConfigurationError(f"{label} must be unpadded base64url") from exc


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _derive_public_key(private_key: str) -> str:
    vapid = Vapid.from_string(private_key)
    numbers = vapid.public_key.public_numbers()
    raw_public_key = (
        b"\x04"
        + int(numbers.x).to_bytes(32, "big")
        + int(numbers.y).to_bytes(32, "big")
    )
    return _encode_base64url(raw_public_key)


def validate_vapid_configuration(require_config: bool | None = None) -> dict:
    public_key = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    claims_sub = os.getenv("VAPID_CLAIMS_SUB", "").strip()
    required = _requires_vapid_config() if require_config is None else require_config

    if not public_key and not private_key:
        if required:
            raise PushConfigurationError(
                "VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY must be set when push is required"
            )
        return {"configured": False, "required": required}

    if not public_key or not private_key:
        raise PushConfigurationError("VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY must be set together")

    if not claims_sub:
        raise PushConfigurationError("VAPID_CLAIMS_SUB must be set when VAPID keys are configured")
    if not (claims_sub.startswith("mailto:") or claims_sub.startswith("https://")):
        raise PushConfigurationError("VAPID_CLAIMS_SUB must start with mailto: or https://")

    raw_private_key = _decode_base64url(private_key, label="VAPID_PRIVATE_KEY")
    if len(raw_private_key) != 32:
        raise PushConfigurationError("VAPID_PRIVATE_KEY must decode to 32 bytes")

    raw_public_key = _decode_base64url(public_key, label="VAPID_PUBLIC_KEY")
    if len(raw_public_key) != 65 or raw_public_key[0] != 4:
        raise PushConfigurationError("VAPID_PUBLIC_KEY must be an uncompressed P-256 public key")

    try:
        derived_public_key = _derive_public_key(private_key)
    except Exception as exc:
        raise PushConfigurationError("VAPID_PRIVATE_KEY is not a valid P-256 private key") from exc

    if public_key != derived_public_key:
        raise PushConfigurationError("VAPID_PUBLIC_KEY does not match VAPID_PRIVATE_KEY")

    return {
        "configured": True,
        "required": required,
        "public_key": public_key,
        "private_key": private_key,
        "claims": {"sub": claims_sub},
    }

class PushService:
    @staticmethod
    def validate_configuration(require_config: bool | None = None) -> dict:
        return validate_vapid_configuration(require_config=require_config)

    @staticmethod
    def is_configured() -> bool:
        return bool(validate_vapid_configuration(require_config=False)["configured"])

    @staticmethod
    def send_notification_to_user(db: Session, user_id: int, payload: dict):
        """Send a push notification to all devices for a given user."""
        subscriptions = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
        return PushService.send_to_subscriptions(subscriptions, payload, db)

    @staticmethod
    def broadcast_notification(db: Session, payload: dict):
        """Send a push notification to all users in the system."""
        subscriptions = db.query(PushSubscription).all()
        return PushService.send_to_subscriptions(subscriptions, payload, db)

    @staticmethod
    def send_to_subscriptions(subscriptions, payload: dict, db: Session):
        """Helper to iterate and send web push to subscription rows."""
        config = validate_vapid_configuration()
        if not config["configured"]:
            if subscriptions:
                logger.warning("web_push_skipped_missing_vapid_config count=%s", len(subscriptions))
            return 0

        payload_data = json.dumps(payload)
        sent_count = 0
        
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
                    vapid_private_key=config["private_key"],
                    vapid_claims=config["claims"]
                )
                logger.info(
                    "web_push_sent",
                    extra={"subscription_fingerprint": subscription_fingerprint},
                )
                sent_count += 1
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

        return sent_count
