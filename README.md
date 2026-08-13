# AgentBox

**Turn a user-controlled Linux server into a remotely managed AI development workstation.**

AgentBox is open AI developer infrastructure for standardizing a user-controlled Linux server as a remotely manageable development workstation. It is designed around capability-aware AI Runtime integration, persistent project sessions, safe lifecycle operations, and minimal routine SSH.

## Project status

AgentBox `0.3.0rc1` is a **pre-release / MVP Release Candidate** for one Linux
x86_64 server and one administrator. Phases 0–9 and the stable Deployment gate
are merged; Phase 10 prepares reproducible artifacts and release documentation.
This is not a stable-release, production-readiness, penetration-test,
enterprise-support, or broad platform-support claim.

The current codebase provides:

- a FastAPI service with health/readiness/meta, authentication, Doctor, and
  capability-aware Codex endpoints;
- explicit SQLite/Alembic persistence for AdminUser, hashed Sessions, and redacted Audit Events;
- local-TTY administrator initialization, Argon2id, CSRF, secure Cookie policy, and bounded login throttling;
- a Worker that leases durable typed Jobs, serializes Project mutations,
  renews bounded Runtime-operation leases, and recovers uncertain work to
  `needs_attention`;
- a typed non-root Runtime Executor over a versioned Unix socket, a no-shell
  process runner, public-help-based Codex detection, Remote start/stop, and an
  ephemeral Pair Code channel, project-scoped Claude/tmux session actions, and
  typed Project/Git/GitHub operations;
- a control-plane CLI and a responsive React application shell with
  login, authenticated Session recovery, Dashboard, Doctor, Settings, and real
  Codex, Claude, and Project management pages alongside clearly marked future sections;
- package boundaries, tests, CI, governance templates, and architecture documents.

Phase 8 adds a checksum-verified, fixture-testable native installer; distinct
`agentbox` and `agentbox-runtime` identities; hardened systemd units; a minimal
socket-activated root Helper; FHS production paths; loopback static/API
serving; online SQLite backup; staged update; verified rollback; safe
data-preserving uninstall; and production `status`/`doctor` diagnostics. See
[Installation](docs/INSTALLATION.md), [Deployment](docs/DEPLOYMENT.md), and
[Rollback](docs/ROLLBACK.md).

Phase 9 adds restart-persistent pseudonymous login throttling, local TTY-only
password/session recovery, stricter Runtime/Helper IPC, syscall filters where
compatible, version-aware systemd validation, crash-injection recovery tests,
sanitized diagnostics export, bounded state retention, and immutable GitHub
Action pins. OpenCloudOS 9 is the designated real-host target; Ubuntu 24.04 is
CI validated, Rocky 9 and Debian 12 remain fixture validated, Ubuntu 22.04 is
explicitly rejected by the native installer because its stock Python is too
old, and aarch64 remains unqualified. See [Platform support](docs/PLATFORM_SUPPORT.md)
and the [MVP security review](docs/SECURITY_REVIEW_MVP.md).

Phase 10 prepares the `0.3.0rc1` Linux x86_64 bundle with a single version
source, prebuilt static Web, exact Python wheel lock, deterministic archive,
`RELEASE_MANIFEST.json`, `SHA256SUMS`, SPDX 2.3 JSON SBOM, third-party license
inventory, artifact-only install smoke, recovery rehearsal, and a fail-closed
`release-gate`. The artifact remains unsigned: SHA-256 verifies integrity, not
publisher authenticity. See [Quickstart](docs/QUICKSTART.md),
[Release notes](docs/releases/0.3.0rc1.md), and
[Known limitations](docs/KNOWN_LIMITATIONS.md).

Phase 7 adds formal Project Workspaces plus safe Git/GitHub foundations. Web and
CLI can create or clone managed workspaces, inspect structured status, manage
ordinary branches, perform fast-forward-only Pull and no-force Push, and create
Draft PRs. Long mutations run as durable typed Jobs through the Runtime
Executor. See [Project Workspaces](docs/PROJECT_WORKSPACES.md),
[Git Integration](docs/GIT_INTEGRATION.md), and
[GitHub Integration](docs/GITHUB_INTEGRATION.md).

AgentBox still does **not** migrate Runtime credentials or existing root
sessions/projects, delete Project files, expose arbitrary paths or commands,
force push, reset, clean, stage/commit files, expose a public listener, manage
SSH/firewall/tunnels, or change Provider/Secret configuration. Codex and Claude
are detected separately; installation guidance is versioned but no existing
Runtime is automatically upgraded.

A future Phase 11 — Provider, Secret & Runtime Continuity Management is
architecture/backlog only. It separates concrete `ProviderDefinitionID` values
from stable AgentBox `RuntimeBindingID` intent, uses a separate Secret Manager
and transactional Runtime-specific config adapters, and reports Provider,
Runtime, Remote, thread, context, and discovery evidence independently. No
Provider API/UI/CLI, Secret backend, config mutation, or continuity claim is
implemented today.

