"""Isolated bounded metadata journal; tmp-only synthetic process/file evidence."""

from __future__ import annotations

import fcntl
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from agentbox_core.kebui_observation import parse_scope
from agentbox_runtime.kebui_admission import (
    SYNTHETIC_ADAPTER_PROFILE,
    AdmissionPhase,
    AdmissionRecord,
    AdmissionRequest,
    KebuiAdmissionError,
    scope_metadata,
)
from agentbox_runtime.kebui_admission_journal import (
    HEADER_RESERVED_BYTES,
    MAX_RECORDS,
    MAX_SNAPSHOT_BYTES,
    RECORD_RESERVED_BYTES,
    KebuiAdmissionJournal,
)


def request(number: int = 1) -> AdmissionRequest:
    value = json.loads(
        (Path(__file__).parents[1] / "fixtures/kebui_observation/v1.json").read_text()
    )["base"]["scope"]
    return AdmissionRequest(
        f"kreq_{number:032x}", parse_scope(value), SYNTHETIC_ADAPTER_PROFILE, f"ksyn_{number:032x}"
    )


def initialize(path: Path) -> KebuiAdmissionJournal:
    return KebuiAdmissionJournal.initialize_for_test(
        path, expected_uid=os.getuid(), expected_gid=os.getgid()
    )


def reopen(path: Path) -> KebuiAdmissionJournal:
    return KebuiAdmissionJournal.open_existing(
        path, expected_uid=os.getuid(), expected_gid=os.getgid()
    )


def test_no_implicit_bootstrap_and_missing_is_not_never_sent(tmp_path: Path) -> None:
    with pytest.raises(KebuiAdmissionError):
        reopen(tmp_path)
    journal = initialize(tmp_path)
    assert journal.read(request()) is None
    with pytest.raises(KebuiAdmissionError):
        initialize(tmp_path)


def test_acceptance_is_atomic_with_slot_and_restart_unknown(tmp_path: Path) -> None:
    journal = initialize(tmp_path)
    item = request()
    record, created = journal.accept(item, "kexe_" + "1" * 32)
    assert created and record.phase is AdmissionPhase.ACCEPTED
    journal.close()
    restarted = reopen(tmp_path)
    restored = restarted.read(item)
    assert restored is not None and restored.phase is AdmissionPhase.UNKNOWN
    changed_view = replace(request(2), scope=replace(item.scope, conversation_id="kcv_" + "9" * 32))
    with pytest.raises(KebuiAdmissionError, match="busy"):
        restarted.accept(changed_view, "kexe_" + "9" * 32)


def test_rejection_is_exact_cas_and_claim_retired(tmp_path: Path) -> None:
    journal = initialize(tmp_path)
    item = request()
    accepted, _ = journal.accept(item, "kexe_" + "1" * 32)
    rejected = journal.transition(
        item, accepted.record_revision, AdmissionPhase.REJECTED_BEFORE_DISPATCH
    )
    with pytest.raises(KebuiAdmissionError):
        journal.transition(item, accepted.record_revision, AdmissionPhase.DISPATCH_FENCED)
    assert journal.read(item) == rejected
    assert journal.accept(request(2), "kexe_" + "1" * 32)[1]


def test_nonblocking_directory_lock(tmp_path: Path) -> None:
    journal = initialize(tmp_path)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(KebuiAdmissionError, match="busy"):
            journal.read(request())
    finally:
        os.close(fd)
    assert journal.read(request()) is None


def test_capacity_reserves_future_states_and_updates_at_limit(tmp_path: Path) -> None:
    journal = initialize(tmp_path)
    assert MAX_RECORDS == 255
    assert HEADER_RESERVED_BYTES + MAX_RECORDS * RECORD_RESERVED_BYTES == MAX_SNAPSHOT_BYTES
    for number in range(1, MAX_RECORDS + 1):
        item = request(number)
        accepted, _ = journal.accept(item, "kexe_" + "1" * 32)
        if number < MAX_RECORDS:
            journal.transition(
                item, accepted.record_revision, AdmissionPhase.REJECTED_BEFORE_DISPATCH
            )
    with pytest.raises(KebuiAdmissionError, match="capacity"):
        journal.accept(request(MAX_RECORDS + 1), "kexe_" + "1" * 32)
    fenced = journal.transition(item, accepted.record_revision, AdmissionPhase.DISPATCH_FENCED)
    ack = journal.transition(
        item, fenced.record_revision, AdmissionPhase.ACKNOWLEDGED, receipt_ref="krcp_" + "f" * 32
    )
    terminal = journal.transition(
        item,
        ack.record_revision,
        AdmissionPhase.TERMINAL,
        receipt_ref="krcp_" + "f" * 32,
        terminal_status="completed",
    )
    assert journal.read(item) == terminal
    assert len((tmp_path / "admission.json").read_bytes()) <= MAX_SNAPSHOT_BYTES
    assert len(json.loads((tmp_path / "admission.json").read_text())["records"]) == MAX_RECORDS


