"""Exact, versioned Privileged Helper protocol."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

HELPER_PROTOCOL_VERSION = 1
MAX_HELPER_FRAME = 16 * 1024
REQUEST_ID = re.compile(r"req_[A-Za-z0-9_-]{8,60}")


def _strict_json_loads(raw: bytes) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    return json.loads(raw, object_pairs_hook=unique_object)


class HelperAction(StrEnum):
    SYSTEMD_DAEMON_RELOAD = "systemd.daemon_reload"
    SYSTEMD_START_AGENTBOX = "systemd.start_agentbox"
    SYSTEMD_STOP_AGENTBOX = "systemd.stop_agentbox"
    SYSTEMD_RESTART_AGENTBOX = "systemd.restart_agentbox"
    SYSTEMD_ENABLE_AGENTBOX = "systemd.enable_agentbox"
    SYSTEMD_DISABLE_AGENTBOX = "systemd.disable_agentbox"


@dataclass(frozen=True)
class HelperRequest:
    request_id: str
    action: HelperAction

    @classmethod
    def decode(cls, raw: bytes) -> HelperRequest:
        if not raw or len(raw) > MAX_HELPER_FRAME or not raw.endswith(b"\n"):
            raise ValueError("invalid frame")
        try:
            value: Any = _strict_json_loads(raw)
        except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise ValueError("invalid JSON") from exc
        if not isinstance(value, dict) or set(value) != {
            "protocol_version",
            "request_id",
            "action",
        }:
            raise ValueError("invalid schema")
        if (
            type(value["protocol_version"]) is not int
            or value["protocol_version"] != HELPER_PROTOCOL_VERSION
        ):
            raise ValueError("unsupported protocol")
        request_id = value["request_id"]
        if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
            raise ValueError("invalid request ID")
        try:
            action = HelperAction(value["action"])
        except (TypeError, ValueError) as exc:
            raise ValueError("unknown action") from exc
        return cls(request_id, action)


@dataclass(frozen=True)
class HelperResponse:
    request_id: str | None
    ok: bool
    code: str
    message: str

    def encode(self) -> bytes:
        payload = {
            "protocol_version": HELPER_PROTOCOL_VERSION,
            "request_id": self.request_id,
            "ok": self.ok,
            "code": self.code,
            "message": self.message,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode() + b"\n"
