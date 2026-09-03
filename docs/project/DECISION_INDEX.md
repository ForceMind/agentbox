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
