# WAW-1 Contract Matrix

This matrix separates the contracts merged into `main` from production
capabilities that still require Linux host evidence and explicit Owner
authorization. It is a verified post-merge snapshot, not a production-readiness
claim.

## Live identity and governance

- Repository: `ForceMind/agentbox`
- Main: `03f862a6cab41cd499a9d9a1024d581348818eda`
- PR: `#43`, `MERGED` (squash merge)
- PR head: `622bbe7be99fbf38e0322230ff3ecb82e8fcc621`
- PR base: `main @ f2de2c7d2212724cc29d3b08140940fbcdf0a884`
- Exact-head CI before merge: `19/19 SUCCESS` (historical evidence for PR #43,
  not a post-merge host or release check)
- Merge commit observed for the exact PR/head/base above. The Owner
  authorization was an external governance record; GitHub `reviewDecision` is
  not that record. This does not authorize WAW-2, production activation, or
  real-host work.

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

- WebSocket stream route, browser terminal renderer/input/resize, and real
  Runtime-backed Noise/PTY admission.
- Real `/stream`, browser terminal rendering/input/output/resize/reconnect.
- WAW-2 Codex slice.
- WAW-3 continuity, mobile, recovery and reboot hardening.
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

Every implementation slice remains `feature branch → Draft PR → exact-head CI →
read-only Architecture/Security/Test review → explicit Owner/host gate`. This
document records that WAW-1 foundation PR #43 has completed that merge gate; it
does not authorize production activation, WAW-2, WAW-3, real Provider login, or
deployment.
