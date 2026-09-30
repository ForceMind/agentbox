from __future__ import annotations

import pytest
from agentbox_installer.hardening import systemd_capabilities, validate_unit_compatibility


@pytest.mark.parametrize("value", ["private", "strict"])
@pytest.mark.parametrize("version", [232, 254, 255, 256])
def test_private_cgroup_modes_are_not_boolean_compatibility(value: str, version: int) -> None:
    unit = f"[Service]\nProtectControlGroups={value}\n"
    assert not systemd_capabilities(unit, version).compatible
    with pytest.raises(ValueError, match="ProtectControlGroups"):
        validate_unit_compatibility(unit, version)


@pytest.mark.parametrize("value", ["private", "strict", "true", "false"])
def test_systemd_257_recognizes_cgroup_modes(value: str) -> None:
    validate_unit_compatibility(f"[Service]\nProtectControlGroups={value}\n", 257)


@pytest.mark.parametrize("value", ["yes", "no", "true", "false", "1", "0", "on", "off"])
def test_existing_boolean_cgroup_hardening_stays_compatible(value: str) -> None:
    validate_unit_compatibility(f"[Service]\nProtectControlGroups={value}\n", 255)


def test_last_scalar_assignment_matches_the_effective_unit() -> None:
    validate_unit_compatibility("ProtectControlGroups=private\nProtectControlGroups=true\n", 255)
    with pytest.raises(ValueError):
        validate_unit_compatibility(
            "ProtectControlGroups=true\nProtectControlGroups=private\n", 255
        )
    with pytest.raises(ValueError):
        validate_unit_compatibility(" ProtectControlGroups = private \n", 255)


@pytest.mark.parametrize("value", ["PRIVATE", "unknown", "private extra"])
def test_unknown_cgroup_security_value_is_not_reported_supported(value: str) -> None:
    with pytest.raises(ValueError):
        validate_unit_compatibility(f"ProtectControlGroups={value}\n", 257)
