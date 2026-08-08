# AgentBox Phase 2 Engineering Report

> Date: 2026-08-09
> Phase: Repository and Engineering Skeleton
> Status: Complete pending human review
> Product functionality: none beyond the engineering skeleton

## Repository

| Item | Result |
|---|---|
| Local path | `/root/AgentBox` |
| Git initialized | Yes |
| Default branch | `main` |
| Bootstrap commit | `8f1ec6a chore: initialize AgentBox repository` |
| Phase 2 branch | `phase/2-engineering-skeleton` |
| Remote | `https://github.com/ForceMind/agentbox` |
| Visibility | Public |
| GitHub Issues | Enabled |
| Private vulnerability reporting | Enabled |
| Branch protection | Requires Human GitHub Settings Action |

`main` contains the Phase 0/1 documents and basic repository metadata. Phase 2
work is isolated on `phase/2-engineering-skeleton`; no ongoing skeleton work was
performed directly on `main`.

Recommended manual repository settings for `main` are: require pull requests,
require the backend/frontend/security checks, prevent force pushes, and prevent
branch deletion. These settings were not changed through an unverified API.

## Engineering Structure

The Phase 2 structure has a deliberately small surface:

```text
apps/
  api/       Minimal FastAPI application
  cli/       Minimal command-line entry point
  web/       Minimal React application
  worker/    Process lifecycle and health-check skeleton
packages/
  agentbox-core/      Shared package marker and version
  agentbox-protocol/  Health/meta DTOs only
  agentbox-runtime/   RuntimeAdapter marker protocol only
helper/               Security and future protocol contract README
installer/            Future installer design boundary README
tests/
  fixtures/           Reserved for sanitized adapter fixtures
  integration/        Reserved; no fake integration tests
  unit/               API, CLI, and import smoke tests
scripts/              Repository-only safety checks
.github/
  workflows/          Backend, frontend, and security CI
  ISSUE_TEMPLATE/     Bug and feature forms plus private security routing
docs/                 Phase 1 design baseline and licensing status
```

The root `pyproject.toml` manages all Python packages and tools. The root
`package.json` and `pnpm-workspace.yaml` manage the frontend workspace. No empty
application packages were added solely for appearance.

## Backend

### Policy and packages

- Supported Python policy: Python `>=3.11`.
- CI matrix: Python 3.11, 3.12, and 3.13.
- Framework baseline: FastAPI, Pydantic, SQLAlchemy, Alembic, and Uvicorn.
- Tooling: Ruff, Black, mypy strict mode, pytest, pip-audit, and pre-commit.
- Packages: `agentbox-core`, `agentbox-runtime`, and `agentbox-protocol`.

SQLAlchemy and Alembic are dependency and packaging foundations only. Phase 2
does not define business tables, create migrations, open SQLite, or enable WAL.

### Implemented endpoints

Only two read-only endpoints exist:

- `GET /healthz` returns `{"status": "ok"}`.
- `GET /api/v1/meta` returns the product name, package version, and API version.

There are no authentication, project, Runtime, Job, settings, log, or system
management routes.

### Verification results

The following commands were actually executed on 2026-08-09:

| Check | Result |
|---|---|
| `ruff check apps packages tests` | PASS — no findings |
| Black check, serially across all 16 Python files | PASS — all files unchanged |
| `mypy apps packages tests` | PASS — no issues in 16 source files |
| `pytest` | PASS — 5 tests passed |
| CLI and Worker smoke invocations | PASS |
| `pip-audit --local --skip-editable` | PASS — no known vulnerabilities; the local editable project is intentionally skipped |

The tests cover the health endpoint, metadata endpoint, package imports, CLI
version, and CLI placeholder JSON output. They do not claim host or Runtime
integration coverage.

## Frontend

- Stack: React, TypeScript strict mode, Vite, and Tailwind CSS.
- Package manager: pnpm 11.20.0, pinned through the root `packageManager` field.
- UI scope: dark-first, responsive engineering-skeleton screen and a backend
  health indicator that calls `GET /healthz`.
- shadcn/ui: no components added; selective adoption remains available when a
  real Phase 4 screen justifies it.

Actual verification results:

| Check | Result |
|---|---|
| `pnpm install --frozen-lockfile --offline` | PASS |
| `pnpm lint` | PASS |
| `pnpm format:check` | PASS |
| `pnpm typecheck` | PASS |
| `pnpm test` | PASS — 1 file, 2 tests |
| `pnpm build` | PASS |
| `pnpm audit --audit-level high` | PASS — no known vulnerabilities |

The production build is a static artifact only; it was not installed or served
as a persistent service.

## CLI

The package entry point supports:

- `agentbox --version`
- `agentbox status [--json]`
- `agentbox doctor [--json]`

`status` and `doctor` explicitly return `Not implemented in Phase 2`. They do
not inspect, mutate, start, stop, install, or authenticate any host component.
The current CLI proves only the entry point, parser, human-readable output, and
stable JSON envelope.

## CI

