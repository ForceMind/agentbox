# AgentBox Phase 10 MVP Release Candidate Report

## Executive Summary

Phase 10 prepares AgentBox `0.3.0rc1` as an unsigned MVP Release Candidate for
a single-administrator, single-server Linux x86_64 deployment. It adds one
reproducible artifact pipeline around the existing Phase 8 installer rather
than adding product capability. The candidate has a canonical manifest,
external SHA-256 checksums, an SPDX 2.3 SBOM, third-party notices, artifact-only
installation and recovery smoke coverage, release documentation, and a
fail-closed `release-gate` workflow.

No tag or GitHub Release has been created. Phase 11 is not started.

## Branch / Commits / PR

- Branch: `phase/10-mvp-release-candidate`
- Baseline main: `0334f8249ceddbcd9ff32a95435905002694e360`
- Final local integrity artifact source: `29e65078afba5c998981e6f66867bf55d459ad89`
- Final real-host rehearsal artifact source: `29e65078afba5c998981e6f66867bf55d459ad89`
- Draft PR: <https://github.com/ForceMind/agentbox/pull/31>
- Commits: seventeen scoped build, test, CI, documentation, release-version,
  CI portability, report, dependency-security, and final integrity commits
  before this evidence update

## Candidate Version

- Python / PEP 440: `0.3.0rc1`
- Planned display/tag: `v0.3.0-rc.1`
- Status: pre-release MVP Release Candidate
- Tag created: no
- GitHub Release created: no

## Artifact Provenance Evidence

### Local reproducibility artifact

- Source commit: `29e65078afba5c998981e6f66867bf55d459ad89`
- Source ref kind: `other` (clean local branch-head build)
- SHA-256: `82fda14bdbf81d8fccc0f16881f63ea842e17e634a15a226771ce666ea582149`
- Size: 20,812,329 bytes
- Purpose: two independent same-environment builds, manifest/inventory/nested
  wheel scans, and bundled-installer artifact-only smoke

### Real-host rehearsal artifact

- Source commit: `29e65078afba5c998981e6f66867bf55d459ad89`
- Source ref kind: `pull_request_head`
- SHA-256: `1e57d0169b3176f2b6b808a345356fb072e298e96fe00904973e688e41e7d667`
- Size: 20,812,312 bytes
- Purpose: AgentBox-only OpenCloudOS update/health/identity/rollback rehearsal

### Current PR CI artifact

- PR head at build: `29e65078afba5c998981e6f66867bf55d459ad89`
- Actual checkout/source commit: `29e65078afba5c998981e6f66867bf55d459ad89`
- Source ref kind: `pull_request_head`
- SHA-256: `1e57d0169b3176f2b6b808a345356fb072e298e96fe00904973e688e41e7d667`
- Size: 20,812,312 bytes
- Workflow evidence: Release Candidate run `31727404716`, including successful
  `release-candidate` and `release-gate`

This committed report cannot permanently contain the hash of an artifact that
also contains this exact report commit without changing that artifact. The CI
job summary/artifact remains the authoritative per-head hash. A report-only
successor head must receive fresh CI and is not silently attributed to the
evidence above.

### Future tag artifact

- Status: **NOT BUILT**
- SHA-256: unknown
- Requirement: rebuild from the separately reviewed tag commit after merge and
  explicit tag authorization; no PR artifact hash is promised to match it

## Version Consistency

`packages/agentbox-core/src/agentbox_core/version.py` is the single source.
Python packaging resolves it dynamically. Root and Web npm metadata use the
tested npm spelling `0.3.0-rc.1`. The CLI, API meta endpoint, installer, manifest,
artifact name, release notes, and safe Web meta display resolve from this source
or the generated artifact contract. Local version consistency and CLI version
checks passed.

## Artifact Files

| File | Size | SHA-256 |
|---|---:|---|
| `agentbox-0.3.0rc1-linux-x86_64.tar.gz` | 20,812,312 bytes | `1e57d0169b3176f2b6b808a345356fb072e298e96fe00904973e688e41e7d667` |
| `RELEASE_MANIFEST.json` | CI artifact member | verified by `SHA256SUMS` and internal/external identity |
| `SBOM.spdx.json` | CI artifact member | verified by `SHA256SUMS` and internal/external identity |
| `SHA256SUMS` | 273 bytes | independently verified in run `31727404716` |

## Artifact Layout

The 69-member archive contains only the VERSION and manifest, Apache-2.0
license and notices, SPDX SBOM, release bootstrap, the AgentBox wheel and locked
Linux x86_64 wheelhouse, Alembic migrations/config, production Web static files,
and selected release documentation. The production Web contains no source map.
The artifact excludes Git data, environment/config/secret files, databases,
projects, Runtime credentials/state, node_modules, development venvs, caches,
Playwright output, and user files. Only `install.sh` is executable.

