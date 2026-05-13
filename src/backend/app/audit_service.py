"""Audit-log service.

Records sensitive user-facing actions in `audit_events`. The persistent
audit trail is independent of the structured request log: the request
log is process-local and rotates with the container, while the audit
trail lives in the same database that backups already cover, so an
incident response can reconstruct who did what across restarts.

Identifying values (email addresses, IPs, user agents) are stored as
short hash fingerprints — same convention the watchlist-alert
delivery table already uses. The raw value never leaves the request
context, so a database leak doesn't expose it.

Failures inside `log_event` swallow themselves and emit a warning. The
audit trail must never block the request path it is annotating; if
the database write fails we still respond to the user.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent

logger = logging.getLogger(__name__)


# Vocabulary of action keys. Keep the strings stable — they show up in
# admin tooling, exports, and downstream queries. New events should
# follow the `<resource>.<verb>` convention.
ACTION_AUTH_LOGIN = "auth.login"
ACTION_AUTH_LOGIN_FAILED = "auth.login_failed"
ACTION_AUTH_LOGOUT = "auth.logout"
ACTION_AUTH_REGISTER = "auth.register"
ACTION_AUTH_PASSWORD_RESET_REQUEST = "auth.password_reset_request"
ACTION_AUTH_PASSWORD_RESET_CONFIRM = "auth.password_reset_confirm"
ACTION_AUTH_MFA_ENABLE = "auth.mfa_enable"
ACTION_AUTH_MFA_DISABLE = "auth.mfa_disable"
ACTION_AUTH_MFA_RESET = "auth.mfa_reset"

ACTION_SETTINGS_ALPACA = "settings.alpaca_update"
ACTION_SETTINGS_PORTFOLIO = "settings.portfolio_update"

ACTION_PAPER_ORDER_PLACE = "paper_order.place"
ACTION_PAPER_ORDER_PLACE_REJECTED = "paper_order.place_rejected"
ACTION_PAPER_ORDER_CANCEL = "paper_order.cancel"

ACTION_BACKUP_CREATE = "backup.create"
ACTION_BACKUP_RESTORE = "backup.restore"
ACTION_BACKUP_EXPORT = "backup.export"
ACTION_BACKUP_IMPORT = "backup.import"

ACTION_ADMIN_USER_CREATE = "admin.user_create"
ACTION_ADMIN_USER_PASSWORD_RESET = "admin.user_password_reset"
ACTION_ADMIN_USER_TOGGLE_ACTIVE = "admin.user_toggle_active"

ACTION_PLATFORM_CONFIG_UPDATE = "platform_config.update"
ACTION_PLATFORM_CONFIG_DELETE = "platform_config.delete"


def _fingerprint(value: str | None) -> str | None:
    """8-byte SHA-256 hex of `value`. Stable across runs, doesn't leak
    the raw string. Returns None for falsy input so the column stays
    NULL instead of carrying an empty fingerprint."""
    if not value:
        return None
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return digest[:16]


def log_event(
    db: Session,
    *,
    action: str,
    user_id: int | None = None,
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditEvent | None:
    """Insert an audit row. Best-effort — never raises into the caller.

    `actor_email` is fingerprinted so the audit trail can group
    failed-login attempts by the address being targeted without
    storing the address itself. `ip_address` and `user_agent` get the
    same treatment.
    """
    try:
        event = AuditEvent(
            user_id=user_id,
            actor_fingerprint=_fingerprint(actor_email),
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            outcome=outcome,
            details_json=json.dumps(details or {}, default=str),
            ip_fingerprint=_fingerprint(ip_address),
            user_agent_fingerprint=_fingerprint(user_agent),
            request_id=request_id,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception("audit_log_write_failed action=%s", action)
        return None


def serialize_event(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "userId": event.user_id,
        "actorFingerprint": event.actor_fingerprint,
        "action": event.action,
        "resourceType": event.resource_type,
        "resourceId": event.resource_id,
        "outcome": event.outcome,
        "details": _safe_load_json(event.details_json),
        "ipFingerprint": event.ip_fingerprint,
        "userAgentFingerprint": event.user_agent_fingerprint,
        "requestId": event.request_id,
        "createdAt": event.created_at.isoformat() if event.created_at else None,
    }


def _safe_load_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    return value