@pytest.mark.parametrize(
    "payload",
    [b"{}", b"{", b"\xff", b"[]", b"x" * (1024 * 1024 + 1)],
    ids=["empty", "truncated", "utf8", "array", "oversize"],
)
def test_corrupt_or_oversized_file_never_opens(tmp_path: Path, payload: bytes) -> None:
    initialize(tmp_path).close()
    (tmp_path / "admission.json").write_bytes(payload)
    with pytest.raises(KebuiAdmissionError):
        reopen(tmp_path)


def test_observer_barrier_does_not_recover_live_owner(tmp_path: Path) -> None:
    journal = initialize(tmp_path)
    observer = KebuiAdmissionJournal.open_existing(
        tmp_path, expected_uid=os.getuid(), expected_gid=os.getgid(), recover=False
    )
    item = request()
    accepted, _ = journal.accept(item, "kexe_" + "1" * 32)
    assert observer.read(item) == accepted
    with pytest.raises(KebuiAdmissionError, match="read_only"):
        observer.accept(request(2), "kexe_" + "1" * 32)
    assert journal.transition(item, accepted.record_revision, AdmissionPhase.DISPATCH_FENCED)
    observer.close()


def test_recovery_retires_another_instances_dispatch_claim(tmp_path: Path) -> None:
    original = initialize(tmp_path)
    item = request()
    accepted, _ = original.accept(item, "kexe_" + "1" * 32)
    recovered = reopen(tmp_path)
    restored = recovered.read(item)
    assert restored is not None and restored.phase is AdmissionPhase.UNKNOWN
    with pytest.raises(KebuiAdmissionError, match="cas_conflict"):
        original.transition(item, accepted.record_revision, AdmissionPhase.DISPATCH_FENCED)
    with pytest.raises(KebuiAdmissionError, match="busy"):
        original.accept(request(2), "kexe_" + "2" * 32)


def test_second_live_instance_cannot_dispatch_foreign_claim(tmp_path: Path) -> None:
    original = initialize(tmp_path)
    second = reopen(tmp_path)  # Recovery happened before there was a live claim.
    item = request()
    accepted, _ = original.accept(item, "kexe_" + "1" * 32)
    assert second.accept(item, "kexe_" + "1" * 32) == (accepted, False)
    with pytest.raises(KebuiAdmissionError, match="claim_retired"):
        second.transition(item, accepted.record_revision, AdmissionPhase.DISPATCH_FENCED)
    assert original.transition(item, accepted.record_revision, AdmissionPhase.DISPATCH_FENCED)


def test_same_key_changed_target_is_conflict_without_old_receipt(tmp_path: Path) -> None:
    journal = initialize(tmp_path)
    item = request()
    journal.accept(item, "kexe_" + "1" * 32)
    changed = replace(item, scope=replace(item.scope, project_id="prj_" + "9" * 32))
    with pytest.raises(KebuiAdmissionError, match="^conflict$"):
        journal.read(changed)


@pytest.mark.parametrize("phase", [AdmissionPhase.DISPATCH_FENCED, AdmissionPhase.ACKNOWLEDGED])
def test_fenced_dispatch_never_downgrades_to_predispatch_rejection(
    tmp_path: Path, phase: AdmissionPhase
) -> None:
    journal = initialize(tmp_path)
    item = request()
    accepted, _ = journal.accept(item, "kexe_" + "1" * 32)
    current = journal.transition(item, accepted.record_revision, AdmissionPhase.DISPATCH_FENCED)
    if phase is AdmissionPhase.ACKNOWLEDGED:
        current = journal.transition(
            item, current.record_revision, phase, receipt_ref="krcp_" + "1" * 32
        )
    with pytest.raises(KebuiAdmissionError, match="invalid_transition"):
        journal.transition(item, current.record_revision, AdmissionPhase.REJECTED_BEFORE_DISPATCH)
    assert journal.read(item) == current


