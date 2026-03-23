"""
Email delivery helpers for account workflows.
"""
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.logging_config import fingerprint_value

logger = logging.getLogger(__name__)


class PasswordResetDeliveryError(RuntimeError):
    """Raised when password reset email delivery cannot be completed."""


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class PasswordResetEmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    smtp_from_email: str
    smtp_from_name: str
    reset_base_url: str
    timeout_seconds: int


def _load_password_reset_email_config() -> PasswordResetEmailConfig:
    smtp_host = _get_env("SMTP_HOST")
    smtp_from_email = _get_env("SMTP_FROM_EMAIL")
    reset_base_url = _get_env("PASSWORD_RESET_BASE_URL")

    missing_fields = [
        name
        for name, value in (
            ("SMTP_HOST", smtp_host),
            ("SMTP_FROM_EMAIL", smtp_from_email),
            ("PASSWORD_RESET_BASE_URL", reset_base_url),
        )
        if not value
    ]
    if missing_fields:
        raise PasswordResetDeliveryError(
            f"Password reset email delivery is not configured. Missing: {', '.join(missing_fields)}"
        )

    smtp_port_raw = _get_env("SMTP_PORT", "587")
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError as exc:
        raise PasswordResetDeliveryError("SMTP_PORT must be an integer") from exc
    if smtp_port <= 0:
        raise PasswordResetDeliveryError("SMTP_PORT must be a positive integer")

    timeout_raw = _get_env("SMTP_TIMEOUT_SECONDS", "15")
    try:
        timeout_seconds = int(timeout_raw)
    except ValueError as exc:
        raise PasswordResetDeliveryError("SMTP_TIMEOUT_SECONDS must be an integer") from exc
    if timeout_seconds <= 0:
        raise PasswordResetDeliveryError("SMTP_TIMEOUT_SECONDS must be a positive integer")

    smtp_use_tls = _is_truthy(_get_env("SMTP_USE_TLS", "true"))
    smtp_use_ssl = _is_truthy(_get_env("SMTP_USE_SSL", "false"))
    if smtp_use_tls and smtp_use_ssl:
        raise PasswordResetDeliveryError("SMTP_USE_TLS and SMTP_USE_SSL cannot both be enabled")

    smtp_username = _get_env("SMTP_USERNAME")
    smtp_password = _get_env("SMTP_PASSWORD")
    if smtp_password and not smtp_username:
        raise PasswordResetDeliveryError("SMTP_USERNAME is required when SMTP_PASSWORD is set")

    return PasswordResetEmailConfig(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_use_tls=smtp_use_tls,
        smtp_use_ssl=smtp_use_ssl,
        smtp_from_email=smtp_from_email,
        smtp_from_name=_get_env("SMTP_FROM_NAME", "Trading Bot V2"),
        reset_base_url=reset_base_url,
        timeout_seconds=timeout_seconds,
    )


def build_password_reset_url(base_url: str, token: str) -> str:
    parts = urlsplit(base_url)
    if not parts.scheme or not parts.netloc:
        raise PasswordResetDeliveryError("PASSWORD_RESET_BASE_URL must be an absolute URL")

    query_items = dict(parse_qsl(parts.query, keep_blank_values=True))
    query_items["token"] = token
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment)
    )


def send_password_reset_email(recipient_email: str, token: str) -> str:
    config = _load_password_reset_email_config()
    reset_url = build_password_reset_url(config.reset_base_url, token)

    message = EmailMessage()
    message["Subject"] = "Reset your Trading Bot password"
    message["From"] = formataddr((config.smtp_from_name, config.smtp_from_email))
    message["To"] = recipient_email

    text_body = (
        "A password reset was requested for your Trading Bot account.\n\n"
        f"Open this link to reset your password:\n{reset_url}\n\n"
        "This link expires in 60 minutes. If you did not request this reset, you can ignore this email."
    )
    html_body = (
        "<p>A password reset was requested for your Trading Bot account.</p>"
        f"<p><a href=\"{reset_url}\">Reset your password</a></p>"
        "<p>This link expires in 60 minutes. If you did not request this reset, you can ignore this email.</p>"
    )

    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    smtp_class = smtplib.SMTP_SSL if config.smtp_use_ssl else smtplib.SMTP
    ssl_context = ssl.create_default_context()

    try:
        if config.smtp_use_ssl:
            smtp = smtp_class(
                config.smtp_host,
                config.smtp_port,
                timeout=config.timeout_seconds,
                context=ssl_context,
            )
        else:
            smtp = smtp_class(
                config.smtp_host,
                config.smtp_port,
                timeout=config.timeout_seconds,
            )

        with smtp:
            smtp.ehlo()
            if config.smtp_use_tls:
                smtp.starttls(context=ssl_context)
                smtp.ehlo()
            if config.smtp_username:
                smtp.login(config.smtp_username, config.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise PasswordResetDeliveryError(f"Failed to send password reset email: {exc}") from exc

    logger.info(
        "password_reset_email_dispatched",
        extra={"recipient_fingerprint": fingerprint_value(recipient_email)},
    )
    return reset_url
