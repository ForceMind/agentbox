# AgentBox

**Turn any Linux server into a remotely managed AI development workstation.**

AgentBox is open AI developer infrastructure for standardizing a user-controlled Linux server as a remotely manageable development workstation. It is designed around capability-aware AI Runtime integration, persistent project sessions, safe lifecycle operations, and minimal routine SSH.

## Project status

AgentBox is in **early pre-alpha development**. Phases 2 and 3 are merged. Phase
4 is adding the authenticated Web product foundation on a dedicated branch.

The current codebase provides:

- a FastAPI service with health/readiness/meta plus login/logout/`auth/me` only;
- explicit SQLite/Alembic persistence for AdminUser, hashed Sessions, and redacted Audit Events;
- local-TTY administrator initialization, Argon2id, CSRF, secure Cookie policy, and bounded login throttling;
- a Worker lifecycle limited to database readiness and expired Session cleanup;
- a control-plane-only CLI and a responsive React application shell with
  login, authenticated Session recovery, Dashboard, Doctor, Settings, and
  clearly marked placeholder product sections;
- package boundaries, tests, CI, governance templates, and architecture documents.

It does **not** manage Codex, generate Pair Codes, run Claude Remote, manage
tmux or projects, operate a root Helper, install system services, expose a
public listener, or modify this host.

## MVP goal

The planned MVP targets one Linux server and one administrator. It aims to provide:

- idempotent installation, diagnostics, update, and rollback;
- capability-aware Codex standalone and Remote Control management;
- one-time Codex Pair Code delivery without persistence or logging;
- project-scoped Claude Remote sessions persisted by tmux;
- minimal Project Workspace and read-only Git visibility;
- a loopback-only authenticated Web panel and recovery-oriented CLI;
- durable SQLite-backed Jobs and SSE progress.

These are roadmap goals, not implemented features.

## What AgentBox is not

AgentBox is not a general Linux administration panel, browser IDE, arbitrary Web terminal, multi-tenant SaaS, Kubernetes manager, container manager, cloud-server marketplace, or third-party credential vault.

## Architecture baseline

- native systemd deployment is planned; Docker is not the default;
- Web/API and Worker run as non-root `agentbox`;
- projects, Git, gh, Codex, Claude, and tmux belong to non-root `agentbox-runtime`;
- a future minimal root Privileged Helper accepts only typed allowlisted actions over a protected Unix Domain Socket;
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
helper/               root Helper design placeholder only
installer/            installer design placeholder only
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

OpenCloudOS 9, Rocky Linux 9, Ubuntu LTS, and Debian stable are planned MVP distribution families. Only the Phase 0 OpenCloudOS host has been inventoried; no distribution is yet claimed as deployment-tested or production-supported. x86_64 is the first planned release architecture, and other architectures remain unqualified.

## Roadmap

1. Phase 2: repository and engineering skeleton — merged in PR #19.
2. Phase 3: control-plane foundation and single-admin authentication — merged in PR #20.
3. Phase 4: authenticated Web foundation — in progress.
4. Phase 5: Codex management.
5. Phase 6: Claude/tmux session management.
6. Phase 7: Project Workspaces and minimal Git.
7. Phase 8: installation, deployment, upgrade, and rollback.
8. Phase 9: security and compatibility hardening.
9. Phase 10: first release.

The detailed gates are in [the development plan](docs/DEVELOPMENT_PLAN.md).

## Documentation

- [Product definition](docs/PRODUCT.md)
- [MVP scope](docs/MVP_SCOPE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API design](docs/API_DESIGN.md)
- [CLI design](docs/CLI_DESIGN.md)
- [Runtime Adapters](docs/RUNTIME_ADAPTERS.md)
- [Web UI design](docs/WEB_UI.md)
- [Test strategy](docs/TEST_STRATEGY.md)
- [ADRs](docs/adr/README.md)
- [Phase 0 report](PHASE0_ENVIRONMENT_REPORT.md)
- [Phase 1 summary](PHASE1_ARCHITECTURE_SUMMARY.md)
- [Phase 2 report](PHASE2_ENGINEERING_REPORT.md)
- [Phase 3 report](PHASE3_CONTROL_PLANE_REPORT.md)

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes. Security-sensitive reports must follow [SECURITY.md](SECURITY.md), not a public Issue.

## License

AgentBox is licensed under the [Apache License, Version 2.0](LICENSE)
(`Apache-2.0`). The decision and its tradeoffs are recorded in
[ADR 0008](docs/adr/0008-license-choice.md) and
[the licensing guide](docs/LICENSING.md).

AgentBox is independent. Codex, Claude, GitHub, and other third-party names are used only for factual compatibility descriptions; no affiliation or endorsement is implied.
