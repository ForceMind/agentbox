# AgentBox Permissions and Linux Identity Model

Status: Phase 1 design baseline

## Decision

AgentBox adopts Model A: system services, Runtime operations, and root-only operations are separated. Model B—root owning all Runtime sessions and projects—is rejected for the MVP.

## Linux Identities

| Identity | Purpose | Login | File access | Prohibited access |
|---|---|---|---|---|
| `root` | operating system and Privileged Helper | existing host policy | AgentBox install/config/system paths | no daily Web/Runtime/Git/tmux work |
| `agentbox` | Web/API and Worker | locked/no interactive password | app DB, non-secret config, journals needed for own units, control sockets | Runtime HOME credentials, arbitrary project contents, root files |
| `agentbox-runtime` | Runtime Executor, Git, gh, Codex, Claude, tmux | password locked; shell available only for controlled local attach/admin flow | Runtime HOME and `/srv/agentbox/projects` | package manager, root Helper internals, AgentBox password/session DB writes |
| administrator OS account/root | local CLI/bootstrap/recovery | operator-controlled | `api.sock` through a dedicated admin group | no automatic access through Web credentials alone |

The MVP uses one Runtime identity for all managed projects. Future multi-user support replaces it with one Runtime identity or subordinate execution domain per project owner without changing the root boundary.

## Groups and Sockets

Exact numeric UID/GID values are selected at install time after collision checks; no fixed numeric ID is assumed.

Suggested logical groups:

- `agentbox`: primary service group for API/Worker state;
- `agentbox-runtime`: primary Runtime group;
- `agentbox-control`: narrow group allowing Worker-to-Runtime socket access;
- `agentbox-admin`: optional local OS users allowed to access `api.sock`.

| Socket | Owner/group | Mode | Allowed peers |
|---|---|---:|---|
| `/run/agentbox/api.sock` | `agentbox:agentbox-admin` | `0660` | local CLI users in admin group; peer UID mapped to a local principal |
| `/run/agentbox/runtime.sock` | `agentbox-runtime:agentbox-control` | `0660` | Worker identity only |
| `/run/agentbox/helper.sock` | `root:agentbox` | `0660` | Worker identity only |

Every server also enforces peer credentials and protocol version. Filesystem mode alone is insufficient.

## Web/API Permissions

Web/API runs as `agentbox`, never root. It may:

- read/write application metadata through the database layer;
- authenticate the administrator and create validated Jobs;
- read sanitized status/result models;
- serve static frontend assets read-only;
- listen on loopback and `api.sock`.

It may not:

- spawn shell, Git, gh, Codex, Claude, tmux, package-manager, or systemctl processes;
- read `/home/agentbox-runtime`, third-party auth files, tmux sockets, project file contents, `/root`, `/etc/shadow`, SSH material, or Helper configuration;
- write `/opt/agentbox`, `/etc/agentbox` root-owned files, systemd units, users/groups, or arbitrary modes/owners;
- connect directly to `helper.sock` from request handlers if architecture enforces Worker-only access.

## Worker Permissions

Worker also runs as `agentbox`. It may claim Jobs, invoke shared Application Services, and call typed Runtime/Helper clients. It has no general subprocess capability. A compromised Job payload remains a typed database record, not argv or a path.

Worker concurrency and per-resource locks are enforced even though Linux permissions do not provide them.

## Runtime Executor Permissions

Runtime Executor runs as `agentbox-runtime`. It may:

- manage registered projects beneath `/srv/agentbox/projects`;
- execute adapter-selected public Codex/Claude/Git/gh/tmux commands;
- maintain its own third-party CLI authentication and tmux socket;
- return bounded, sanitized results.

It does not expose auth files or environment to API/Worker. Authentication is performed through the third-party CLI's supported flow as the Runtime user. AgentBox stores only a status observation.

The executor accepts Project IDs and RuntimeInstallation IDs; it resolves paths and executable policy internally. It never accepts arbitrary paths, shell, argv, environment maps, unit names, or package names.

## Privileged Helper Permissions

The Helper is root only because its allowed actions need root. It does not become a generic privilege broker.

### Allowed Action Families

- `platform_query_privileged`
- `package_plan_apply` using a server-created logical dependency plan
- `agentbox_release_install`
- `agentbox_release_activate`
- `agentbox_release_rollback`
- `agentbox_units_reload`
- `agentbox_unit_action` for an exact compiled allowlist
- `agentbox_identity_initialize`
- `agentbox_directory_initialize`
- `agentbox_path_mode_repair` for exact FHS roots
- `agentbox_backup_snapshot` for approved AgentBox data

