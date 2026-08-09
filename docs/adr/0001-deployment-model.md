# ADR 0001: Default native systemd deployment

## Status

Accepted

## Context

AgentBox manages host systemd services, package managers, Unix users and permissions, tmux sessions, local Git workspaces, and Codex/Claude installations. The Phase 0 host runs systemd successfully and does not have Docker installed. Containers would add a host-control escape path or extensive mounts while providing limited isolation for the operations that define the product.

## Decision

The MVP defaults to native systemd services for Web/API, Worker, Runtime Executor, and Privileged Helper. Docker is not installed or required by AgentBox. A containerized development environment or later optional Web tier may be evaluated separately, but cannot be described as the default host-management deployment.

## Alternatives Considered

- **All-in-Docker:** rejected for the MVP because safe control of host systemd, users, packages, tmux, credentials, and project ownership becomes more complex and tends to require dangerous mounts or a privileged container.
- **Hybrid by default:** deferred; it increases two deployment surfaces before the single-host model is proven.
- **One native root service:** rejected because deployment convenience does not justify a Web-facing root process.

## Consequences

AgentBox must build and test distro-specific native installation, units, filesystem ownership, and upgrades. Operators can use standard journald and systemd recovery. Container-only portability claims are not made.

## Security Impact

Native deployment avoids a privileged container and Docker socket exposure, but systemd hardening and strict Unix-user separation become mandatory. The Web/API still binds to loopback and runs non-root.

## Operational Impact

OpenCloudOS/Rocky use the RPM-family adapter and Ubuntu/Debian the APT-family adapter. Units are versioned program contracts. Existing host units and services are inventoried and never silently replaced.

## Revisit Conditions

Revisit if a later remote-only mode no longer manages the host, if a secure rootless container boundary can satisfy all host operations, or if supported environments lack usable systemd.