## MVP goal

The planned MVP targets one Linux server and one administrator. It aims to provide:

- idempotent installation, diagnostics, update, and rollback;
- capability-aware Codex standalone and Remote Control management;
- one-time Codex Pair Code delivery without persistence or logging;
- project-scoped Claude Remote sessions persisted by tmux;
- formal Project Workspaces, safe Git status/branch/Pull/Push, and Draft PRs;
- a loopback-only authenticated Web panel and recovery-oriented CLI;
- durable SQLite-backed Jobs and SSE progress.

Phase 8 provides the deployment mechanics, Phase 9 hardens their security and
compatibility boundary, and Phase 10 packages the reviewed candidate. A tag,
GitHub Release, signed distribution, broader native-host validation, and a
production support promise are not created or claimed by the Phase 10 PR.

## What AgentBox is not

AgentBox is not a general Linux administration panel, browser IDE, arbitrary Web terminal, multi-tenant SaaS, Kubernetes manager, container manager, cloud-server marketplace, or third-party credential vault.

## Architecture baseline

- native systemd deployment is implemented; Docker is not the default;
- Web/API and Worker run as non-root `agentbox`;
- projects, Git, gh, Codex, Claude, and tmux belong to non-root `agentbox-runtime`;
- a minimal socket-activated root Privileged Helper accepts only six typed,
  argument-free AgentBox service actions over a protected Unix Domain Socket;
- Project Workspaces default to `/srv/agentbox/projects`;
- configuration, state, runtime files, and installed releases use `/etc/agentbox`, `/var/lib/agentbox`, `/run/agentbox`, and `/opt/agentbox`;
- Web/API defaults to `127.0.0.1:8787`;
- backend: Python 3.11+, FastAPI, Pydantic Settings, SQLAlchemy, Alembic, and SQLite WAL;
- frontend: React, TypeScript, Vite, Tailwind CSS, and selective shadcn/ui;
- API contracts begin at `/api/v1`; progress will use SSE before WebSocket.

## Security principles

AgentBox will not expose an arbitrary Shell API. Root operations must be named, typed, bounded, independently validated, and executed only by the narrow Helper. Runtime credentials remain owned by third-party CLIs under the Runtime user. Tokens, passwords, OAuth codes, Pair Codes, cookies, SSH private keys, and complete authentication configuration must not enter AgentBox logs or persistence.

The default network listener is loopback. Remote access is an explicit operator-managed Tailscale, Cloudflare Tunnel, VPN, or HTTPS reverse-proxy integration.

See [the security design](docs/SECURITY.md), [permissions model](docs/PERMISSIONS.md), and [threat model](docs/THREAT_MODEL.md).

## Repository map

```text
apps/                 API, Worker, CLI, and Web application shells
packages/             shared core, protocol, and Runtime boundaries
helper/               minimal typed root Helper and socket protocol
installer/            platform-aware installer and deployment assets
tests/                 unit tests and reserved fixture/integration areas
scripts/               repository-only safety checks
docs/                  product, architecture, security, and ADR documents
.github/               CI and contribution templates
```

## Local development

Prerequisites: Linux or a compatible development environment, Python 3.11+, Node.js 22+, and pnpm 11.20.0.

Python setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip "setuptools>=83"
python -m pip install -e ".[dev]"
ruff check apps packages tests
black --check apps/api apps/worker apps/cli packages tests
mypy apps/api apps/worker apps/cli packages tests
pytest
```

Run the explicitly limited API during development:

```bash
agentbox-api
```

Codex and Claude mutations require the separate non-root Runtime Executor. In development
it uses `.agentbox-dev/runtime.sock`; start it in another foreground terminal:

```bash
agentbox-runtime
```

The API never spawns Codex. `agentbox codex status` may fall back to safe local
detection when the Runtime socket is absent; `start`, `stop`, and `pair` do not.
The API also never spawns tmux/Claude or Git/gh directly. Phase 7 development
uses `.agentbox-dev/projects` (or `AGENTBOX_PROJECT_ROOT`); create/clone is
performed only by the Runtime Executor through marker-bound staging and atomic
finalization. Claude commands require the Runtime socket and use only
server-resolved formal Project IDs.

Initialize a development database and local administrator explicitly:

```bash
alembic upgrade head
agentbox admin init
```

Development state is placed beneath `.agentbox-dev/` by default and is ignored
by Git. No production secret is bundled; production requires an explicit
`AGENTBOX_SECRET_KEY` and safe paths/listener configuration.

Frontend setup and checks:

```bash
pnpm install
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

The browser suite uses an isolated temporary database, random test-only secret,
random loopback ports, and Chromium:

