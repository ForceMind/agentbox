# AgentBox MVP Security Review

Status: Phase 9 internal architecture/code/operations review. This is not a
penetration test, certification, stable-release guarantee, or multi-host audit.

## Scope and assets

The review covers the single-server/single-administrator Web/API, Worker,
SQLite/WAL, Runtime Executor, Privileged Helper, Unix sockets, systemd units,
installer/update/rollback, Project metadata boundaries, CLI, diagnostics, and
GitHub Actions supply chain. Protected assets include the application secret,
administrator password hash and Sessions, Runtime credentials, Project source,
Pair Codes, Claude output, Git/gh credentials, release/backup identity, and
root authority.

Provider/Secret management, Provider switching, public ingress automation,
SSH/firewall/tunnel management, browser terminal, multi-user/multi-server, and
SaaS are outside scope and remain unimplemented.

## Trust boundaries

1. Browser/CLI to loopback API with exact Host/Origin, Secure Cookie, CSRF, and
   explicit trusted-proxy policy.
2. API/Worker (`agentbox`) to Runtime (`agentbox-runtime`) through typed,
   bounded, UID/GID-authenticated UDS requests.
3. `agentbox` to the socket-activated root Helper through six fixed,
   argument-free AgentBox lifecycle actions.
4. Root installer to root-owned configuration, releases, units, receipts,
   journals, and verified backups.
5. Runtime to third-party public CLI contracts and user-owned Runtime HOME/
   Project Workspaces.

## Controls reviewed

- Non-root API, Worker, and Runtime identities; Runtime/app credential and
  filesystem separation; empty service capability sets.
- Strict systemd filesystem/kernel/device/network boundaries with service-local
  syscall filtering and documented Runtime compatibility exceptions.
- Argon2id, bounded password concurrency, persistent pseudonymous login
  throttling, idle/absolute Session TTLs, CSRF, no-store responses, local
  TTY-only password/session recovery, and revoke-all behavior.
- Strict API mutation models; bounded request/output/body fields; no arbitrary
  executable, argv, cwd, env, path, PID, signal, unit, or package surfaces.
- UDS frame caps, duplicate/deep/malformed/concatenated rejection, protocol
  versioning, fixed actions, bounded correlation IDs, timeouts, and peer UID/GID.
- Online WAL backup/integrity verification, staged release activation,
  transaction identity journal, explicit partial-state classification, and
  rollback verification.
- Secret/credential/Pair/Claude output canaries, Bearer and credential-URL
  redaction, metadata-only Audit/Jobs, and guarded diagnostics export.
- Immutable GitHub Action commits, dependency audits, archive limits, checksum
  verification, and fixture/real-host claim separation.

## Residual risks and unsupported configurations

- Runtime requires HOME, outbound network, namespace compatibility, and
  executable memory for current third-party tools; it is less sandboxed than
  API/Worker/Helper.
- The unit sandbox is not a chroot/VM. `PrivateUsers` is not enabled.
- SHA-256 detects accidental/tampered bytes only when the expected digest is
  independently trusted. `0.3.0rc1` remains explicitly unsigned; signing key
  governance and publisher authenticity require a later reviewed decision.
- OpenCloudOS 9 x86_64 is the only designated real-host validation. Ubuntu
  24.04 is CI validated, Rocky 9/Debian 12 are fixture validated, Ubuntu 22.04
  native install is rejected, and aarch64 is unqualified.
- TLS termination, reverse-proxy allowlisting, firewall, SSH, tunnels, host
  backup, monitoring, and Project-source backup are operator responsibilities.
- SQLite fits the bounded single-host MVP but is not a distributed database.
- Diagnostics pattern scanning cannot prove arbitrary text is non-sensitive;
  operators must review reports before sharing.

## Manual operational requirements

- Keep the API on loopback behind operator-managed HTTPS; configure only exact
  trusted proxies/origins and do not disable Secure Cookies.
- Authenticate Codex, Claude, and gh independently as `agentbox-runtime`; never
  copy root credentials or adopt root sessions automatically.
- Protect `/etc/agentbox`, `/var/lib/agentbox/backups`, Runtime HOME, and
  external backup copies. Monitor disk space and journald.
- Review every install/update plan and backup identity; do not bypass a partial
  transaction or failed rollback-verification state.
- Revalidate current public Runtime installation/config/help contracts before
  changing third-party installation policy.

## Security reporting

Use GitHub's private security-advisory reporting channel for the repository when
available. Do not publish credentials, Pair Codes, private host evidence, or an
unpatched exploit in a public Issue. If private reporting is unavailable,
contact the repository maintainer through a private channel and provide only
the minimum reproducible, redacted evidence.

## Phase 10 release-artifact boundary

The RC builder requires a clean tracked commit, a hash-locked 73-package Python
build/test toolchain, exact Python runtime release lock, fixed Node/pnpm,
frozen pnpm lock, fixed `SOURCE_DATE_EPOCH`, deterministic Web/wheel/tar/gzip
inputs, and two independent same-runner builds with identical output. PR jobs
explicitly build the PR head rather than GitHub's synthetic merge ref. The
manifest records the actual source commit and ref kind, build toolchain,
version, platform, migration head, allowlist, per-file digests,
`>=3.11,<3.14`/cp311-cp313 artifact compatibility, SBOM/license files, and
unsigned status. A separate exact/hash-locked `pip 26.2.1` bootstrap wheel is
bound into the manifest, file inventory, SBOM, notices, and nested scan.

Release finalization also pins `wheel 0.46.2` and verifies the universal pip and
wheel artifacts on CPython 3.11, 3.12, and 3.13. The Release Candidate job runs
`pip-audit` against the exact build environment, and `release-gate` fails closed
unless both this packaging matrix and the complete build/verification job pass.

Verification checks external `SHA256SUMS`, external/internal manifest and SBOM
identity, schema, version/wheel/API consistency, complete file allowlist,
digests, target platform, migration metadata, path normalization, duplicate
paths, archive links/types/modes/limits, required static files, and secret
canaries. Secret scanning covers tar members and bounded, in-memory nested wheel
member names and decompressed bytes; malformed, duplicate, unsafe, or oversized
wheels fail closed. The artifact carries a CPython 3.11–3.13 Linux x86_64 wheelhouse and
prebuilt Web files; Node/Vite are absent from the production control-plane
runtime requirement.

CI executes the exact bundled `install.sh`: shell syntax, public bundle
verification, offline wheelhouse-only bootstrap, fixture plan/apply, cleanup,
and data-preserving uninstall. The root-private bootstrap imports pip directly
from its verified wheel and installs to a temporary target, so it needs no host
venv module, ensurepip, global pip, network index, or source checkout. CI runs
this path under a Python wrapper that rejects those host facilities and covers
Ubuntu 24.04/Debian 12 no-venv fixtures. A manually recreated venv remains a
second-layer runtime smoke, not a substitute for the bootstrap test.

The PR Release Candidate workflow has read-only permissions, immutable Action
pins, no Secrets, no publishing permission, one bounded CI artifact, and a
fail-closed aggregate `release-gate`. Artifact checks do not prove publisher
authenticity, legal compliance, penetration-test coverage, cross-runner
reproducibility, clean-host real-system installation, or host reboot recovery.
