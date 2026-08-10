# AgentBox Development Plan

## Planning rules

This plan is a sequence of approval gates, not an authorization to execute later phases. Each phase ends before the next begins. Once a repository exists, `main` will be protected; implementation work will use a focused feature branch and a reviewable pull request. Phase 0 and Phase 1 artifacts describe evidence and decisions only—they do not imply that AgentBox has been implemented or tested.

Product-surface priority is CLI/recovery contract, installer, then Web daily experience. Delivery dependencies differ: the API and frontend foundation can be built before the final installer, because Phase 8 must package and validate the completed Runtime components rather than an empty service. Installation design, protocol boundaries, and dry-run semantics are fixed before that implementation phase.

The project stays focused on a single-server, single-administrator MVP. Security boundaries, Runtime compatibility, and recoverability are release requirements rather than post-release polish.

## Phase 0 — Environment and permission assessment

- **Goal:** establish a reproducible inventory of the real server without changing it.
- **Input:** target Linux host, existing tools and services, read-only command access.
- **Output:** `PHASE0_ENVIRONMENT_REPORT.md`, risks, blockers, and host-specific gates.
- **Not in scope:** installing packages, altering services, credentials, firewall, Git, or projects.
- **Acceptance:** every requested area is reported as observed, failed, unknown, or not checked; sensitive output is redacted.
- **Tests:** command exit-code capture, path resolution, and report spot checks; no destructive probes.
- **Documentation:** inventory, security findings, directory and deployment recommendations.
- **Commit/PR:** none required before repository initialization; preserve the report for later review.
- **Stop condition:** report exists and the overall status and blockers are explicit.
- **Human approval:** any host-level check requiring elevated access beyond the inspection scope.

## Phase 1 — Product and architecture documents

- **Goal:** make the MVP, trust boundaries, contracts, and delivery plan explicit.
- **Input:** Phase 0 report, product constraints, and verified public CLI behavior.
- **Output:** the documents in `docs/`, eight ADRs initially marked Proposed, and `PHASE1_ARCHITECTURE_SUMMARY.md`; ADRs 0001–0008 were Accepted during Phase 2 finalization.
- **Not in scope:** repository initialization, code, units, schemas, dependencies, or external GitHub changes.
- **Acceptance:** all 60 product and architecture questions have a clear recommendation; terminology and security rules are consistent.
- **Tests:** document inventory, contradiction scan, prohibited-pattern scan, and decision coverage review.
- **Documentation:** this complete Phase 1 set.
- **Commit/PR:** none in this phase; Phase 2 will decide how the initial history is formed.
- **Stop condition:** documents and self-check summary exist and no Phase 2 action has begun.
- **Human approval:** completed on 2026-08-09 for Apache-2.0, initial repository ownership/visibility, and ADRs 0001–0008.

## Phase 2 — Repository and engineering skeleton

- **Goal:** create a minimal monorepo that enforces the agreed boundaries without implementing product workflows.
- **Input:** approved Phase 1 documents and resolved repository/license decisions.
- **Output:** Git repository, Python and frontend package skeletons, lint/type/test configuration, CI, contribution templates, and ADR status updates.
- **Not in scope:** working authentication, Runtime control, privileged system changes, installer execution, or production deployment.
- **Acceptance:** one-command local lint and test entry points; backend, frontend, CLI, and protocol packages have dependency direction checks; no arbitrary-shell abstraction.
- **Tests:** skeleton imports, formatting, static type checks, empty database migration smoke test in a temporary directory, frontend build smoke test.
- **Documentation:** contributor setup, supported tool versions, repository map, and local development safety notes.
- **Commit/PR:** initialize only after approval; use a small bootstrap sequence or one reviewed initial PR, never push directly to protected `main` after protection is active.
- **Stop condition:** skeleton CI is green and contains no production control implementation.
- **Human approval:** completed for `git init`, GitHub repository creation, Apache-2.0, initial default branch, and remote push; final PR merge remains manual.

## Phase 3 — Minimal backend and authentication (completed and merged)

