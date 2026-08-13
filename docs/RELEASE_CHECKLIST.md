# AgentBox MVP Release Checklist

Status: Phase 9 release-candidate gate; completing this list does not publish a
release or authorize Phase 10.

## Source and governance

- [ ] Release commit is on protected `main` and all required checks are green.
- [ ] Version and changelog are approved; tag does not already exist.
- [ ] Diff contains no Provider Manager, Secret Manager, public-network, SSH,
      firewall, tunnel, multi-server, or SaaS scope.
- [ ] Open Critical/High security findings are zero; accepted residual risks
      have an owner and human approval.

## Build and dependencies

- [ ] Backend ruff, Black, mypy, pytest, Alembic round trip, and `pip-audit`
      pass on the supported Python matrix.
- [ ] Frontend lint, format, typecheck, unit tests, production build, and
      high-level audit pass.
- [ ] Playwright E2E and the four-job Deployment matrix plus
      `deployment-gate` pass.
- [ ] Secret, repository-boundary, forbidden-primitive, and immutable workflow
      action-pin scans pass.
- [ ] Python/frontend dependency inventories and release file manifest are
      generated. If an SBOM is produced, its format/tool/version is recorded.

## Database and recovery

- [ ] Alembic upgrade/downgrade/upgrade works on a disposable database.
- [ ] WAL-active online backup passes integrity and concurrent-write tests.
- [ ] Upgrade backup, migration, activation, service restart, readiness,
      version, and commit stages have fault evidence.
- [ ] Rollback rejects missing/corrupt/mismatched release, DB, unit, socket,
      health, readiness, and version evidence.
- [ ] Retention protects current/previous release and receipt-pinned backup and
      never deletes an unverified object.

## Installation and compatibility

- [ ] Artifact checksum, manifest, archive bounds, extraction type/path/link
      defenses, and unit minimum-version validation pass.
- [ ] OpenCloudOS read-only/service lifecycle validation is current.
- [ ] Ubuntu/Rocky/Debian claims exactly match `PLATFORM_SUPPORT.md`; fixture
      evidence is not called real-host support.
- [ ] API remains loopback-only and services run under documented identities.
- [ ] Existing root Codex/Claude/tmux/gh/project state remains unchanged.

## Security and privacy

- [ ] Password, Session, CSRF, application secret, Git URL, gh token, Pair Code,
      and Claude output canaries are absent from logs and persistence.
- [ ] Runtime/Helper malformed-frame, peer UID/GID, and fixed-action tests pass.
- [ ] Production secure Cookie/exact HTTPS Origin and explicit trusted-proxy
      semantics pass; no direct HTTP login is recommended.
- [ ] Diagnostics export is new-file-only, `0600`, size bounded, redacted, and
      reviewed manually before sharing.

## Artifacts and publication

- [ ] Release archive is produced from the approved commit with prebuilt Web
      assets and a release-local venv strategy.
- [ ] SHA-256 values are published separately and described as integrity—not
      authenticity—evidence.
- [ ] A signed-release mechanism is approved before claiming authenticity.
- [ ] Install, update, rollback, known limitations, platform qualification,
      backup responsibility, security reporting, and remaining manual Runtime
      login steps are current.
- [ ] Human approval explicitly authorizes Phase 10 publication.
