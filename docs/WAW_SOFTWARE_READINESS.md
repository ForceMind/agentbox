# WAW Software Readiness — 2026-09-03

## Decision

**Software contracts and metadata workflow are delivered; the interactive
terminal product is not complete and is not production-qualified.**

This record covers the software-only stages requested on 2026-09-03. It does
not approve the historical WAW architecture proposal, activate a host, authorize
Secret handling, publish a release or create a support promise. A packaged copy
carries the same limitation as the repository copy.

## Delivered scope and immutable evidence

| Stage | PR | Reviewed head | Observed merge | Exact-head CI |
| --- | --- | --- | --- | --- |
| A/B — plan and recovery contracts | [#58](https://github.com/ForceMind/agentbox/pull/58) | `f3bb9035e061fc0babfcace6af891f257eb7fa74` | `d2470601a06da0a4024fa1772b4f32ec2daa7293` | 19/19 SUCCESS |
| C — Codex control contracts | [#59](https://github.com/ForceMind/agentbox/pull/59) | `3e0e7a921e008d9c6b5198d37b8254fbee174068` | `7c1c755854077d2e0989ff1d3ab3d54f77e9e707` | 19/19 SUCCESS |
| D — Workspace metadata UX | [#60](https://github.com/ForceMind/agentbox/pull/60) | `9be95b10e57a3daa3690205d6c2ffad8da74424d` | `6972f0dba907afd9741c2dc3584f431ee32765ed` | 19/19 SUCCESS |
| E — software readiness and packaged boundaries | [#61](https://github.com/ForceMind/agentbox/pull/61) | `0c894ff52f49793f599eb33c4b92b8223e6109b3` | `35191eeaf858041cf5c0767dc1579b67690444ec` | 19/19 SUCCESS |

Implemented behavior includes complete recovery/lease identity fencing,
canonical cursor/epoch validation, stale browser event rejection, symmetric
Claude/Codex WAW control contracts, precise READY Project/AgentType lookup,
explicit Start and exact Stop confirmation. The page never converts metadata,
HTTP success or a ticket into `ADMITTED`; terminal controls remain unavailable.

Independent read-only Architecture/Security/Test reviews were used for the
software changes. The primary agent additionally inspected actual Chromium
renderings and tested native Stop confirmation, Cancel/Escape/focus, desktop
and mobile sizing, failure and empty states using synthetic metadata.

Local supporting evidence: 101 recovery tests; 56 API/admission/command tests;
115 frontend tests; type/lint/format/build checks; Linux-target mypy over 188
files. The complete CI matrix includes Backend on Python 3.11/3.12/3.13,
Frontend on Node 22, desktop/mobile E2E, Deployment, Security and Release
Candidate. Linux CI, not the macOS environment, is the supported execution gate.

## Independently checked baseline artifact

This immutable artifact is from the merged **implementation baseline**, before
this documentation/packaging stage. The current stage's CI rebuilds its own
artifact from its exact head; no future hash is predicted here.

- [Release Candidate run 33718909935](https://github.com/ForceMind/agentbox/actions/runs/33718909935): terminal success.
- Source commit: `6972f0dba907afd9741c2dc3584f431ee32765ed`; ref kind: `main`.
- Artifact ID: `9879550362`; name: `agentbox-0.3.0rc1-linux-x86_64`.
- GitHub artifact ZIP digest: `083133e434847b8594000ef007397255452f69a581ea4920fed740742a9717ba`.
- Tarball SHA-256: `1c90ed319fbef8d839783253e28baf85b4fa91307ef1c207c216ac6078320753`.
- Manifest SHA-256: `8a53aa08438bac9954fcb09f2f6fc54aaffbcf0dc1775cdd917654339f396d45`.
- SBOM SHA-256: `a1e04466c3f19793e5866eded579de066f91a6437533e4db620ca07c08b39790`.
- Tarball size: `27498769` bytes; manifest schema `4`; version `0.3.0rc1`;
  database revision `0007_waw_host_identity_fence`; Python `>=3.11,<3.14`.
- `scripts/check-release-artifact.py` with the exact source/ref above exited `0`:
  77 archive members and 2,757 nested wheel members scanned, no source maps or
  canaries. The artifact was **not installed or executed** during this check.
- Hashes establish integrity only. The artifact is unsigned. Existing platform
  labels describe the MVP matrix and do not qualify WAW terminal/host behavior.

The candidate workflow also builds twice and requires byte-for-byte equality,
verifies manifest/checksums/SBOM/notices/dependency inventory, and runs the
artifact-only fixture install/recovery smoke. These are software/fixture gates.

## Verified Stage E package

[Run 33719963292](https://github.com/ForceMind/agentbox/actions/runs/33719963292)
produced artifact `9879903829` from exact E head
`0c894ff52f49793f599eb33c4b92b8223e6109b3` (`pull_request_head`). All 19 head
checks passed; PR #61 then merged as `35191eeaf858041cf5c0767dc1579b67690444ec`.
Independent download/scan confirmed all four WAW documents, 81 archive members,
2,757 nested wheel members, 27,510,853 bytes and no source maps/canaries (exit 0).

- GitHub artifact ZIP digest: `c41e70223397df9a75502cc05cd178aa1766a84da5e6642e68701ac73ce6c4e5`.
- Tarball SHA-256: `9b1dcd19452a79ee933a4781da368d70415deb374b2a6bd46353501b0c23eb03`.
- Manifest SHA-256: `20d460d8e1a4aee9c05149289d474fcbf2ed9d20904acd685eccb154d60ed354`.
- SBOM SHA-256: `4405cf4f6c8510da3cfacf346a0231893ac8133c94bc5cda3200da3068c676d4`.

No installation, execution, tag or publication was performed. This final
snapshot records already-observed artifacts and does not predict a later
snapshot/merge artifact's hash.

## Mac development clarification

The Owner subsequently clarified that development continues on the current Mac.
The remaining software is not blocked merely because no Linux host is attached:
shared Runtime, protocol and browser components can be implemented and tested
locally and in CI. The gates below constrain actual activation, architectural
changes and readiness claims; they are not a blanket prohibition on Mac coding.
A–E remain completed increments, not a claim that all remaining software is done.

The current increment adds the concrete Claude/Codex command union and shared
supervisor path, preserving AgentType/binding/epoch fences. The legacy Claude
tmux adapter remains explicit about unsupported Codex; real process/bootstrap
and encrypted terminal integration remain subsequent work.

## Stage F — implementation and qualification

| Area | Current state | Required next condition |
| --- | --- | --- |
| Architecture scope | [Detailed WAW proposal](https://github.com/ForceMind/agentbox/blob/6972f0dba907afd9741c2dc3584f431ee32765ed/WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md) remains PROPOSED; software slices do not approve real transport | Explicit Owner scope for implementing the proposed real transport/process profile |
| Disposable host | No target or SSH alias has been supplied for this task | Identify an isolated Linux test host and authorize the bounded install/start/stop/restart/recovery scope; preserve existing production state |
| CLI/process execution | Fixed command contracts exist; complete isolated Claude/Codex PTY/process path is not delivered | Implement the Runtime-only fixed executor/PTY path under the approved architecture; qualify executable/cwd/marker and exact Stop |
| Transport and terminal | Real Noise, authenticated WebSocket transport and browser terminal wiring are unavailable | Implement and verify approved crypto/profile vectors, trust anchors and ciphertext-only API/proxy behavior |
| Legacy process interlocks | Error codes/API rejection exist; actual probes and bidirectional interlocks are not implemented | Prove no adoption, no silent co-run and exact conflict handling against known managed processes |
| Linux isolation | Software attestations/fixtures exist; WAW real-host evidence is absent | Observe systemd/socket/cgroup/namespace/LSM/seccomp/devpts/provenance and failure cleanup on the target |
| Login and Trust readiness | No WAW Runtime-user readiness evidence was collected | Authorized operator completes official CLI prerequisites locally; only redacted readiness, never credentials or private HOME data, enters evidence |
| Continuity and reboot | Pure reducers and synthetic contracts exist; end-to-end restart/reboot path is incomplete | Verify desktop/mobile reconnect, uncertain input, cleanup, Runtime/API restart and reboot with attributable evidence |
| Publication/support | No new release/tag or production activation occurred | Exact version/tag/artifact authorization after all applicable gates; no force/history rewrite/admin bypass |

The detailed observation order is in [the host checklist](WAW1_HOST_GATE_CHECKLIST.md).
Every unobserved host item stays NOT RUN/UNKNOWN/BLOCKED, never PASS. The product
must remain unadmitted until these requirements are met. Routine GitHub merges
cannot substitute for the missing authorization, target or real evidence.

Repository governance and the active checklist are in `docs/project/`; those
source-management documents may not be included in the standalone artifact.
The packaged workflow and recovery documents explain the current product limits
without requiring access to that directory.