- **Goal:** deliver the versioned API foundation, single-admin authentication, persistence, audit structure, and safe local daemon lifecycle.
- **Input:** Phase 2 skeleton, API/Data Model/Security contracts.
- **Output:** FastAPI application, SQLite/Alembic schema, password bootstrap, secure sessions, CSRF and rate limiting, health/readiness endpoints, Worker session maintenance, and audit redaction. Durable Job records/execution remain in the later Job workstream.
- **Not in scope:** Codex or Claude control, project mutation, root Helper operations, or public binding.
- **Acceptance:** binds to `127.0.0.1` by default; has no default credential; authentication and CSRF rules hold; no secret-bearing fields exist.
- **Tests:** unit/integration tests for login, lockout, cookies, CSRF, session expiry, authorization, migrations, and audit redaction.
- **Documentation:** admin bootstrap, API error envelope, configuration reference, and security assumptions.
- **Commit/PR:** separate PRs for persistence, auth, and job/audit foundations where practical; threat-sensitive changes require review.
- **Stop condition:** backend foundation is reviewable without Runtime or root privileges.
- **Human approval:** password initialization UX, session lifetime defaults, and any change to network binding.

## Phase 4 — Authenticated Web foundation (completed and merged)

- **Goal:** provide the seven MVP page shells and authenticated read-only dashboard experience.
- **Input:** stable Phase 3 API contracts and frontend ADR.
- **Output:** React application with Login, Dashboard, Codex, Claude, Projects,
  Doctor, Logs, and Settings routes; centralized API/Auth state; authenticated
  read-only Doctor endpoint; isolated Playwright harness and CI workflow. SSE
  client behavior is deferred until a real Job stream exists.
- **Not in scope:** browser terminal, visual shell, mobile-native client, elaborate design system, or WebSocket PTY.
- **Acceptance:** authentication lifecycle works, protected routes do not leak cached data, accessibility basics and responsive layouts are covered.
- **Tests:** component tests, API mock tests, Playwright login/navigation/session-expiry flows, production build.
- **Documentation:** frontend conventions, browser security behavior, and API compatibility policy.
- **Commit/PR:** focused PRs; generated assets are reviewed and lockfile changes are intentional.
- **Stop condition:** UI consumes only versioned contracts and does not duplicate server-side policy.
- **Human approval:** product copy and minimal visual direction.

## Phase 5 — Codex management (completed and merged)

Status: merged in PR #22.

- **Goal:** implement the Codex Runtime Adapter and safe Remote Control/Pair workflows.
- **Input:** captured CLI fixtures, Phase 0 Codex evidence, and approved Pair Code contract.
- **Output:** detection, version and capability reporting, conflict diagnostics,
  typed UDS Runtime execution, start/stop, ephemeral Pair Code channel, Web/CLI,
  safe Doctor summary, and remediation findings. General log viewing remains
  deferred.
- **Not in scope:** dependency on Codex private directories, automatic authentication, Pair Code storage, or unsupported `status` assumptions.
- **Acceptance:** changing or missing subcommands produce `unsupported`/`unavailable`, not unsafe fallback; Pair Code never reaches database, audit, logs, SSE, or generic Job results.
- **Tests:** adapter fixtures across versions, hostile output, timeout/output caps, no-persistence canary scans, process ownership, and error classification.
- **Documentation:** supported evidence matrix, known limitations, authentication guidance, and current-host migration plan.
- **Commit/PR:** adapter detection, lifecycle, and Pair handling should be separately reviewable; Pair handling receives security review.
- **Stop condition:** product code contains no root Runtime path; production is
  designed for `agentbox-runtime`, while Phase 5 development/host validation
  deliberately uses the current existing-user context without migrating auth.
- **Human approval:** remediation of the existing legacy Codex unit and UID/GID 1001 ownership anomaly on the assessed host.

## Phase 6 — Claude session management

Status: implemented on `phase/6-claude-session-management`; awaiting Draft PR
review. This does not authorize Phase 7.