@pytest.mark.parametrize(
    "fault",
    ["write", "short_write", "file_fsync", "replace", "after_replace", "dir_fsync", "reopen"],
)
def test_commit_faults_sticky_fence_and_reopen_never_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    import stat

    journal = initialize(tmp_path)
    item = request()
    original_write, original_fsync, original_replace, original_open = (
        os.write,
        os.fsync,
        os.replace,
        os.open,
    )
    started = False
    replaced = False

    def write(fd: int, data: bytes) -> int:
        nonlocal started
        started = True
        if fault == "write":
            raise OSError("synthetic-write-error")
        if fault == "short_write":
            return 0
        return original_write(fd, data)

    def fsync(fd: int) -> None:
        directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        if started and (
            (fault == "file_fsync" and not directory) or (fault == "dir_fsync" and directory)
        ):
            raise OSError("synthetic-fsync-error")
        original_fsync(fd)

    def rename(*args: Any, **kwargs: Any) -> None:
        nonlocal replaced
        if fault == "replace":
            raise OSError("synthetic-replace-error")
        result = original_replace(*args, **kwargs)
        replaced = True
        if fault == "after_replace":
            raise OSError("synthetic-after-replace-error")
        return result

    def opened(path: str, *args: Any, **kwargs: Any) -> int:
        if replaced and fault == "reopen" and path == "admission.json":
            raise OSError("synthetic-reopen-error")
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", write)
        patch.setattr(os, "fsync", fsync)
        patch.setattr(os, "replace", rename)
        patch.setattr(os, "open", opened)
        with pytest.raises(KebuiAdmissionError, match="commit_uncertain"):
            journal.accept(item, "kexe_" + "1" * 32)
        with pytest.raises(KebuiAdmissionError, match="store_unavailable"):
            journal.read(item)
    recovered = reopen(tmp_path)
    record = recovered.read(item)
    if fault in {"after_replace", "dir_fsync", "reopen"}:
        assert record is not None and record.phase is AdmissionPhase.UNKNOWN
        with pytest.raises(KebuiAdmissionError, match="busy"):
            recovered.accept(request(2), "kexe_" + "1" * 32)
    else:
        assert record is None
    assert not list(tmp_path.glob("*.tmp"))


def test_short_writes_are_fully_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_write = os.write
    journal = initialize(tmp_path)
    monkeypatch.setattr(os, "write", lambda fd, data: original_write(fd, data[:7]))
    record, _ = journal.accept(request(), "kexe_" + "1" * 32)
    assert journal.read(request()) == record


def test_terminal_rename_failure_needs_new_instance_file_and_dir_barrier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stat

    journal = initialize(tmp_path)
    observer = KebuiAdmissionJournal.open_existing(
        tmp_path, expected_uid=os.getuid(), expected_gid=os.getgid(), recover=False
    )
    item = request()
    accepted, _ = journal.accept(item, "kexe_" + "1" * 32)
    fenced = journal.transition(item, accepted.record_revision, AdmissionPhase.DISPATCH_FENCED)
    original_fsync, original_replace = os.fsync, os.replace
    renamed = False

    def rename(*args: Any, **kwargs: Any) -> None:
        nonlocal renamed
        original_replace(*args, **kwargs)
        renamed = True

    def fsync(fd: int) -> None:
        if renamed and stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("synthetic-directory-fsync-error")
        original_fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", rename)
        patch.setattr(os, "fsync", fsync)
        with pytest.raises(KebuiAdmissionError, match="commit_uncertain"):
            journal.transition(
                item,
                fenced.record_revision,
                AdmissionPhase.TERMINAL,
                receipt_ref="krcp_" + "1" * 32,
                terminal_status="completed",
            )
        assert (
            json.loads((tmp_path / "admission.json").read_text())["records"][0]["phase"]
            == "terminal"
        )
        with pytest.raises(KebuiAdmissionError):
            reopen(tmp_path)
        with pytest.raises(KebuiAdmissionError):
            observer.read(item)
    calls = []
    with monkeypatch.context() as patch:

        def counted_fsync(fd: int) -> None:
            calls.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
            original_fsync(fd)

        patch.setattr(os, "fsync", counted_fsync)
        recovered = reopen(tmp_path)
        assert calls[:2] == ["file", "directory"]
        restored = recovered.read(item)
        assert restored is not None and restored.phase is AdmissionPhase.TERMINAL
        assert recovered.accept(request(2), "kexe_" + "1" * 32)[1]
    with pytest.raises(KebuiAdmissionError, match="store_unavailable"):
        observer.read(item)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "mode", "directory", "missing"])
