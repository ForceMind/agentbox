from __future__ import annotations

import os
import stat

import pytest
from agentbox_core.database import _production_database_directory_is_safe


def _directory_details(*, uid: int, gid: int, mode: int) -> os.stat_result:
    return os.stat_result((stat.S_IFDIR | mode, 1, 1, 1, uid, gid, 0, 0, 0, 0))


@pytest.mark.parametrize(
    ("uid", "gid", "mode", "effective_uid", "effective_gids", "expected"),
    [
        (993, 994, 0o700, 993, {994, 992}, True),
        (0, 994, 0o1770, 993, {994, 992}, True),
        (0, 994, 0o1770, 0, {0}, True),
        (0, 994, 0o0770, 993, {994, 992}, False),
        (0, 991, 0o1770, 993, {994, 992}, False),
        (993, 994, 0o1770, 993, {994, 992}, False),
        (993, 994, 0o0750, 993, {994, 992}, False),
        (0, 994, 0o1777, 993, {994, 992}, False),
    ],
)
def test_production_database_directory_policy_is_exact(
    uid: int,
    gid: int,
    mode: int,
    effective_uid: int,
    effective_gids: set[int],
    expected: bool,
) -> None:
    assert (
        _production_database_directory_is_safe(
            _directory_details(uid=uid, gid=gid, mode=mode),
            effective_uid=effective_uid,
            effective_gids=effective_gids,
        )
        is expected
    )
