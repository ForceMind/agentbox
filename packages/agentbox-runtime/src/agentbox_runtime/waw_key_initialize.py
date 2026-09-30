"""Fixed local Runtime key initialization; stdout contains a public pin only."""

from __future__ import annotations

import argparse
import grp
import json
import platform
import pwd
import sys
from collections.abc import Sequence

from agentbox_runtime.waw_runtime_profile import (
    WAWRuntimeMode,
    load_waw_runtime_profile,
    revalidate_waw_runtime_profile,
)
from agentbox_runtime.waw_static_key import (
    _FIXED_ROOT,
    _RUNTIME_ACCOUNT,
    _SYSCALLS,
    WAWRuntimeStaticKeyError,
    _open_fixed_key,
    _require_exact_process_identity,
)


def initialize_runtime_key(*, recover: bool = False) -> str:
    if type(recover) is not bool or platform.system() != "Linux":
        raise WAWRuntimeStaticKeyError("Runtime key initialization requires Linux")
    account = pwd.getpwnam(_RUNTIME_ACCOUNT)
    group = grp.getgrnam(_RUNTIME_ACCOUNT)
    if account.pw_uid == 0 or group.gr_gid == 0 or account.pw_gid != group.gr_gid:
        raise WAWRuntimeStaticKeyError("Runtime key identity is invalid")
    _require_exact_process_identity(account.pw_uid, group.gr_gid)
    profile = load_waw_runtime_profile()
    disabled = profile.mode is WAWRuntimeMode.DISABLED
    if recover and not disabled:
        raise WAWRuntimeStaticKeyError("Runtime key recovery requires disabled mode")
    revalidate_waw_runtime_profile(profile)
    key = _open_fixed_key(
        root=_FIXED_ROOT,
        runtime_uid=account.pw_uid,
        runtime_gid=group.gr_gid,
        ancestor_uid=0,
        syscalls=_SYSCALLS,
        initialize=disabled,
        recover=recover,
    )
    try:
        key.preflight()
        revalidate_waw_runtime_profile(profile)
        return key.public_fingerprint()
    finally:
        if key.close() is not True:
            raise WAWRuntimeStaticKeyError("Runtime key initialization cleanup is unconfirmed")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentbox-runtime-key")
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args(argv)
    try:
        fingerprint = initialize_runtime_key(recover=args.recover)
    except (RuntimeError, OSError, KeyError):
        print("Runtime key initialization unavailable", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "schema_version": "agentbox-runtime-key-public.v1",
                "runtime_attestation_x25519_fingerprint": fingerprint,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
