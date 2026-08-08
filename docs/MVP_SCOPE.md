# AgentBox MVP Scope

Status: Phase 1 design baseline

## Scope Decision

The MVP is a **single-server, single-administrator, native-systemd AI workstation manager**. It includes a secure local Web panel, a recovery-oriented CLI, an idempotent installer, capability-aware Runtime management, persistent Claude sessions, minimal project/Git visibility, and durable single-host Jobs.

The candidate scope is accepted with three corrections:

1. Git write operations (`commit`, `push`, PR creation) are deferred because the first release must first prove path, credential, hook, confirmation, and audit boundaries.
2. Project hard deletion is deferred; MVP may create/clone/list projects but cannot permanently delete them.
3. Python 3.12+ is not an MVP minimum because the verified OpenCloudOS host has Python 3.11.6. The backend target is Python 3.11+ with CI covering supported versions; adopting 3.12 as a later minimum requires a compatibility ADR update.

## MVP Must-Have

### Installation and Lifecycle

- distribution, architecture, systemd, package-manager, dependency, path, permission, port, and existing-service detection;
- idempotent native systemd installation with dry-run and an explicit plan;
- dedicated non-root Web/API, Worker, and Runtime identities plus a root Privileged Helper;
- `agentbox status`, `agentbox doctor`, and machine-readable `--json` output;
- versioned release directories, basic update check/apply, health verification, and rollback;
- clear handling of interrupted, offline, unsupported, and partially completed installs.

### Local Authentication

- exactly one local administrator;
- CLI-only first-admin initialization;
- Argon2id password hashing, secure session-token storage by hash, expiry and revocation;
- HttpOnly/SameSite cookies, HTTPS-aware Secure cookie policy, CSRF protection, Origin checks, login throttling, and recent re-authentication for sensitive actions;
- loopback-only default listener.

### Codex Management

- find configured and PATH-visible candidates, resolve realpaths, show version and likely source;
- detect multiple executables and npm/standalone conflicts;
- report Capability state rather than assuming commands;
- install/update planning and controlled execution when supported;
- start and stop Remote Control through an adapter when capability is detected;
- generate a one-time Pair Code without persistence, logging, SSE, or audit-body capture;
- distinguish daemon health evidence from unsupported `status` commands;
- show bounded, redacted operational logs and repair guidance.

### Claude Session Management

- detect command, version, likely installation source, auth status when safely available, and Remote Control capability;
- create one namespaced tmux session per Project Workspace as the Runtime user;
- start Claude Remote Control only inside the selected project directory;
- list state, show bounded recent output, stop a managed session, and return a safe local attach command;
- prevent duplicate managed sessions and refuse collision with unmanaged sessions;
- guide manual Workspace Trust when it cannot be safely detected; never trust `/root` broadly.

### Minimal Projects and Git

- configure one project root, default `/srv/agentbox/projects`;
- create an empty Project Workspace and clone a credential-free HTTP(S) or SSH Git URL through a Job;
- list projects, copy path, and show branch, dirty-file count, HEAD summary, and sanitized remote URL;
- start Claude Remote from a registered project;
- validate ownership, canonical paths, symlinks, repository boundaries, and time/output limits;
- do not execute repository hooks during AgentBox-controlled MVP operations unless explicitly documented and sandboxed.

### Web Pages

- Login;
- Dashboard;
- Codex;
- Claude;
- Projects;
- Doctor;
- Logs;
- Settings.

The Web displays management controls and status, not a full terminal or code editor.

### Jobs, Diagnostics, and Audit

- SQLite-backed Job table and one separately supervised Worker process;
- `queued`, `running`, `succeeded`, `failed`, `cancelled`, and `needs_attention` states;
- lease, idempotency, timeout, cancellation, bounded output, and restart recovery;
- SSE for status/progress events;
- structured Audit Events with actor, action, target, time, request ID, outcome, and error class only;
- explicit error taxonomy: Unsupported, Unavailable, Unauthenticated, Broken, Conflict, ValidationFailed, Timeout, Forbidden, and NeedsAttention.

## MVP Optional

These may ship only if all must-have release gates are satisfied:

