# AgentBox Rollback

Status: Phase 8 implementation, pending human review

Use `agentbox system rollback [--version VERSION]` as root. Without an explicit
target, the install receipt selects the previous release. The command refuses
an unknown/unverified release or a database-incompatible target without the
recorded verified backup.

Rollback stops only AgentBox services, restores the recorded DB/config/unit
snapshot when required, atomically activates the verified prior release,
restarts exact AgentBox services, and checks:

- active release and semantic version;
- database backup integrity and compatibility;
- systemd service state through readiness;
- loopback `/healthz` and `/readyz`;
- `/meta` version evidence.

Only after all checks pass is the result `Rollback verified`. Any failed check
is `Rollback attempted but verification failed` and requires operator recovery;
the CLI does not disguise uncertainty or continue mutating the host.

Rollback never changes Runtime HOME, Runtime authentication, project source,
root sessions, SSH, firewall, cloudflared, or Provider configuration. Backups
under `/var/lib/agentbox/backups` are retained for explicit recovery.
