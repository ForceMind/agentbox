# Decision and Architecture Index

## Current execution policy

- `GOV-AUTOMATION-1` is superseded for routine repository work: the Coding Agent
  may perform CI-gated Ready/merge/read-back without a governance bot or an
  additional Owner Merge Authorization. See `GOVERNANCE.md` and `AGENTS.md`.
- `GOV-AUTOMATION-2`: revalidate live repository identity, exact PR/head/base and
  terminal CI; snapshots do not override Git/GitHub.
- `GOV-AUTOMATION-3`: real-host activation, architecture decisions, Secret
  handling and production support remain subject to explicit authorization
  and evidence. Routine merge permission does not satisfy these gates.
- `EXECUTION-2026-09-03`: Owner authorized parallel multi-agent development and
  requires GitHub/document updates at every completed stage. See
  `EXECUTION_PLAN.md` for scope, ownership, dependencies and exit criteria.

- `MAC-DEVELOPMENT-2026-09-03`: Owner clarified continued development on the
  current Mac. Separate software implementation/local+CI checks from actual
  Linux activation and qualification; a missing Linux target does not block
  independent software work. See `NEXT_ACTION.md`.

## Architecture and evidence

- `WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md`: historical WAW
  proposal and detailed safety contracts; its historical status is retained.
- `docs/WAW1_CONTRACT_MATRIX.md`: implementation/evidence mapping, not host
  readiness or new authorization.
- `docs/WAW1_HOST_GATE_CHECKLIST.md`: required host observations and recovery
  conditions; unobserved items remain `NOT RUN`.
- `docs/WAW3_RECOVERY_CONTRACTS.md`: software recovery classification, browser
  event fences, validation mapping and explicit unimplemented integration scope.
- `docs/WORKSPACE_METADATA_WORKFLOW.md`: current metadata UI/control workflow, exact lookup and Stop boundaries, tests and visual evidence limits.
- `docs/WAW_SOFTWARE_READINESS.md`: immutable software/artifact evidence, current capability limits and explicit Stage F input/gates.
- `CURRENT_STATE.md`: last verified snapshot. `NEXT_ACTION.md`: current software
  stage and remaining gates.

- `MAC-RUNTIME-COMPOSITION-2026-09-03`: continue concrete lifecycle-to-supervisor
  software composition on Mac. Read-only status probes and durable generation
  reservation are required before claiming Runtime observations; attachment
  prepare remains separate from actual admission. No host activation or
  architecture proposal approval is inferred.


- `REMAINING-EXECUTION-2026-09-03`: Owner requested reassessment and persistent
  parallel development, routing complex work to `gpt-5.6-sol` and ordinary work
  to `gpt-5.6-terra`. Current finite goals/dependencies are in
  [REMAINING_PLAN.md](REMAINING_PLAN.md). Routine implementation/CI/merge continue;
  unapproved architecture and real-host/key/production actions retain their gates.

- `WAW-STREAM-SUPPLEMENT-ACCEPTED`: the complete protocol supplement is accepted by the Coding Agent under the Owner's explicit 2026-09-03 software decision delegation. It resolves key/context, verification, ACK, drop, limit and signed-pin contradictions. Prior independent review passed; implementation is R4/R5, and host/production evidence remains separate.

- `SOFTWARE-DECISION-DELEGATION-2026-09-03`: Owner explicitly permits the Coding Agent to decide goals, plans and software architecture for the ongoing objective. See GOVERNANCE for scope; resolve software choices with evidence/review without repeatedly requesting the same authorization.

- `WAW-WIRE-IMPLEMENTATION-2026-09-03`: under delegated software authority, the [wire contract](../WAW_WIRE_CONTRACT.md) records precise early-failure precedence, exact numeric/version handling, retry limits, bounded opaque-source pairing and synchronized sequence acceptance. Independent review and actual parser-budget evidence are recorded separately from authority effects.

- `WAW-BROWSER-BOUNDED-MODEL-2026-09-04`: Owner accepted the
  [browser implementation decision](WAW_BROWSER_IMPLEMENTATION_DECISION.md).
  R9 uses a project-owned bounded terminal model over typed tokenizer output,
  keeps the 32 KiB logical-line count across waits without a wall-clock expiry,
  retains the 100 ms incomplete carry deadline, and immediately fences ambiguous
  parser state. xterm is not admitted for this implementation.
- `WAW-BROWSER-TRUST-PROVIDER-GATE-2026-09-04`: signature/lifecycle consumer
  software may proceed, but a real independent provider must separately prove
  bootstrap authority, atomic floors, trusted time, network/origin policy and
  loss/revocation delivery. Missing provider keeps production Connect closed.
- `WAW-BROWSER-TRUST-PROVIDER-V1-2026-09-04`: Owner approved a managed MV3
  Chromium extension, fixed Native Messaging bridge and independent local
  `trustd`. The ordinary build is externally inert; production Connect requires
  a CRX-key-derived ID, exact Origin/update policy and R12 installation evidence.
- `WAW-BROWSER-ROOT-CHECKPOINT-V1-2026-09-04`: a successor accepted while its
  exact predecessor is valid creates an atomic provider checkpoint binding
  `accepted_at`, root/signer identity and the complete root-history digest.
  Later rotations verify the previous exact prefix before advancing this
  cumulative proof. Restart keeps full history/tombstones, checks the direct
  signer/root pair at that recorded time and checks current root/pin at final
  trusted time; missing, late, truncated, forked or rolled-back evidence fails
  closed.
- `BROWSER-LOCALE-V1-2026-09-04`: only `navigator.languages[0]` selects UI
  locale; primary language `zh` maps to `zh-CN`, every other or malformed value
  maps to English. Technical identifiers and protocol values remain English.
- `WAW-INPUT-OWNERSHIP-2026-09-04`: one 65536-byte encoded INPUT ledger follows
  ownership from native ready through ASGI/relay pending to Runtime send. Layer
  transitions do not release/reacquire capacity, and first overflow synchronously
  fences I/O. The 128-slot/8 MiB parser pool remains a separate budget.
- `WAW-R11-COMPOSITION-2026-09-05`: R11 executes serially as rc6 controller
  composition, rc7 deterministic composed failure injection, rc8 artifact/ops
  rehearsal and rc9 full bilingual UI. rc6 first binds control/stream to the same
  pidfd-backed API/Runtime peers, persists Runtime epoch classification, adds
  bounded Runtime redraw and single application ownership. See
  [WAW_R11_CONTROLLER_COMPOSITION](../WAW_R11_CONTROLLER_COMPOSITION.md).
