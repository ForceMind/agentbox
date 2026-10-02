from __future__ import annotations

import hashlib

from agentbox_runtime.waw_vendor_probe import waw_vendor_probe_output_digest


def test_vendor_probe_output_digest_frames_stdout_and_stderr_boundary() -> None:
    stdout = b"a"
    stderr = b"bc"
    framed = (
        len(stdout).to_bytes(8, "big")
        + stdout
        + len(stderr).to_bytes(8, "big")
        + stderr
    )

    assert waw_vendor_probe_output_digest(stdout, stderr) == hashlib.sha256(framed).hexdigest()
    assert waw_vendor_probe_output_digest(stdout, stderr) != hashlib.sha256(stdout + stderr).hexdigest()
    assert waw_vendor_probe_output_digest(b"a", b"bc") != waw_vendor_probe_output_digest(
        b"ab", b"c"
    )