| Workflow | Checks |
|---|---|
| `.github/workflows/backend.yml` | Python 3.11/3.12/3.13 install, Ruff, Black, mypy, pytest |
| `.github/workflows/frontend.yml` | Frozen pnpm install, ESLint, Prettier, TypeScript, Vitest, Vite build |
| `.github/workflows/security.yml` | Repository boundary checks, pip-audit, pnpm audit, and PR-only dependency review |

The workflows require no project secrets or commercial services. Immutable SHA
pinning for third-party actions remains a future hardening task.

## GitHub Resources

### Milestones

Exactly five open milestones were created:

1. Foundation
2. Core Control Plane
3. Runtime Management
4. Installation & Hardening
5. MVP Release

### Issues

Exactly 18 initial Issues were created from `docs/DEVELOPMENT_PLAN.md`. They
cover the engineering foundation, versioned contracts, persistence,
authentication, Web/CLI foundations, Job execution, helper protocol, Codex and
Claude adapters, tmux lifecycle, Project Workspaces, installer,
upgrade/rollback, hardening, compatibility, and MVP release. Every Issue uses
the required Context, Scope, Out of scope, Acceptance criteria, Tests, Security
considerations, and Dependencies sections.

Issue list: <https://github.com/ForceMind/agentbox/issues>

### Draft PR

Draft PR: <https://github.com/ForceMind/agentbox/pull/19>

The PR targets `main` from `phase/2-engineering-skeleton` and explicitly states
that no AgentBox Runtime management functionality is implemented.

## Security Checks

| Check | Result |
|---|---|
| Repository secret-pattern scan | PASS |
| Python dependency audit | PASS |
| Frontend dependency audit | PASS |
| Arbitrary shell/process API boundary scan | PASS |
| API mutation-route boundary scan | PASS — only two GET routes |
| Root execution/system modification review | PASS — none implemented or performed |
| `git diff --check` | PASS |

The scans did not read private authentication stores or token contents. The
repository ignores `.env`, private-key formats, local databases, virtual
environments, build products, and dependency directories. The checks are useful
guardrails, not a claim that the pre-alpha repository has completed a full
security audit.

## Deviations and Clarifications

1. The approved Phase 2 baseline of Python `>=3.11` is used. This is consistent
   with the corrected Phase 1 recommendation and avoids claiming that the
   observed host Python 3.11 is Python 3.12.
2. No shadcn/ui component was added because the engineering screen needs none;
   the Phase 1 decision was selective adoption, not mandatory dependency growth.
3. ADR 0008 remains Proposed. Consequently, no final `LICENSE` file was added;
   `docs/LICENSING.md` records the MIT, Apache-2.0, and AGPL-3.0 decision status.
4. API tests use HTTPX's in-process ASGI transport. This avoids depending on a
   real listener and keeps Phase 2 from starting a persistent service.
5. The helper and installer are documentation-only boundaries. No root helper,
   shell passthrough, package-manager execution, systemd unit, or installer
   implementation exists.
6. The worker is an idle lifecycle skeleton only. It does not open SQLite,
   consume Jobs, invoke the helper, or call any Runtime.

No Phase 1 architecture decision was overturned.

## Known Limitations

The following capabilities are intentionally not implemented:

- login, sessions, CSRF, rate limiting, or administrator management;
- database schema, migrations, SQLite Job storage, worker recovery, or SSE;
- Privileged Helper implementation or Unix Domain Socket protocol;
- Codex detection, lifecycle, Remote Control, or Pair Code generation;
- Claude detection, Remote Control, Workspace Trust, or tmux management;
- Project Workspace and Git/GitHub business operations;
- installation, system users/directories, systemd deployment, update, rollback,
  backup, or migration;
- production Web screens or public network exposure.

No host service, firewall rule, SSH setting, cloudflared setting, Codex/Claude
state, tmux session, system user, or system directory was changed.

## Remaining Gates and Human Actions

There is no blocker to reviewing the Phase 2 skeleton. Before later deployment
or Runtime work, the Phase 0/1 gates remain in force:

- accept or amend the Proposed ADRs, especially the license choice;
- configure and approve `main` branch protection in GitHub;
- decide the long-term developer checkout owner and location;
- approve UID/GID selection and the migration plan for existing root-owned
  Codex/Claude/tmux/authentication state;
- review the existing Codex system service before Codex integration;
- preflight port 8787, cloudflared, firewall/cloud security group, and other
  listeners before starting or exposing Web/API;
- verify supported distribution versions through later VM tests.

## Phase 3 Recommendation

After this Draft PR is reviewed and approved, Phase 3 should establish only the
minimal control-plane foundation described in `docs/DEVELOPMENT_PLAN.md`:

- application configuration with secure defaults;
- SQLite/Alembic infrastructure and the minimum persistence primitives;
- single-administrator authentication, session, CSRF, and login-rate-limit
  foundations;
- daemon health/lifecycle integration and contract tests;
- continued enforcement of the no-arbitrary-shell and no-secret-storage rules.

Phase 3 must not silently expand into Codex Pair, Claude/tmux, Project Workspace,
installer, system deployment, or public network exposure work.
