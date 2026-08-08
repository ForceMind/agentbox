# AgentBox Privileged Helper — Design Placeholder

No Privileged Helper is implemented in Phase 2. This directory contains no root-execution source, systemd unit, socket, or executable.

The future Helper will:

- run as root only because a small allowlist of host operations requires it;
- communicate through a protected, versioned Unix Domain Socket under `/run/agentbox`;
- never listen on TCP;
- accept only strongly typed, explicitly allowlisted actions;
- independently authenticate Unix peers and validate schema, action, parameters, state, paths, time limits, output limits, and concurrency;
- build fixed executable/argument/environment/working-directory policy on the server side;
- return stable, bounded, redacted results;
- remain separate from the non-root Web/API and Worker.

It will not:

- provide Shell, command-string, executable-path, argv passthrough, or generic file APIs;
- accept an arbitrary environment, package name, unit name, path, user name, UID/GID, URL, or script body;
- execute Git, gh, Codex, Claude, or tmux as root;
- read, copy, store, or return third-party Tokens, cookies, passwords, Pair Codes, SSH keys, or authentication files;
- modify SSH, firewall, tunnels, VPN, unrelated services, projects, or backups through a generic action;
- trust caller validation in place of its own checks.

Future protocol requirements include explicit major/minor negotiation, framed and size-limited messages, `SO_PEERCRED`, default-deny action dispatch, opaque resource identifiers, idempotency/confirmation binding, request IDs, timeouts, cancellation boundaries, output redaction, and mismatch failure. ADR 0002 and `docs/PERMISSIONS.md` govern implementation.
