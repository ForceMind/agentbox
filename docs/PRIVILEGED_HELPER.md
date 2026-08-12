# AgentBox Privileged Helper

Status: Phase 8 minimal implementation, pending human review

## Boundary

The Helper is a root, socket-activated service used only for fixed AgentBox
service lifecycle operations. Installation, package changes, users,
directories, release activation, migration, backup, update, and rollback remain
administrator-invoked installer responsibilities; they are intentionally not
expanded into runtime Helper powers.

Protocol version 1 permits only these no-argument actions:

- `SYSTEMD_DAEMON_RELOAD`
- `SYSTEMD_START_AGENTBOX_SERVICE`
- `SYSTEMD_STOP_AGENTBOX_SERVICE`
- `SYSTEMD_RESTART_AGENTBOX_SERVICE`
- `SYSTEMD_ENABLE_AGENTBOX_SERVICE`
- `SYSTEMD_DISABLE_AGENTBOX_SERVICE`

Each maps internally to an exact `/usr/bin/systemctl` argv and the compiled
AgentBox unit list. The protocol has no representation for shell, command,
executable, argv, environment, cwd, path, mode, user, UID/GID, PID, signal,
package, URL, file content, or caller-selected service/unit.

## Transport and validation

`agentbox-helper.socket` creates `/run/agentbox/helper.sock` as
`root:agentbox` mode `0660`. The server accepts only socket activation file
descriptor 3, requires effective UID 0, validates `SO_PEERCRED` against a
root-owned numeric UID allowlist, and rejects unknown or duplicate fields.

Requests are one newline-delimited JSON object, protocol version 1, sanitized
request ID, and one action. The frame is capped at 16 KiB; each connection has
a timeout and one request; global concurrency is bounded. Commands use an
absolute executable, fixed PATH/environment/cwd, no shell, fixed timeout,
bounded output, and process-group termination on timeout.

Auditing records only timestamp, action, caller UID, sanitized request ID, and
success/failure. It never records request payloads, secrets, Runtime
credentials, API keys, or command output.

## Security evidence

Tests cover invalid peer UID, malformed JSON, invalid protocol, unknown action,
unknown/extra fields, oversized frames, timeouts, concurrency limits, request
ID injection, and attempted path/argv/service injection. A repository boundary
check prevents API/Worker/shared layers from importing Helper or installer
implementation and confines root/process operations to approved layers.

The initial Web/API has no Restart AgentBox control. The ordinary Web cannot
choose any system service, and the Helper cannot run Codex, Claude, Git, gh, or
tmux.
