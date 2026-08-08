# AgentBox Architecture Decision Records

ADRs record decisions that change AgentBox's trust boundaries, deployment, data ownership, or long-term engineering constraints. Every record started as `Proposed` in Phase 1. The authorized maintainer accepted ADRs 0001–0008 during Phase 2 finalization on 2026-08-09; acceptance records the decision but does not authorize work outside the current phase.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-deployment-model.md) | Native systemd is the default deployment | Accepted |
| [0002](0002-privilege-separation.md) | Non-root services plus a narrow root Helper | Accepted |
| [0003](0003-project-directory-model.md) | `/srv/agentbox/projects` is the default project root | Accepted |
| [0004](0004-runtime-user-model.md) | A separate `agentbox-runtime` user owns Runtimes and projects | Accepted |
| [0005](0005-job-execution-model.md) | SQLite-backed Jobs plus one systemd Worker and SSE | Accepted |
| [0006](0006-frontend-stack.md) | React, TypeScript, Vite, Tailwind, selective shadcn/ui | Accepted |
| [0007](0007-database-choice.md) | SQLite, SQLAlchemy, Alembic, and WAL for the MVP | Accepted |
| [0008](0008-license-choice.md) | Apache-2.0 is the initial project license | Accepted |

## Process

An ADR PR contains the context and evidence, not only the preferred option. A decision becomes `Accepted` only after the authorized maintainer approves it. Reversal creates a new ADR; the old one remains in history and points to its successor. Implementation must not silently contradict an Accepted ADR.
