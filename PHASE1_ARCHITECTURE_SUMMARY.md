# AgentBox Phase 1 Architecture Summary

> Phase: Product definition, architecture, and development plan
> Date: 2026-08-08
> Status: **DOCUMENTATION COMPLETE — APPROVED DURING PHASE 2 FINALIZATION**

> Post-Phase 1 decision update (2026-08-09): the authorized maintainer approved
> the documented architecture baseline and selected Apache-2.0. ADRs 0001–0008
> are now Accepted. This note records later approval; the Phase 1 execution and
> environment statements below remain historical.

## Executive Summary

AgentBox MVP is defined as a **single-server, single-administrator AI developer workstation control plane**. It standardizes installation and diagnostics; capability-aware Codex Remote management and one-time pairing; project-scoped Claude Remote sessions persisted by tmux; safe Project Workspace and read-only Git visibility; and a small authenticated Web panel plus recovery-oriented CLI.

The recommended deployment is native systemd. Web/API and Worker run as non-root `agentbox`; Git, gh, Codex, Claude, tmux, projects, and third-party authentication belong to a separate non-root `agentbox-runtime`; a minimal root Privileged Helper accepts only typed, allowlisted system operations over a protected Unix Domain Socket. Docker is not the default. Web/API listens on `127.0.0.1:8787` by default, and remote access is supplied by a separately administered Tailscale, Cloudflare Tunnel, VPN, or HTTPS reverse proxy.

The stack recommendation is Python 3.11+ with FastAPI, Pydantic, SQLAlchemy, Alembic, and SQLite WAL; React, TypeScript, Vite, Tailwind CSS, and selective shadcn/ui; a persistent SQLite Job model executed by one separate systemd Worker; and SSE for progress. WebSocket, Redis, Celery, plugins, multi-server, multi-tenant, and browser terminals are deferred.

No product code, installer, systemd unit, database migration, Git repository, GitHub resource, service, user, credential, pairing flow, or tmux session was created or changed in Phase 1.

## Phase 0 Basis

`PHASE0_ENVIRONMENT_REPORT.md` was read in full before work began. Its overall status is **READY WITH WARNINGS**, not BLOCKED, and it states that documentation/ADR work has no system-level hard blocker.

Architecture-relevant observed facts retained here are:

- OpenCloudOS 9.4 x86_64 KVM host, systemd 255 running, 2 vCPU, 3.5 GiB RAM, no swap, and no Docker;
- Python 3.11.6, Node 22, npm 10, pnpm, Git, GitHub CLI, SQLite, tmux, bubblewrap, Codex standalone, and Claude Code are present;
- current source and third-party authentication/session state are root-owned; the current directory is not a Git repository and Git author identity is unset;
- Codex standalone 0.146.1 is the selected command, no npm Codex conflict was observed, and public help exposed `remote-control start`, `stop`, and `pair` but not `status`;
- an old enabled but inactive root `codex.service` points to a missing path, and a Codex managed binary subtree has unmapped UID/GID 1001 ownership;
- existing root-owned Claude/tmux sessions are unmanaged, and new Workspace Trust must be project-specific;
- the host already runs cloudflared and other wildcard listeners, port 8000 is occupied, and existing network/services are out of scope for silent reuse or modification.

These are current-host observations, not permanent AgentBox contracts. Third-party private paths and configuration formats are never used as required interfaces.

## Formal Recommendations

### Product and MVP (questions 1–7)

| # | Conclusion |
|---:|---|
| 1 | V1 solves the repeatable conversion of one Linux server into a remotely manageable AI development workstation while reducing routine SSH—not general server administration or browser coding. |
| 2 | MVP includes idempotent install/doctor/status/update basics; Codex detection/conflict/lifecycle/pairing; Claude project-tmux lifecycle; Project create/clone/list/read-only Git status; seven minimal Web views; and single-admin security. |
| 3 | Rich GitHub/PR/Actions, Git commit/push, destructive Git/project actions, browser terminal, Docker management, multiple servers/users/tenants, plugins, enterprise SSO, telemetry, billing, bots, and native apps are deferred. |
| 4 | Product-surface priority is shared Application Services/CLI recovery contract first, installer second, and Web daily experience third. Delivery sequencing may build the Web foundation before the final installer because the installer must package completed components; all three remain MVP release requirements. |
| 5 | The initial user is a technically capable individual developer or small-team administrator controlling their own Linux cloud server and willing to perform initial SSH bootstrap/authentication. |
| 6 | Yes. V1 is explicitly single-server and single-administrator. It is not presented as multi-tenant. |
| 7 | MVP succeeds when a clean supported host can be installed, locally authenticated, diagnosed, paired with Codex, given a persistent project-scoped Claude session, and used for safe project/Git visibility without root Web, default public exposure, or secret persistence. |

