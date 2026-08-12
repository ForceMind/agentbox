# AgentBox Installation Design

Status: Phase 1 design baseline. Phase 8 implementation and operator guidance
supersede operational details here; see `INSTALLATION.md`, `DEPLOYMENT.md`, and
`PLATFORM_SUPPORT.md`.

Status: Phase 1 design baseline; no installer is implemented in this phase.

## Goals

The installer must safely transform a supported user-controlled Linux server into an AgentBox host while preserving existing services. It is idempotent, inspectable, resumable, version-pinned, and rollback-aware. “One-click” means one reviewed entrypoint with a visible plan—not opaque remote root shell execution.

## Supported Platforms

MVP targets these families:

- OpenCloudOS 9 family;
- Rocky Linux 9 family;
- Ubuntu supported LTS family;
- Debian current stable family.

Exact minor releases and architectures become release metadata only after CI or manual qualification. x86_64 is the first required architecture because it is the verified Phase 0 environment; other architectures return Unsupported until artifacts and Runtime compatibility are tested.

Native systemd is required for the MVP. A container or non-systemd host returns Unsupported with explanation, not a partially installed system.

## Distribution Detection

`PlatformFacts` is collected from stable system interfaces:

- `/etc/os-release`: `ID`, `ID_LIKE`, `VERSION_ID`;
- `uname`: kernel and architecture;
- PID 1 and `systemctl`: systemd capability;
- package database/manager commands;
- filesystem/mount/cgroup facts;
- current identity and intended UID/GID collisions;
- existing AgentBox paths/units/releases;
- relevant Runtime/tool versions and ports.

Detection never chooses a backend from a user-supplied package manager string. Ambiguous distributions become Unsupported or require an explicit documented adapter.

## Package Manager Abstraction

```text
PackageBackend
├── detect()
├── query_installed(logical_dependency)
├── resolve(logical_dependency_set)
├── refresh_metadata_plan()
├── install_plan()
├── apply_exact_plan()
└── verify()

DnfBackend  -> OpenCloudOS / Rocky
AptBackend  -> Ubuntu / Debian
```

Application code names logical dependencies such as `git`, `tmux`, `bubblewrap`, `sqlite_cli`, or `build_toolchain`. A versioned platform map resolves them to approved package candidates. The API never supplies raw package names, repository URLs, or manager flags to the Helper.

Repository enablement is a distinct, high-risk plan step. GitHub CLI availability varies by RPM distribution; if an official repository is needed, the plan shows repository origin, key/fingerprint metadata, affected files, and removal steps. No repository is silently added.

## Installation Modes

### Inspect/Dry-Run

Default for remote initiation. Produces a plan with:

- supported/unsupported platform decision;
- dependencies already satisfied/missing/conflicting;
- users/groups and collision checks;
- paths, owners, modes, units, bind address/port;
- downloads, origins, versions, sizes, and available verification;
- existing services/projects/sessions classified as unmanaged;
- database/config changes and rollback boundary;
- actions requiring explicit confirmation.

No state changes occur.

### Apply

Consumes a server-created plan ID and digest that is still fresh. The Helper recomputes critical preconditions before each step. Caller cannot edit the plan or substitute packages/paths.

### Repair

Compares desired and observed AgentBox-owned state, then plans only approved repairs. It never adopts or rewrites unknown files/units automatically.

## Bootstrap Entry

Preferred public distribution is a small versioned bootstrap artifact with a published checksum/signature or provenance. The administrator downloads, verifies, and runs it locally. Documentation may offer a convenience download command, but the security model must not depend on blind `curl | sh`.

If a third-party Runtime officially distributes only a remote install script, AgentBox downloads it to root-owned staging with TLS/host/size limits, records its digest, displays the limitation and plan, and requires confirmation. AgentBox must not claim a signature that the publisher does not provide.

## Ordered Installation Steps

