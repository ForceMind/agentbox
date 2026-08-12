# AgentBox Phase 8 Installation and Deployment Report

## Executive Summary

Phase 8 converts AgentBox from a development checkout into a checksum-verified,
versioned native systemd deployment for one Linux server. The implementation
adds an idempotent platform-aware installer, separate Web and Runtime users,
strict production paths, a typed socket-activated root Helper, explicit
database migration, online SQLite backup, staged update, verified rollback,
data-preserving uninstall, static frontend serving, and production diagnostics.

Automated backend, frontend, browser, installer, security-boundary, type,
format, and dependency checks pass. A gated OpenCloudOS 9.4 x86_64 fresh
installation and multi-version update/rollback exercise passes after two
fail-closed validation findings were fixed and retested. This is Phase 8
evidence, not a general production-readiness or multi-distribution support
claim.

## Branch / Commits / PR

- Repository: `ForceMind/agentbox`
- Baseline: `90c7f5dd6d15369753079e9f8965d67091eed818`
- Branch: `phase/8-installation-deployment`
- Commits: 11 semantic Phase 8 commits, including the post-review blocker fixes
- Draft PR: `https://github.com/ForceMind/agentbox/pull/28`
- Final development version: `0.2.8+dev.8`
- Validation artifact SHA-256:
  `b93544f3235067aa8150b8c280ded283ae0b7659fe3bd1885b1afe7b19c6b6cb`

## Platform

The real validation host is OpenCloudOS 9.4 x86_64 with native systemd. The
installer parses `/etc/os-release`; it never infers distribution from `uname`.
OpenCloudOS 9 is the real-host validation target. Ubuntu 24.04 has CI-preview
coverage. Ubuntu 22.04 is an unsupported rejection fixture because stock
Python 3.10 is below the AgentBox 3.11 minimum. Rocky 9 and Debian 12 have
fixture-only preview coverage. `aarch64` is detected but explicitly unsupported until
artifacts and Runtime dependencies are qualified.

No package change was necessary on the real host because Python/venv, Git,
tmux, curl, bubblewrap, SQLite, and systemd were already present. Package
install mappings are fixed and internal for DNF/APT.

## Process Identities

| Identity | Real UID:GID | Process responsibility |
|---|---:|---|
| `agentbox` | `993:994` | API, static Web, Worker, SQLite, Jobs |
| `agentbox-runtime` | `992:993` | Runtime Executor, projects, Codex, Claude, tmux, Git, gh |
| `root` | `0:0` | installer and on-demand Helper only |

Both service accounts use `/usr/sbin/nologin`. Group
`agentbox-runtime-ipc` GID 992 contains both service users and grants only the
Runtime socket filesystem boundary.

## Directory Layout

| Path | Owner/group | Mode |
|---|---|---:|
| `/etc/agentbox` | `root:agentbox` | `0750` |
| `/var/lib/agentbox` | `root:agentbox` | `1770` |
| `/var/lib/agentbox/backups` | `root:root` | `0700` |
| `/var/log/agentbox` | `agentbox:agentbox` | `0750` |
| `/run/agentbox` | `root:agentbox-runtime-ipc` | `3770` |
| `/srv/agentbox/projects` | `agentbox-runtime:agentbox-runtime` | `0700` |
| `/home/agentbox-runtime` | `agentbox-runtime:agentbox-runtime` | `0700` |
| `/opt/agentbox` | `root:root` | `0755` |

Non-secret configuration uses `root:agentbox 0640`; the application and Helper
environments and receipt/journal are `root:root 0600`; DB is
`agentbox:agentbox 0600`; backups are root-only; unit files are
`root:root 0644`. Sticky/setgid parent modes prevent either application or IPC
peer from replacing root- or other-peer-owned entries.

## systemd Units

- `agentbox-api.service`: active, `User=agentbox`, `Group=agentbox`
- `agentbox-worker.service`: active, `User=agentbox`, `Group=agentbox`
- `agentbox-runtime.service`: active, `User=agentbox-runtime`
- `agentbox-helper.socket`: active/listening, `root:agentbox 0660`
- `agentbox-helper.service`: socket activated, one bounded connection, then
  normal inactive state