- **Goal:** manage project-scoped Claude Remote sessions through tmux without embedding a terminal.
- **Input:** synthetic/redacted Claude fixtures, Runtime Executor, a minimal configured-root immediate-child registry, and Workspace Trust rules. Formal Project Workspaces remain Phase 7.
- **Output:** public-help detect/version/capabilities, create/list/status/recent-output/stop, exact attach instructions, marker-backed duplicate/collision prevention, Runtime restart rediscovery, and manual Workspace Trust guidance.
- **Not in scope:** automatic trust, reading private auth files, `/root` trust, browser terminal, or root-owned new sessions.
- **Acceptance:** production sessions are designed for `agentbox-runtime`, are tied to canonical configured Project IDs, survive SSH loss through tmux, and expose bounded/sanitized sensitive output. Phase 6 development validation under root is not production identity evidence.
- **Tests:** Claude/tmux fixtures, collision and stale-session cases, path/symlink escape, exact-stop safety, output sanitation/no-persistence, unknown authentication, API/CLI/Web, and desktop/mobile Fake Runtime E2E.
- **Documentation:** session lifecycle, attach workflow, trust limitations, and recovery runbook.
- **Commit/PR:** lifecycle and output handling remain separate review units when possible.
- **Stop condition:** no unmanaged shell input can reach tmux or Claude invocation.
- **Human approval:** adoption or migration of the existing root-owned tmux/Claude sessions.

## Phase 7 — Projects and basic Git

- **Goal:** deliver the safe Project Workspace registry, create/clone/list/status, and Runtime launch integration.
- **Input:** project-directory ADR, path-safety implementation plan, and Git fixtures.
- **Output:** project registry, canonical path guard, safe clone, read-only status/branch/change count/remote display, and project-to-Claude launch.
- **Not in scope:** commit, push, PR creation, deletion, hard reset, branch deletion, hooks execution, or automatic legacy movement.
- **Acceptance:** all paths remain beneath `/srv/agentbox/projects`; symlink/race/path traversal tests pass; Git files are Runtime-user owned.
- **Tests:** malicious URLs and repository names, symlink swaps, hooks/submodules, large output, concurrent clone, ownership, and interrupted clone recovery.
- **Documentation:** project lifecycle, Git safety defaults, legacy `/root/projects` adoption, and backup expectations.
- **Commit/PR:** path guard and Git process runner require dedicated security-focused review.
- **Stop condition:** no arbitrary repository path or Git option is accepted.
- **Human approval:** importing any legacy root-owned project or enabling later write-oriented Git operations.

## Phase 8 — Installation, upgrade, rollback, and deployment

- **Goal:** make native systemd installation reproducible, idempotent, verifiable, and reversible.
- **Input:** approved units and protocols, signed/checksummed release artifact design, distro test images.
- **Output:** dry-run/apply/repair installer, Web/API/Worker/Runtime Executor/Helper units, release switching, schema migration, health gate, rollback, and uninstall plan.
- **Not in scope:** Docker as the default, firewall/SSH mutation, automatic tunnel setup, or deletion of user projects/authentication data.
- **Acceptance:** repeated install converges; interrupted install resumes safely; failed health check rolls back program files while preserving compatible data.
- **Tests:** clean and dirty VM matrices, idempotency, offline/network failure, power-loss simulations, upgrade/rollback, unit hardening, and permissions.
- **Documentation:** operator install/upgrade/rollback/uninstall runbooks and distro caveats.
- **Commit/PR:** installer, units, and Helper policy changes need security and operations review; releases come only from tagged protected commits.
- **Stop condition:** deployment tests pass on each supported distribution family or documented preview support is narrowed.
- **Human approval:** host installation, user/group creation, service enable/start, and remediation of conflicting services.

## Phase 9 — Security audit and compatibility hardening

- **Goal:** validate the complete MVP against its threat model and supported host/Runtime matrix.
- **Input:** feature-complete release candidate, fixtures, ephemeral VMs, and Phase 0 risk register.
- **Output:** resolved findings, compatibility matrix, dependency review, restore drill, performance limits, and release-blocker list.
- **Not in scope:** feature expansion, multi-tenancy, plugins, or cosmetic redesign.
- **Acceptance:** no open Critical/High finding; secret canaries are absent from persistent stores; privilege and upgrade tests pass; degraded tools return correct capability states.
- **Tests:** penetration-oriented API/IPC tests, command/path/environment injection, supply-chain verification, distro VMs, backups, migrations, and failure recovery.
- **Documentation:** updated threat model, security advisories process, compatibility and known-issues pages.
- **Commit/PR:** fixes remain narrow; security-sensitive embargo handling follows the vulnerability policy.
- **Stop condition:** release candidate satisfies the documented security and support gates.
- **Human approval:** acceptance of any residual Medium risk or reduced distro support.

## Phase 10 — First release