### Privilege and security (questions 8–20)

| # | Conclusion |
|---:|---|
| 8 | Web/API must never run as root. |
| 9 | A Privileged Helper is required for the small set of unavoidable system changes. |
| 10 | Helper handles only allowlisted AgentBox units, supported package plans, user/directory initialization, bounded ownership changes, verified release activation/rollback, and narrow system diagnostics. |
| 11 | Helper does not run arbitrary shell, Git/gh, Codex, Claude, tmux, HTTP, arbitrary paths, or credential reads; it does not manage SSH, firewall, tunnels, projects, or backups through a generic API. |
| 12 | Browser uses HTTP/SSE to Web/API; local CLI normally uses the API UDS; Worker uses separate versioned UDS protocols to Runtime Executor and Helper. Neither internal service listens on TCP. |
| 13 | No shell-shaped API or argv passthrough exists. Each action has a server-defined implementation, schema, policy, and executable. |
| 14 | Enforce typed/enumerated parameters, canonical registered paths, symlink/race defenses, fixed executable/working directory, environment allowlist, time/output/concurrency limits, peer credentials, and stable error codes in both caller and executor. |
| 15 | Dangerous actions use a short-lived, single-use Confirmation Challenge bound to user, action, target, state precondition, request digest, and typed phrase. `--yes` cannot bypass high-risk confirmation. |
| 16 | Audit records actor, action, resource, time, request/Job ID, result, and error class. It excludes secrets, command bodies, raw output, Pair Code, and private authentication data. |
| 17 | Pair Code uses recent authentication plus CSRF, direct bounded no-store response to one authorized Web request or interactive TTY, memory-only handling, log/body suppression, and immediate zeroization/best-effort discard. It never enters Job, DB, SSE, audit, history, or JSON CLI output. |
| 18 | Root Helper must not call tmux, Codex, or Claude. A separate non-root `agentbox-runtime` Runtime Executor may call exact adapter-selected argv for those tools. |
| 19 | AgentBox-managed tmux and AI Runtime processes belong to `agentbox-runtime`, as do their HOME, auth, and project files. |
| 20 | Yes. Use dedicated locked `agentbox` and `agentbox-runtime` identities; detect numeric UID/GID collisions rather than assigning a fixed ID. |

### Deployment (questions 21–30)

| # | Conclusion |
|---:|---|
| 21 | No. AgentBox does not default to Docker and does not require Docker. |
| 22 | systemd directly represents host processes, UIDs, journald, recovery, and package/tmux/runtime control but requires distro/permission work. Docker improves packaging isolation but host control would demand dangerous sockets/mounts/privilege and duplicates ownership concerns. |
| 23 | Native systemd is the formal MVP recommendation; an optional hybrid Web tier may be reconsidered later. |
| 24 | Yes. Build React into immutable static assets and pair it with a FastAPI `/api/v1` service. |
| 25 | No mandatory Nginx/Caddy dependency. They are supported as separately configured HTTPS reverse proxies when an operator needs them. |
| 26 | Default is `127.0.0.1:8787` plus local UDS; never `0.0.0.0` without an explicit setting and security warning. Port availability is preflighted. |
| 27 | Tailscale, Cloudflare Tunnel, VPN, and HTTPS proxy are documented external access patterns. AgentBox does not silently install/reconfigure or inherit them; each needs TLS/access-policy/origin review. |
| 28 | Upgrade downloads a pinned, verified release to a new immutable `/opt/agentbox/releases/<version>`, backs up state, runs compatible migrations, atomically switches `current`, restarts in order, and health-gates completion. |
| 29 | Rollback switches to a retained prior verified release and restores a compatible config/database backup when required. Irreversible schema changes must block automatic rollback and demand an explicit plan. |
| 30 | Installer separates discovery/plan/apply/verify, journals durable checkpoints, uses declarative resource tests, stages then atomically activates, supports dry-run/repair, and resumes or rolls back without overwriting unrelated state. |

### Projects, paths, and ownership (questions 31–37)