All five installed units pass `systemd-analyze verify`. Real-host
`systemd-analyze security` reports API 2.7, Worker 2.0, Runtime 3.7, and Helper
2.3 (`OK`). The sandbox directives were functionally exercised on the real
host; these scores are evidence, not a hardening certification.

## API

API runs non-root, serves the built `web/dist` artifact, and listens exactly on
`127.0.0.1:8787`. `/healthz`, `/readyz`, and `/api/v1/meta` pass. Authenticated
browser security remains governed by Secure cookies and explicit HTTPS origins
behind an operator-managed proxy. No firewall, proxy, tunnel, or TLS setup is
performed.

## Worker

Worker runs non-root as `agentbox`, uses the production DB and typed Runtime
socket, and has no root/sudo/general subprocess boundary.

## Runtime Executor

Runtime runs as `agentbox-runtime` with HOME `/home/agentbox-runtime`, Project
Root `/srv/agentbox/projects`, and an exact environment/PATH. A same-UID stale
Runtime socket is removed only after a failed connection and stable inode/type/
owner recheck; active or changed sockets fail closed.

Real production status reports Codex, Claude 2.1.228, tmux 3.4, Git, and gh
through the Runtime boundary. GitHub is unauthenticated; Runtime authentication
is not fabricated. Tool probes created only independent Runtime-user cache/
backup metadata. No root credential files were copied or read.

## Privileged Helper

Helper protocol v1 exposes only six fixed actions: systemd daemon reload and
start/stop/restart/enable/disable of the compiled AgentBox unit set. There is no
shell, command, executable, argv, environment, cwd, raw path, mode, user,
package, PID, signal, or caller-selected unit/service field. A real malformed
`RESTART_SSH` request was rejected as `HELPER_PROTOCOL_INVALID`; the Helper
exited successfully and its socket remained active.

## UDS Security

- Runtime socket: `agentbox-runtime:agentbox-runtime-ipc 0660`
- Helper socket: `root:agentbox 0660`
- `SO_PEERCRED` UID validation on both servers
- versioned exact-schema messages, unknown-field/action rejection
- 16 KiB Helper frame cap, bounded request/connection/concurrency/timeout
- no caller path/argv/env/executable/PID/signal control

## Installer

The thin Bash bootstrap delegates to Python. Plan verifies platform, artifact,
dependencies, systemd, port, and installation state without persistent writes.
Apply requires EUID 0, a valid SHA-256, safe archive/manifest, and a global
non-blocking lifecycle lock. Extraction rejects traversal, absolute names,
links, devices, duplicates, and count/size overflow. Writes use no-follow,
temporary files, fsync, atomic replacement, and object identity checks.

The final artifact includes one offline AgentBox wheel plus all dependency
wheels, migrations, Alembic config, and prebuilt frontend. Production does not
install Python packages globally and does not need Node/Vite to serve Web.

## Idempotency

Fixture reinstall proves that a same-version identical artifact makes no
lifecycle change and preserves secret, TOML additions, DB/admin fixture, and
projects. Same-version content mismatch, newer-installed downgrade, partial
state, unsafe symlink, unknown unit, and directory collision fail closed.

## Third-party Dependencies

Base dependencies use fixed distro package mappings and verify availability
after install. Codex, Claude, and gh separate detect/version/install-policy/
verify from authentication. Phase 8 detects existing tools and documents
official setup guidance; it does not automatically upgrade a working Runtime.
The static Web artifact removes Node as a production Web requirement.

## Codex / Claude Installation Policy

Install is not login. Any future third-party install command must first be
revalidated against then-current official public documentation. No historical
installer URL is treated as permanent. Existing installations are detected and
never overwritten silently.

## Runtime Authentication Migration

The installer did not copy, chown, read, log out, stop, adopt, or rename
`/root/.codex`, `/root/.claude`, `/root/.config/gh`, root Runtime processes, or
root sessions. Runtime user authentication remains explicit manual setup.

## Database

Production SQLite is `/var/lib/agentbox/agentbox.db`, owned by `agentbox 0600`.
WAL, foreign keys, busy timeout, and explicit Alembic migrations remain in use.
The installed revision is `0002_project_jobs`. Application startup never runs
migrations. No production administrator was auto-created.

## Backup

