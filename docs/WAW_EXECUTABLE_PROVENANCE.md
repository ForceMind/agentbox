# WAW executable provenance foundation

`agentbox_runtime.waw_executable` provides descriptor-held, read-only verification
of trusted installation pins. It is not a Runtime action, path gateway, manifest
loader or process launcher. Only trusted Runtime composition supplies inventory;
browser/API/Worker requests cannot provide paths, hashes, limits or commands.

This is R10.1 of [REMAINING_PLAN](project/REMAINING_PLAN.md). The separate
[interactive-profile assessment](WAW_INTERACTIVE_PROFILE_ASSESSMENT.md) records
the still-missing launch, state-root, version and retention contracts. The
[historical architecture](../WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md)
defines the eventual process isolation and fixed execution boundary.

## Input, lifetime and failure contract

- `WAWExecutableKind` is closed: tmux, pane bootstrap, bridge, attach supervisor,
  Claude and Codex. An inventory copies its typed pins and permits selection only
  by a configured kind. Incomplete trusted inventories fail for missing kinds.
- `WAWExecutablePin` supplies an absolute local path, exact lowercase SHA-256 and
  a byte ceiling of 64 bytes through 256 MiB; paths are bounded to 4096 encoded
  bytes and 128 components. No caller-provided command or environment is involved.
- `inventory.open(kind)` requires non-root Linux x86_64. It walks from `/` through
  held directory descriptors with `O_NOFOLLOW`, `O_CLOEXEC` and `O_NONBLOCK`.
  Ancestors and the final file must be root-owned and not group/world writable;
  setuid/setgid modes are rejected. The final object must be a regular file with
  other-read/execute permission, within its size cap and a matching fixed ELF header.
- Verification compares descriptor and no-follow path identity before and after
  bounded SHA-256 reads. Device, inode, ownership and mode remain fixed; final
  file size/timestamps/link count are also checked. Directory content timestamps
  are excluded because unrelated package updates do not alter ancestry identity.
- `WAWVerifiedExecutable.identity` is an immutable observation, not permission
  to execute a later path. `revalidate()` repeats the live checks using the held
  chain. Revalidation failure permanently closes the entire handle.
- Context exit, explicit `close()` and finalization release owned descriptors.
  Close and revalidation share a lock, preventing descriptor reuse during a check.
  Repeated close is harmless; a closed handle cannot revalidate. No FD is exported.

The verifier does not prove loader/library integrity, file-capability/namespace
policy, supported vendor version, CLI runnability or an atomic descriptor-to-exec
handoff. Those remain required before a future launcher may execute anything.
Root-owned immutable deployment and host policy are separate evidence, not an
inference from a successful hash.

## Verification evidence

- `.venv/bin/python -m pytest -q tests/unit/test_waw_executable.py`: exit 0,
  80 passed and one native Linux test skipped on Mac.
- Scoped Ruff, Black and `mypy --platform linux`: exit 0.
- Independent sol read-only review: PASS. The reviewer reran 80 cases and used
  additional in-memory failure injection for revalidation EIO/KeyboardInterrupt
  and close-after-release EINTR; all safely closed and rejected later reuse.

Mac positive tests explicitly simulate ownership/platform/stat evidence while
performing real descriptor reads, replacement/rename checks and cleanup. The
native Linux test only reads `/usr/bin/true` as a non-root user; it never executes
it. Linux CI and its exact head are recorded separately in CURRENT_STATE. These
tests do not qualify a real tmux/CLI host. There is no visible UI change.
