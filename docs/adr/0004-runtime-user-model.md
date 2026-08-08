# ADR 0004: Separate non-root Runtime user

## Status

Proposed

## Context

Git file ownership, GitHub/Codex/Claude authentication, Claude Workspace Trust, and tmux socket ownership must agree. Model B—root owns every Runtime and project—would preserve some existing root state but makes third-party tools and repository content part of the root trust domain. Having Web/API own everything is better than root but lets a Web compromise directly own developer credentials and live sessions.

## Decision

Adopt Model A with two ordinary service identities: `agentbox` for Web/API and Worker, and `agentbox-runtime` for Project Workspaces, Git/gh, Codex, Claude, tmux, and their user-scoped authentication. A non-root Runtime Executor owned by `agentbox-runtime` exposes a narrow versioned UDS at `/run/agentbox/runtime.sock`; it accepts only Runtime/project actions. The root Helper does not run these tools.

New Workspace Trust is performed manually for the concrete registered project path, never `/root` or the broad project parent. The installer must detect UID/GID collisions rather than assume fixed numeric IDs.

## Alternatives Considered

- **Model B, root owns all Runtimes/projects:** rejected for excessive privilege, poor credential boundaries, and poor multi-user evolution.
- **One `agentbox` user for Web and Runtime:** simpler, but rejected because it gives Web/API direct ownership of third-party credentials and sessions.
- **Operator's existing login user:** possible future personal mode, but inconsistent for unattended service lifecycle and migration.
- **Per-project user:** stronger isolation but too operationally heavy for a single-admin MVP.

## Consequences

The product has an extra process/protocol and requires explicit interactive authentication as `agentbox-runtime`. Operators cannot reuse root authentication by merely pointing at private files. Current root-owned sessions/projects require explicit migration or remain unmanaged.

## Security Impact

A Web/API compromise must pass the allowlisted Runtime protocol and cannot directly read Runtime home credentials. The Runtime Executor still handles untrusted repositories and must enforce command/path/env/output constraints; it has no root privileges.

## Operational Impact

tmux, Git, Claude, and Codex processes share a consistent UID and HOME. Backups exclude authentication material. UID/GID discovery and ownership repair plans are required, particularly because Phase 0 found unmapped ownership 1001 on part of the existing Codex installation.

## Revisit Conditions

Revisit when adding multiple administrators/users, per-user credentials, stronger per-project isolation, or a supported migration path from existing operator accounts.