## Release Manifest

Schema 3 records candidate version, actual source commit and ref kind, target
platform/architecture, RC build mode, artifact-specific Python range
`>=3.11,<3.14`, supported ABIs cp311/cp312/cp313, locked pip/setuptools/wheel/
Node/pnpm toolchain, qualified platform claims, migration head, authenticity
status, public metadata filenames, exact file/executable allowlists, and
per-file SHA-256. The verifier rejects missing, unknown, broadened, or
inconsistent compatibility/provenance metadata and checks the observed
wheelhouse ABI inventory.

## Reproducibility

Two builds from separate empty staging directories, the same clean commit,
dependency locks, and `SOURCE_DATE_EPOCH` produced byte-identical public output.
Both final local tarballs have SHA-256
`82fda14bdbf81d8fccc0f16881f63ea842e17e634a15a226771ce666ea582149`.
Ordering, timestamps, uid/gid, user/group names, file modes, JSON ordering, and
gzip metadata are normalized. The first rehearsal exposed and fixed an
out-of-tree wheel-staging defect before this passing run.

- Same-environment exact reproducibility: pass
- Cross-runner byte reproducibility: not qualified

## Checksums

External `SHA256SUMS` covers the tarball, manifest, and SBOM with basename-only
entries. Independent verification passed. Internal per-file checks are bound by
the externally checked manifest. These checks establish integrity only.

## SBOM

The generated SPDX 2.3 JSON has 33 unique packages: AgentBox, 24 Python runtime
dependencies, and 8 frontend production dependencies. It includes versions,
package-manager references, declared/concluded license identifiers, and source
or home references where published. It contains no environment, host package
inventory, credential, or user path.

## Third-party Licenses

The builder and CI cross-check `requirements-release.lock`, the actual
wheelhouse, reviewed frontend production inventory, SPDX package entries, and
`THIRD_PARTY_NOTICES.md`; 32 third-party package identities/versions/licenses
matched. Observed licenses
are Apache-2.0, MIT, MIT-0, ISC, BSD-3-Clause, PSF-2.0, and the declared
`MIT AND PSF-2.0` expression. No GPL/AGPL or unknown runtime license was accepted
by the build. This is an engineering inventory, not legal advice; publication
still requires human license review.

## Offline / Online Install Dependency

Offline install is **partial**. After the artifact and required system packages
exist, its embedded hash-locked wheelhouse supports AgentBox on CPython
3.11-3.13 Linux x86_64 without PyPI, and production Web needs no Node/Vite.
Bootstrap package-manager prerequisites may still need configured distro
repositories. Claude/Node, Codex, and `gh` remain optional Runtime dependencies;
their absence does not block the control plane.

## Release Workflow

`.github/workflows/release-candidate.yml` is read-only, uses immutable audited
Action SHAs, persists no checkout credential, consumes no secret, and cannot
tag, publish, or write to a registry. Pull requests explicitly checkout
`github.event.pull_request.head.sha`; pushes build `github.sha`. CI asserts the
checkout and manifest commit/ref-kind before upload. The workflow installs a
73-package exact/hash-locked Python build/test environment rather than upgrading
to latest pip/wheel or resolving `.[dev]`, verifies fixed Node `22.23.2` and
pnpm `11.20.0`, builds twice, compares public output, validates
manifest/checksums/SBOM/licenses/archive/secrets, runs artifact-only install and
recovery smoke, and uploads a seven-day artifact.

## release-gate

`release-gate` depends on the complete `release-candidate` job and uses
`always()` plus an exact `success` result check, so failure, cancellation, or
skip cannot report success. It performs no duplicate build. Local equivalent
steps passed and the real GitHub check context `release-gate` completed
successfully on source commit `29e65078afba5c998981e6f66867bf55d459ad89`.

## Validation and CI

- Backend: Ruff, Black, mypy, migration upgrade/downgrade/upgrade and 541 pytest
  tests passed locally;
  all Python 3.11/3.12/3.13 GitHub quality jobs passed.
- Frontend: lint, format, typecheck, 25 unit tests, production build, and
  high-severity audit passed locally and on GitHub.
- E2E: 54 Playwright tests passed on GitHub.
- Deployment: 153 selected local tests passed; all four Ubuntu/Python installer
  matrix jobs and `deployment-gate` passed on GitHub.
- Security: repository boundaries, Action pins, secret scan, dependency review,
  Python audit, and frontend audit passed.
- Release: locked toolchain, version/docs/license drift, double build,
  reproducibility, manifest, checksums, SBOM, tar/nested-wheel secret scan,
  actual `install.sh` smoke, upload, and
  `release-gate` passed on GitHub.
- Protect main remained unchanged with its existing ten required checks, all of
  which passed on `29e65078afba5c998981e6f66867bf55d459ad89`.

