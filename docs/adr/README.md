# AgentBox Architecture Decision Records

ADRs record decisions that change AgentBox's trust boundaries, deployment, data ownership, or long-term engineering constraints. Every record starts as `Proposed` in Phase 1. Human review may change it to `Accepted`, `Rejected`, or later `Superseded`; Phase 1 does not itself authorize implementation.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-deployment-model.md) | Native systemd is the default deployment | Proposed |
| [0002](0002-privilege-separation.md) | Non-root services plus a narrow root Helper | Proposed |
| [0003](0003-project-directory-model.md) | `/srv/agentbox/projects` is the default project root | Proposed |
| [0004](0004-runtime-user-model.md) | A separate `agentbox-runtime` user owns Runtimes and projects | Proposed |
| [0005](0005-job-execution-model.md) | SQLite-backed Jobs plus one systemd Worker and SSE | Proposed |
| [0006](0006-frontend-stack.md) | React, TypeScript, Vite, Tailwind, selective shadcn/ui | Proposed |
| [0007](0007-database-choice.md) | SQLite, SQLAlchemy, Alembic, and WAL for the MVP | Proposed |
| [0008](0008-license-choice.md) | Apache-2.0 is the recommended initial license | Proposed |

## Process

An ADR PR contains the context and evidence, not only the preferred option. A decision becomes `Accepted` only after the authorized maintainer approves it. Reversal creates a new ADR; the old one remains in history and points to its successor. Implementation must not silently contradict an Accepted ADR.
