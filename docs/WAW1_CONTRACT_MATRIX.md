# WAW-1 Contract Matrix

This matrix separates the contracts merged into `main` from production
capabilities that still require Linux host evidence and explicit Owner
authorization. It is a verified post-merge snapshot, not a production-readiness
claim.

## Live identity and governance

- Repository: `ForceMind/agentbox`
- Verified main on 2026-09-03: `24d08414b20e7158e8c84694aac59d0326799bfd`.
- Main exact-head workflows: Backend, Frontend, E2E, Deployment, Security,
  Release Candidate all terminal `success`. See `project/CURRENT_STATE.md`.
- Historical foundation PR: `#43`, `MERGED` (squash merge)
- PR head: `622bbe7be99fbf38e0322230ff3ecb82e8fcc621`
- PR base: `main @ f2de2c7d2212724cc29d3b08140940fbcdf0a884`
- Exact-head CI before merge: `19/19 SUCCESS` (historical evidence for PR #43,
  not a post-merge host or release check)
- Merge commit observed for the exact PR/head/base above. The Owner
  authorization was an external governance record; GitHub `reviewDecision` is
  not that record. Subsequent software authorization is tracked in
  `project/NEXT_ACTION.md`; no repository merge proves host/production readiness.

## Implemented and tested contracts

These entries describe code and synthetic/CI test evidence. They do not imply a
real host, provider login, interactive terminal, or production route.

| Area | Evidence |
| --- | --- |
| Workspace identity, lifecycle, generation, binding, lease and quarantine | `packages/agentbox-runtime/src/agentbox_runtime/waw_lifecycle.py`, `packages/agentbox-core/src/agentbox_core/waw.py`, `waw_lease.py`; lifecycle/domain/lease tests |
| Workspace and cgroup durable attestations | `waw_workspace_attestation.py`, `waw_cgroup_attestation.py`, `waw_cgroup_attestation_store.py`; attestation/store/lifecycle tests. These are validated metadata records only; live cgroup readback remains host-gated. |
| Strict manifest codecs and cross-manifest pins | `waw_manifest_codecs.py`, `waw_host_manifest.py`, `waw_bootstrap.py`; manifest/bootstrap tests |
| Metadata-only public auth probe | `waw_auth_probe.py`, `tests/unit/test_waw_auth_probe.py`; no CLI or auth-file access |
| Attachment ticket and admission contracts | `packages/agentbox-core/src/agentbox_core/waw_tickets.py`, `apps/api/src/agentbox_api/waw_admission.py`; ticket/admission tests |
| ABWS v1 framing and bounded stream pump | `packages/agentbox-protocol/src/agentbox_protocol/abws.py`, `abws_stream.py`; ABWS tests |
| Contract-only Noise metadata state machine | `waw_noise_contract.py`; fixed sequence, tuple/epoch/replay/terminal tests; no cryptography |
| Contract-only WebSocket policy and parser | `waw_websocket_contract.py`, `waw_websocket_parser.py`; masking/RSV/length/fragment/close tests; no network listener |
| Bounded terminal-output sanitizer | `waw_terminal_sanitizer.py`; strict UTF-8, C0/C1/Cc/Cf and ESC/OSC tests; no PTY or renderer |
| Layer-boundary composition tests | `tests/unit/test_waw_transport_layers.py`; parser→policy, ABWS independence and Noise enum-only checks |
| HTTP lifecycle/ticket scaffolding (synthetic only) | `apps/api/src/agentbox_api/workspaces.py` exposes CSRF/recent-auth fenced Start, Stop, Attachment-ticket and fresh Reconnect routes; routes require an already bound Runtime and durable workspace row. |
| Synthetic ABWS stream bridge (contract only) | `waw_stream_contract.py`, `waw_stream_bridge.py`, and stream tests compose bounded input/resize/replay/GAP/detach/close behavior over `WAWSupervisor`; no listener or cryptography. |
| WAW-2 Codex command identity and lifecycle (synthetic only) | `waw_codex_command.py` / `test_waw_codex_command.py` enforce Project/workspace identity, fixed argv and executable provenance. PR #55 extends Runtime lifecycle tests to Codex. The current software stage adds symmetric API Start/Stop/ticket and Web parser/action contracts with ASGI/Fake Runtime evidence; real CLI/transport and legacy interlocks remain incomplete. |
| Fail-closed WebSocket boundary | `apps/api/src/agentbox_api/main.py` has an authenticated route boundary that refuses service without a qualified handler; no production encrypted stream is claimed. |

## Contract-only boundaries

- `READY_FOR_EXTERNAL_HANDSHAKE` means only that a metadata sequence was
  accepted. It does not mean authenticated, secure, established, or Runtime
  ready.
- WebSocket parser/policy handles parsed or bounded metadata only. It is not an
  Origin/CSRF/authentication gate, TLS boundary, or production `/stream`.
- The terminal sanitizer is not a Secret scrubber, XSS defense, terminal
  emulator, or authenticated stream. It accepts one complete bounded record;
  partial streaming state requires a separate bounded design.
- Synthetic cgroup cleanup decisions never replace host-authenticated cgroup
  readback or the locked durable store acknowledgment.
- Fake Runtime and in-memory tests do not prove real Provider, host, systemd,
  PTY, tmux, namespace, or browser behavior.

## Host-gated and not validated

- Sole production Runtime startup path: manifest loader → external anchor and
  cross-pin verification → host attestation → epoch → lifecycle/control server.
- Linux installer owner/mode/ancestor/mount/inode provenance.
- systemd socket activation, exact socket identity, peer credentials and
  pidfd lifecycle.
- cgroup hierarchy/controller readback, quotas, `cgroup.events`, same-UID
  write denial, namespaces, seccomp/LSM and `PrivateDevices`/devpts.
- Real `openpty`/process-group/`TIOCSCTTY`/resize/tmux process bridge.
- Real Noise cryptography, WebSocket upgrade, reverse proxy and browser
  transport.
- Isolated Runtime-user Claude login/Trust/readiness and disposable-host demo.

Any failed or unknown host evidence remains a block; no plaintext fallback or
automatic adoption is allowed.

## Not implemented

- Functional encrypted WebSocket stream, browser terminal renderer/input/resize
  wiring and Runtime-backed Noise/PTY admission.
- Real `/stream`, browser terminal rendering/input/output/resize/reconnect.
- Complete WAW-2 real Codex CLI/transport slice and legacy Remote Control interlocks; the Project-scoped API path is implemented separately as a software contract.
- Complete WAW-3 continuity, mobile, recovery composition and reboot hardening;
  existing lease/ring/cleanup contracts are being extended, not reimplemented.
- Final release artifacts, production deployment and launch.
- Provider API keys, Secret handling, account/channel balance monitoring.

## Verification and governance commands

These commands must be rerun against the live head before claims are updated:

```text
git fetch origin --prune
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
gh pr view 43 --json state,isDraft,headRefOid,baseRefOid,mergeCommit,mergeStateStatus,reviewDecision
gh pr checks 43
```

The current routine flow is `feature branch → CI → merge → exact read-back`.
Security-critical changes receive independent read-only Architecture/Security/Test
review. Draft state, a governance bot and a separate Owner Merge Authorization
are not routine merge requirements. Architecture changes, real host activation,
Secret handling and production publication retain their separate explicit gates.
See `project/GOVERNANCE.md` and `project/EXECUTION_PLAN.md`.