| # | Conclusion |
|---:|---|
| 31 | Development source: `/home/<developer>/src/AgentBox`; installed releases/static: `/opt/agentbox`; config: `/etc/agentbox`; DB/state/backups: `/var/lib/agentbox`; primary logs: journald, optional `/var/log/agentbox`; runtime/UDS: `/run/agentbox`; projects: `/srv/agentbox/projects`; units: `/etc/systemd/system` for manual installs or distro unit directory for packages. |
| 32 | `/srv/agentbox/projects` is the recommended default. `/opt` is program payload; `/root/projects` forces root coupling and cannot be traversed by normal service users on the assessed host. |
| 33 | Git operations run as `agentbox-runtime`, never root or Web/API. MVP Git operations are deliberately limited, with network prompts/hooks/config constrained. |
| 34 | Claude tmux sessions are created and owned by `agentbox-runtime` for a registered concrete Project Workspace. |
| 35 | Resolve from an open trusted root using descriptor-relative/race-resistant operations where available; reject `..`, absolute/client paths, symlink components, unexpected ownership/types/mounts, and post-validation swaps. String-prefix checking alone is insufficient. |
| 36 | Project deletion is deferred. A future design requires dry-run impact, clean/dirty state evidence, recent reauthentication, a target/state-bound challenge, typed name, quarantine/trash before timed purge, backup awareness, and no broad recursive path. |
| 37 | Back up consistent SQLite snapshots, non-secret config, registered project content/history as selected, audit/diagnostic metadata, and manifest/checksums. Restore into staging on a new host, map logical users rather than UID numbers, verify ownership/integrity, and reauthenticate every third-party Runtime. |

### Technology selection (questions 38–49)

| # | Conclusion |
|---:|---|
| 38 | FastAPI, Pydantic, SQLAlchemy, and Alembic are appropriate. The MVP minimum is Python **3.11+**, not 3.12+, because the verified host has 3.11.6; CI can include newer versions and a later minimum change requires review. |
| 39 | SQLite is sufficient for one server/admin with WAL, short/coordinated writes, busy timeout, consistent backups, and a clean PostgreSQL migration boundary. |
| 40 | React, TypeScript, and Vite fit the focused static dashboard and typed API client. |
| 41 | Use Tailwind CSS and only selected shadcn/ui source components; avoid a broad design-system dependency program. |
| 42 | Yes. Web routes, CLI local read-only mode, and Worker handlers share one Python Application Services package. Interfaces/adapters separate I/O. |
| 43 | No WebSocket is required for MVP. Browser terminal/PTY is deferred. |
| 44 | Yes. SSE is preferred for one-way Job/status progress and resume cursors. |
| 45 | No distributed task queue is needed for the single-host MVP. |
| 46 | Yes. Use a SQLite Job/JobEvent model with a separate supervised Worker, leases, resource locks, idempotency/checkpoints, and conservative restart recovery. |
| 47 | Yes. A monorepo is appropriate for backend, CLI, frontend, shared schemas/protocols, tests, docs, and deployment assets, with enforced dependency direction. |
| 48 | Yes. HTTP begins at `/api/v1`; internal IPC also has explicit protocol versions and negotiation. |
| 49 | A plugin system is post-MVP and must not shape V1 internals beyond ordinary adapter interfaces. Design it only after core Runtime APIs and trust boundaries stabilize. |

### External-tool compatibility (questions 50–55)

| # | Conclusion |
|---:|---|
| 50 | Support OpenCloudOS/Rocky through an RPM-family adapter and Ubuntu/Debian through an APT-family adapter, while detecting actual capabilities rather than treating family names as identical. Verify exact versions in disposable VMs before claiming support. |
| 51 | Package management is a plan-producing interface for query/install/update/remove metadata, with DNF/YUM/RPM and APT/dpkg implementations, normalized locks/errors, dry-run, and no raw package-manager arguments from clients. |
| 52 | Runtime Adapters use configured stable entrypoint then `command -v`/realpath/version/help/public status evidence. Private managed paths and auth files are diagnostics at most and never business contracts. |
| 53 | Saved redacted fixtures and capability probes drive compatibility. Missing/renamed commands return a conservative state and remediation; there is no guessed command or private-file fallback. |
| 54 | Yes. Capability Detection is mandatory and stored with evidence source, confidence, observed version/time, and error classification. |
| 55 | `unsupported` means the detected version/platform lacks the feature; `unavailable` means prerequisite/entrypoint is absent; `unauthenticated` means a safe public check confirms login is needed; `broken` means the capability should work but execution/output is invalid. `unknown` is used where safe evidence is insufficient. |

### Open source and license (questions 56–60)

