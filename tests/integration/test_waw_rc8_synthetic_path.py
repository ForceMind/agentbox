"""rc8 software rehearsal foundation; synthetic data is not host evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from agentbox_api.waw_admission import wire_admission_tuple
from agentbox_protocol.abws import FrameType as F
from agentbox_protocol.awce import decode_awce
from agentbox_protocol.waw_crypto_profile import BrowserCryptoProfile
from agentbox_protocol.waw_wire import decode_wire_frame
from support.waw_rc8_synthetic import (
    AB,
    GENERATION,
    RUNTIME_EPOCH,
    browser_frame,
    claims_from_admission,
    loopback_bind_permitted,
    synthetic_waw_cluster,
    verify_synthetic_trust_record,
)

pytestmark = pytest.mark.skipif(
    not loopback_bind_permitted(),
    reason="sandbox prevents the required loopback socket bind",
)


def test_rc8_separate_process_socket_crypto_pty_path(tmp_path: Path) -> None:
    plaintext = b"synthetic-rc8-input\n"
    expected_output = b"PTY:" + plaintext

    with synthetic_waw_cluster(tmp_path) as cluster:
        status, started = cluster.http("POST", "/v1/workspaces/synthetic/start")
        assert status == 200
        admission = started["admission"]
        claims = claims_from_admission(admission)
        assert wire_admission_tuple(claims) == admission
        assert started["ticket"].startswith("wat_")
        trust_record = started["trust_record"]
        assert isinstance(trust_record, dict)
        trusted_fingerprint = verify_synthetic_trust_record(trust_record, cluster.trust_anchor)
        tampered_trust = {**trust_record, "runtime_fingerprint": "0" * 64}
        with pytest.raises(ValueError, match="synthetic trust record"):
            verify_synthetic_trust_record(tampered_trust, cluster.trust_anchor)
        assert trusted_fingerprint == started["runtime_fingerprint"]

        crypto = BrowserCryptoProfile(
            admission,
            RUNTIME_EPOCH,
            trusted_fingerprint,
        )
        with cluster.browser() as browser:
            browser.send(
                browser_frame(
                    F.WS_HELLO,
                    {
                        "protocol_version": 1,
                        **admission,
                        "runtime_epoch": RUNTIME_EPOCH,
                        "ticket": started["ticket"],
                        "resume_cursor": None,
                        "previous_runtime_epoch": None,
                    },
                    1,
                )
            )
            browser.send(browser_frame(F.KEY_INIT, crypto.start(), 2))

            opcode, raw = browser.receive()
            attest = decode_wire_frame(raw, AB)
            assert opcode == 2 and attest.frame_type is F.KEY_ATTEST
            assert attest.json_payload is not None
            assert (
                attest.json_payload["runtime_attestation_x25519_fingerprint"]
                == started["runtime_fingerprint"]
            )
            browser.send(
                browser_frame(F.KEY_CONFIRM, crypto.receive_attest(attest.json_payload), 3)
            )
            opcode, raw = browser.receive()
            confirmed = decode_wire_frame(raw, AB)
            assert opcode == 2 and confirmed.frame_type is F.KEY_CONFIRM_ACK
            crypto.receive_ack(confirmed.json_payload)

            opcode, raw = browser.receive()
            admitted = decode_wire_frame(raw, AB)
            assert opcode == 2 and admitted.frame_type is F.ADMITTED
            assert admitted.json_payload is not None
            assert admitted.json_payload["state"] == "RUNNING"

            browser.send(browser_frame(F.INPUT, crypto.encrypt_input(plaintext), 4))
            accepted = False
            written = False
            output = bytearray()
            while not (accepted and written and expected_output in output):
                opcode, raw = browser.receive()
                assert opcode == 2, (opcode, raw)
                frame = decode_wire_frame(raw, AB)
                if frame.frame_type is F.ACK:
                    assert frame.json_payload is not None
                    accepted |= frame.json_payload["result"] == "accepted"
                    written |= frame.json_payload["result"] == "written_to_pty"
                elif frame.frame_type is F.OUTPUT:
                    envelope = decode_awce(frame.payload)
                    output.extend(
                        crypto.decrypt_output(
                            frame.payload,
                            expected_cursor=envelope.stream_cursor,
                        )
                    )
            assert output.count(expected_output) == 1

            browser.send(
                browser_frame(
                    F.RESIZE,
                    {
                        "protocol_version": 1,
                        "attachment_id": claims.attachment_id,
                        "lease_number": str(claims.lease_number),
                        "columns": 100,
                        "rows": 40,
                    },
                    5,
                )
            )
            opcode, raw = browser.receive()
            resized = decode_wire_frame(raw, AB)
            assert opcode == 2 and resized.frame_type is F.RESIZE_ACK
            assert resized.json_payload is not None
            assert resized.json_payload["result"] == "applied"
            assert (
                resized.json_payload["effective_columns"],
                resized.json_payload["effective_rows"],
            ) == (
                100,
                40,
            )

            browser.send(
                browser_frame(
                    F.DETACH,
                    {
                        "protocol_version": 1,
                        "attachment_id": claims.attachment_id,
                        "lease_number": str(claims.lease_number),
                    },
                    6,
                )
            )
            detached: dict[str, Any] | None = None
            closed = False
            while detached is None or not closed:
                opcode, raw = browser.receive()
                assert opcode == 2, (opcode, raw)
                frame = decode_wire_frame(raw, AB)
                if frame.frame_type is F.DETACH_ACK:
                    detached = frame.json_payload
                elif frame.frame_type is F.CLOSE:
                    closed = True
            assert detached is not None
            assert detached["result"] == "detached"
            assert detached["cleanup_state"] == "ATTACH_PTY_CLOSED"
            assert detached["reason_code"] is None

        status, stopped = cluster.http(
            "POST", "/v1/workspaces/synthetic/stop", {"generation": GENERATION}
        )
        assert status == 200
        assert started["api_pid"] != stopped["runtime_pid"]
        assert stopped["child_pid"] not in {started["api_pid"], stopped["runtime_pid"]}
        assert stopped["state"] == "STOPPED"
        assert stopped["child_stopped"] is True
        assert stopped["geometry"] == [100, 40]
        assert stopped["input_count"] == 1
        assert stopped["detach_count"] == 1
        assert stopped["registry_count"] == 0

        # The used bearer is rejected before a second Runtime prepare/open.
        with cluster.browser() as replay:
            replay.send(
                browser_frame(
                    F.WS_HELLO,
                    {
                        "protocol_version": 1,
                        **admission,
                        "runtime_epoch": RUNTIME_EPOCH,
                        "ticket": started["ticket"],
                        "resume_cursor": None,
                        "previous_runtime_epoch": None,
                    },
                    1,
                )
            )
            opcode, raw = replay.receive()
            assert opcode == 8
            assert int.from_bytes(raw[:2], "big") == 4403

        status, shutdown = cluster.http("POST", "/synthetic/shutdown")
        assert status == 200
        assert shutdown["issuance_fenced"] is True
        assert shutdown["authority_clean"] is True
        assert shutdown["runtime"]["registry_count"] == 0
        assert shutdown["runtime"]["prepare_count"] == 1
        assert shutdown["audit"] == {"prepared": 1, "admitted": 1, "detached": 1}
        cluster.assert_children_clean()
