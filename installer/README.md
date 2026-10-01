# AgentBox Installer

Phase 8 implements a typed, platform-aware native installer. The Bash entry is
only a root/bootstrap gate; Python owns detection, planning, artifact safety,
identities, FHS layout, migrations, systemd, backup, update, rollback, and
data-preserving uninstall.

The first browser deployment is still under qualification. After fixed WAW
enrollment/publication, `configure-waw-web --origin https://host.example --plan`
checks the current Root-owned overlay and `/etc/agentbox-web/tls/fullchain.pem`
(Root 0644) plus `privkey.pem` (Root 0600), then plans only the exact browser
Origin and loopback trusted proxy. Applying configuration requires WAW services
to be offline; it starts no service. Run fixed WAW activation before
`activate-waw-web --origin https://host.example`. Web activation restarts only
the separate HTTPS service and requires an already configured Origin.

These internal commands are not yet the promised self-install command:
automatic certificates/renewal and the final installer sequence remain open.
PEM/hostname checks and service-manager status do not prove public CA trust,
actual browser/CLI use or reboot/upgrade/rollback qualification.

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