| # | Conclusion |
|---:|---|
| 56 | Yes. AgentBox is well suited to open source because operators need to audit root boundaries, adapters benefit from community compatibility evidence, and Linux distributions vary. |
| 57 | Apache License 2.0 was recommended in Phase 1 and accepted during Phase 2 finalization; the canonical `LICENSE` file is now present. |
| 58 | MIT is simple/permissive without an express patent grant; Apache-2.0 is permissive with explicit patent and notice terms; AGPL-3.0 adds network copyleft for modified hosted services but increases enterprise and compatibility friction. MIT and Apache both permit closed commercial derivatives. |
| 59 | Recommend Apache-2.0 for adoption plus patent clarity. Choose AGPL only if preventing closed hosted forks outweighs adoption friction after legal/business review. |
| 60 | Use factual nominative references, attribute owners, avoid third-party logos by default, do not imply sponsorship/endorsement, include an independent-project trademark disclaimer, and review third-party terms/fixtures/notices. |

## Unified Service and Process Direction

```text
Browser --HTTP/SSE--> Web/API (agentbox, loopback)
Local CLI --api.sock-/
                         |
                         v
                  Application Services
                         |
                         v
                  SQLite + Job Worker (agentbox)
                       /   \
          runtime.sock/     \helper.sock
                     v       v
         Runtime Executor   Privileged Helper
         (agentbox-runtime) (root)
          | Git/gh/Codex/     | systemd/packages/
          | Claude/tmux       | install/ownership
```

The CLI uses the service and the same Application Services whenever the daemon is available. With the daemon stopped, only explicitly read-only discovery/status commands may invoke the same service-layer code locally. All mutation, Job, confirmation, Runtime, privileged, pair, and audit-producing actions require the daemon. CLI/API major mismatch fails closed; minor additions use Capability negotiation.

## Directory Layout

| Purpose | Recommended path | Ownership/direction |
|---|---|---|
| development checkout | `/home/<developer>/src/AgentBox` | human developer; current `/root/AgentBox` is Phase 1 workspace only |
| immutable releases | `/opt/agentbox/releases/<version>` | root-owned, not runtime-writable |
| active release | `/opt/agentbox/current` | atomic link/selector to verified release |
| Web static assets | `/opt/agentbox/current/web` | immutable and unable to expose projects |
| config | `/etc/agentbox` | root-controlled, least-readable; no third-party tokens |
| state/SQLite | `/var/lib/agentbox` | `agentbox`; mode-restricted |
| backups | `/var/lib/agentbox/backups` | protected and independently transport-encrypted |
| primary logs | journald | structured, bounded, redacted |
| optional file logs | `/var/log/agentbox` | only when required, rotate/permission restrict |
| Runtime IPC/PIDs | `/run/agentbox` | systemd `RuntimeDirectory`, protected sockets |
| Project Workspaces | `/srv/agentbox/projects` | `agentbox-runtime`; per-project restricted directories |
| Runtime HOME | `/home/agentbox-runtime` | third-party auth/tmux home, excluded from normal backup |
| manual system units | `/etc/systemd/system` | root-owned; packaged path follows distribution policy |

Legacy `/root/projects` is kept unmanaged. A future explicit, confirmed adoption copies into a staging path beneath `/srv`, validates it, and activates it atomically; AgentBox never broad-trusts `/root`, copies root credentials, or auto-chowns legacy data.

## Documents Created

- `docs/PRODUCT.md`
- `docs/MVP_SCOPE.md`
- `docs/ARCHITECTURE.md`
- `docs/SECURITY.md`
- `docs/PERMISSIONS.md`
- `docs/INSTALLATION_DESIGN.md`
- `docs/UPGRADE_AND_ROLLBACK.md`
- `docs/BACKUP_AND_MIGRATION.md`
- `docs/RUNTIME_ADAPTERS.md`
- `docs/API_DESIGN.md`
- `docs/CLI_DESIGN.md`
- `docs/DATA_MODEL.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/GITHUB_WORKFLOW.md`
- `docs/TEST_STRATEGY.md`
- `docs/THREAT_MODEL.md`
- `docs/adr/README.md`
- `docs/adr/0001-deployment-model.md`
- `docs/adr/0002-privilege-separation.md`
- `docs/adr/0003-project-directory-model.md`
- `docs/adr/0004-runtime-user-model.md`
- `docs/adr/0005-job-execution-model.md`
- `docs/adr/0006-frontend-stack.md`
- `docs/adr/0007-database-choice.md`
- `docs/adr/0008-license-choice.md`
- `PHASE1_ARCHITECTURE_SUMMARY.md`

