# AgentBox Deployment

Status: Phase 8 implementation, pending human review

## Process identities

| Process | Identity | Privilege boundary |
|---|---|---|
| API/static Web | `agentbox:agentbox` | DB, logs, config read, Runtime socket client |
| Worker | `agentbox:agentbox` | Jobs, DB, typed Runtime requests |
| Runtime Executor | `agentbox-runtime:agentbox-runtime` | Runtime HOME and Project Root |
| Helper | `root:root`, socket activated | six fixed AgentBox service actions only |

`agentbox-runtime-ipc` is the narrow supplementary group for the Runtime UDS.
The API and Worker never run as root, use sudo, or directly execute Runtime or
system management commands.

## Filesystem layout

| Path | Owner | Mode | Purpose |
|---|---|---:|---|
| `/etc/agentbox` | `root:agentbox` | `0750` | TOML and root-created environment files |
| `/var/lib/agentbox` | `root:agentbox` | `1770` | SQLite parent; sticky bit protects root-owned recovery names |
| `/var/lib/agentbox/backups` | `root:root` | `0700` | verified privileged lifecycle backups |
| `/var/log/agentbox` | `agentbox:agentbox` | `0750` | reserved app logs; services default to journald |
| `/run/agentbox` | `root:agentbox-runtime-ipc` | `3770` | setgid/sticky protected sockets |
| `/srv/agentbox/projects` | `agentbox-runtime:agentbox-runtime` | `0700` | managed workspaces |
| `/home/agentbox-runtime` | `agentbox-runtime:agentbox-runtime` | `0700` | independent Runtime config/auth/tmux state |
| `/opt/agentbox` | `root:root` | `0755` | releases and atomic `current` link |

The database is `/var/lib/agentbox/agentbox.db`; migrations are an installer
step and never silently run at application startup. The frontend is a prebuilt
`web/dist` artifact served by the API, so Node and Vite are not production Web
requirements.

## Services and sockets

The installed units are `agentbox-api.service`, `agentbox-worker.service`,
`agentbox-runtime.service`, `agentbox-helper.socket`, and the on-demand
`agentbox-helper.service`. API/Worker/Runtime use `Restart=on-failure` with
bounded start limits. The Helper is not a permanent root daemon.

The Runtime socket is `/run/agentbox/runtime.sock`, owned by Runtime with the
IPC group and mode `0660`. The Helper socket is `/run/agentbox/helper.sock`,
owned by root with group `agentbox` and mode `0660`. Both protocols are
versioned, bounded, typed, reject unknown fields, and enforce Linux peer
credentials. Neither accepts executable, argv, environment, cwd, raw path,
PID, signal, package, or caller-selected service.

The unit sandbox uses absolute entrypoints, an empty capability bounding set,
loopback/network restrictions where applicable, `NoNewPrivileges`, private
devices/tmp/network where compatible, namespace restrictions outside Runtime,
`ProtectSystem=strict`, kernel/control-group protections, and exact
`ReadWritePaths`. Offline `systemd-analyze security` reports API 2.9, Worker
2.6, Runtime 3.7, and Helper 2.5 (`OK`). These are recorded exposure estimates,
not a hardening certification; functional behavior must also pass on the real
validation host.

## Network model

The production default is exactly `127.0.0.1:8787`. Installation does not open
a firewall, configure TLS, or trust forwarded headers. Remote access belongs
behind an operator-managed VPN, Tailscale, Cloudflare Tunnel, or HTTPS reverse
proxy. Trusted proxy addresses and browser origins must be configured
explicitly; wildcard trust is forbidden.

Authentication keeps Phase 3 Secure-cookie and HTTPS-origin rules. Loopback
health checks are intentionally unauthenticated, but authenticated browser use
requires the configured secure external origin. Local health checks do not
weaken cookie or origin policy.

## Production configuration

`/etc/agentbox/agentbox.toml` contains non-secret metadata. The application
secret is generated into `/etc/agentbox/environment` as `root:root 0600`, is
injected by systemd, and is never printed. Runtime and Helper environment files are separate so the
Runtime cannot read the Web application secret and the API cannot read Runtime
credentials. This application secret is not the future Phase 11 Secret Manager.

## Runtime migration

## Phase 9 sandbox profile

API, Worker, and Helper use `SystemCallFilter=@system-service` with `EPERM` for
denied calls. Worker and Helper have private networking; API is limited to Unix
and loopback Internet-family sockets. Runtime retains Internet access,
HOME/Project writes, namespace creation, and executable-memory compatibility,
while keeping an empty capability set, strict system files, private devices/tmp,
and kernel/control-group protection. Offline scores are API 1.4, Worker 0.6,
Runtime 3.7, and Helper 0.9; scores are evidence, not a security guarantee.

### Existing-state migration

Installation does not stop, adopt, rename, or migrate existing root Codex,
Claude, tmux, gh, or project state. The production Runtime begins independently
and may correctly report installed-but-unauthenticated or unavailable. Project
migration and Runtime authentication are explicit operator workflows.