The final report-triggered audit detected newly published High advisory
`GHSA-2v37-7h3g-55p8` in the Vite/PostCSS development chain. The transitive
`nanoid` build dependency is now explicitly pinned from vulnerable `3.3.17` to
patched `3.3.18`; frozen install, `pnpm why`, audit, lint, format, typecheck,
25 tests, production build, and frontend-license drift check pass locally. This
dependency is not part of the shipped production runtime SBOM.

## Installer Smoke

The exact extracted `install.sh` passed `bash -n`, ran public artifact
verification, created a private bootstrap venv, installed with `PIP_NO_INDEX=1`
and artifact wheelhouse only, forwarded fixture plan/apply/uninstall arguments,
and cleaned its temporary directory on venv/pip failures. Negative coverage
rejects missing VERSION/wheelhouse, Python 3.10/3.14, test override misuse, and
bootstrap failures. A second manually created venv still validates Python entry
points, production static Web, migration, loopback health/readiness/meta, and
data-preserving uninstall without Node or source-installed AgentBox.

## Fixture Fresh Install

Fixture fresh install passed. Three consecutive applies preserved the
application secret, config, database/admin-like data, projects, Runtime HOME,
and stable users/service records. Uninstall removed program activation while
preserving database, projects, and Runtime credentials/Home. This is fixture
evidence, not a clean-host real installation claim.

## Upgrade Dress Rehearsal

Phase 8/9 lifecycle tests cover staged activation, online SQLite backup, partial
migration failure, interrupted staged/migrated/activated recovery states,
service/readiness/version/migration gates, and forward recovery. Phase 10 added
PEP 440 RC comparison and retention support after artifact-only smoke exposed
the old parser limitation. Fixture upgrade coverage passed. The final real-host
run used the PR-head CI artifact, updated from `0.2.10+dev.9` to `0.3.0rc1`,
created verified backup `20260813T175038.550897Z`, and completed version,
health, readiness, identity, socket, and loopback verification.

An initial post-integrity rehearsal attempt exposed a real bootstrap defect:
the private bootstrap `umask 077` was inherited by production Installer venv
creation, preventing the non-root `agentbox` identity from executing Alembic.
The transaction automatically reported `upgrade failed; rollback verified` and
restored the stable release. Commit `29e65078afba5c998981e6f66867bf55d459ad89`
restores managed `umask 022` immediately before invoking `agentbox-install`,
retains a private bootstrap venv, adds deterministic forwarding/umask tests, and
passed the subsequent real-host update and rollback.

## Rollback Dress Rehearsal

Fixture rollback restores only receipt-pinned release and DB snapshot state and
verifies services, sockets, health/readiness, version, DB integrity, and
migration identity. False-positive cases for missing/corrupt release or backup,
service/helper/socket failures, wrong version, health/readiness failure, and DB
integrity failure remain covered. Fixture rollback passed. Real-host rollback
from `0.3.0rc1` to `0.2.10+dev.9` reported `health_verified=true`; final API,
readiness, version, migration, SQLite integrity, sockets, listener, services and
Doctor checks passed.

## Real-host Dress Rehearsal

Passed using CI artifact SHA-256
`1e57d0169b3176f2b6b808a345356fb072e298e96fe00904973e688e41e7d667`
after Backend, Frontend, Security, E2E, Deployment, `deployment-gate`, and
`release-gate` were green on the Draft PR. The AgentBox-only cycle was:

1. recorded stable release `0.2.10+dev.9`, process identities, listener,
   config/application-secret hashes, Runtime/root-Runtime metadata and services;
2. planned and verified the exact candidate artifact and digest;
3. created a consistent online SQLite backup and activated `0.3.0rc1`;
4. verified production API version, health/readiness, Doctor, service users,
   socket modes, loopback listener, config/secret hashes and resource use;
5. rolled back through the candidate lifecycle to `0.2.10+dev.9`;
6. verified the final stable version, logical DB equality with the backup,
   integrity/migration head, health/readiness, Doctor, service identities,
   sockets, listener, project count, Runtime HOME count, root Runtime metadata,
   config and application-secret hashes.

The existing root Codex/Claude PIDs, root tmux session, and credential-directory
metadata were unchanged. SSH, firewall, cloudflared, reverse proxies, projects,
Runtime credentials and root Runtime state were not mutated. This was a
real-host update/rollback rehearsal, not a real-host fresh install.

## Final Host State

**PRE-REHEARSAL STABLE RELEASE**: `0.2.10+dev.9`, healthy and ready on
`127.0.0.1:8787`. The final candidate payload was removed after verified
rollback; the pre-existing inactive earlier rehearsal release was restored to
its original path. The final PR-head candidate is not the active production
target.

## Platform Matrix