def test_unsafe_snapshot_provenance_is_rejected(tmp_path: Path, kind: str) -> None:
    initialize(tmp_path).close()
    target = tmp_path / "admission.json"
    if kind == "symlink":
        target.rename(tmp_path / "other")
        target.symlink_to(tmp_path / "other")
    elif kind == "hardlink":
        os.link(target, tmp_path / "other")
    elif kind == "fifo":
        target.unlink()
        os.mkfifo(target, 0o600)
    elif kind == "mode":
        target.chmod(0o644)
    elif kind == "directory":
        target.unlink()
        target.mkdir(mode=0o700)
    else:
        target.unlink()
    with pytest.raises(KebuiAdmissionError):
        reopen(tmp_path)


def test_directory_replacement_and_mode_drift_fence_held_instance(tmp_path: Path) -> None:
    journal = initialize(tmp_path)
    moved = tmp_path.with_name(tmp_path.name + "-moved")
    tmp_path.rename(moved)
    tmp_path.mkdir(mode=0o700)
    with pytest.raises(KebuiAdmissionError):
        journal.read(request())
    with pytest.raises(KebuiAdmissionError, match="store_unavailable"):
        journal.read(request())
    other = initialize(tmp_path)
    tmp_path.chmod(0o755)
    with pytest.raises(KebuiAdmissionError):
        other.read(request())
    tmp_path.chmod(0o700)


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_key",
        "extra_root",
        "extra_record",
        "missing_slot",
        "duplicate_record",
        "collision",
        "revision_overflow",
        "invalid_utf8",
        "noncanonical",
    ],
)
def test_closed_snapshot_schema_and_slot_invariants(tmp_path: Path, change: str) -> None:
    journal = initialize(tmp_path)
    journal.accept(request(), "kexe_" + "1" * 32)
    journal.close()
    target = tmp_path / "admission.json"
    value = json.loads(target.read_text())
    if change == "extra_root":
        value["body"] = "body-canary"
    elif change == "extra_record":
        value["records"][0]["error"] = "body-canary"
    elif change == "missing_slot":
        del value["records"][0]["execution_id"]
    elif change in {"duplicate_record", "collision"}:
        value["records"].append(json.loads(json.dumps(value["records"][0])))
        if change == "collision":
            value["records"][1]["request"]["request_id"] = "kreq_" + "2" * 32
    elif change == "revision_overflow":
        value["journal_revision"] = str(2**64)
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    if change == "duplicate_key":
        raw = raw.replace(
            b'{"journal_revision":', b'{"journal_revision":"1","journal_revision":', 1
        )
    elif change == "invalid_utf8":
        raw = raw.replace(b"submit_turn", b"\xff")
    elif change == "noncanonical":
        raw += b" "
    target.write_bytes(raw)
    with pytest.raises(KebuiAdmissionError) as error:
        reopen(tmp_path)
    assert "body-canary" not in str(error.value)


def test_utf8_bytes_and_maximum_revision_framing_fit_reserved_budget() -> None:
    from agentbox_runtime import kebui_admission_journal as module
    from agentbox_runtime.kebui_admission import MAX_REVISION, AdmissionRecord

    item = request()
    counters = {
        name: str(MAX_REVISION)
        for name in item.scope.__dataclass_fields__
        if name.endswith("epoch") or name.endswith("revision") or name == "generation"
    }
    metadata = scope_metadata(item.scope)
    metadata.update(counters)
    item = replace(item, scope=parse_scope(metadata))
    maximum = AdmissionRecord(
        item,
        "kexe_" + "f" * 32,
        AdmissionPhase.TERMINAL,
        str(MAX_REVISION),
        "krcp_" + "f" * 32,
        "completed",
    )
    actual = len(module._json(module._record_dict(maximum))) + 1
    reserved = module.reserved_record_bytes(maximum)
    assert actual <= reserved <= RECORD_RESERVED_BYTES
    snapshot = module._Snapshot(
        str(MAX_REVISION),
        tuple(
            replace(maximum, request=replace(item, request_id=f"kreq_{number:032x}"))
            for number in range(MAX_RECORDS)
        ),
    )
    encoded = module._encode(snapshot)
    assert len(encoded) <= HEADER_RESERVED_BYTES + MAX_RECORDS * reserved <= MAX_SNAPSHOT_BYTES
    assert module._decode(encoded) == snapshot
    assert len(module._json({"x": "é"})) > len(module._json({"x": "é"}).decode("utf-8"))
    with pytest.raises(KebuiAdmissionError):
        replace(item, content_admission_ref="ksyn_" + "é" * 32)


