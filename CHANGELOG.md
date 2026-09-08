# Changelog

All notable AgentBox changes are recorded here. The project follows semantic
versioning for release display and PEP 440 for the Python package.

## [0.3.0rc11] - Unreleased

- R12-B candidate: resolve production WAW mode from one fixed installer-owned
  API profile; a safely absent leaf preserves disabled management compatibility.
- Reject unsafe/noncanonical/replaced profiles and production mode injection;
  revalidate the startup snapshot before serving and reuse one installed app.
- Clean factory-owned database resources on construction failure while preserving
  caller-owned services. Runtime provider/host/client qualification remains separate.
- Candidate validation, review and delivery status: `docs/releases/0.3.0rc11.md`.

## [0.3.0rc10] - Unreleased

- WEV-1 candidate: invalidate stale Workspace Runtime observations and Stop
  confirmations after browser lifecycle interruptions; re-read state on return
  without automatically sending Agent lifecycle operations.
- Adds the workstation evolution research, capability matrix and bounded
  follow-up decisions; R12 host, Secret and publication gates stay independent.
- Advances the unified version and explicitly admits rc10 in the release gate;
  frozen rc8 rehearsal evidence and unknown-version rejection remain intact.
- Validation and delivery status are tracked in `docs/WORKSTATION_EVOLUTION.md`.

### Delivery evidence

- PR #87 head `80a6972466a514aa67577bb7812cf4c649a5983c` completed the 26-check
  contract: 24 success and two prescribed rc8 historical skips. It merged normally
  as `b3e9cd5dbfbdca0c5e0cd652dc0cce7e1e53214e` at `2026-09-08T03:44:14Z`,
  with verified parents `b72f6ea...` and `80a6972...`.
- All six post-main workflows succeeded on that exact merge.
- Web CI passed 1109 tests; browser-trust extension CI passed 6; final local
  Chromium acceptance passed 96 with 28 existing matrix skips. Independent
  Architecture/Test/Security reviews passed after the recorded repairs.
- No tag, Release, deployment, real-host activation or R12 qualification.

## [0.3.0rc9] - Unreleased

### Added

- R11 rc9 delivers browser-selected
  bilingual UI: typed English/`zh-CN` catalogs, catalog parity checks, route and
  state migration, and API error-code localization without server prose.
- The document locale is fixed from only `navigator.languages[0]` before React
  renders. Primary `zh` maps to `zh-CN`; all other, absent or malformed first
  preferences map to English. Technical values remain English.
- The test-only Workspace harness has a distinct origin and is excluded from the
  production bundle. Sensitive E2E artifacts (trace, video and screenshots)
  remain disabled.
- Safe text component contracts reject raw-HTML props while preserving the
  repository browser-source execution boundary.
- Project and Project-detail technical values now wrap inside their cards at
  desktop and mobile widths, preventing horizontal viewport overflow.
- The Workspace Project selector and terminal input can shrink within their
  mobile rows.
- Long status badges wrap within mobile runtime-card headings without hiding
  their state text.

### Delivery evidence

- PR #85 final exact head `751d4d010f92e18780bd6d96fdb3c9ea23107464` completed
  all 26 checks. It merged normally at `2026-09-06T17:57:57Z` as
  `b07f944ef2c7b590e5a3f1fa50354d6f492d6c31`, with exact parents
  `b191f4bc259cf6c4e0357afa85a9be0c41acb8ef` and
  `751d4d010f92e18780bd6d96fdb3c9ea23107464`.
- Post-main Security `34050212985`, Deployment `34050213004`, Frontend
  `34050212993`, E2E `34050212986`, Release Candidate `34050213006`, and Backend
  `34050213380` all completed success.
- Local evidence is Web unit 44 files / 1088 tests, Chromium E2E 92 passed / 28
  intentional matrix skips, release-candidate unit 45 tests, and browser trust
  extension 3 files / 6 tests; each completed successfully before this record.
- Version mapping is Python `0.3.0rc9`, npm `0.3.0-rc.9`, and MV3 `0.3.0.9`.
- `release-gate`, rc8 synthetic/import and the current-candidate checks succeeded.
  The historical `rc8-predecessor-artifact` and `rc8-artifact-operations` jobs
  were exactly `skipped`, as required for rc9.

### Status