## Post-Phase 2 Remaining Human Decisions

The architecture, repository namespace/visibility, Git author identity, and
Apache-2.0 license are resolved. The following implementation-specific choices
remain:

1. Choose the long-term human development account/source checkout location. `/home/<developer>/src/AgentBox` is recommended; Phase 2 has not moved `/root/AgentBox`.
2. Approve the migration/remediation plan for the old root `codex.service`, unmapped UID/GID 1001 Codex files, root-owned Runtime authentication, and existing root tmux/Claude sessions. No changes were made.
3. Approve the desired remote-access integration after reviewing current cloudflared routes, access policy, TLS, firewall/cloud security group, and port conflicts. Loopback remains the only default.
4. Approve exact supported distro versions/architectures after Phase 8 VM evidence; current recommendation names families, not an unverified universal support promise.

## Remaining Phase 0 Gates

Phase 0 reported no blocker to Phase 1 documentation. The following gates remain before their corresponding implementation actions:

- before moving the development checkout: approve its long-term owner and path;
- before user creation: select non-conflicting UID/GID and resolve the unmapped Codex UID/GID 1001 ownership plan;
- before Codex integration: review the old enabled/inactive root `codex.service`, select a stable verified entrypoint, and do not use its private managed path as a contract;
- before non-root Runtime use: establish the `agentbox-runtime` HOME/auth/Workspace Trust/Git/tmux ownership model without copying root credentials;
- before any Web/API start/exposure: preflight port 8787, existing wildcard listeners, iptables/cloud security group, and cloudflared; do not reuse port 8000;
- before resource-heavy parallelism: account for 2 vCPU, 3.5 GiB RAM, and no swap with default Job concurrency one and explicit limits.

None of these prevented architecture writing. They do prevent silently entering implementation or deploying services.

## Phase 1 Consistency Self-check

The checks below review documentation content only; they are not product tests and do not claim implementation.

| # | Check | Result |
|---:|---|---|
| 1 | Deployment model consistent | PASS — native systemd is default; Docker is deferred/optional only |
| 2 | Root boundary consistent | PASS — only the narrow Helper is root; Web/API and Worker are non-root |
| 3 | Project directory consistent | PASS — default is `/srv/agentbox/projects`; `/root/projects` is legacy/unmanaged |
| 4 | Runtime user consistent | PASS — Git/gh/Codex/Claude/tmux and projects belong to `agentbox-runtime` |
| 5 | API and CLI naming consistent | PASS — `/api/v1`, Job actions, capability/error names, and listed CLI commands align |
| 6 | MVP Scope and Development Plan align | PASS — required features map to Phases 3–8; deferred features remain outside MVP |
| 7 | Threat Model and Security coverage align | PASS — identified Web, IPC, path, Runtime, secret, update, DB, and backup threats have controls/tests |
| 8 | Data Model supports API and Jobs | PASS — required entities, statuses, JobEvent/SSE, confirmation, audit, diagnostics, and capability evidence exist |
| 9 | Pair Code persistence prohibited | PASS — no model/storage/audit/log/SSE/JSON path stores it; special direct channel is specified |
| 10 | No arbitrary Shell API | PASS — API/IPC/CLI use action registries and typed server-built argv only |
| 11 | Docker not default | PASS — ADR 0001 and all deployment documents select native systemd |
| 12 | `/root/projects` not default | PASS — it is explicitly legacy and requires approved copy/adoption |
| 13 | Major choices explained | PASS — eight ADRs cover deployment, privilege, projects, Runtime user, Jobs, frontend, DB, and license; all were Accepted during Phase 2 finalization |
| 14 | GitHub planning bounded | PASS — five proposed Milestones and about 18 initial Issues; none were created |
| 15 | No false implementation claims | PASS — documents identify designs, proposals, and future test gates; no feature/test is reported as implemented/passed |

Additional inventory checks confirm all required Phase 1 filenames are present. Sensitive-value review looks for prohibited *handling* and examples only; no real Token, OAuth code, Pair Code, cookie, password, SSH key, or authentication configuration was intentionally read or written. No contradiction remains unresolved inside the chosen architecture. Items still needing ownership/business/host approval are listed above rather than hidden.

## Historical Next-Phase Recommendation

Phase 1 recommended **Phase 2 — Repository and engineering skeleton** after
explicit human approval. That approval and Phase 2 have since occurred: the
ADRs and Apache-2.0 license are resolved, and the engineering skeleton is in PR
#19. This historical summary does not authorize Phase 3.
