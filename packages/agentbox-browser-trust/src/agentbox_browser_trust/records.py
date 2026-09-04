"""Independent verification of the frozen public WAW root and pin records."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NoReturn
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from agentbox_browser_trust.codec import (
    TRUST_RECORD_MAX,
    b64url_decode,
    b64url_encode,
    canonical_json,
    exact_object,
    strict_json,
)

BOOTSTRAP_POLICY_SHA256 = "87e70aac507cf4a4a230d4910cc8c864a0d585974ad71949fcdbc6754cc8cb72"
BOOTSTRAP_KEY_ID = "bootstrap-2029"
BOOTSTRAP_PUBLIC_KEY = "A6EHv_POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg"
CLOCK_SKEW = timedelta(seconds=300)
MAX_SAFE_INTEGER = (1 << 53) - 1
ID = re.compile(r"^[a-z0-9._-]{1,64}$")
HOST_ID = re.compile(r"^wri_[a-f0-9]{32}$")
HEX64 = re.compile(r"^[a-f0-9]{64}$")
TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")

BOOTSTRAP_KEYS = frozenset({"schema_version", "key_id", "public_key"})
ROOT_KEYS = frozenset(
    {
        "schema_version",
        "root_revision",
        "key_id",
        "public_key",
        "signer_key_id",
        "state",
        "valid_from",
        "valid_until",
        "revoked_at",
        "supersedes_key_id",
        "signature_algorithm",
        "signature",
    }
)
PIN_KEYS = frozenset(
    {
        "schema_version",
        "repository",
        "origin",
        "pin_revision",
        "runtime_host_installation_id",
        "runtime_host_installation_revision",
        "runtime_attestation_x25519_fingerprint",
        "valid_from",
        "valid_until",
        "revoked_at",
        "supersedes_fingerprint",
        "signature_algorithm",
        "key_id",
        "signature",
    }
)
CHECKPOINT_KEYS = frozenset(
    {
        "schema_version",
        "root_revision",
        "key_id",
        "public_key",
        "signer_key_id",
        "signer_public_key",
        "root_history_sha256",
        "accepted_at",
    }
)


class TrustRecordError(ValueError):
    """A signed trust record or its lifecycle is invalid."""


def _fail() -> NoReturn:
    raise TrustRecordError("browser trust record is invalid")


def _record(raw: bytes, keys: frozenset[str]) -> dict[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= TRUST_RECORD_MAX:
        _fail()
    try:
        value = strict_json(raw, limit=TRUST_RECORD_MAX)
        record = exact_object(value, keys)
    except ValueError:
        _fail()
    if any(item is not None and type(item) not in (str, int) for item in record.values()):
        _fail()
    if any(
        type(item) is str and (not item.isascii() or any(ord(ch) < 0x20 for ch in item))
        for item in record.values()
    ):
        _fail()
    return record


def _revision(value: object) -> int:
    if type(value) is not int or value < 1 or value > MAX_SAFE_INTEGER:
        _fail()
    return value


def _timestamp(value: object) -> datetime:
    if type(value) is not str or not TIMESTAMP.fullmatch(value):
        _fail()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        _fail()
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z" != value:
        _fail()
    return parsed


def _valid_interval(record: dict[str, object], now: datetime) -> None:
    start = _timestamp(record["valid_from"])
    end = _timestamp(record["valid_until"])
    if end <= start or now < start - CLOCK_SKEW or now > end + CLOCK_SKEW:
        _fail()
    revoked = record["revoked_at"]
    if revoked is not None:
        revoked_at = _timestamp(revoked)
        if revoked_at < start or revoked_at > end:
            _fail()


def _public_key(value: object) -> bytes:
    return b64url_decode(value, size=32, limit=32)


def _verify(record: dict[str, object], domain: bytes, public_key: bytes) -> None:
    if record["signature_algorithm"] != "Ed25519":
        _fail()
    signature = b64url_decode(record["signature"], size=64, limit=64)
    unsigned = {key: value for key, value in record.items() if key != "signature"}
    signed = domain + b"\0" + canonical_json(unsigned, limit=TRUST_RECORD_MAX)
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, signed)
    except (InvalidSignature, ValueError):
        _fail()


def canonical_origin(value: object) -> str:
    if (
        type(value) is not str
        or not value.isascii()
        or not value
        or any(ord(ch) <= 0x20 for ch in value)
    ):
        _fail()
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        _fail()
    host = parsed.hostname
    if not host:
        _fail()
    if ":" in host:
        if "." in host or host != host.lower():
            _fail()
        try:
            canonical_host = ipaddress.IPv6Address(host).compressed
        except ValueError:
            _fail()
        expected = f"https://[{canonical_host}]"
    else:
        canonical_host = host.lower()
        if host != canonical_host or len(host) > 253:
            _fail()
        try:
            address = ipaddress.IPv4Address(host)
            canonical_host = str(address)
        except ValueError:
            labels = host.split(".")
            if any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
            ):
                _fail()
        expected = f"https://{canonical_host}"
    if parsed.port not in (None, 443):
        expected += f":{parsed.port}"
    if expected != value:
        _fail()
    return value


@dataclass(frozen=True)
class ValidatedEnrollment:
    bootstrap_record: bytes
    root_records: tuple[bytes, ...]
    pin_record: bytes
    root_revision: int
    pin_revision: int
    pin_record_sha256: str
    runtime_attestation_fingerprint: str
    pin_supersedes_fingerprint: str | None
    pin_revoked_at: str | None
    pin_valid_from: str
    pin_valid_until: str
    origin: str
    runtime_host_installation_id: str
    runtime_host_installation_revision: int
    root_active: bool
    authenticated_checkpoint: dict[str, object] | None
    retired_root_key_ids: frozenset[str]
    revoked_root_key_ids: frozenset[str]


def root_history_digest(roots: tuple[bytes, ...]) -> str:
    """Bind a checkpoint to the exact canonical root history through its root."""
    if not 1 <= len(roots) <= 64:
        _fail()
    return hashlib.sha256(canonical_json([b64url_encode(root) for root in roots])).hexdigest()


def create_authenticated_checkpoint(
    roots: tuple[bytes, ...], accepted_at: str
) -> dict[str, object] | None:
    """Create the durable checkpoint only after a complete chain was verified."""
    if len(roots) < 2:
        return None
    _timestamp(accepted_at)
    current = _record(roots[-1], ROOT_KEYS)
    signer = _record(roots[-2], ROOT_KEYS)
    if (
        current["state"] != "ACTIVE"
        or current["signer_key_id"] != signer["key_id"]
        or current["supersedes_key_id"] != signer["key_id"]
        or current["key_id"] == signer["key_id"]
        or current["public_key"] == signer["public_key"]
    ):
        _fail()
    return {
        "schema_version": "waw-runtime-root-checkpoint-v1",
        "root_revision": current["root_revision"],
        "key_id": current["key_id"],
        "public_key": current["public_key"],
        "signer_key_id": signer["key_id"],
        "signer_public_key": signer["public_key"],
        "root_history_sha256": root_history_digest(roots),
        "accepted_at": accepted_at,
    }


def _checkpoint(
    value: object,
    roots: tuple[bytes, ...],
    root: dict[str, object],
    index: int,
    *,
    now: datetime,
) -> dict[str, object]:
    checkpoint = exact_object(value, CHECKPOINT_KEYS)
    if (
        checkpoint["schema_version"] != "waw-runtime-root-checkpoint-v1"
        or _revision(checkpoint["root_revision"]) != root["root_revision"]
        or checkpoint["key_id"] != root["key_id"]
        or checkpoint["public_key"] != root["public_key"]
        or checkpoint["signer_key_id"] != root["signer_key_id"]
        or checkpoint["root_history_sha256"] != root_history_digest(roots[: index + 1])
        or root["state"] != "ACTIVE"
        or root["supersedes_key_id"] != root["signer_key_id"]
        or root["key_id"] == root["signer_key_id"]
    ):
        _fail()
    if (
        type(checkpoint["signer_key_id"]) is not str
        or not ID.fullmatch(checkpoint["signer_key_id"])
        or type(checkpoint["root_history_sha256"]) is not str
        or not HEX64.fullmatch(checkpoint["root_history_sha256"])
    ):
        _fail()
    signer_public_key = _public_key(checkpoint["signer_public_key"])
    accepted_at = _timestamp(checkpoint["accepted_at"])
    if accepted_at > now:
        _fail()
    _valid_interval(root, accepted_at)
    _valid_interval(root, now)
    _verify(root, b"agentbox-waw/runtime-root/v1", signer_public_key)
    return checkpoint


def validate_enrollment(
    bootstrap_raw: bytes,
    roots_raw: tuple[bytes, ...],
    pin_raw: bytes,
    *,
    now: datetime,
    minimum_root_revision: int = 0,
    minimum_pin_revision: int = 0,
    authenticated_checkpoint: object | None = None,
    retired_root_key_ids: frozenset[str] = frozenset(),
    revoked_root_key_ids: frozenset[str] = frozenset(),
    verify_persisted_tombstones: bool = False,
) -> ValidatedEnrollment:
    if now.tzinfo is None or now.utcoffset() != timedelta(0) or not 1 <= len(roots_raw) <= 64:
        _fail()
    bootstrap = _record(bootstrap_raw, BOOTSTRAP_KEYS)
    if (
        bootstrap["schema_version"] != "waw-runtime-bootstrap-v1"
        or bootstrap["key_id"] != BOOTSTRAP_KEY_ID
        or bootstrap["public_key"] != BOOTSTRAP_PUBLIC_KEY
        or hashlib.sha256(bootstrap_raw).hexdigest() != BOOTSTRAP_POLICY_SHA256
    ):
        _fail()
    bootstrap_key = _public_key(bootstrap["public_key"])

    previous: dict[str, object] | None = None
    previous_key = bootstrap_key
    expected_retired = set(retired_root_key_ids)
    expected_revoked = set(revoked_root_key_ids)
    retired: set[str] = set()
    revoked: set[str] = set()
    checkpoint: dict[str, object] | None = None
    checkpoint_index = -1
    if authenticated_checkpoint is not None:
        probe = exact_object(authenticated_checkpoint, CHECKPOINT_KEYS)
        revision = _revision(probe["root_revision"])
        for index, raw in enumerate(roots_raw):
            root = _record(raw, ROOT_KEYS)
            if root["root_revision"] == revision:
                checkpoint = _checkpoint(probe, roots_raw, root, index, now=now)
                checkpoint_index = index
                break
        if checkpoint is None or checkpoint_index < 1:
            _fail()
    for index, raw in enumerate(roots_raw):
        root = _record(raw, ROOT_KEYS)
        revision = _revision(root["root_revision"])
        if (
            root["schema_version"] != "waw-runtime-root-v1"
            or (previous is None and revision != 1)
            or (previous is not None and revision != _revision(previous["root_revision"]) + 1)
        ):
            _fail()
        if type(root["key_id"]) is not str or not ID.fullmatch(root["key_id"]):
            _fail()
        if root["state"] not in ("ACTIVE", "REVOKED"):
            _fail()
        if (root["state"] == "ACTIVE") != (root["revoked_at"] is None):
            _fail()
        if index == checkpoint_index - 1:
            assert checkpoint is not None
            _valid_interval(root, _timestamp(checkpoint["accepted_at"]))
        elif index >= checkpoint_index:
            _valid_interval(root, now)
        if previous is None:
            if (
                root["signer_key_id"] != BOOTSTRAP_KEY_ID
                or root["supersedes_key_id"] is not None
                or root["state"] != "ACTIVE"
            ):
                _fail()
        elif previous["state"] != "ACTIVE":
            _fail()
        elif root["state"] == "ACTIVE":
            if (
                root["signer_key_id"] != previous["key_id"]
                or root["supersedes_key_id"] != previous["key_id"]
                or root["key_id"] == previous["key_id"]
                or root["public_key"] == previous["public_key"]
                or root["key_id"] in retired
                or root["key_id"] in revoked
            ):
                _fail()
        elif (
            root["signer_key_id"] != BOOTSTRAP_KEY_ID
            or root["supersedes_key_id"] != previous["key_id"]
            or root["key_id"] != previous["key_id"]
            or root["public_key"] != previous["public_key"]
        ):
            _fail()
        signer = bootstrap_key if root["signer_key_id"] == BOOTSTRAP_KEY_ID else previous_key
        _verify(root, b"agentbox-waw/runtime-root/v1", signer)
        if previous is not None:
            if root["state"] == "ACTIVE":
                retired.add(str(previous["key_id"]))
            else:
                revoked.add(str(root["key_id"]))
        previous = root
        previous_key = _public_key(root["public_key"])

    assert previous is not None
    if verify_persisted_tombstones:
        latest_active_index = (
            len(roots_raw) - 1 if previous["state"] == "ACTIVE" else len(roots_raw) - 2
        )
        if latest_active_index < 0:
            _fail()
        latest_active = _record(roots_raw[latest_active_index], ROOT_KEYS)
        if latest_active["state"] != "ACTIVE":
            _fail()
        if _revision(latest_active["root_revision"]) == 1:
            if checkpoint is not None:
                _fail()
        elif (
            checkpoint is None
            or checkpoint["root_revision"] != latest_active["root_revision"]
            or checkpoint["key_id"] != latest_active["key_id"]
        ):
            _fail()
    if verify_persisted_tombstones and (expected_retired != retired or expected_revoked != revoked):
        _fail()
    root_revision = _revision(previous["root_revision"])
    if root_revision < minimum_root_revision:
        _fail()
    pin = _record(pin_raw, PIN_KEYS)
    if (
        pin["schema_version"] != "waw-runtime-pin.v1"
        or pin["repository"] != "ForceMind/agentbox"
        or pin["key_id"] != previous["key_id"]
    ):
        _fail()
    origin = canonical_origin(pin["origin"])
    pin_revision = _revision(pin["pin_revision"])
    host_revision = _revision(pin["runtime_host_installation_revision"])
    if (
        pin_revision < minimum_pin_revision
        or type(pin["runtime_host_installation_id"]) is not str
        or not HOST_ID.fullmatch(pin["runtime_host_installation_id"])
        or type(pin["runtime_attestation_x25519_fingerprint"]) is not str
        or not HEX64.fullmatch(pin["runtime_attestation_x25519_fingerprint"])
    ):
        _fail()
    supersedes = pin["supersedes_fingerprint"]
    if supersedes is not None and (type(supersedes) is not str or not HEX64.fullmatch(supersedes)):
        _fail()
    pin_valid_from = pin["valid_from"]
    pin_valid_until = pin["valid_until"]
    pin_revoked_at = pin["revoked_at"]
    if (
        type(pin_valid_from) is not str
        or type(pin_valid_until) is not str
        or (pin_revoked_at is not None and type(pin_revoked_at) is not str)
    ):
        _fail()
    _valid_interval(pin, now)
    _verify(pin, b"agentbox-waw/runtime-pin/v1", previous_key)
    record_sha256 = hashlib.sha256(pin_raw).hexdigest()
    return ValidatedEnrollment(
        bootstrap_record=bootstrap_raw,
        root_records=roots_raw,
        pin_record=pin_raw,
        root_revision=root_revision,
        pin_revision=pin_revision,
        pin_record_sha256=record_sha256,
        runtime_attestation_fingerprint=pin["runtime_attestation_x25519_fingerprint"],
        pin_supersedes_fingerprint=supersedes,
        pin_revoked_at=pin_revoked_at,
        pin_valid_from=pin_valid_from,
        pin_valid_until=pin_valid_until,
        origin=origin,
        runtime_host_installation_id=pin["runtime_host_installation_id"],
        runtime_host_installation_revision=host_revision,
        root_active=previous["state"] == "ACTIVE",
        authenticated_checkpoint=checkpoint,
        retired_root_key_ids=frozenset(retired),
        revoked_root_key_ids=frozenset(revoked),
    )
