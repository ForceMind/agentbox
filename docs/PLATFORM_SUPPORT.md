# AgentBox Platform Support

Status: `0.3.0rc1` qualification matrix

| Platform | Package adapter | Evidence | Qualification |
|---|---|---|---|
| OpenCloudOS 9 x86_64 | DNF | fixture, offline unit analysis, designated OpenCloudOS 9.4 host install/update/rollback/service validation | **Real-host validated** |
| Ubuntu 22.04 x86_64 | APT | GitHub Actions runs rejection, unit, installer, and recovery fixtures with Python 3.11/3.13 | **Unsupported native install**: stock Python 3.10 |
| Ubuntu 24.04 x86_64 | APT | four-job Deployment matrix coverage across Ubuntu/Python combinations; offline units and fixture lifecycle | **CI validated**; no native PID 1 claim |
| Rocky Linux 9 x86_64 | DNF | os-release, package mapping, filesystem plan, systemd 252 capability, installer/update/rollback fixtures | **Fixture validated** |
| Debian 12 x86_64 | APT | os-release, package mapping, filesystem plan, systemd 252 capability, installer/update/rollback fixtures | **Fixture validated** |
| any `aarch64` | detected | fail-closed rejection fixture; no qualified Runtime/artifact inventory | **Unsupported / unqualified** |
| other distro/version/architecture | none | fail-closed rejection fixture | **Unsupported** |

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

The `0.3.0rc1` Linux x86_64 artifact carries a hash-locked wheelhouse for
CPython ABIs `cp311`, `cp312`, and `cp313`; its manifest contract is
`>=3.11,<3.14`. The bootstrap rejects Python 3.10 and 3.14 before venv/pip.
This artifact boundary does not permanently cap future source compatibility.
AgentBox core installation is offline after the artifact and checksum files are
obtained; distro package installation and
optional Runtime-tool installation may still require configured repositories.

Fixture evidence is not a real systemd/VM support claim. Rocky/Debian are not
described as deployment-tested. Expanding this matrix requires verified
release artifacts, systemd behavior, dependency repositories, Runtime tools,
upgrade/rollback, and security tests on the target architecture.

## systemd baselines

AgentBox maps every security directive in generated units to a minimum public
systemd version and rejects an incompatible unit before installation. Current
qualified baselines are 249 (Ubuntu 22.04 rejection evidence), 252
(Rocky/Debian fixtures), and 255 (OpenCloudOS/Ubuntu 24.04 evidence). This is a
compatibility gate, not a promise that every distro with that systemd version
is supported.

## Runtime dependency classification

Python 3.11–3.13 for this RC artifact, Git, SQLite, systemd, and the
release-local venv are core. Codex,
Claude, gh, tmux, bubblewrap, Node, npm, and pnpm are separately reported
Runtime capabilities. A missing optional Runtime tool degrades only that
integration; the prebuilt API/Web control plane can remain ready without Node.

Ubuntu 22.04 CI installs Python 3.11/3.13 for repository tests only. The native
installer intentionally rejects stock Ubuntu 22.04 because it selects
`/usr/bin/python3` (3.10), which cannot install the `requires-python >=3.11`
release wheel. A future supported adapter must provide and verify an official
3.11+ interpreter without silently replacing the system Python.