Before each upgrade, services are quiesced and SQLite's online backup API
creates a root-owned snapshot. The backup switches its private copy to DELETE
journal mode, passes integrity and complete per-file digest verification, and
includes safe TOML, managed units, the tmpfiles policy, version, revision, and release metadata. It
excludes projects, Runtime credentials, root state, and Provider secrets.

## Upgrade

Upgrade stages a distinct verified release and venv, backs up, migrates,
atomically activates `current`, restarts exact units, and now requires API,
Worker, Runtime, Helper socket, both UDS files, health/readiness, and meta
version before commit. Real healthy upgrade `0.2.2+dev.8 → 0.2.3+dev.8` passed.
The final review found and repaired two recovery incompatibilities before the
verified forward update `0.2.4+dev.8 → 0.2.5+dev.8` passed.
After automated review feedback, the receipt-bound identity and rollback-target
fixes were validated by healthy updates through `0.2.8+dev.8`.

## Rollback

Rollback validates a SemVer target, verified release, receipt-bound backup,
root ownership, bundle digests, DB integrity, unit/config restoration, service
state, UDS state, health/readiness, and version. Real rollback
`0.2.3+dev.8 → 0.2.2+dev.8` was verified, after which forward update was
reapplied. Fixture fault injection separately proves `rollback attempted but
verification failed` is not reported as success.

## Network Exposure

Only `127.0.0.1:8787` was created. Port 8000, SSH, firewall, cloud security
groups, cloudflared, nginx/apache, and Docker were unchanged. Trusted proxies
default empty and no forwarded header source is trusted automatically.

## Production Config

`/etc/agentbox/agentbox.toml` contains non-secret settings. A CSPRNG application
secret lives only in `/etc/agentbox/environment` and was absent from inspected
journald output. Runtime and Helper environments are separate. This app secret
does not implement or anticipate the Phase 11 Provider Secret Manager.

## Doctor

Production `agentbox status` reports API/Worker/Runtime running, Helper
available, DB/Project Root ready, Codex/Claude/tmux/Git installed, and GitHub
unauthenticated. Doctor adds safe platform, identity, mode/owner, unit, service,
socket, listener, migration, config, and Runtime-tool evidence without secrets.

## Automated Tests

- Backend: 423 passed
- Frontend Vitest: 25 passed
- Playwright: 54 passed (desktop and mobile Chromium)
- Installer/deployment focused: 115 passed
- Black, Ruff, mypy, source boundary: passed
- `systemd-analyze verify`: passed
- pip audit and pnpm high-level audit: no known vulnerabilities

## CI

Existing Backend, Frontend, Security, and E2E workflows remain. A Deployment
workflow adds a safe Ubuntu 22.04/24.04 and Python 3.11/3.13 matrix for
installer, Helper, deployment/static fixtures, and the source boundary. It does
not mutate runner users or `/etc`. Required remote PR checks are evaluated
after the Draft PR is pushed.

## Real-host Changes

Created users `agentbox`, `agentbox-runtime`; groups `agentbox`,
`agentbox-runtime`, `agentbox-runtime-ipc`; the directory/config/DB/release
layout above; five units; one tmpfiles policy; and the loopback listener. No
packages were installed. Multiple versioned validation releases and root-owned
backups are intentionally retained. Failed-attempt artifacts and diagnostic DB
files were moved to named `/tmp/agentbox-failed-install-recovery.*` directories
instead of being destructively discarded.

## Real-host Validation

Fresh install, migrations, services, static/API endpoints, loopback listener,
users/modes, UDS, process identities, Helper rejection, cross-user denials,
online backup, update, rollback, rollback verification, final update, status,
Doctor, and systemd analysis pass. The two baseline root Codex processes and
the baseline root Claude process remain present with their original start
times. Additional root Claude daemon activity is independent of AgentBox;
no AgentBox service runs under root Runtime identity or accesses those homes.
SSH, firewall, cloudflared, and legacy `codex.service` active states match the
pre-install snapshot.

## Security Review

Threats T-71 through T-88 document Web-to-Helper escalation, UDS spoofing,
symlink/TOCTOU/world-writable paths, package/artifact supply chain, archive
escape, rollback mismatch, migration failure, stale symlinks/sockets,
unit/environment injection, secret permissions, restart loops, credential and
project crossover, partial install, lifecycle races, and PATH hijacking.