- create a local backup bundle for AgentBox metadata and selected clean project repositories;
- opt-in read-only health checks for a configured reverse proxy or tunnel without changing it;
- show Git ahead/behind counts when they can be computed without a network fetch;
- provide a limited project archive/export that excludes secrets and `.git` credentials;
- responsive install/update progress detail beyond the minimal SSE stream.

Optional work cannot delay security, rollback, Runtime, pairing, or project-session correctness.

## Deferred Beyond MVP

- `git add`, `git commit`, `git pull`, `git push`, branch deletion, force push, hard reset, and `gh pr create`;
- GitHub Issue, Actions, PR review, and repository administration;
- project permanent deletion and automated destructive cleanup;
- embedded browser terminal, interactive PTY, and general filesystem editor;
- WebSocket unless a later bidirectional PTY feature is approved;
- multi-server orchestration, multi-user workspaces, RBAC, enterprise SSO;
- Docker management or Docker as the default deployment;
- plugin system or marketplace;
- native mobile app, chat bots, cloud purchasing, Kubernetes, billing, telemetry;
- automated migration/adoption of existing root Codex/Claude/tmux sessions.

## Explicitly Never in the Product Contract

- arbitrary shell/API execution;
- raw user-supplied executable paths, argv lists, package names, environment maps, systemd unit names, or filesystem paths sent to root;
- storage or display of third-party tokens, cookies, passwords, OAuth codes, SSH private keys, full auth files, or persisted Pair Codes;
- default `0.0.0.0` binding;
- silent modification of SSH, firewall, cloud security groups, tunnels, or unmanaged services;
- using Codex/Claude private configuration structure as a required API.

## Acceptance Metrics

| Area | Release acceptance |
|---|---|
| Clean install | A documented clean reference VM reaches authenticated Dashboard and green/qualified Doctor without manual file edits |
| Idempotency | Re-running the same install plan produces no unintended state change and reports already-satisfied steps |
| Privilege | Web/API and Worker are non-root; only allowlisted system actions reach the root Helper |
| Network | Default listener is `127.0.0.1`; no AgentBox wildcard listener appears after default install |
| Pairing | Pair Code is displayed once and absent from SQLite, journald, Audit Events, Job summaries, traces, and fixtures |
| Codex | Installation conflicts and capabilities are reported; missing `remote-control status` does not mark the Runtime Broken |
| Claude | A project-scoped tmux session survives SSH disconnect and is stopped without affecting unmanaged sessions |
| Project safety | Traversal/symlink/hook/credential-in-URL tests fail closed; all Git files remain Runtime-user owned |
| Jobs | Restart recovery deterministically requeues safe work or marks uncertain work `needs_attention` |
| Upgrade | Previous release and database backup can be restored after an injected post-migration health failure |
| Security | No unresolved Critical/High release-blocking finding; required threat-model tests pass |
| Compatibility | Release-gated tests pass on the declared OpenCloudOS/Rocky/Ubuntu/Debian matrix |

## Release Conditions

- all must-have behavior is implemented and documented;
- required tests in `TEST_STRATEGY.md` pass on the release matrix;
- upgrade and rollback have been exercised from the previous supported release;
- threat-model controls have evidence, not only documentation;
- operator documentation identifies external access and backup responsibilities;
- third-party compatibility is stated as detected capability, not guaranteed private behavior;
- a license has been explicitly approved and added in a later phase.

## Failure Conditions

The release is not an MVP if any of the following is true:

- Web/API or Worker requires root;
- an endpoint accepts arbitrary commands or paths;
- Pair Codes or third-party credentials enter persistent storage or logs;
- default installation binds publicly;
- the installer overwrites existing services or projects without an approved plan;
- Runtime/Git/tmux files are root-owned by default;
- service restart can silently repeat an uncertain destructive Job;
- Codex/Claude capability changes cause unsafe fallback rather than Unsupported/NeedsAttention;
- no tested rollback exists for application and database changes.

## MVP Completion Statement

MVP completion means a server owner can perform the core AI-workstation lifecycle safely with minimal routine SSH. It does not mean every GitHub, Linux, or terminal workflow has moved into the browser.
