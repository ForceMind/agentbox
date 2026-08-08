# ADR 0003: Project Workspaces under `/srv/agentbox/projects`

## Status

Accepted

## Context

Projects are mutable service-managed workspaces used by Git, Claude, and tmux. They must be portable and backup-friendly, remain outside program releases and Web static files, and be reachable by an ordinary Runtime user. The assessed `/root/projects` is beneath a non-traversable `/root` ancestor and is unsuitable for a non-root service. `/opt/agentbox/projects` would mix mutable user data with installed program files.

## Decision

New installations use `/srv/agentbox/projects/<project-slug>` as the only default project root. Each Project record has an immutable ID, validated slug, canonical path, ownership, and lifecycle state. Files are owned by `agentbox-runtime`; Web/API has metadata access and delegates file/Git operations. `/opt/agentbox` contains releases/static files, `/etc/agentbox` config, `/var/lib/agentbox` state/backups, and `/run/agentbox` ephemeral IPC.

Legacy `/root/projects` content is never automatically trusted, moved, chowned, or registered. An explicit future adoption Job copies to a staging directory beneath `/srv`, validates path/ownership/repository state, then atomically activates after confirmation. Copying is preferred to in-place control.

## Alternatives Considered

- **`/root/projects`:** rejected as the default because it forces root ownership and broad trust of `/root`.
- **`/opt/agentbox/projects`:** rejected because `/opt` is for installed program payloads, not mutable user workspaces.
- **`/home/agentbox/projects`:** viable for a personal interactive user, but less clear than `/srv` for service-managed data and conflicts with separating Web and Runtime identities.
- **Arbitrary configured roots:** deferred because it enlarges path and backup policy complexity.

## Consequences

Backups and migrations have a stable project root. Manual shell users need explicit access or attach instructions. Existing root projects require a migration workflow and temporary duplicate disk capacity.

## Security Impact

All path operations use Project IDs and race-resistant canonical resolution beneath the root; symlink traversal, unexpected mounts, and path-prefix tricks are rejected. Web static serving can never expose this directory.

## Operational Impact

Install creates the root with deliberate owner/mode; Git, Claude, Codex workspace commands, and tmux all run as `agentbox-runtime`. Backup policy can separately snapshot repositories and AgentBox state.

## Revisit Conditions

Revisit for true multi-user isolation, storage-volume selection, network filesystems, per-user home integration, or multiple approved workspace roots.