Real UID tests prove Web cannot read Runtime files/write projects/systemd or
invoke an arbitrary Helper action, and Runtime cannot read app secret/write
config/systemd/connect to Helper. Helper and Runtime injection, frame, peer,
timeout, concurrency, and stale socket tests pass. No Critical/High dependency
finding was reported.

## Deviations

The first real install failed closed at migration because Alembic did not read
TOML and needed a fixed production `AGENTBOX_DATABASE_URL`; no release or DB was
left active. The second attempt passed migration but exposed an immediate
startup health race. Both were fixed with a fixed installer-only DB URL and a
bounded readiness poll.

The first upgrade exposed a stale Runtime socket after SIGTERM and ephemeral
SQLite backup WAL sidecars. The lifecycle's earlier API-only health check did
not catch Runtime failure. Fixes add stable-inode same-UID stale-socket
recovery, DELETE-journal backup copies, complete bundle verification, and a
service/socket deployment gate. A malformed Helper test later exposed a
`RuntimeMaxSec` failure state; Helper now handles one bounded activation and
exits normally. All fixes gained regression coverage and passed a new real-host
cycle.

No Accepted ADR was overturned and no Proposed ADR or human architecture
approval is required.

## Final Privilege & Recovery Review

### Remaining systemd security findings

All four services now score `OK`, not Medium. Remaining analyzer findings are
accepted, explicit capabilities rather than blanket access:

- API — exposure 2.7. It needs AF_UNIX for Runtime IPC, AF_INET for the exact
  loopback listener, host networking for that listener, and the IPC
  supplementary group. `IPAddressAllow=localhost` plus `IPAddressDeny=any`
  constrains IP destinations. A chroot/private user namespace and broad syscall
  deny list remain deferred until Python/SQLite/static-serving compatibility is
  qualified.
- Worker — exposure 2.0. `PrivateNetwork=true`; AF_UNIX and the IPC
  supplementary group are required for Runtime requests. A private user
  namespace and broad syscall deny list remain deferred for Python/SQLite/UDS
  compatibility.
- Runtime — exposure 3.7. It requires its private HOME, Project Root, AF_UNIX,
  provider network access, and user/mount/process namespaces used by bubblewrap.
  `MemoryDenyWriteExecute` and namespace restriction remain intentionally off
  for Node/V8, Codex, Claude, tmux, and bwrap. It still has an empty capability
  bounding/ambient set and cannot write system configuration.
- Helper — exposure 2.3. It remains UID 0 solely to issue the six compiled
  AgentBox systemd lifecycle operations through `/usr/bin/systemctl`. Its
  capability bounding and ambient sets are empty, network is private, only
  AF_UNIX is allowed, filesystem is read-only, and it has no writable path.
  Private users/chroot and a broad syscall deny list are deferred because they
  can break host systemd-bus access; the Helper is socket activated and handles
  one bounded request.

### Privilege boundary

Real UID probes confirm `agentbox` cannot read Runtime HOME/credentials, write
Project Root or systemd units, and `agentbox-runtime` cannot read the root-only
application environment or DB, or write AgentBox config/systemd. API, Worker,
and Runtime run as their declared non-root users. `/var/lib/agentbox` is
root-owned sticky `1770`; `/run/agentbox` is root-owned sticky/setgid `3770`;
receipt, journal, backup, config-secret, releases, current symlink, and units
cannot be replaced by either service identity. No set-ID executable, file
capability, world-writable executable, runtime sudo, or generic root primitive
exists.

### Helper attack surface

Protocol v1 is exact-schema and maps enum values only to fixed AgentBox unit
operations. Tests and real probes reject caller fields for service, path,
argv, executable, command, cwd, env, mode, UID/GID, package, PID, signal,
unknown action, extra frame, invalid Unicode/newline, and oversized input.
Socket mode is `root:agentbox 0660`; SO_PEERCRED validates both primary UID and
GID. Runtime and an unrelated user cannot connect. An allowed API peer sending
an SSH/service-injection payload receives `HELPER_PROTOCOL_INVALID`.

### Upgrade crash recovery

