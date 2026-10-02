#!/usr/bin/env python3
"""CI-only actual APT package-guard probe on a native systemd runner.

The probe requires a disposable GitHub Actions Ubuntu 24.04 host where nginx,
certbot and /usr/sbin/policy-rc.d are absent before the test. It installs only
the fixed browser packages through the production HostOperations APT boundary
while the production WAWPackageStartGuard is present, records systemd state
before/during/after installation, and removes package unit enablement in cleanup.

A passing probe is package-behavior evidence, not complete AgentBox deployment
qualification.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from agentbox_installer.host import HostOperations
from agentbox_installer.platform import PackageFamily
from agentbox_installer.waw_manifest_install import WAWManifestIssuer
from agentbox_installer.waw_package_guard import _RAW, WAWPackageStartGuard

PACKAGES = ("nginx", "certbot")
UNITS = ("nginx.service", "certbot.timer")
POLICY = Path("/usr/sbin/policy-rc.d")


def package_installed(name: str) -> bool:
    result = subprocess.run(
        ("/usr/bin/dpkg-query", "-W", "-f=${Status}", name),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
    )
    return result.returncode == 0 and result.stdout.strip() == "install ok installed"


def unit_state(name: str) -> dict[str, str]:
    result = subprocess.run(
        (
            "/usr/bin/systemctl",
            "show",
            name,
            "--property=LoadState",
            "--property=ActiveState",
            "--property=UnitFileState",
        ),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"systemd query failed for {name}")
    state: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"LoadState", "ActiveState", "UnitFileState"}:
            state[key] = value
    if set(state) != {"LoadState", "ActiveState", "UnitFileState"}:
        raise RuntimeError(f"incomplete systemd state for {name}")
    return state


def main() -> int:
    if (
        sys.argv[1:]
        or os.environ.get("GITHUB_ACTIONS") != "true"
        or platform.system() != "Linux"
        or os.geteuid() != 0
    ):
        raise SystemExit("isolated Linux root GitHub Actions runner required")
    if Path("/proc/1/comm").read_text().strip() != "systemd":
        raise SystemExit("native systemd PID 1 required; no simulated pass")
    if POLICY.exists() or POLICY.is_symlink():
        raise SystemExit("pre-existing policy-rc.d makes this runner unsuitable")
    already = [name for name in PACKAGES if package_installed(name)]
    if already:
        raise SystemExit(f"fresh package evidence requires absent packages: {already}")

    before = {unit: unit_state(unit) for unit in UNITS}
    issuer = WAWManifestIssuer(
        Path("/"),
        "0.3.0rc30",
        owner_uid=0,
        root_gid=0,
        runtime_uid=0,
        runtime_gid=0,
    )
    host = HostOperations(real_host=True)
    during: dict[str, dict[str, str]] = {}

    def install() -> None:
        host.install_packages(PackageFamily.APT, PACKAGES)
        if POLICY.read_bytes() != _RAW:
            raise AssertionError("package guard changed during APT")
        during.update({unit: unit_state(unit) for unit in UNITS})
        active = {
            unit: state["ActiveState"]
            for unit, state in during.items()
            if state["ActiveState"] == "active"
        }
        if active:
            raise AssertionError(f"package services started despite policy-rc.d: {active}")

    try:
        WAWPackageStartGuard(issuer).run(install)
        if POLICY.exists() or POLICY.is_symlink():
            raise AssertionError("package guard survived successful APT transaction")
        if not all(package_installed(name) for name in PACKAGES):
            raise AssertionError("fixed APT packages were not installed")
        after = {unit: unit_state(unit) for unit in UNITS}
        if during != after:
            raise AssertionError("unit state changed when the package guard was removed")
        print(
            json.dumps(
                {
                    "schema_version": "agentbox-waw-package-guard-probe.v1",
                    "packages": list(PACKAGES),
                    "before": before,
                    "during_guard": during,
                    "after_guard": after,
                    "services_started": False,
                    "guard_removed": True,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        subprocess.run(
            ("/usr/bin/systemctl", "disable", "--now", *UNITS),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        )
        if POLICY.exists() and POLICY.read_bytes() == _RAW:
            POLICY.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
