"""Fixed browser-extension to trustd session protocol."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NoReturn

from agentbox_browser_trust.codec import b64url_encode, canonical_json, exact_object
from agentbox_browser_trust.records import canonical_origin
from agentbox_browser_trust.store import BrowserTrustStore, BrowserTrustStoreError

PROTOCOL_VERSION = 1
FINGERPRINT = re.compile(r"^[a-f0-9]{64}$")
DOCUMENT_ID = re.compile(r"^[A-Fa-f0-9-]{16,128}$")
PAGE_NONCE = re.compile(r"^[A-Za-z0-9_-]{43}$")
CORRELATION_ID = re.compile(r"^[a-z]+_[a-f0-9]{32}$")
DECIMAL = re.compile(r"^(?:0|[1-9][0-9]{0,19})$")
BROKER_OPEN_KEYS = frozenset(
    {
        "type",
        "protocol_version",
        "origin",
        "document_id",
        "native_nonce",
        "provider_installation_key_fingerprint",
    }
)
PAGE_KEYS = frozenset({"type", "protocol_version", "page_nonce", "sequence", "correlation_id"})
PAGE_TYPES = frozenset({"OPEN", "SNAPSHOT_GET", "CONFIRM_CURRENT", "PING", "CLOSE"})
INVALIDATION_REASONS = frozenset({"changed", "lost", "closed", "time-backward"})


class TrustProtocolError(ValueError):
    """The fixed provider session has been violated and must close."""


def _fail() -> NoReturn:
    raise TrustProtocolError("browser trust protocol is invalid")


def _u64(value: object) -> int:
    if type(value) is not str or not DECIMAL.fullmatch(value):
        _fail()
    parsed = int(value)
    if parsed > 0xFFFFFFFFFFFFFFFF:
        _fail()
    return parsed


@dataclass(frozen=True)
class BrokerIdentity:
    origin: str
    document_id: str
    native_nonce: str
    installation_fingerprint: str
    installation_id: str
    provider_epoch: str


class TrustProtocolSession:
    """One top-level browser document, one provider epoch and ordered messages."""

    def __init__(self, store: BrowserTrustStore, broker_open: object) -> None:
        item = exact_object(broker_open, BROKER_OPEN_KEYS)
        fingerprint = item["provider_installation_key_fingerprint"]
        document_id = item["document_id"]
        native_nonce = item["native_nonce"]
        if (
            item["type"] != "BROKER_OPEN"
            or item["protocol_version"] != PROTOCOL_VERSION
            or type(fingerprint) is not str
            or not FINGERPRINT.fullmatch(fingerprint)
            or type(document_id) is not str
            or not DOCUMENT_ID.fullmatch(document_id)
            or type(native_nonce) is not str
            or not PAGE_NONCE.fullmatch(native_nonce)
            or fingerprint != store.installation_fingerprint()
        ):
            _fail()
        origin = canonical_origin(item["origin"])
        snapshot = store.snapshot()
        if snapshot["origin_network_proof"]["effective_origin"] != origin:  # type: ignore[index]
            _fail()
        self.store = store
        # OPEN consumes this one atomic store read. A second DNS-backed snapshot
        # would turn the browser's fixed request deadline into two serial probes.
        self._opening_snapshot = snapshot
        self.identity = BrokerIdentity(
            origin=origin,
            document_id=document_id,
            native_nonce=native_nonce,
            installation_fingerprint=fingerprint,
            installation_id="bti_" + fingerprint[:32],
            provider_epoch=str(snapshot["provider_epoch"]),
        )
        self._expected_request = 1
        self._next_response = 1
        self._page_nonce: str | None = None
        self._closed = False

    def broker_opened(self) -> dict[str, object]:
        body = {
            "protocol_version": 1,
            "type": "BROKER_OPENED",
            "origin": self.identity.origin,
            "document_id": self.identity.document_id,
            "native_nonce": self.identity.native_nonce,
            "provider_installation_id": self.identity.installation_id,
            "provider_epoch": self.identity.provider_epoch,
            "provider_public_key": b64url_encode(self.store.installation_public_key()),
        }
        return {**body, "signature": self.store.sign_session(body)}

    def handle(self, value: object) -> dict[str, object]:
        if self._closed:
            _fail()
        item = exact_object(value, PAGE_KEYS)
        request_type = item["type"]
        nonce = item["page_nonce"]
        correlation = item["correlation_id"]
        if (
            item["protocol_version"] != 1
            or type(request_type) is not str
            or request_type not in PAGE_TYPES
            or type(nonce) is not str
            or not PAGE_NONCE.fullmatch(nonce)
            or type(correlation) is not str
            or not CORRELATION_ID.fullmatch(correlation)
            or _u64(item["sequence"]) != self._expected_request
        ):
            _fail()
        if self._page_nonce is None:
            if request_type != "OPEN":
                _fail()
            self._page_nonce = nonce
        elif nonce != self._page_nonce or request_type == "OPEN":
            _fail()
        self._expected_request += 1

        try:
            snapshot = self._opening_snapshot if request_type == "OPEN" else self.store.snapshot()
        except BrowserTrustStoreError as error:
            return self.invalidate(
                error.reason if error.reason in {"changed", "closed", "time-backward"} else "lost"
            )
        if snapshot["provider_epoch"] != self.identity.provider_epoch:
            return self.invalidate("changed")

        if request_type == "OPEN":
            response: dict[str, object] = {
                "provider_installation_id": self.identity.installation_id,
                "provider_epoch": self.identity.provider_epoch,
                "document_id": self.identity.document_id,
                "origin": self.identity.origin,
            }
            result_type = "OPENED"
        elif request_type == "SNAPSHOT_GET":
            response = {"snapshot": snapshot}
            result_type = "SNAPSHOT"
        elif request_type == "CONFIRM_CURRENT":
            response = {
                "provider_epoch": self.identity.provider_epoch,
                "trusted_time": snapshot["trusted_time"],
            }
            result_type = "CONFIRMED"
        elif request_type == "PING":
            response = {}
            result_type = "PONG"
        else:
            response = {"reason": "closed"}
            result_type = "CLOSE"
            self._closed = True
        return self._response(result_type, correlation, response)

    def invalidate(self, reason: str) -> dict[str, object]:
        if reason not in INVALIDATION_REASONS or self._page_nonce is None:
            _fail()
        self._closed = True
        return self._response("INVALIDATE", "evt_" + "0" * 32, {"reason": reason})

    def _response(
        self, response_type: str, correlation_id: str, body: dict[str, object]
    ) -> dict[str, object]:
        if self._page_nonce is None:
            _fail()
        response = {
            "type": response_type,
            "protocol_version": 1,
            "page_nonce": self._page_nonce,
            "sequence": str(self._next_response),
            "correlation_id": correlation_id,
            **body,
        }
        canonical_json(response)
        self._next_response += 1
        return response