@pytest.mark.parametrize("same_request", [True, False])
def test_two_live_instances_race_with_only_one_admission(
    tmp_path: Path, same_request: bool
) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    first = initialize(tmp_path)
    second = reopen(tmp_path)
    barrier = threading.Barrier(2)

    def attempt(journal: KebuiAdmissionJournal, number: int) -> tuple[AdmissionRecord, bool] | None:
        barrier.wait(timeout=5)
        try:
            return journal.accept(request(number), "kexe_" + "1" * 32)
        except KebuiAdmissionError as error:
            assert str(error) == "busy"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(attempt, first, 1)
        b = pool.submit(attempt, second, 1 if same_request else 2)
        results = [a.result(timeout=5), b.result(timeout=5)]
    assert sum(result is not None and result[1] for result in results) == 1
    value = json.loads((tmp_path / "admission.json").read_text())
    assert len(value["records"]) == 1
    assert value["records"][0]["phase"] == "accepted"


def test_file_identity_replacement_during_durability_barrier_is_fenced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stat

    journal = initialize(tmp_path)
    original_fsync = os.fsync
    changed = False

    def fsync(fd: int) -> None:
        nonlocal changed
        original_fsync(fd)
        if not changed and stat.S_ISREG(os.fstat(fd).st_mode):
            changed = True
            payload = (tmp_path / "admission.json").read_bytes()
            replacement = tmp_path / "replacement.json"
            replacement.write_bytes(payload)
            replacement.chmod(0o600)
            replacement.replace(tmp_path / "admission.json")

    monkeypatch.setattr(os, "fsync", fsync)
    with pytest.raises(KebuiAdmissionError, match="invalid_snapshot"):
        journal.read(request())
    with pytest.raises(KebuiAdmissionError, match="store_unavailable"):
        journal.read(request())


def test_explicit_expected_owner_mismatch_never_opens(tmp_path: Path) -> None:
    initialize(tmp_path).close()
    with pytest.raises(KebuiAdmissionError, match="invalid_directory"):
        KebuiAdmissionJournal.open_existing(
            tmp_path, expected_uid=os.getuid() + 1, expected_gid=os.getgid()
        )


def test_full_budget_updates_existing_record_to_maximum_revision(tmp_path: Path) -> None:
    from agentbox_runtime import kebui_admission_journal as module
    from agentbox_runtime.kebui_admission import MAX_REVISION, AdmissionRecord

    journal = initialize(tmp_path)
    item = request(MAX_RECORDS)
    journal.accept(item, "kexe_" + "1" * 32)
    records = tuple(
        AdmissionRecord(
            request(number), "kexe_" + "1" * 32, AdmissionPhase.REJECTED_BEFORE_DISPATCH, "2"
        )
        for number in range(1, MAX_RECORDS)
    )
    fenced = AdmissionRecord(
        item, "kexe_" + "1" * 32, AdmissionPhase.DISPATCH_FENCED, str(MAX_REVISION - 2)
    )
    snapshot = module._Snapshot(str(MAX_REVISION - 2), (*records, fenced))
    (tmp_path / "admission.json").write_bytes(module._encode(snapshot))
    ack = journal.transition(
        item, fenced.record_revision, AdmissionPhase.ACKNOWLEDGED, receipt_ref="krcp_" + "f" * 32
    )
    terminal = journal.transition(
        item,
        ack.record_revision,
        AdmissionPhase.TERMINAL,
        receipt_ref="krcp_" + "f" * 32,
        terminal_status="completed",
    )
    assert terminal.record_revision == str(MAX_REVISION)
    assert journal.read(item) == terminal
    assert len((tmp_path / "admission.json").read_bytes()) <= MAX_SNAPSHOT_BYTES


@pytest.mark.parametrize("stage", ["initialize", "reopen", "read"])
def test_orphan_or_unexpected_directory_inventory_fails_closed(tmp_path: Path, stage: str) -> None:
    journal = initialize(tmp_path) if stage != "initialize" else None
    orphan = tmp_path / ".admission-orphan.tmp"
    orphan.write_bytes(b"synthetic-uncommitted-bytes")
    orphan.chmod(0o600)
    with pytest.raises(KebuiAdmissionError, match="invalid_inventory"):
        if stage == "initialize":
            initialize(tmp_path)
        elif stage == "reopen":
            reopen(tmp_path)
        else:
            assert journal is not None
            journal.read(request())
    assert orphan.read_bytes() == b"synthetic-uncommitted-bytes"
