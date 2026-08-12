# AgentBox Platform Support

Status: Phase 8 evidence matrix, pending human review

| Platform | Package adapter | Automated evidence | Status |
|---|---|---|---|
| OpenCloudOS 9 x86_64 | DNF | fixture, systemd analysis, designated real-host gate | validation target |
| Ubuntu 22.04 x86_64 | APT | rejection fixture and GitHub Actions | unsupported: stock Python 3.10 |
| Ubuntu 24.04 x86_64 | APT | fixture and GitHub Actions | CI preview |
| Rocky Linux 9 x86_64 | DNF | fixture only | preview |
| Debian 12 x86_64 | APT | fixture only | preview |
| any `aarch64` | detected | rejection test | unsupported |
| other distro/version/architecture | none | rejection test | unsupported |

`/etc/os-release` ID, version, and `ID_LIKE` drive a typed adapter. Architecture
is normalized independently. `uname` is not used to infer a distribution.
Package managers and package names are fixed internal mappings; callers cannot
supply a package name or command.

Required base checks cover Python and venv capability, Git, tmux, curl,
bubblewrap, SQLite, systemd, and fixed package prerequisites. `gh`, Codex,
Claude, Node, npm, and pnpm have separate detect/version/install-policy/verify
results. The prebuilt Web does not require Node in production. Codex and Claude
installation guidance must be revalidated against current official public
documentation before any distribution change; install does not imply login.

Fixture or container evidence is not a real systemd/VM support claim. Phase 8
must report OpenCloudOS real-host evidence separately and must not describe
Rocky/Debian as deployment-tested. Expanding this matrix requires verified
release artifacts, systemd behavior, dependency repositories, Runtime tools,
upgrade/rollback, and security tests on the target architecture.

Ubuntu 22.04 CI installs Python 3.11/3.13 for repository tests only. The native
installer intentionally rejects stock Ubuntu 22.04 because it selects
`/usr/bin/python3` (3.10), which cannot install the `requires-python >=3.11`
release wheel. A future supported adapter must provide and verify an official
3.11+ interpreter without silently replacing the system Python.