1. **Lock and snapshot:** acquire global install lock; inventory AgentBox state; never lock unrelated services.
2. **Preflight:** platform, resources, time, DNS/network, systemd, paths, ports, existing services, Runtime conflicts, UID/GID collisions.
3. **Phase 0 gates:** refuse identity creation if UID/GID 1001 collides with unresolved Codex ownership; flag existing root `codex.service`, cloudflared, port 8000, and root sessions as unmanaged.
4. **Resolve plan:** logical dependencies, release artifact, users/groups, directories, unit names, config defaults.
5. **Download/verify:** use staging under `/var/tmp/agentbox`; verify size, digest and available signature/provenance.
6. **Install release:** extract safely to `/opt/agentbox/releases/<version>.staging`, verify manifest, then rename atomically.
7. **Initialize identities:** choose unused IDs; create locked `agentbox` and `agentbox-runtime` plus narrow groups only after approval.
8. **Initialize FHS paths:** `/etc/agentbox`, `/var/lib/agentbox`, `/var/cache/agentbox`, `/srv/agentbox/projects`, and systemd-created `/run/agentbox`.
9. **Configuration:** write a versioned non-secret config from a validated schema; do not import root auth.
10. **Database:** create/verify SQLite with restrictive ownership; apply migrations in a transaction where supported.
11. **Units:** install only AgentBox-namespaced units; validate with systemd tooling; daemon-reload.
12. **Activate:** switch `/opt/agentbox/current`; start Helper/Runtime/Worker/API in dependency order on loopback.
13. **Verify:** API/UDS peer/DB/permission/listener/Doctor smoke checks.
14. **Admin bootstrap:** local TTY initializes the one administrator after services are healthy.
15. **Receipt:** write a non-secret installation receipt with version, completed step IDs, artifact digests, platform adapter, and outstanding warnings.

## Idempotency

Every step has:

- a stable step ID and schema version;
- a read-only `check()` that reports satisfied, change-needed, conflict, or unknown;
- explicit preconditions and desired state;
- an `apply()` that performs one bounded change;
- a `verify()` independent of the write path;
- rollback metadata or an explicit non-reversible warning.

Re-running the same version never rotates credentials, changes chosen UIDs, overwrites administrator configuration, re-clones projects, re-trusts workspaces, or restarts healthy unrelated services. Drift outside AgentBox-owned paths is reported, not corrected.

## Interruption and Re-entry

- A root-owned install journal records step IDs/statuses and sanitized summaries, never command output or secrets.
- On restart, the installer reacquires the lock and re-runs checks; it does not assume a recorded step completed.
- Completed immutable release directories are reusable only if manifest verification succeeds.
- Incomplete staging directories are quarantined with a plan; no automatic recursive deletion of an unknown path.
- A step interrupted after an uncertain external action becomes `needs_attention` and requires operator review.

## Logging

The console and install journal include request/plan/step IDs, target logical resource, start/end, outcome, error code, and safe remediation. They omit Pair Codes, tokens, cookies, passwords, OAuth codes, SSH keys, auth files, full environments, credential-bearing URLs, and raw third-party installer output.

Verbose mode cannot disable secret suppression. A support bundle contains allowlisted facts only.

## Verification

- files match release manifest and expected root ownership/modes;
- no release file is writable by service/Runtime users;
- service users cannot read each other's protected state;
- sockets have correct mode and peer rejection behavior;
- AgentBox binds only configured loopback address;
- existing listeners/units remain unchanged;
- SQLite integrity and schema version are correct;
- units use expected executable/config paths and hardening baseline;
- `agentbox doctor` returns qualified status with unresolved external dependencies clearly classified.

## Failure Rollback

Before the activation boundary, remove/quarantine only installer-created staging and revert individually recorded files/users when safe. After activation, restore previous `current`, configuration backup, database backup, and prior AgentBox units. Never roll back distribution packages automatically if they may be shared by other software; report them as retained dependencies.

If rollback cannot prove correctness, stop AgentBox units, preserve evidence, leave existing host services untouched, and return `needs_attention` with manual recovery steps.

## Offline and Network Failure

- Detection, status, local dry-run, and installed-release repair remain available offline.
- Plans distinguish DNS, TLS, repository metadata, artifact missing, authentication, and checksum failures.
- Downloads use resumable staging only when the artifact protocol safely supports it; final verification is mandatory.
- Cached artifacts require matching version, digest, origin, and expiry metadata.
- Offline bundles are a later optional feature and must be signed/manifested; the MVP does not accept an arbitrary local archive as trusted.

## Uninstall Strategy

Uninstall is post-MVP/high risk but its contract is planned:

- default removes only AgentBox units and immutable program releases after confirmation;
- preserve `/etc/agentbox`, `/var/lib/agentbox`, backups, Runtime HOME, and projects unless separately selected;
- never remove shared system dependencies by default;
- stop managed sessions only after explicit review;
- produce an inventory and recovery instructions before any deletion;
- authentication reset and permanent data deletion require separate challenges.

## Phase 2 Inputs

Phase 2 must choose packaging/build tooling, exact unit names, configuration schema, supported platform matrix, artifact signing approach, and installer language without implementing system changes during scaffolding.
