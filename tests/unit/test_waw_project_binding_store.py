from __future__ import annotations

from pathlib import Path

import pytest
from agentbox_runtime.waw_project_binding_store import (
    WAWDurableProjectBinding,
    WAWProjectBindingStore,
    WAWProjectBindingStoreError,
    WAWProjectBindingVerifier,
    WAWProjectBindingVerifierError,
)

PROJECT_ID = "prj_" + "1" * 32
HOST_ID = "wri_" + "2" * 32


def _binding(
    *,
    revision: str = "1",
    digest: str = "a" * 64,
    previous_revision: str | None = None,
    previous_digest: str | None = None,
) -> WAWDurableProjectBinding:
    return WAWDurableProjectBinding(
        project_id=PROJECT_ID,
        relative_key="demo",
        project_revision="1",
        binding_revision=revision,
        binding_digest=digest,
        previous_binding_revision=previous_revision,
        previous_binding_digest=previous_digest,
        runtime_host_installation_id=HOST_ID,
        runtime_host_installation_revision="1",
    )


def test_store_commits_exact_current_head_and_requires_the_next_predecessor(
    tmp_path: Path,
) -> None:
    store = WAWProjectBindingStore.test_only(tmp_path / "bindings")
    first = _binding()
    assert store.get(PROJECT_ID) is None
    assert store.commit(first) == first
    assert store.commit(first) == first

    with pytest.raises(WAWProjectBindingStoreError):
        store.commit(
            _binding(revision="3", digest="b" * 64, previous_revision="2", previous_digest="b" * 64)
        )
    with pytest.raises(WAWProjectBindingStoreError):
        store.commit(
            _binding(revision="2", digest="b" * 64, previous_revision="1", previous_digest="c" * 64)
        )

    second = _binding(
        revision="2",
        digest="b" * 64,
        previous_revision="1",
        previous_digest="a" * 64,
    )
    assert store.commit(second) == second
    assert store.list_current() == (second,)
    store.close()


def test_store_rejects_noncanonical_or_unexpected_inventory(tmp_path: Path) -> None:
    directory = tmp_path / "bindings"
    store = WAWProjectBindingStore.test_only(directory)
    store.commit(_binding())
    (directory / "unexpected").write_text("x", encoding="utf-8")
    with pytest.raises(WAWProjectBindingStoreError):
        store.list_current()
    store.close()


def test_verifier_uses_descriptor_held_project_identity(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    (root / "demo").mkdir(mode=0o700)
    verifier = WAWProjectBindingVerifier.test_only(root)
    request = {"project_id": PROJECT_ID, "relative_key": "demo", "project_revision": "1"}
    first = verifier.binding_digest(request)
    assert len(first) == 64

    (root / "demo").rmdir()
    (root / "demo").mkdir(mode=0o700)
    assert verifier.binding_digest(request) != first
    verifier.close()
    with pytest.raises(WAWProjectBindingVerifierError):
        verifier.binding_digest(request)


@pytest.mark.parametrize("relative_key", ["../demo", "demo+one", " demo", "demo/"])
def test_verifier_rejects_non_wire_project_keys(tmp_path: Path, relative_key: str) -> None:
    root = tmp_path / "projects"
    root.mkdir(mode=0o700)
    (root / "demo").mkdir(mode=0o700)
    verifier = WAWProjectBindingVerifier.test_only(root)
    with pytest.raises(WAWProjectBindingVerifierError):
        verifier.binding_digest(
            {"project_id": PROJECT_ID, "relative_key": relative_key, "project_revision": "1"}
        )
    verifier.close()
