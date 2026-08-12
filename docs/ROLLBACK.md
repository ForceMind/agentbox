# AgentBox Rollback

Status: Phase 8 implementation, pending human review

Use `agentbox system rollback [--to VERSION]` as root. Without an explicit
target, the install receipt selects the previous release. An explicit target
must exactly match that receipt-bound previous release; arbitrary older
retained releases are rejected. The backup manifest's application version and
migration revision must also match the target.

Rollback stops only AgentBox services, restores the recorded DB/config/unit
and tmpfiles snapshot when required, atomically activates the verified prior release,
restarts exact AgentBox services, and checks:

- active release and semantic version;
- database backup integrity, receipt-pinned manifest, exact migration revision,
  and absence of stale WAL/SHM dependency;
- systemd service state through readiness;
- loopback `/healthz` and `/readyz`;
- `/meta` version evidence.
- Runtime and Helper sockets through the deployment readiness gate.

Only after all checks pass is the result `Rollback verified`. Any failed check
is `Rollback attempted but verification failed` and requires operator recovery;
the CLI does not disguise uncertainty or continue mutating the host.
`agentbox system recover` is available only for an exact preflight-only or
`rollback_pending` journal. It revalidates the receipt-selected current release, exact database
revision, service/socket state, both health endpoints, and reported version
before closing the original journal as verified. It does not replay a
migration, restore a caller-selected backup, or change the active release.

Releases older than `0.2.5` require the original service-private database
parent (`agentbox:agentbox 0700`). The rollback boundary applies that exact
legacy mode only during an explicit recovery probe, then restores the hardened
`root:agentbox 1770` sticky layout. Automatic rollback to those releases is
rejected because they cannot survive a later restart under the hardened
boundary. After a successful legacy recovery probe, the operator must proceed
directly to a verified forward update; an intervening legacy restart fails
closed.

Rollback never changes Runtime HOME, Runtime authentication, project source,
root sessions, SSH, firewall, cloudflared, or Provider configuration. Backups
under `/var/lib/agentbox/backups` are retained for explicit recovery.
