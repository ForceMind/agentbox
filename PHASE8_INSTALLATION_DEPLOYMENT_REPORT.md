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
- Commits and Draft PR: recorded after this report is finalized
- Final development version: `0.2.4+dev.8`
- Validation artifact SHA-256:
  `250f1b9f63d157ea323ed9e52c7c4e3354cef407d6a0bc2c1bc0b8c26b0e8bb6`

## Platform

The real validation host is OpenCloudOS 9.4 x86_64 with native systemd. The
installer parses `/etc/os-release`; it never infers distribution from `uname`.
OpenCloudOS 9 is the real-host validation target. Ubuntu 22.04/24.04 have
fixture plus GitHub Actions groundwork. Rocky 9 and Debian 12 have fixture-only
preview coverage. `aarch64` is detected but explicitly unsupported until
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
| `/var/lib/agentbox` | `agentbox:agentbox` | `0700` |
| `/var/lib/agentbox/backups` | `root:root` | `0700` |
| `/var/log/agentbox` | `agentbox:agentbox` | `0750` |
| `/run/agentbox` | `root:agentbox-runtime-ipc` | `2770` |
| `/srv/agentbox/projects` | `agentbox-runtime:agentbox-runtime` | `0700` |
| `/home/agentbox-runtime` | `agentbox-runtime:agentbox-runtime` | `0700` |
| `/opt/agentbox` | `root:root` | `0755` |

Configuration files use `0640` with their exact reader group; the Helper
environment is `root:root 0600`; DB/receipt/journal are `agentbox 0600`;
backups are `root 0600`; unit files are `root:root 0644`.

## systemd Units

- `agentbox-api.service`: active, `User=agentbox`, `Group=agentbox`
- `agentbox-worker.service`: active, `User=agentbox`, `Group=agentbox`
- `agentbox-runtime.service`: active, `User=agentbox-runtime`
- `agentbox-helper.socket`: active/listening, `root:agentbox 0660`
- `agentbox-helper.service`: socket activated, one bounded connection, then
  normal inactive state

All five installed units pass `systemd-analyze verify`. Offline
`systemd-analyze security` reports Medium: API 7.0, Worker 6.7, Runtime 7.1,
Helper 7.1. The sandbox directives were functionally exercised on the real
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
includes safe TOML, managed units, version, revision, and release metadata. It
excludes projects, Runtime credentials, root state, and Provider secrets.

## Upgrade

Upgrade stages a distinct verified release and venv, backs up, migrates,
atomically activates `current`, restarts exact units, and now requires API,
Worker, Runtime, Helper socket, both UDS files, health/readiness, and meta
version before commit. Real healthy upgrade `0.2.2+dev.8 → 0.2.3+dev.8` passed;
the final `0.2.4+dev.8` deployment also passed.

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

- Backend: 362 passed
- Frontend Vitest: 25 passed
- Playwright: 54 passed (desktop and mobile Chromium)
- Installer/deployment focused: 55 passed
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
Doctor, and systemd analysis pass. Root Codex and Claude PIDs and the active
states of SSH, firewall, cloudflared, and legacy `codex.service` match the
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

## Known Limitations

- checksum verification is implemented; release signing/provenance is not;
- only OpenCloudOS has real-host evidence; Ubuntu is CI preview and
  Rocky/Debian fixture preview;
- `aarch64` is unsupported;
- SELinux/AppArmor policy coverage is absent on this host;
- reverse proxy/TLS/Tailscale/Cloudflare setup is operator-managed;
- Project tree backup and destructive purge are unavailable;
- Codex/Claude public behavior and authentication require per-version/operator
  validation;
- systemd security scores remain Medium and require Phase 9 review.

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
