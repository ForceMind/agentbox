"""rc8 software rehearsal foundation; synthetic data is not host evidence."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from support.waw_rc8_synthetic import loopback_bind_permitted, run_synthetic_path


def test_rc8_separate_process_socket_crypto_pty_path(tmp_path: Path) -> None:
    if not loopback_bind_permitted():
        if os.environ.get("AGENTBOX_RC8_REQUIRE_LOOPBACK") == "1":
            pytest.fail("required rc8 loopback socket bind is unavailable")
        pytest.skip("sandbox prevents the required loopback socket bind")
    run_synthetic_path(tmp_path)
