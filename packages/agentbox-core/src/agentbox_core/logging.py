"""Structured logging with allowlisted fields and secret-key redaction."""

from __future__ import annotations

import contextvars
import json
import logging
from datetime import UTC, datetime
from typing import Any

from agentbox_core.security import is_sensitive_key, redact_text

request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "agentbox_request_id", default=None
)


class JsonLogFormatter(logging.Formatter):
    """Emit a compact JSON record without arbitrary LogRecord serialization."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        request_id = getattr(record, "request_id", None) or request_id_context.get()
        if request_id:
            payload["request_id"] = str(request_id)[:72]
        event = getattr(record, "event", None)
        if event:
            payload["event"] = str(event)[:80]
        fields = getattr(record, "safe_fields", None)
        if isinstance(fields, dict):
            payload["fields"] = {
                str(key)[:64]: redact_text(value, limit=256) if isinstance(value, str) else value
                for key, value in fields.items()
                if not is_sensitive_key(str(key))
                and isinstance(value, (str, int, bool, type(None)))
            }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    **safe_fields: str | int | bool | None,
) -> None:
    logger.log(level, message, extra={"event": event, "safe_fields": safe_fields})
