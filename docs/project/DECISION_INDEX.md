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
