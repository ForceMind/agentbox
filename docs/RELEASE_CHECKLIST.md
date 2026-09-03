# AgentBox MVP Release Candidate Checklist

Candidate: `0.3.0rc1`; planned tag: `v0.3.0-rc.1`.

Completing the preparation boxes does not authorize a tag, GitHub Release, or
stable-support claim. Publication boxes remain manual and require review after
the Phase 10 PR is merged.

## Source and version

- [ ] Build from a clean tracked checkout at the reviewed source commit.
- [ ] All required and additional exact-head checks are terminal successful and applicable reviews are resolved.
- [ ] Python core, package metadata, `agentbox --version`, `/api/v1/meta`, Web
      package, installer, manifest, artifact name, release notes, and changelog
      report one consistent candidate version.
- [ ] Planned tag does not already exist; source commit and
      `SOURCE_DATE_EPOCH` are recorded.
- [ ] No tag or GitHub Release is created by the PR workflow.

## Build and dependency controls

- [ ] Python release dependencies are exact and SHA-256 locked; the artifact
      contains the qualified Linux x86_64 CPython 3.11–3.13 wheelhouse.
- [ ] `requirements-release-build.lock` pins and hashes every Python build/test
      package, including pip/setuptools/wheel; the workflow installs no
      range-resolved `.[dev]` or `latest` packaging tool.
- [ ] `requirements-release-bootstrap.lock` contains exactly the pip wheel
      version/hash embedded in `install.sh`; manifest, SBOM, notices, nested
      wheel scan, and per-file digest inventory include that wheel.
- [ ] `requirements-release-packaging.lock` matches the pip/wheel entries in the
      full build lock, installs with `--require-hashes --no-deps`, and passes on
      CPython 3.11, 3.12, and 3.13 before `release-gate` succeeds.
- [ ] `pip-audit --local --skip-editable` reports no known vulnerability in the
      exact release build/test environment.
- [ ] Node `22.23.2` and pnpm `11.20.0` match the toolchain recorded in the
      manifest, and the toolchain checker passes against the clean CI environment.
- [ ] `pnpm install --frozen-lockfile` and production Web build pass.
- [ ] GitHub Actions use only audited immutable SHA pins and minimal read-only
      permissions; PR builds receive no secrets or write token.
- [ ] Backend ruff, Black, mypy, pytest, Alembic
      upgrade/downgrade/upgrade, and `pip-audit` pass.
- [ ] Frontend lint, format, typecheck, unit, build, and high audit pass.
- [ ] E2E, four-job Deployment matrix, `deployment-gate`, and every current required/additional
      exact-head check passes (19 observed for the WAW software PRs).

## Reproducibility and artifact contract

- [ ] Two independent clean staging builds with the same source, lockfiles, and
      `SOURCE_DATE_EPOCH` produce byte-identical artifact SHA-256 values.
- [ ] Tar order, timestamps, uid/gid, names, modes, gzip timestamp, JSON order,
      Web output, and wheel output are deterministic in the same CI environment.
- [ ] Artifact filename is `agentbox-<version>-linux-x86_64.tar.gz` and size is
      within the documented limit without node_modules, browser, dev venv, test
      cache, source map, database, config, Project, or credential content.
- [ ] `RELEASE_MANIFEST.json` schema, actual source commit/ref kind, target,
      file allowlist, per-file SHA-256, `>=3.11,<3.14` plus cp311/cp312/cp313
      ABI contract, locked build/bootstrap toolchain, migration head,
      SBOM/license names, and unsigned status verify.
- [ ] `SHA256SUMS` independently verifies the tarball, external manifest, and
      external SBOM using safe relative filenames.
- [ ] Archive verification rejects absolute/traversal/normalization-colliding/
      duplicate paths, links, devices, FIFO/socket, unexpected type, unsafe
      mode, member/size overflow, missing file, and digest mismatch.

## SBOM and licenses

- [ ] SPDX 2.3 JSON SBOM contains AgentBox plus direct/transitive Python and
      production frontend packages with versions, managers, and declared
      licenses.
- [ ] `THIRD_PARTY_NOTICES.md` and generated inventory match the lockfiles.
- [ ] Unknown licenses are flagged; no obvious Apache-2.0 distribution blocker
      is accepted without human/legal review.
- [ ] License results are described as an engineering inventory, not legal advice.

## Security and privacy

- [ ] Source and final artifact secret scans pass, including all Phase 10
      password/Session/CSRF/Pair/Claude/Git/GitHub/Provider/SSH canaries.
- [ ] Secret scanning covers tar member names/bytes and bounded decompression of
      every nested wheel member; malformed, duplicate, unsafe, oversized, or
      canary-containing wheel content fails closed.
- [ ] Static assets have no production source maps, developer absolute paths,
      or secret canaries.
- [ ] Artifact contains no world-writable executable, setuid/setgid bit, file
      capability, unexpected executable, symlink, hardlink, or special node.
