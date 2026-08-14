# AgentBox Installation

Status: Phase 10 MVP Release Candidate runbook

## Safety boundary

The installer owns only AgentBox users, groups, FHS paths, release files, unit
files, configuration, and database state listed by `agentbox-install plan`.
It does not modify SSH, firewall rules, cloud security groups, cloudflared,
reverse proxies, Docker, existing root Runtime installations, root tmux
sessions, `/root/projects`, or Provider/Secret configuration.

Never install an unverified network stream directly into a shell on a shared
host. Download the tarball, `RELEASE_MANIFEST.json`, `SBOM.spdx.json`, and
`SHA256SUMS`; verify the published hashes and bundled artifact contract, inspect
the plan, and then apply it:

```bash
sha256sum --check SHA256SUMS
mkdir agentbox-release
tar -xzf agentbox-<version>-linux-x86_64.tar.gz -C agentbox-release
./agentbox-release/install.sh verify-artifact \
  --artifact ./agentbox-<version>-linux-x86_64.tar.gz \
  --checksums ./SHA256SUMS \
  --manifest ./RELEASE_MANIFEST.json \
  --sbom ./SBOM.spdx.json
sudo ./agentbox-release/install.sh plan \
  --artifact ./agentbox-<version>-linux-x86_64.tar.gz \
  --sha256 <expected-sha256>
sudo ./agentbox-release/install.sh apply \
  --artifact ./agentbox-<version>-linux-x86_64.tar.gz \
  --sha256 <expected-sha256>
```

The RC has no production download URL and uses checksums rather than signed
artifacts. Checksums provide integrity only when acquired independently; they
do not authenticate the publisher. A future `curl | bash` convenience form is
not the recommended verification path.

## Preflight

`plan` is read-only. It parses `/etc/os-release`, checks architecture and
systemd, tests only `127.0.0.1:8787`, detects exact dependencies, classifies an
existing installation, verifies the release archive and checksum, and prints
all planned users, groups, directories, files, units, packages, services, and
network effects. It does not use `uname` to guess a distribution.

Apply requires effective UID 0. The ordinary `agentbox` CLI remains non-root;
only lifecycle mutations require an administrator to invoke the installer.
Port conflicts fail closed and the installer never kills the owner or silently
changes the product default.

The `0.3.0rc1` bundle is qualified only for Linux x86_64 with CPython 3.11,
3.12, or 3.13. The bundled `install.sh` checks this contract before bootstrap
and reports an explicit error for Python 3.10 or 3.14. It verifies and imports
the artifact's exact/hash-locked `pip 25.3` wheel directly, then installs the
temporary Installer with `--target`, `--no-index`, and the artifact wheelhouse.
It does not require host `python3-venv`, `ensurepip`, global pip, PyPI, or a
source checkout. After platform/package preflight, the inner Installer may
install the typed venv package needed by the permanent release-local venv.

Service-account names are not adopted merely because they exist. On a fresh
host, any pre-existing `agentbox`, `agentbox-runtime`, or associated group name
is a collision. On reinstall/update, reuse requires root-owned receipt evidence
whose UID/GID values match the fixed primary groups, homes, and nologin shells;
partial or mismatched identity sets fail before user/group mutation or chown.

## Transaction

The apply path takes a global non-blocking lifecycle lock and then:

1. installs a fixed platform package set when required;
2. creates fixed system identities and exact FHS directories;
3. preserves or creates restrictive configuration and a CSPRNG application secret;
4. verifies and stages an immutable versioned release and release-local venv;
5. stops AgentBox services only for an upgrade;
6. creates an online SQLite/config/unit backup;
7. runs `alembic upgrade head` explicitly as `agentbox`;
8. installs exact unit files and atomically switches `/opt/agentbox/current`;
9. reloads, enables, and starts exact AgentBox units;
10. verifies health, readiness, and release metadata before committing a receipt.

The root-only transaction journal includes a random transaction ID and the
expected path, type, existed-before state, owner/mode/device/inode identity,
and (where created) post-mutation identity. Fresh-install rollback removes only
an unchanged database/current object proven to belong to that transaction.

Installer logs and receipts never contain the application secret, Runtime
credentials, passwords, Pair Codes, Provider keys, or arbitrary request data.

## Idempotency and partial failure

Reinstalling the same exact artifact verifies it and leaves the secret,
configuration, database, administrator records, Runtime HOME, and projects
unchanged. A different artifact with the same version is rejected. Older
versions require the rollback flow; in-place overwrite is unavailable.

An interrupted first install may retain clearly AgentBox-owned identities,
directories, configuration, staged releases, units, and a secret-free journal
so a later inspection classifies `staged`, `partially_migrated`, `activated`,
`rollback_pending`, or `unknown`. Re-entry fails closed instead of replaying
mutation. It never removes unknown
files while guessing. Upgrade failures attempt restoration and report either
`rollback verified` or `rollback attempted but verification failed`.

## Authentication after install

No default administrator or password is created. Initialize the production
administrator locally without printing the password:

```bash
sudo -u agentbox /opt/agentbox/current/venv/bin/agentbox admin init
```

The Runtime user authenticates independently with public Codex, Claude, and
GitHub CLI flows. Do not copy or `chown` `/root/.codex`, `/root/.claude`, or
`/root/.config/gh`.

## Verification

### Phase 9 verification addition

Phase 9 validates generated unit directives against the installed systemd
version before any privileged write. Missing optional Runtime dependencies
degrade only their integration and do not invalidate the prebuilt API/Web core.
Ubuntu 22.04 native installation remains rejected until a trusted Python 3.11–3.13
strategy exists; CI-provided Python is test evidence, not an installer source.

Use `agentbox status`, `agentbox doctor`, `systemctl status` for the exact units,
and loopback-only `/healthz` and `/readyz`. See [Deployment](DEPLOYMENT.md),
[Upgrade](UPGRADE.md), and [Platform Support](PLATFORM_SUPPORT.md).
