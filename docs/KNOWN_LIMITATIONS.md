# AgentBox MVP Release Candidate Known Limitations

This document describes `0.3.0rc1`. It is a pre-release MVP candidate, not a
production-readiness, penetration-test, enterprise-support, or broad Linux
compatibility claim.

- The product is single-server and single-administrator only.
- OpenCloudOS 9 x86_64 is the only real-host validated platform.
- Ubuntu 24.04 x86_64 is CI validated; native PID 1/systemd behavior has not
  been validated on a dedicated host.
- Stock Ubuntu 22.04 is unsupported because Python 3.10 does not meet the
  Python 3.11 minimum. CI fixtures using injected Python do not change that.
- Rocky Linux 9 and Debian 12 are fixture validated only.
- aarch64 and non-Linux AgentBox hosts are unsupported and unqualified.
- Release artifacts have SHA-256 integrity metadata but no signature,
  provenance attestation, or cryptographically verified publisher identity.
- TLS termination, exact trusted-proxy/origin configuration, VPN/tunnel setup,
  firewall, SSH, cloud security groups, and public ingress remain operator
  responsibilities. AgentBox defaults to loopback and does not automate them.
- AgentBox backs up control-plane SQLite/config/release metadata, not the
  Project source tree. Git remotes and operator backups remain required.
- Host reboot recovery has not been validated.
- Runtime uses broader compatibility allowances than API, Worker, and Helper:
  Codex, Claude, Node/V8, tmux, Git, and bubblewrap may require HOME, outbound
  network, user namespaces, and executable memory. The systemd sandbox is not a
  chroot or VM.
- Codex/Claude public CLI behavior can change. Unknown evidence degrades to
  Unknown/Unsupported rather than using private state.
- The local Playwright suite may require host browser libraries; GitHub E2E is
  the authoritative automated browser gate when local dependencies are absent.
- AgentBox does not automatically configure remote access, migrate root Runtime
  credentials/sessions/projects, or back up Runtime credentials.
- Phase 11 includes non-secret Provider/Runtime/Profile/Binding models,
  capability observation contracts and a Runtime-owned Secret Store foundation.
  Product Provider/Secret management, config activation, Provider switching and
  automatic failover remain incomplete; foundations are not production evidence.
- No browser terminal, multi-server operation, SaaS control plane, automatic
  package registry publication, or stable-support promise is included.

## Web Agent Workspace software boundary

- READY Project/Claude/Codex metadata selection, explicit Start and exact Stop
  are implemented; Start requires a pre-registered trusted Runtime binding.
- Codex WAW API/ticket contracts are separate from legacy Remote Control.
  API-reported conflicts fail closed, but real legacy process probes and
  bidirectional interlocks are not implemented.
- Browser terminal Connect/Reconnect/Detach/input/output/resize remain
  unavailable. HTTP status, Start success and ticket issuance never imply
  `ADMITTED` or `connected`.
- Real isolated CLI/PTY execution, Noise cryptography, authenticated WebSocket
  transport, browser terminal wiring and end-to-end Runtime/API restart/reboot
  recovery remain unimplemented or unqualified. Pure/fake contracts do not
  establish these capabilities.
- Metadata JSON integers beyond JavaScript's safe range are rejected rather
  than rounded into a Stop target; full uint64 control values remain strings.
- See `project/EXECUTION_PLAN.md`, `WORKSPACE_METADATA_WORKFLOW.md` and
  `WAW1_HOST_GATE_CHECKLIST.md`. Current software preparation is not production
  readiness, a release publication or a new platform-support promise.