- [ ] SHA-256 is called integrity evidence only; artifact signature and
      authenticity are explicitly `not available`.
- [ ] Open P0/P1 security issues and unresolved blocking review threads are zero.
- [ ] `SECURITY_REVIEW_MVP.md`, threat model, security policy, and known residual
      risks are current; this work is not described as a penetration test.

## Installation and recovery

- [ ] `bash -n` and the artifact's actual `install.sh` verification, offline
      bootstrap, fixture plan/apply, failure cleanup, and argument forwarding
      work without an installed source-checkout AgentBox package.
- [ ] Bootstrap succeeds with host venv/ensurepip/global pip unavailable, uses
      only the artifact pip wheel and wheelhouse through `--no-index`/`--target`,
      and Ubuntu 24.04 plus Debian 12 no-venv fixtures pass.
- [ ] Prerelease precedence covers numeric identifiers, rc normalization,
      stable ordering, ignored build metadata, leading-zero rejection, plan,
      apply, downgrade rejection, rollback selection, and retention ordering.
- [ ] AgentBox API/static Web installs and runs without Node/Vite.
- [ ] Fixture fresh install, triple reinstall, application-secret/admin/DB/
      Project/Runtime-HOME preservation, and data-preserving uninstall pass.
- [ ] Alembic migration reaches the manifest head in a temporary SQLite DB.
- [ ] Health, readiness, metadata version, static Web, and CLI help/version smoke pass.
- [ ] Upgrade backup/migration/activation and injected failure evidence pass.
- [ ] Rollback verifies release, DB integrity/revision, units, sockets,
      health/readiness, and version; verification failure is never called success.
- [ ] OpenCloudOS rehearsal plan is reviewed only after all automated gates pass.
- [ ] Real-host rehearsal updates only AgentBox-owned release state, verifies the
      candidate, rolls back, and ends at the pre-rehearsal stable release.
- [ ] DB/admin/Projects/config/application secret/Runtime HOME and credential
      metadata remain unchanged; root Runtime, SSH, firewall, and cloudflared
      remain untouched.

## Documentation and claims

- [ ] README, Quickstart, release notes, Installation, Upgrade, Rollback,
      Platform Support, MVP Acceptance, Known Limitations, and Changelog agree.
- [ ] Relative documentation links and reasonable anchors pass automated checks.
- [ ] CLI help lists only implemented commands; no Provider command or dangerous
      Git operation is documented as available.
- [ ] Platform claims use only Real-host validated, CI validated, Fixture
      validated, or Unsupported.
- [ ] Release notes list manual admin initialization, independent Runtime logins,
      secure remote access, backup limits, unsigned artifact, and out-of-scope work.

## Publication after merge (manual, not Phase 10 PR actions)

- [ ] Rebuild from merged protected `main` and compare reviewed source commit.
- [ ] Obtain human approval for the candidate version and release notes.
- [ ] Create the reviewed tag once; never replace or force-update it.
- [ ] Build final artifacts from the tag and repeat checksums/verify/SBOM/audits.
- [ ] Create a Draft GitHub Release marked pre-release and attach all files.
- [ ] Review rendered notes and downloaded artifacts before publication.
- [ ] Publish the pre-release only with explicit human authorization.

## Reviewed lock regeneration

`requirements-release-build.in` is the human-reviewed direct input. Regenerate
the Linux x86_64/CPython 3.11 lock only in a disposable environment by
downloading binary wheels, recording each selected distribution's exact version
and SHA-256, then run `scripts/check-release-toolchain.py`. Review every diff;
never regenerate the lock dynamically inside the Release Candidate workflow.
The two-line `requirements-release-packaging.lock` must be reviewed at the same
time and must exactly match the pip/wheel versions and hashes in the full lock.

## WAW software preparation versus product release

The phase-specific evidence record is `WAW_SOFTWARE_READINESS.md`. This checklist
is a gate template; boxes are not retroactively marked from synthetic evidence.

Software evidence may cover:

- [ ] Closed Claude/Codex API and Web contracts, identity and stale-event fences.
- [ ] Exact Project/AgentType metadata queries, explicit Start/exact Stop and
      desktop/mobile metadata interactions.
- [ ] Reproducible candidate, exact source commit/ref kind, manifest/checksums,
      SBOM/notices and archive/canary scans.

The following remain separate product/host gates:

- [ ] Explicit Architecture/Owner scope for real Noise/PTY/WebSocket and CLI
      execution; an authorized disposable Linux target and recovery conditions.
- [ ] Actual legacy process probes/interlocks and no-adoption/exact-stop proof.
- [ ] Real desktop/mobile terminal input/output/resize/detach/reconnect and
      Runtime/API restart/reboot recovery with attributable non-secret evidence.
- [ ] Runtime-only login/Trust readiness without credential or HOME disclosure.
- [ ] Exact version/tag/artifact publication authorization and final release
      read-back. Ordinary code merges do not authorize production activation.

A CI-built software artifact cannot check any of the real-host boxes above.
