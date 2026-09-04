# Changelog

All notable AgentBox changes are recorded here. The project follows semantic
versioning for release display and PEP 440 for the Python package.

## [0.3.0rc5] - Unreleased

### Added

- Runtime host manifest v2, exact-six executable and exact-two interactive
  profiles, descriptor-held launch handles and complete policy cross-pins.
- Fixed C17 pane-bootstrap/bridge/attach helpers and Runtime PTY/WBR transport
  with READY, attach/detach/reconnect, bounded relay and cgroup-backed Stop.
- Version-bound qualified auth probing, local-TTY login/trust seams and one
  host-wide WAW/legacy start conflict coordinator.
- Inert WAW `tmux`, sandbox, Claude and Codex policy templates in the Runtime
  package, including a canonical exact-two Codex TOML policy bundle and fixed
  package-data/release-inventory checks.
- WAW native helper source and the reviewed portable/Linux build-check scripts
  in release artifacts for inspection and later qualification.
- Browser-trust packaging derives and verifies the numeric MV3 rc5 identity
  (`0.3.0.5`) from the npm candidate version.
- The fixed interactive-process contract, including the R10 software boundary
  and the distinct R11 integration/R12 host-evidence gates.

### Fixed

- Rootless workspace mounts reanchor kernel-derived lookup hints inside U1 and
  exact-match them to the held directory authority before non-recursive bind;
  U2 remains blocked until mount, capability, seccomp and FD lockdown complete.
- Exact Stop removes tmux 3.2a stale socket names only after cgroup empty proof
  and an identity-bound, dirfd-relative read-back/unlink/read-back sequence.
- Failed Start records the tmux socket identity before accepting the pane and
  applies the same cleanup after cgroup empty proof, preserving safe retries.
- Pane/bootstrap exit is observed through non-child pidfd readiness; only direct
  launcher and attach-supervisor children use `waitid`, and unknown pane exit
  status remains explicit instead of raising `ECHILD` or inventing a code.
- Failed Start exhausts pane observation, direct-child reap, cgroup cleanup,
  socket cleanup and local FD closure independently while preserving the first
  cleanup error and its original Start context.
- The bridge uses raw outer-terminal input and a bounded 64-position random
  tmux cursor/DSR acknowledgment before pane exit; delayed vendor queries cannot
  impersonate the post-exit challenge, and unparsed challenge prefixes fail closed.

### Known limitations

- The templates and helper source neither install nor enable a unit/socket,
  production binary, vendor CLI/account, policy enrollment or Secret.
- Real vendor compatibility, signed/reproducible native binaries and installed
  host isolation/recovery evidence remain R12; browser/API controller integration
  and complete cross-page bilingual UI remain R11.

## [0.3.0rc4] - Unreleased

### Added

- Closed browser trust record/lifecycle verification with generation-bound
  invalidation leases and a managed Chromium external-port adapter.
- An externally inert MV3 bridge, fixed Native Messaging/trustd protocol,
  service-owned signed trust store, chained revision-floor journal, signed
  intact-state time high-water and public-only deployment bundle generator.
- A bounded Unicode 13 terminal model and cooperative scheduler whose tokenizer,
  model, projection and render work share one five-millisecond callback deadline.
- Browser-language `zh-CN`/English selection and bilingual Workspace copy; other
  browser languages fall back to English.

### Fixed

- Trust commits recheck the exact provider registration synchronously, validate
  every signing predecessor at final trusted time, reject oversized records
  before copying and retire failed subscriptions exactly once.
- Bidi/default-ignorable, Hangul and emoji modifier handling no longer relies on
  browser shaping, and CPU work crossing fixed windows is accounted correctly.

### Known limitations

- Production Connect remains disabled until a reviewed extension ID, managed
  Chrome policy, Native Host/trustd installation and R12 evidence are supplied.
- The software time high-water does not resist a privileged consistent rollback
  of the whole trustd store while an older pin remains time-valid; R12 must
  qualify or externally anchor it.
- Full terminal/controller integration and complete cross-page bilingual UI
  remain R11 work; fixed interactive processes remain R10 work.

## [0.3.0rc3] - Unreleased

### Added

- Native bounded WebSocket admission and API ciphertext relay over the exact
  Runtime encrypted attachment stream.
- A shared 65,536-byte encoded INPUT ownership ledger from native ready through
  Runtime send, plus the independent 128-slot/8 MiB parser allocation pool.

### Fixed

- Terminal/output, pending-PING and first-ciphertext-drop paths synchronously
  fence authority and actual publication before late data can continue.
- Runtime failure metadata uses fresh browser-leg correlation identifiers and
  revalidates authorization before every emitted failure frame.
- Relay and admission cleanup remain single-task and cancellation-resistant;
  authority-fence or CLOSE-encoding failures cannot skip Runtime cleanup, Audit
  or local transport closure, and cannot release an unproven authority record.

### Known limitations

- R8 requires exact-head CI and merge before delivery.
- Browser trust, terminal/controller, fixed interactive CLI and host qualification
  remain later stages.

## [0.3.0rc2] - Unreleased

### Added

- Runtime-owned encrypted WAW attachment stream and bounded inherited Unix
  listener, with exact lease, publication and cleanup fences.

### Fixed

- Exact detach/Stop prevents a previously prepared or partially written OUTPUT
  from publishing after cleanup, and preserves input/reconciliation faults.

### Known limitations

- R7 was delivered by PR #76; its real-host qualification remains separate.
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