The root-only schema-2 journal records a random transaction ID plus each exact
path/type, `existed_before`, initial owner/mode/device/inode, and created-object
identity. Restart classifies preflight-interrupted, staged, partially migrated,
activated, rollback-pending, and unknown states without replay. Explicit
`system recover` is limited to exact preflight-only or rollback-pending state
and verifies receipt-selected current release, DB revision/integrity, services,
sockets, health/readiness, and reported version. A conflicting same-version
staging directory is rejected before journal mutation.

The review intentionally exercised failure recovery. It found that the new
root-owned sticky DB parent initially conflicted with both the old application
validator and root-run explicit migration. The final policy accepts only the
legacy service-private `0700` shape or exact root-owned sticky `1770` shape;
non-root processes additionally require the directory group. Pre-0.2.5
automatic rollback is rejected because it cannot survive a later restart under
the hardened boundary. The bounded legacy recovery probe exists only to reach
a verified forward update.

### Rollback verification

The rollback bundle now includes DB, safe config, all managed units, and the
tmpfiles policy, each covered by the root-owned manifest and receipt-pinned
digest. Restore removes WAL/SHM after service stop, atomically restores the DB,
and verifies integrity plus target migration revision. Service restart,
healthz, readyz, reported version, Runtime/helper sockets, missing old release,
corrupt backup, and DB-integrity failures all remain distinct negative tests.
Only the complete predicate can report `Rollback verified`.

### Real-host post-review evidence

The final active release is `0.2.8+dev.8`; API/Worker/Runtime and Helper socket
are active, Helper service is normally inactive, and all process UIDs match the
model. `/healthz`, `/readyz`, meta version, SQLite integrity/revision, both UDS
owners/modes, Doctor, systemd unit verification, and exposure analysis pass.
The only TCP listener is `127.0.0.1:8787`. The application secret digest is
unchanged from the pre-review snapshot, is absent from inspected journald, and
the environment remains `root:root 0600`. No package, SSH, firewall,
cloudflared, nginx, or root Runtime change was performed.

The first post-review update attempts failed closed and were not hidden: one
exposed the old-release DB-parent compatibility boundary; one exposed a
preflight journal left by a conflicting staged artifact; and one exposed that
tmpfiles had not been part of the rollback bundle. DB/current identities stayed
verified, failed releases were moved intact to named `/tmp` quarantine paths,
and each defect received an automated regression before the final real update
passed.

The post-ready automated review then identified five additional blockers. The
installer now refuses unproven pre-existing service-account/group names,
restricts rollback to the receipt's direct previous release and validates the
backup's target version/revision, preflights every uninstall target before
stopping services, rejects stock Ubuntu 22.04 due its Python 3.10 runtime, and
documents the implemented `--to` rollback option. Targeted tests cover account
shape/provenance, retained-release rollback mismatch, backup-target mismatch,
and zero-mutation uninstall refusal. The final `0.2.8+dev.8` real-host update
proves the receipt-bound identities match the installed accounts.

## Known Limitations

- checksum verification is implemented; release signing/provenance is not;
- only OpenCloudOS has real-host evidence; Ubuntu 24.04 is CI preview, Ubuntu
  22.04 is unsupported, and Rocky/Debian are fixture preview;
- `aarch64` is unsupported;
- SELinux/AppArmor policy coverage is absent on this host;
- reverse proxy/TLS/Tailscale/Cloudflare setup is operator-managed;
- Project tree backup and destructive purge are unavailable;
- Codex/Claude public behavior and authentication require per-version/operator
  validation;
- system-call deny-list hardening is deferred pending Runtime/CLI compatibility
  qualification; the real-host exposure scores are 2.0–3.7 (`OK`).

## Remaining Manual Setup

- `agentbox admin init` as the production `agentbox` identity;
- independent Codex login as `agentbox-runtime` if required;
- independent Claude login as `agentbox-runtime` if required;
- independent `gh auth login` as `agentbox-runtime`;
- optional HTTPS reverse proxy/VPN/tunnel with explicit origin/trusted-proxy
  configuration;
- operator-managed project import and project backup policy.

## Phase 9 Recommendation

After human review and merge of the Phase 8 Draft PR, proceed only under a
separate Phase 9 authorization to security and compatibility hardening. Phase
11 Provider/Secret/Runtime Continuity remains `NOT STARTED`; no Provider
Manager, Secret Manager, Provider switch, API key access, or Codex config
mutation occurred.
