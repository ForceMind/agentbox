# AgentBox MVP Release Candidate Quickstart

These commands apply to the `0.3.0rc1` pre-release artifact baseline. Source has
advanced to the unqualified `0.3.0rc3` development candidate; do not substitute
that newer version into these commands without a reviewed artifact and new host
qualification. OpenCloudOS 9 is the only real-host validated baseline platform;
review [Platform Support](PLATFORM_SUPPORT.md) before installing.

## 1. Download and verify

Download these files from the same reviewed candidate build:

```text
agentbox-0.3.0rc1-linux-x86_64.tar.gz
RELEASE_MANIFEST.json
SBOM.spdx.json
SHA256SUMS
```

Verify the independently distributed hashes before extraction:

```bash
sha256sum --check SHA256SUMS
```

SHA-256 establishes byte integrity only. This candidate is not signed and its
publisher authenticity is not cryptographically verified.

Extract into a new staging directory, then ask the bundled installer to repeat
the manifest, allowlist, per-file digest, archive, platform, version, SBOM, and
migration checks:

```bash
mkdir agentbox-0.3.0rc1
tar -xzf agentbox-0.3.0rc1-linux-x86_64.tar.gz -C agentbox-0.3.0rc1
./agentbox-0.3.0rc1/install.sh verify-artifact \
  --artifact ./agentbox-0.3.0rc1-linux-x86_64.tar.gz \
  --checksums ./SHA256SUMS \
  --manifest ./RELEASE_MANIFEST.json \
  --sbom ./SBOM.spdx.json
```

## 2. Review and install

The artifact contains the complete CPython 3.11/3.12/3.13 Linux x86_64
wheelhouse and prebuilt Web assets. Its bootstrap rejects Python 3.10, Python
3.14+, non-Linux systems, and non-x86_64 hosts before installation. It imports
the artifact's hash-locked `pip 26.2.1` wheel directly and installs the temporary
Installer into a root-private target directory with `--no-index`; host
`python3-venv`, `ensurepip`, global pip, PyPI, and a source checkout are not
bootstrap prerequisites. The inner Installer can then provision the typed
production venv package when needed. This artifact-specific boundary is
narrower than the source package's open-ended `>=3.11` metadata. The AgentBox
control plane does not need Node, npm, pnpm, or Vite at runtime. Run the
read-only plan first:

```bash
sudo ./agentbox-0.3.0rc1/install.sh plan \
  --artifact ./agentbox-0.3.0rc1-linux-x86_64.tar.gz \
  --sha256 "$(sha256sum agentbox-0.3.0rc1-linux-x86_64.tar.gz | cut -d' ' -f1)"
```

After reviewing every listed user, group, path, package, unit, and service:

```bash
sudo ./agentbox-0.3.0rc1/install.sh apply \
  --artifact ./agentbox-0.3.0rc1-linux-x86_64.tar.gz \
  --sha256 "$(sha256sum agentbox-0.3.0rc1-linux-x86_64.tar.gz | cut -d' ' -f1)"
```

The installer never creates a default administrator or password.

## 3. Initialize the administrator

Run the local TTY bootstrap without printing the password:

```bash
sudo -u agentbox /opt/agentbox/current/venv/bin/agentbox admin init
```

## 4. Configure secure remote access

AgentBox listens only on `127.0.0.1:8787`. Authenticated production browser use
is expected to follow this model:

```text
Browser -> HTTPS -> explicit trusted reverse proxy/tunnel -> loopback AgentBox HTTP
```

Use an operator-managed Tailscale connection, Cloudflare Tunnel, VPN, or HTTPS
reverse proxy. Keep Secure Cookies enabled and configure exact trusted proxies
and HTTPS origins. AgentBox does not modify SSH, firewall rules, cloudflared,
nginx, or cloud security groups. Do not publish bare HTTP or bind AgentBox to
`0.0.0.0`.

## 5. Authenticate Runtime tools independently

Complete each official login flow as `agentbox-runtime`:

```text
Codex login or Remote Pair setup
Claude Code login
gh auth login
```

Do not copy or chown `/root/.codex`, `/root/.claude`, or `/root/.config/gh`.
Claude, Codex, or gh may honestly remain `Not installed`, `Unauthenticated`, or
`Unknown`; missing optional Runtime tools do not prevent the core AgentBox
control plane from becoming Ready.

## 6. Verify

```bash
/opt/agentbox/current/venv/bin/agentbox status
/opt/agentbox/current/venv/bin/agentbox doctor
curl --fail http://127.0.0.1:8787/healthz
curl --fail http://127.0.0.1:8787/readyz
```

Open the operator-managed HTTPS URL only after the proxy/origin policy is
configured. See [Installation](INSTALLATION.md), [Upgrade](UPGRADE.md),
[Rollback](ROLLBACK.md), and [Known Limitations](KNOWN_LIMITATIONS.md).
