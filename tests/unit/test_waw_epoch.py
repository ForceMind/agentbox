from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from agentbox_runtime.waw_epoch import WAWRuntimeEpochError, WAWRuntimeEpochStore


def _store(tmp_path: Path, value: str = "1") -> WAWRuntimeEpochStore:
    directory = tmp_path / "epoch"
    directory.mkdir(mode=0o700)
    path = directory / "epoch.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(
            fd, json.dumps({"epoch": value, "schema_version": "waw-runtime-epoch-v1"}).encode()
        )
        os.fsync(fd)
    finally:
        os.close(fd)
    return WAWRuntimeEpochStore(directory, expected_uid=os.geteuid(), expected_gid=os.getegid())


def test_consume_is_monotonic_and_durable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.consume() == 2
    assert store.consume() == 3
    assert (tmp_path / "epoch" / "epoch.json").read_text() == (
        '{"epoch":"3","schema_version":"waw-runtime-epoch-v1"}'
    )


def test_fenced_bootstrap_writes_first_epoch_once(tmp_path: Path) -> None:
    directory = tmp_path / "epoch"
    directory.mkdir(mode=0o700)
    store = WAWRuntimeEpochStore(directory, expected_uid=os.geteuid(), expected_gid=os.getegid())

    assert store.bootstrap() == 1
    assert (directory / "epoch.json").read_text() == (
        '{"epoch":"1","schema_version":"waw-runtime-epoch-v1"}'
    )
    assert store.consume() == 2
    with pytest.raises(WAWRuntimeEpochError):
        store.bootstrap()


def test_bootstrap_does_not_accept_zero_counter(tmp_path: Path) -> None:
    store = _store(tmp_path, "0")
    with pytest.raises(WAWRuntimeEpochError):
        store.bootstrap()


@pytest.mark.parametrize("value", ["0", "01", "١", "not-a-number"])
def test_rejects_noncanonical_epoch(tmp_path: Path, value: str) -> None:
    store = _store(tmp_path, value)
    with pytest.raises(WAWRuntimeEpochError):
        store.consume()


def test_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    directory = tmp_path / "epoch"
    directory.mkdir(mode=0o700)
    (directory / "epoch.json").write_text(
        '{"epoch":"1","epoch":"2","schema_version":"waw-runtime-epoch-v1"}'
    )
    os.chmod(directory / "epoch.json", 0o600)
    store = WAWRuntimeEpochStore(directory, expected_uid=os.geteuid(), expected_gid=os.getegid())
    with pytest.raises(WAWRuntimeEpochError):
        store.consume()


def test_rejects_unsafe_directory_mode(tmp_path: Path) -> None:
    store = _store(tmp_path)
    (tmp_path / "epoch").chmod(0o755)
    with pytest.raises(WAWRuntimeEpochError):
        store.consume()


def test_rejects_missing_epoch_file(tmp_path: Path) -> None:
    directory = tmp_path / "epoch"
    directory.mkdir(mode=0o700)
    store = WAWRuntimeEpochStore(directory, expected_uid=os.geteuid(), expected_gid=os.getegid())
    with pytest.raises(WAWRuntimeEpochError):
        store.consume()


def test_concurrent_consumers_do_not_reuse_epoch(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as executor:
        values = sorted(executor.map(lambda _item: store.consume(), range(2)))
    assert values == [2, 3]


@pytest.mark.parametrize("failure", ["prepare", "validate"])
def test_prepared_consume_does_not_commit_an_invalid_executor(tmp_path: Path, failure: str) -> None:
    store = _store(tmp_path)

    def prepare(epoch: str) -> tuple[str, object]:
        if failure == "prepare":
            raise ValueError("unbound factory")
        return epoch, object()

    def validate(_prepared: tuple[str, object], _epoch: str) -> None:
        if failure == "validate":
            raise ValueError("unbound executor")

    with pytest.raises(ValueError, match="unbound"):
        store.consume_prepared(prepare, validate)
    assert store.consume() == 2


def test_prepared_consume_commits_the_exact_constructed_epoch(tmp_path: Path) -> None:
    store = _store(tmp_path)
    observed: list[str] = []

    def prepare(epoch: str) -> list[str]:
        observed.append(epoch)
        return observed

    value, prepared = store.consume_prepared(
        prepare, lambda result, epoch: result.append(f"validated-{epoch}")
    )
    assert value == 2
    assert prepared == ["2", "validated-2"]
    assert store.consume() == 3
