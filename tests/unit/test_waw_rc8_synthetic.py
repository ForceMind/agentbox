from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from support import waw_rc8_synthetic as synthetic


def _registry(path: Path, *, mode: int = 0o600) -> tuple[bytes, bytes]:
    payload = b"rc8-payload-canary-0123456789"
    private_key = bytes(range(32))
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "canaries": [
                    {"kind": "payload", "value_base64": base64.b64encode(payload).decode("ascii")},
                    {
                        "kind": "private_key",
                        "value_base64": base64.b64encode(private_key).decode("ascii"),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    path.chmod(mode)
    return payload, private_key


def test_canary_registry_supplies_actual_payload_and_browser_private_key(tmp_path: Path) -> None:
    path = tmp_path / "canaries.json"
    payload, private_key = _registry(path)

    assert synthetic._read_canary_registry(path) == {
        "payload": payload,
        "private_key": private_key,
    }
    ticket = b"wat_0123456789abcdef0123456789abcdef"
    synthetic._write_completed_canary_registry(
        path,
        {"payload": payload, "private_key": private_key, "ticket": ticket},
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    assert [item["kind"] for item in value["canaries"]] == ["payload", "private_key", "ticket"]
    assert path.stat().st_mode & 0o777 == 0o600


def test_canary_registry_rejects_relaxed_permissions_and_missing_ticket(tmp_path: Path) -> None:
    path = tmp_path / "canaries.json"
    payload, private_key = _registry(path, mode=0o644)

    with pytest.raises(ValueError, match="synthetic canary registry"):
        synthetic._read_canary_registry(path)

    path.chmod(0o600)
    with pytest.raises(ValueError, match="synthetic canary registry"):
        synthetic._write_completed_canary_registry(
            path,
            {"payload": payload, "private_key": private_key, "ticket": b"short"},
        )


def test_synthetic_role_logs_and_fixture_evidence_are_private_and_structural(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir(mode=0o700)
    monkeypatch.setenv("AGENTBOX_RC8_EVIDENCE_DIR", str(evidence))

    assert synthetic._prepare_synthetic_evidence() == evidence
    for role in ("api", "runtime", "pty"):
        for stream in ("stdout", "stderr"):
            path = evidence / f"{role}.{stream}"
            assert path.is_file()
            assert path.stat().st_mode & 0o777 == 0o600
    synthetic._record_pty_event("started")
    assert (evidence / "pty.stdout").read_text(encoding="ascii") == "pty:started\n"


def test_ticket_is_registered_before_a_later_synthetic_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "canaries.json"
    payload, private_key = _registry(path)

    def fail_after_ticket(
        _tmp_path: Path,
        *,
        plaintext: bytes,
        browser_ephemeral_private_key: bytes,
        ticket_observer: Callable[[str], None],
    ) -> str:
        assert plaintext == payload
        assert browser_ephemeral_private_key == private_key
        ticket_observer("wat_0123456789abcdef0123456789abcdef")
        raise RuntimeError("later synthetic failure")

    monkeypatch.setattr(synthetic, "loopback_bind_permitted", lambda: True)
    monkeypatch.setattr(synthetic, "run_synthetic_path", fail_after_ticket)

    assert synthetic._main(["--require-loopback", "--canary-file", str(path)]) == 1
    value = json.loads(path.read_text(encoding="utf-8"))
    assert [item["kind"] for item in value["canaries"]] == ["payload", "private_key", "ticket"]
