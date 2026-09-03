# Changelog

All notable AgentBox changes are recorded here. The project follows semantic
versioning for release display and PEP 440 for the Python package.

## [0.3.0rc2] - Unreleased

### Added

- Runtime-owned encrypted WAW attachment stream and bounded inherited Unix
  listener, with exact lease, publication and cleanup fences.

### Fixed

- Exact detach/Stop prevents a previously prepared or partially written OUTPUT
  from publishing after cleanup, and preserves input/reconciliation faults.

### Known limitations

- R7 software review is complete; exact-head CI/merge and R8 remain separate.
- Browser terminal/controller, independent trust provider, fixed interactive
  CLI execution, Linux isolation and real-host qualification remain unfinished.

## [0.3.0rc1] - Unreleased

### Added

- Single-administrator authenticated FastAPI/React control plane with
  health/readiness/meta, Doctor, Settings, CLI, and desktop/mobile browser flows.
- Codex capability/status and Remote start/stop management plus an ephemeral,
  recent-authenticated Pair Code channel.
- Claude Code project Sessions owned by managed tmux under the isolated Runtime
  identity, with explicit manual trust/attach guidance.
- Formal Project Workspaces, durable typed Jobs, safe create/clone, structured
  Git status, ordinary branch operations, fast-forward-only Pull, no-force Push,
  and Draft GitHub PR creation.
- Native platform-aware installation, FHS paths, distinct service identities,
  hardened systemd units, minimal socket-activated root Helper, staged updates,
  online SQLite backup, verified rollback, and data-preserving uninstall.
- Reproducible Linux x86_64 RC bundle, internal/external release manifest,
  `SHA256SUMS`, SPDX 2.3 JSON SBOM, dependency license inventory, hardened
  artifact verifier, isolated install smoke, and stable `release-gate` CI.

### Changed

- Version metadata now derives from the Python core version source; package,
  Web, API, CLI, installer manifest, artifact name, and documentation are
  checked for consistency.
- Production API/Web remains independent of Node/Vite; optional Runtime tools
  degrade individually instead of blocking the control plane.
- Platform labels are standardized as Real-host validated, CI validated,
  Fixture validated, or Unsupported.

### Security

- API, Worker, and Runtime run non-root; the root Helper accepts only six fixed,
  argument-free AgentBox lifecycle actions and verifies UDS peer UID/GID.
- Pair Codes remain transient and excluded from SQLite, Audit, Jobs, logs,
  reports, browser storage, and release artifacts.
- Login limiting persists pseudonymous bounded buckets across restarts;
  diagnostics, IPC, Git/gh, Runtime output, and release files are canary scanned.
- Artifacts reject traversal, path-normalization collisions, links, special
  files, unsafe modes, duplicate paths, unallowlisted files, and digest/schema/
  platform/version/migration inconsistencies.
- Release bootstrap/build packaging tools are pinned to patched `pip 26.2.1`
  and `wheel 0.46.2`, audited in the exact build environment, and compatibility
  checked on CPython 3.11–3.13 before `release-gate` can succeed.
- SHA-256 provides integrity only. This candidate has no signature or verified
  publisher authenticity.

### Fixed

- Password rotation and concurrent login now serialize correctly so a login
  cannot create a surviving Session from the old password after rotation.
- Upgrade crash states, partial migration restoration, backup identity,
  retention, and rollback verification fail closed instead of reporting an
  unverified recovery as success.
- Git credential/config injection, clone residue activation, unsafe refs, and
  active-Claude workspace mutation are rejected by typed Runtime policies.

### Known limitations

- OpenCloudOS 9 x86_64 is the only real-host validated platform; Ubuntu 24.04
  is CI validated, Rocky 9/Debian 12 are fixture validated, stock Ubuntu 22.04
  and aarch64 are unsupported.
- External HTTPS/proxy/tunnel configuration, Project backup, host reboot
  validation, artifact signing, and broader Runtime compatibility remain open.
- Provider Manager, Secret Manager, Provider switching/failover, multi-server,
  SaaS, and browser terminal are not implemented.

## [0.2.10+dev.9] - Internal development baseline

Phase 9 security hardening baseline used for the `0.3.0rc1` preparation. It was
not published as a stable release.
