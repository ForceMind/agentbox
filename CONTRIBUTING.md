# Contributing to AgentBox

AgentBox is pre-alpha infrastructure with a planned root privilege boundary. Small changes can have large security consequences, so contributions must preserve the documented architecture.

## 文档语言

新增或更新项目文档时，默认使用简体中文。代码标识、API 路径、CLI 命令、配置键、错误码和第三方产品名称保留英文。若面向国际协作者提供英文版本，应保证其安全约束和架构结论与中文主文档一致。

## Before starting

1. Read `docs/PRODUCT.md`, `docs/MVP_SCOPE.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/PERMISSIONS.md`, and relevant ADRs.
2. Search existing Issues and ADRs before proposing a new mechanism.
3. For a changed trust boundary, default bind, project root, Runtime user, database, deployment model, or license, propose an ADR before implementation.
4. Never include real credentials, Pair Codes, authentication files, private repository content, or public host details in an Issue, fixture, log, screenshot, or commit.

## Workflow

- Do not develop directly on `main`.
- Create one short-lived branch for one coherent outcome.
- Open a Draft PR early for privilege, authentication, IPC, update, path, or Runtime work.
- Use Conventional Commit-style messages such as `build: add frontend workspace` or `test: cover API metadata`.
- Do not force-push protected/shared branches or rewrite published tags.
- Keep generated dependency-lock changes intentional and reviewable.

## Local checks

Python:

```bash
ruff check apps packages tests
black --check apps/api apps/worker apps/cli packages tests
mypy apps/api apps/worker apps/cli packages tests
pytest
```

Frontend:

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm format:check
```

Repository safety:

```bash
bash scripts/check-secrets.sh
bash scripts/check-skeleton-boundaries.sh
git diff --check
```

## Pull requests

Describe the objective, changes, tests actually run, risks, security impact, known limitations, and follow-ups. Do not claim tests passed unless the listed commands actually succeeded. Keep product code, tests, and the documentation required for the outcome together; split unrelated cleanup.

The Phase 2 skeleton deliberately contains no authentication, database schema, Runtime management, project management, installer execution, systemd unit, or Privileged Helper implementation. Contributions must not bypass phase gates merely because a package directory exists.

## Reporting vulnerabilities

Do not open a public Issue for a suspected vulnerability. Follow the private process in the repository-root `SECURITY.md`.

## Contribution license

Unless a separate written agreement explicitly states otherwise, intentionally
submitted contributions are provided under the repository's
[Apache License 2.0](LICENSE), as recorded in
[ADR 0008](docs/adr/0008-license-choice.md).
