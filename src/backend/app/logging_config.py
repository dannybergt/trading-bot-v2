import hashlib
import json
import logging
import os
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any


_REQUEST_LOG_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "request_log_context",
    default=None,
)
_STANDARD_LOG_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__.keys()) | {
    "message",
    "asctime",
}


def _serialize_log_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_serialize_log_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_log_value(current) for key, current in value.items()}
    return str(value)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = _REQUEST_LOG_CONTEXT.get() or {}
        for key, value in context.items():
            setattr(record, key, value)
        return True


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = _serialize_log_value(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def set_request_log_context(**values: Any) -> Token:
    context = {
        key: serialized
        for key, value in values.items()
        if (serialized := _serialize_log_value(value)) not in (None, "")
    }
    return _REQUEST_LOG_CONTEXT.set(context)


def reset_request_log_context(token: Token) -> None:
    _REQUEST_LOG_CONTEXT.reset(token)


def fingerprint_value(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    if not normalized:
        return None
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest}"


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = os.getenv("LOG_FORMAT", "json").strip().lower()

    handler = logging.StreamHandler()
    handler.addFilter(RequestContextFilter())
    if log_format == "text":
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    else:
        handler.setFormatter(JsonLogFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
