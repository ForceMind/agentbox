from __future__ import annotations

import json
from typing import cast

import pytest
from agentbox_runtime.waw_process_profile import (
    WAWProcessProfileError,
    decode_executable_inventory_v1,
    encode_executable_inventory_v1,
)
from test_waw_manifest_codecs import _inventory_v1


def _release_inventory(version: str = "0.3.0rc30") -> dict[str, object]:
    data = json.loads(_inventory_v1())
    data.pop("schema_version")
    for entry in data["executables"]:
        if entry["kind"] in {"pane_bootstrap", "bridge", "attach_supervisor"}:
            entry["path"] = entry["path"].replace(
                "/opt/agentbox/current/", f"/opt/agentbox/releases/{version}/"
            )
    return cast(dict[str, object], data)


@pytest.mark.parametrize("version", ["0.3.0rc30", "0.3.0", "1.0.0b2"])
def test_native_helpers_pin_one_immutable_release_without_current_symlink(version: str) -> None:
    inventory = decode_executable_inventory_v1(
        encode_executable_inventory_v1(_release_inventory(version))
    )
    helpers = inventory.executables[1:4]
    assert all(
        entry.path.startswith(f"/opt/agentbox/releases/{version}/libexec/") for entry in helpers
    )
    assert all("/current/" not in entry.path for entry in helpers)


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/agentbox-waw-bridge",
        "/opt/agentbox/releases/../../tmp/libexec/agentbox-waw-bridge",
        "/opt/agentbox/releases/caller/libexec/agentbox-waw-bridge",
        "/opt/agentbox/releases/0.3.0rc30/libexec/caller",
        "/opt/agentbox/releases/0.3.0rc30/bin/agentbox-waw-bridge",
    ],
)
def test_native_release_paths_cannot_select_arbitrary_names_or_roots(path: str) -> None:
    data = _release_inventory()
    data["executables"][2]["path"] = path  # type: ignore[index]
    with pytest.raises(WAWProcessProfileError):
        encode_executable_inventory_v1(data)


@pytest.mark.parametrize(
    "path",
    [
        "/opt/agentbox/current/libexec/agentbox-waw-bridge",
        "/opt/agentbox/releases/0.3.0rc29/libexec/agentbox-waw-bridge",
    ],
)
def test_native_helpers_cannot_mix_release_generations(path: str) -> None:
    data = _release_inventory()
    data["executables"][2]["path"] = path  # type: ignore[index]
    with pytest.raises(WAWProcessProfileError, match="one installed release"):
        encode_executable_inventory_v1(data)


def test_tmux_stays_at_its_fixed_system_location() -> None:
    data = _release_inventory()
    data["executables"][0]["path"] = "/opt/agentbox/releases/0.3.0rc30/libexec/tmux"  # type: ignore[index]
    with pytest.raises(WAWProcessProfileError):
        encode_executable_inventory_v1(data)
