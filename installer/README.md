# AgentBox Installer

Phase 8 implements a typed, platform-aware native installer. The Bash entry is
only a root/bootstrap gate; Python owns detection, planning, artifact safety,
identities, FHS layout, migrations, systemd, backup, update, rollback, and
data-preserving uninstall.

`setup-fresh-waw` is now the composed fresh-install candidate in PR #136.
It accepts the verified release artifact/checksum plus Origin/ACME contact and
runs the already-qualified phases in a fixed order: deferred install, fixed
browser dependencies, fixed vendors, manifests, policies, qualified enrollment,
then the existing HTTPS setup. A staged interruption needs explicit
`--recover`; a same-version continuation is admitted only with exact artifact
and committed deferred-install evidence. If WAW activation already began, the
recovery path skips offline phases and resumes the existing Web setup instead of
replaying policy/vendor work.

This is a software composition candidate, not yet a published one-command
release. Real public-host fresh install, ACME/HTTPS, authenticated Claude/Codex,
physical clients, reboot, upgrade and rollback still require qualification.

The first browser deployment is still under qualification. After fixed WAW
enrollment/publication, `configure-waw-web --origin https://host.example --plan`
checks the current Root-owned overlay and `/etc/agentbox-web/tls/fullchain.pem`
(Root 0644) plus `privkey.pem` (Root 0600), then plans only the exact browser
Origin and loopback trusted proxy. Applying configuration requires WAW services
to be offline; it starts no service. Run fixed WAW activation before
`activate-waw-web --origin https://host.example`. Web activation restarts only
the separate HTTPS service and requires an already configured Origin.

These internal commands are not yet the promised self-install command:
the final installer/dependency sequence and qualification remain open.
PEM/hostname checks and service-manager status do not prove public CA trust,
actual browser/CLI use or reboot/upgrade/rollback qualification.

`provision-waw-web-certificate --origin https://host.example --email owner@example.com
--plan` plans fixed standalone ACME issuance without network or writes. Apply
requires `--agree-acme-terms`, distro `/usr/bin/certbot` and available/inbound
port 80; it never stops another listener. The CA/account/archive use only the
private AgentBox namespace. A matching interrupted TLS pair needs `--recover`;
another operator's certificate or certificate store is not adopted.

`maintain-waw-web --recover` is the fixed daily maintenance action. It refreshes
the public bootstrap before expiry and, for explicitly configured ACME, renews
near-expiry certificates. Only changed TLS triggers an HTTPS restart; Runtime
continues. Operator-managed TLS remains operator-managed. A refreshed bootstrap
invalidates old browser leases and may require reloading the page; it does not
stop the server CLI. Public CA/DNS/firewall validation still belongs to the
operator's real installation.

`setup-waw-web --origin https://host.example --email owner@example.com --plan`
composes the browser entry for an already installed, fully enrolled WAW host.
Applying needs `--agree-acme-terms`; matching recovery adds `--recover`.
It checks prerequisites before requesting a certificate, then publishes the
page, commits Origin, activates WAW if necessary and starts HTTPS. A previously
started WAW graph keeps its Runtime process. This still requires prior vendor/
manifest enrollment and fixed dependencies; it is not the final download/install
entry and does not claim real browser/CLI qualification.

`install-waw-vendors --plan` describes the fixed native Claude/Codex download
set without network or writes. Apply requires a completed installation and
offline/idle WAW evidence, installs only verified Root-owned native executables,
and never executes an upstream install script or logs in. Foreign/distro
installations require explicit enrollment; they are not replaced. Recover only
matching interrupted publication with `--recover`. Version pins update with a
reviewed AgentBox batch, not automatically from an upstream latest endpoint.

`enroll-qualified-waw-vendors --plan` validates the current fixed
AgentBox-owned Claude/Codex release without executing either CLI. Apply publishes
only the release-qualified normalized versions and Codex unauthenticated digest,
after the verified v2 executable inventory and a fresh executable re-read both
match the qualified final ELF SHA-256 values. `--recover` resumes only the
same matching publication. The Runtime later verifies actual login state through
the native auth helper; installer enrollment never reads credentials or starts a
Provider process.

Fresh browser setup can use `apply --artifact ... --sha256 ... --defer-activation`
to install the verified release, database and disabled profiles without starting
the legacy services. The result explicitly reports health_verified=false. A
staged retry must retain `resume-install ... --defer-activation`; changing this
mode rejects. This option is fresh-install only and does not disable an existing
installation. It provides the offline stage for vendor/enrollment/setup; the
final download entry still needs that complete sequence.

`install-waw-dependencies --plan` reports missing fixed browser dependencies
(tmux, bubblewrap, nginx, certbot) for APT/systemd >=255 targets. Apply requires
the completed deferred/offline stage and verifies results after installation.
A temporary exact APT service-start policy is removed after the transaction;
another operator's policy is never replaced. Only a complete matching guard can
be recovered with `--recover`; partial or foreign state needs operator attention.
Actual package startup/boot behavior remains under qualification. Other legacy
platform support is preserved; automatic browser dependency provisioning is
currently APT-only.

Use `install.sh plan` before `install.sh apply`. Fixture tests set
`AGENTBOX_INSTALLER_TEST_MODE=1` and redirect every path to a temporary root;
normal callers cannot select an alternate filesystem root. See
[`docs/INSTALLATION.md`](../docs/INSTALLATION.md).

No installer, bootstrap script, package-manager command, systemd unit, or host mutation is implemented in Phase 2.

A future installation experience may offer a documented `curl | bash` convenience bootstrap, but the security design does not depend on blindly executing remote content. The bootstrap must be version-pinned, downloaded for inspection, and verified with published checksums plus signatures/provenance where available before execution.

The future installer must provide:

- `/etc/os-release`, architecture, PID 1/systemd, resource, path, port, service, and UID/GID detection;
- explicit OpenCloudOS/Rocky DNF-family and Ubuntu/Debian APT-family package-manager adapters;
- logical dependency plans rather than user-provided package names or flags;
- inspect/dry-run as the default remote workflow;
- idempotent check/apply/verify steps and a durable non-secret journal;
- interruption recovery and honest `needs_attention` states;
- verified, versioned releases under `/opt/agentbox`;
- planned initialization of the `agentbox` and `agentbox-runtime` users after collision checks;
- planned `/etc/agentbox`, `/var/lib/agentbox`, `/srv/agentbox/projects`, and systemd-managed `/run/agentbox` paths;
- exact AgentBox-namespaced systemd services only;
- health-gated activation and safe rollback;
- preservation of existing services, credentials, Runtime sessions, projects, network, and shared packages.

It must never silently run DNF/YUM/APT, add a repository, create a user, change ownership, write a unit, start a service, modify networking, or adopt the Phase 0 host's existing Codex/Claude/tmux state. `docs/INSTALLATION_DESIGN.md` is the governing plan.