```bash
pnpm --filter @agentbox/web exec playwright install chromium
pnpm e2e
```

Do not run `playwright install-deps` on a shared host. Use a supported CI image
or obtain explicit approval for system packages. The E2E harness never uses the
normal `.agentbox-dev` database or a real administrator.

The Vite development proxy points only to `http://127.0.0.1:8787`. These commands do not install a system service or create AgentBox system users/directories.

## Environment support status

OpenCloudOS 9 x86_64 is the first real-host validation target. Ubuntu 24.04 is
a CI preview; Ubuntu 22.04 remains an unsupported CI fixture because its stock
Python 3.10 does not satisfy AgentBox's Python 3.11 minimum. Rocky Linux 9 and
Debian 12 are preview platforms with fixture coverage only. `aarch64` is
detected but fails closed until release artifacts and Runtime tools are qualified. See
[Platform Support](docs/PLATFORM_SUPPORT.md); none of these labels is a general
production support promise.

## Roadmap

1. Phase 2: repository and engineering skeleton — merged in PR #19.
2. Phase 3: control-plane foundation and single-admin authentication — merged in PR #20.
3. Phase 4: authenticated Web foundation — merged in PR #21.
4. Phase 5: capability-aware Codex management — merged in PR #22.
5. Phase 6: Claude/tmux session management — merged in PR #25.
6. Phase 7: Project Workspaces and safe Git/GitHub foundation — merged in PR #27.
7. Phase 8: installation, deployment, upgrade, and rollback — merged in PR #28.
8. Deployment aggregate gate — merged in PR #29 and required on `main`.
9. Phase 9: security and compatibility hardening — merged in PR #30.
10. Phase 10: MVP Release Candidate packaging and documentation — in progress.
11. Phase 11: Provider, Secret & Runtime Continuity Management — future
    post-MVP planning tracked in Issue #23; does not change Phases 6–10.

The detailed gates are in [the development plan](docs/DEVELOPMENT_PLAN.md).

## Documentation

项目文档默认使用简体中文。代码标识、API 路径、CLI 命令、配置键、错误码和第三方产品名称保留英文。既有英文文档将按后续相关变更逐步翻译，不在纯收尾阶段批量改写。

- [Product definition](docs/PRODUCT.md)
- [MVP scope](docs/MVP_SCOPE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API design](docs/API_DESIGN.md)
- [CLI design](docs/CLI_DESIGN.md)
- [Runtime Adapters](docs/RUNTIME_ADAPTERS.md)
- [Codex integration](docs/CODEX_INTEGRATION.md)
- [Claude integration](docs/CLAUDE_INTEGRATION.md)
- [Provider Manager](docs/PROVIDER_MANAGER.md)
- [Web UI design](docs/WEB_UI.md)
- [Test strategy](docs/TEST_STRATEGY.md)
- [Quickstart](docs/QUICKSTART.md)
- [MVP acceptance](docs/MVP_ACCEPTANCE.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [0.3.0rc1 release notes](docs/releases/0.3.0rc1.md)
- [Installation](docs/INSTALLATION.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Upgrade](docs/UPGRADE.md)
- [Rollback](docs/ROLLBACK.md)
- [Uninstall](docs/UNINSTALL.md)
- [Platform support](docs/PLATFORM_SUPPORT.md)
- [Privileged Helper](docs/PRIVILEGED_HELPER.md)
- [ADRs](docs/adr/README.md)
- [Phase 0 report](PHASE0_ENVIRONMENT_REPORT.md)
- [Phase 1 summary](PHASE1_ARCHITECTURE_SUMMARY.md)
- [Phase 2 report](PHASE2_ENGINEERING_REPORT.md)
- [Phase 3 report](PHASE3_CONTROL_PLANE_REPORT.md)
- [Phase 4 report](PHASE4_WEB_FOUNDATION_REPORT.md)
- [Phase 5 report](PHASE5_CODEX_MANAGEMENT_REPORT.md)
- [Phase 6 report](PHASE6_CLAUDE_SESSION_REPORT.md)
- [Phase 7 report](PHASE7_PROJECT_GIT_REPORT.md)
- [Phase 8 report](PHASE8_INSTALLATION_DEPLOYMENT_REPORT.md)
- [Phase 9 report](PHASE9_SECURITY_HARDENING_REPORT.md)

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes. Security-sensitive reports must follow [SECURITY.md](SECURITY.md), not a public Issue.

## License

AgentBox is licensed under the [Apache License, Version 2.0](LICENSE)
(`Apache-2.0`). The decision and its tradeoffs are recorded in
[ADR 0008](docs/adr/0008-license-choice.md) and
[the licensing guide](docs/LICENSING.md).

AgentBox is independent. Codex, Claude, GitHub, and other third-party names are used only for factual compatibility descriptions; no affiliation or endorsement is implied.
