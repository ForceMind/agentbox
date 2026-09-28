# R12-D dormant WAW socket substrate

Status: software candidate on `codex/r12-installer-waw-sockets`, 2026-09-28.
The [R12 plan](project/PRODUCTION_READINESS_PLAN.md) governs subsequent
production composition and host qualification. This batch installs no real
host resource during development.

The installer package now contains two socket units targeting the existing
`agentbox-runtime.service`:

| Unit | Fixed path | FD name |
| --- | --- | --- |
| `agentbox-waw-control.socket` | `/run/agentbox-waw/workspace-control.sock` | `agentbox-waw-control` |
| `agentbox-waw-stream.socket` | `/run/agentbox-waw/workspace-stream.sock` | `agentbox-waw-stream` |

Both use `SocketUser=agentbox-runtime`,
`SocketGroup=agentbox-runtime-ipc`, `SocketMode=0660`, `Accept=no`, and
`RemoveOnStop=true`. `LISTEN_FDNAMES` carries the roles; systemd's cross-unit
FD order is not authoritative. The runtime loader added in PR #101 verifies
both named descriptors and the matching path. PID 1 delivery is still untested.

The installer plan records these units, creates `/run/agentbox-waw` as
root:`agentbox-runtime-ipc` mode 0750, its Runtime-owned `tmp` (0755) and
`tmux` (0700) children, and root-owned `auth-probe` (0755). It also creates
Runtime-owned `keys-v1` (0700) and separate Claude/Codex vendor homes (0700)
below `/var/lib/agentbox-waw`; no key or vendor credential is generated or
read. The Runtime service's write allowlist includes only its scratch, tmux
and vendor-home leaves. Existing new paths with mismatched mode or owner fail
before being adopted.

`enable_and_start` intentionally does not enable or start either WAW socket.
If matching package units are present, stop/uninstall closes them before the
Runtime service. An older release's backup without those units removes only
the exact package unit bytes during rollback and writes the restored unit
inventory to the receipt. Changed or unsafe unit files reject the operation;
the rollback preflight occurs before database restoration. Upgrading a future
release whose WAW unit asset bytes differ requires a deliberate versioned
transition because the current host stop path fails closed on that drift.

Local evidence: an x86_64 installer fixture on macOS completed 105 passing
unit cases with one `systemd-analyze` skip; focused directory, socket,
upgrade/rollback, tampered rollback and stop-order tests passed. The native
macOS aarch64 platform is intentionally unsupported by the installer.
Linux `systemd-analyze` and installer CI, PID 1 FD delivery, Runtime `_main`,
static key, policy/manifest/public anchor, native binary, cgroup delegation,
real Claude/Codex and host restart/cleanup remain separate required work.
G2/G3/HG-04 remain `NOT RUN`; this batch does not authorize host activation.