- rc9 and all R11 software rc6–rc9 are delivered as software evidence. No tag,
  GitHub Release, production deployment, Provider credential operation or real
  host activation occurred. R12 remains independent, unstarted and host-gated.

## [0.3.0rc8] - Unreleased

### Added

- R11 rc8 adds the artifact and operations rehearsal: it builds native helpers
  from unpacked artifact source, imports only from an artifact wheelhouse
  environment, and uses a synthetic key/peer/trust/PTY harness for typed attach,
  input, output, resize, detach and exact Stop paths.
- The upgrade then rollback rehearsal uses rc7 release-record merge
  87f5bce964eba231a6a7ade73eaedac7e54646ae as its exact predecessor and
  verifies non-secret database, Project, Runtime-home and epoch canaries plus
  receipt and journal integrity.

### Verification

- Candidate c998fb9981553e6fbd6e411f7fe79f57ddc8ebb2 completed all 26
  exact-head checks. The full Linux gate verifies separate exact artifacts,
  CPython 3.11/3.12/3.13 artifact imports, a non-skipping 3.11 synthetic path,
  upgrade/rollback and all-surface dynamic canary scans.
- The candidate also bounds cancellation-resistant WAW work-ledger shutdown so
  unresolved cleanup retains ownership and enters the typed incomplete-shutdown
  state rather than hanging the caller.

### Merge read-back

- Documentation head 710ceef696757a8a1f2a9165f2312672db57bb1e completed a fresh
  26 exact-head matrix and merged normally in PR #83 as
  95bf65d6114008b962985f7311941499c961a7b8, with exact parents 87f5bce and
  710ceef. Security, Deployment, Frontend, E2E, Release Candidate and Backend
  all completed success on that merge.

### Status

- The rc8 software rehearsal is delivered. It remains unreleased: no tag,
  GitHub Release, host action, credential use or R12 qualification occurred.

## [0.3.0rc7] - Unreleased

### Added

- R11 rc7 adds deterministic, test-only composed failure injection for WAW
  admission, relay, restart, shutdown, browser lifecycle and exact Stop paths.
- Closed checkpoints, void gates, integer-nanosecond clocks, controlled partial
  writes and canary scans exercise failure boundaries without handling Provider
  credentials or activating host policy.

### Verification

- PR #81 candidate `04ef0ae2b94e127cacc496e7876bd41cf203f43d` completed the
  20/20 exact-head CI matrix and merged normally as
  `b0eaef2e4e54cf1aba86e7669733d0adc885c1fb`; exact read-back and all six
  standard post-main workflows are successful.

### Known limitations

- At the rc7 release-record checkpoint, rc8 artifact/upgrade/rollback and rc9
  full route/state localization were unfinished. The rc8 section above records
  its candidate software evidence; R12 host qualification and rc9 remain
  unfinished.

## [0.3.0rc6] - Unreleased

### Added

- R11 rc6 composes the browser terminal page with the existing typed controller,
  bounded DOM renderer, managed-provider availability, viewport-only resize and
  localized English/Chinese Workspace controls.
- Current Project/binding read-back now fences WebSocket admission and active
  relay publication; a post-Start drift creates a durable exact Stop operation
  and records only a positive Stop acknowledgement as `STOPPED`.

### Fixed

- Page lifecycle, input ownership, stale action errors and exact Stop preserve
  the controller's control identity without retaining browser plaintext.
- The terminal renderer uses closed fixed-cell classes for normal, wide and
  sparse cells; no output is parsed as HTML or placed in a dynamic style.

### Known limitations

- This source candidate remains software evidence only. Signed Chromium
  enrollment, trustd installation, real CLI/PTY and host qualification remain
  R12 work.

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
- Exact Stop gives tmux a bounded interval to reap the observed pane zombie and
  remove its process group after pidfd exit/cgroup-empty proof.
- The bridge uses raw outer-terminal input and a bounded 64-position random
  tmux cursor/DSR acknowledgment before pane exit; delayed vendor queries cannot
  impersonate the post-exit challenge, and unparsed challenge prefixes fail closed.
- The Linux tail-integrity fixture keeps all 2,048 digest-checked frames ahead of
  its intentional DSR overlap noise, so canonical inner-PTY echo can affect only
  excluded padding and cannot create a sanitizer scheduling flake.

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