| Platform | Qualification |
|---|---|
| OpenCloudOS 9 x86_64 | Real-host validated; RC update/rollback rehearsal passed |
| Ubuntu 24.04 x86_64 | CI validated; not a real PID 1 host claim |
| Ubuntu 22.04 stock x86_64 | Unsupported: Python 3.10 is below requirement |
| Rocky Linux 9 x86_64 | Fixture validated |
| Debian 12 x86_64 | Fixture validated |
| aarch64 | Unsupported / unqualified |

## Resource Baseline

The control-plane DB was 172,032 bytes, final rehearsed CI artifact 20,812,312
bytes, and production static assets 326,056 bytes. Earlier RC evidence recorded
idle process RSS and a complete lifecycle transaction within the available
2-vCPU/3.5-GiB host envelope. This is a single operational observation on the
2-vCPU/3.5-GiB OpenCloudOS host, not benchmark certification.

## Secret Scan

Repository secret-pattern checks and the public bundle scan passed. Tar member
names and regular bytes plus 2,079 nested wheel member names and bounded,
decompressed regular bytes were checked in memory for application/session/CSRF/
Codex Pair/Claude output/GitHub/Git/Provider/SSH canaries. Wheel count,
per-member size, aggregate expanded size, duplicate/colliding path, malformed
ZIP, encrypted member, and unexpected file-type failures are fail closed. No
source maps or canaries were present. This claim is deliberately limited to tar
members and nested wheel contents; it does not claim arbitrary recursive
decompression of every possible file format.

## Release Notes / Changelog

`docs/releases/0.3.0rc1.md` accurately describes included MVP capabilities,
excluded Phase 11/future features, exact platform qualifications, manual Runtime
authentication, update/rollback, security notes, and known limits. CHANGELOG
groups meaningful Added/Changed/Security/Fixed/limitations evidence, including
the password-rotation/login race fix, persistent login limiter, Helper boundary,
Git safety, ephemeral Pair Code, and diagnostics sanitation.

## Documentation

README, Quickstart, Installation, Deployment, Upgrade, Rollback, Uninstall,
Platform Support, Known Limitations, Release Checklist, MVP Acceptance,
Architecture, Security, Threat Model, Test Strategy, CLI design, product/scope,
development plan, release notes, and security review are aligned. Automated
relative-link and local-anchor checks passed for 76 documentation links.

## MVP Acceptance

`docs/MVP_ACCEPTANCE.md` separates automated PASS, required MANUAL operations,
and unsupported boundaries for login/dashboard, Codex Pair, Claude/tmux,
projects, Git/GitHub Draft PR, Doctor, install/update/rollback, non-root process
identity, loopback binding, and excluded features. Manual real Runtime login and
end-user workflow remain operator acceptance items.

## Security Review

The release boundary fails closed on a dirty checkout; provenance/ref mismatch;
overbroad Python/ABI or unlocked build-toolchain metadata; archive traversal,
non-canonical/duplicate/case-fold-colliding names, links and special files;
undeclared content; unsafe modes; digest, schema, version, platform, migration,
or SBOM mismatch; unknown/GPL/AGPL license; artifact size over 100 MiB; source
maps; or embedded tar/nested-wheel canaries. The workflow is read-only and
action-pinned. This is not a penetration test or a general production-readiness
claim.

## Unsigned Artifact Risk

Artifact signature and publisher authenticity are unavailable. SHA-256 detects
change relative to a separately trusted checksum but does not establish who
published either object. Signing key/provenance governance is deferred for
separate human approval and is not implemented by Provider/Secret management.

## Known Limitations

Only OpenCloudOS has real-host installation and RC update/rollback evidence.
Ubuntu 24 is CI-only, Rocky/Debian fixture-only, Ubuntu 22
stock and aarch64 unsupported. TLS/remote access and explicit trusted-proxy
configuration remain operator responsibilities. Artifacts are unsigned;
cross-runner reproducibility, reboot recovery, automatic project backup, public
network automation, Provider Manager, Secret Manager, and multi-host/SaaS are
not supported. Runtime retains documented compatibility allowances for its
third-party tools.

## Remaining Manual Release Steps

1. Complete review and merge the Phase 10 PR.
2. Build again from the reviewed merged `main` commit.
3. Select and review the exact `v0.3.0-rc.1` tag target.
4. Create the reviewed tag only after human authorization.
5. Build and independently verify final artifacts from that tag.
6. Recheck SHA256SUMS, manifest, SBOM, licenses, and release notes.
7. Create a Draft GitHub Release marked pre-release.
8. Attach the verified artifacts and review rendered release notes.
9. Publish the pre-release only after a final human release decision.
10. Separately decide whether `release-gate` should become the eleventh required check.

## Phase 11 Status

**NOT STARTED.** Provider Manager, Provider Secret Manager, RuntimeBindingID,
Provider switching/failover, and continuity implementation remain out of scope.