- **Goal:** publish a reproducible, documented MVP release.
- **Input:** approved release candidate, completed security gate, release signing/checksum material, and restore evidence.
- **Output:** version tag, source archive, verified artifacts, checksums/signatures, changelog, installation docs, and rollback notice.
- **Not in scope:** automatic deployment to user servers, telemetry, paid services, or post-MVP feature commitments.
- **Acceptance:** clean-host install and upgrade-from-previous-candidate tests pass; artifacts match source; rollback and recovery instructions are validated.
- **Tests:** final matrix rerun, artifact verification, smoke install, browser flows, adapter fixtures, and database migration/restore drill.
- **Documentation:** release notes, support statement, security contact, known limitations, and checksums.
- **Commit/PR:** release commit/tag comes from protected `main`; no force push or tag replacement.
- **Stop condition:** artifacts are published and the next roadmap is separately approved.
- **Human approval:** version number, license, public release, support promise, and publication credentials.

## Phase 11 — Provider, Secret & Runtime Continuity Management (future post-MVP)

Status: architecture and backlog only; tracked by Issue #23. This Phase follows
Phase 10 and does not insert into, reorder, or authorize Phases 6–10.

- **Goal:** add a runtime-neutral Provider Registry, Secret Manager, Active
  Provider Binding, transactional config switching, verified rollback, and a
  Runtime Continuity Manager without coupling Provider selection to Remote
  lifecycle or private session state.
- **Input:** completed Phase 10; approved platform Secret boundaries; and a fresh
  validation of the then-current public Codex version, config/model-provider
  schema, wire APIs, auth/reload/restart behavior, Remote lifecycle,
  thread/provider relationship, discovery, active-writer, resume, macOS, and
  Windows behavior.
- **Output:** distinct `ProviderDefinitionID` and `RuntimeBindingID` models;
  typed Provider metadata/adapters; Linux/macOS/Windows Secret backends; a
  shared Config Transaction Manager; atomic activation and rollback
  verification; layered Provider/Runtime/Remote/continuity evidence; recovery
  guidance; and approved API/CLI/Web surfaces.
- **Not in scope before approval:** reading or changing API keys, creating a
  Secret Store, editing Codex config, adding/activating Providers, restarting
  Codex, changing Remote sessions, or implementing any Provider API/UI/CLI.
- **Acceptance:** unrelated Runtime configuration and original file existence,
  permissions, lifecycle, Active Provider, Runtime Binding, generated profile,
  and Secret reference are recoverable and rollback-verified; raw API keys
  never enter argv, URLs, ordinary Provider tables, output, logs, audit, Git,
  reports, or generic Job data; Provider request success never implies Remote,
  thread, context, or discovery success; no session DB/JSONL/rollout mutation or
  automatic Provider failover exists.
- **Tests:** public-contract fixtures; Provider protocol/model matrix;
  Config Transaction fault injection; concurrent edit/symlink/permission
  races; Secret canaries; paid-test confirmation; active writer protection; and
  a two-fake-provider harness that independently verifies Runtime request,
  Remote recovery, thread resume, context continuity, and thread discovery.
- **Documentation:** `PROVIDER_MANAGER.md`, Linux/macOS/Windows capability
  matrix, Secret operations, activation/restart impact, rollback verification,
  continuity levels, recovery, and known compatibility limitations.
- **Commit/PR:** split implementation by trust boundary; Secret storage/injection
  and config mutation require dedicated security review.
- **Stop condition:** no Provider may be activated until current public Runtime
  contracts, active-writer safety, config transaction, lifecycle restoration,
  and rollback verification are proven; Unknown/Experimental remains explicit
  for every unverified continuity dimension.
- **Human approval:** Secret Manager backends, config ownership boundary, real
  Provider credentials or paid tests, activation, Runtime restart, session
  impact, any independent daemon proposal, and every continuity/support claim.

## Cross-phase change control

A changed trust boundary, default bind address, Runtime ownership model, project root, database choice, license, or deployment model requires an ADR update before implementation. A discovered external CLI behavior is recorded as a fixture and capability rule rather than silently becoming a new invariant.
# Phase 7 status

Project Workspace plus Git/GitHub foundation is implemented on `phase/7-project-git-management`: formal Projects, durable Jobs, create/clone, structured status, branch operations, ff-only Pull, no-force Push, Draft PR, Web/CLI/Doctor, and Phase 6 Claude migration. Provider/Secret Management remains Phase 11. Installer, production user/systemd migration, Helper and Phase 8 work are not included.