Each action has schema, preconditions, fixed executable resolution, time/output/concurrency limits, and a rollback/uncertainty policy.

### Explicitly Forbidden

- arbitrary command, script body, shell fragment, argv passthrough, environment map, file content, URL, package name, user name, UID/GID, path, or unit name from the caller;
- Git/gh/Codex/Claude/tmux execution as root;
- reading/copying Runtime or root auth material;
- firewall, SSH, cloud tunnel, VPN, kernel, bootloader, sudoers, or unrelated service modification;
- deleting projects, backups, logs, unmanaged users, or unmanaged units;
- resolving an action through the caller's PATH.

## Project Ownership

- Default root: `/srv/agentbox/projects`, initialized by root but not writable as a whole by Web/API.
- Managed project directories: `agentbox-runtime:agentbox-runtime`, normally `0750`.
- Git, Claude, tmux, and project file operations all execute as `agentbox-runtime`.
- Web/API accesses project metadata, not files. Runtime Executor returns explicit bounded read models.
- No global Git `safe.directory=*` workaround.
- A project whose owner/mode/path differs from its recorded policy becomes `needs_attention` until explicitly adopted/repaired.

## Existing `/root/projects` Compatibility

`/root/projects` is never the new default because `/root` is non-traversable to the Runtime user, root ownership pollutes Git state, and trusting a broad root path is unsafe.

Compatibility is an explicit adoption workflow, not transparent access:

1. discover project metadata read-only as an administrator;
2. stop related unmanaged sessions;
3. inspect owner, dirty Git state, remotes, hooks, submodules, size, symlinks, and secrets risk;
4. choose copy (recommended) or move in a dry-run plan;
5. back up or confirm recovery source;
6. copy into a staging path beneath `/srv/agentbox/projects` without following unsafe links;
7. assign Runtime ownership, verify content and Git status, then atomically activate;
8. leave the original untouched until explicit later cleanup outside MVP.

Existing root Codex/Claude authentication and tmux sessions are not copied. The Runtime user re-authenticates and completes project-specific Workspace Trust.

## Runtime and tmux Ownership

- All AgentBox-managed tmux sessions are created by `agentbox-runtime`.
- Session names derive from opaque RuntimeSession IDs and a fixed prefix, not raw project names.
- The Runtime user's socket is not shared with root's existing `/tmp/tmux-0` server.
- Helper may start/stop the fixed Runtime Executor systemd unit, but it does not call tmux/Codex/Claude directly.
- Local attach is an operator action performed as `agentbox-runtime` through a documented command; the Web only returns the command in MVP.

## systemd Unit Permissions

- manually installed unit files: root:root `0644` under `/etc/systemd/system`;
- executable releases: root:root, immutable to service users under `/opt/agentbox/releases`;
- writable paths granted through exact `ReadWritePaths`/`StateDirectory`/`RuntimeDirectory` declarations;
- API and Worker use `User=agentbox`; Runtime uses `User=agentbox-runtime`; Helper uses root;
- units receive minimal PATH and environment, no inherited interactive shell profile;
- recommended hardening includes `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome`, capability bounding, address-family restrictions, syscall filters, and explicit path exceptions, tailored per process;
- Helper cannot use hardening that prevents its specific allowlisted duties, but receives no network access except where an approved install/update action requires it.

## sudo and polkit

### sudo

Web/API and Worker receive no general sudo access. A narrow sudoers command list is also not the primary design because argument/path matching is fragile and tends to become a shell escape. Local administrators may use existing sudo/root for bootstrap and recovery outside the Web trust path.

### polkit

Polkit is not required in the MVP. It adds policy/runtime dependencies and does not replace typed action validation. It may be reconsidered for desktop/user-session integrations, not for the initial server architecture.

## Phase 0 Migration Gates

Before identities or units are created:

- choose unused UID/GID values and specifically avoid reusing unmapped 1001 until standalone Codex ownership is resolved;
- review the existing enabled/inactive root `codex.service` pointing to missing `/usr/bin/codex`;
- decide whether existing root projects are discovered only or offered a later adoption plan;
- do not touch root tmux/Claude/Codex processes;
- preflight port 8787 and existing cloudflared/iptables boundaries.

These are implementation gates, not blockers to Phase 1 documentation.
## Phase 7 ownership

The Runtime user owns Project Root, non-group/world-writable workspace
directories, Git processes, `gh` processes and Claude/tmux sessions. Web/API
never invokes Git or `gh`. AgentBox neither adds global `safe.directory`,
changes ownership, crosses into root's Git/GitHub authentication, nor creates
`/srv` in this phase. Ownership or top-level mode mismatch is
diagnostic/fail-closed work for deployment migration.
