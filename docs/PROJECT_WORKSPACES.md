# Project Workspaces

## Model

Phase 7 makes `Project` a durable domain entity. Its opaque `prj_*` ID is the
API identity; its normalized slug and immutable `relative_path` are not
caller-controlled paths. The database stores only the relative component.
Runtime resolution joins that component to the configured Project Root and
rejects roots or children that are symlinks, inaccessible, nested, missing,
outside the root, foreign-owned, or unsafe because the root/workspace is
group/world writable.

Development uses `.agentbox-dev/projects`. The production architecture remains `/srv/agentbox/projects`; this phase does not create that directory or modify host ownership.

## Creation and cloning

Create and Clone reserve a Project row in `creating` state and enqueue a typed
durable Job. Runtime creates a marker-bound staging workspace under
`.agentbox-tmp`, then activates it with descriptor-relative Linux
`renameat2(RENAME_NOREPLACE)` and a directory fsync. It never falls back to an
overwriting rename. A failure can remove only the operation directory or final
directory carrying both the exact Job marker and staging identity. Empty
Project rollback additionally requires the marker to be the only entry; clone
rollback uses the distinct clone marker before bounded recursive cleanup. A
final-path or case-normalized collision removes only unused owned staging.
Unknown, non-empty empty-Project, or user-created directories are never removed.

The Project becomes `ready` in the database only after activation and Runtime
validation. Failure after that transition preserves the workspace and records
`needs_attention`; it never rolls back an already-ready workspace.

Clone accepts only bounded GitHub HTTPS and `git@github.com` repository identities. Local paths and Git `file`, `ext`, helper, or option injection are rejected. Submodules are not initialized and LFS smudge is disabled.

## Phase 6 migration

Safe immediate children previously enumerated by Phase 6 are reconciled into formal Project rows without moving them. Claude APIs expose the formal Project ID, while Runtime continues receiving the immutable historical relative key. Deterministic tmux naming therefore remains unchanged and existing managed sessions are not orphaned or adopted by similarity.

## Lifecycle limits

There is no filesystem Project Delete. Creating, ready, error, and archived states are modeled, but Phase 7 does not expose destructive deletion. Workspace paths are not accepted in API bodies. Project mutations are serialized by the durable Job resource lock.
