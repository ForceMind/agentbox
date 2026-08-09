# ADR 0002: Privilege separation with a narrow root Helper

## Status

Accepted

## Context

Some installation and maintenance actions require root, while HTTP parsing, authentication, project status, and Runtime workflows do not. Running the entire application as root would turn a Web flaw into unrestricted host control. Avoiding all privileged cooperation would prevent AgentBox from managing native installation and services.

## Decision

Web/API and Worker run as non-root `agentbox`. A minimal Privileged Helper runs as root and listens only on `/run/agentbox/helper.sock`. It accepts a versioned, strongly typed, allowlisted IPC protocol; authenticates peers with socket permissions and `SO_PEERCRED`; uses fixed executable paths, argument builders, working directories, environment allowlists, time/output/concurrency limits, and standardized errors.

The Helper may manage approved AgentBox systemd units, supported package plans, AgentBox users/directories/ownership, verified release activation/rollback, and narrowly enumerated system diagnostics. It does not run arbitrary shell text; execute Git, GitHub CLI, Codex, Claude, or tmux; read third-party credentials; serve HTTP; access arbitrary paths; change SSH/firewall/tunnels; or delete projects/backups through a generic file API.

## Alternatives Considered

- **Root Web/API:** rejected as an excessive blast radius.
- **Passwordless broad sudo:** rejected because command-line composition and policy are harder to constrain and audit.
- **polkit-first:** deferred; it adds policy/desktop integration complexity without removing the need for a narrow service protocol.
- **No privileged component:** insufficient for the installation and systemd scope.

## Consequences

The codebase needs a separate protocol, action registry, unit, tests, and upgrade compatibility window. Some operations become Jobs rather than direct requests. The boundary is more explicit and independently auditable.

## Security Impact

The Helper remains the highest-value target. Its protocol must reject unknown fields/actions, canonicalize all allowed paths, bind confirmations to exact digests, redact output, and default deny. Compromise of Web/API must not imply arbitrary root execution.

## Operational Impact

Helper and client versions require negotiation. The Helper never listens on TCP. Socket/group ownership and systemd sandbox directives are tested on real disposable VMs.

## Revisit Conditions

Revisit if required privileged actions can be eliminated, if a portable capability-based OS API replaces the Helper, or if formal review finds the protocol broader than a constrained sudo/polkit policy.
