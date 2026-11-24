# ADR 0012: 在 AgentBox 既有能力边界内融合 T3 Code

## Status

Accepted as an implementation direction under the Owner's current instruction
to integrate T3 Code's implementation ideas and every feature into AgentBox.
This branch is a reviewable software candidate until the normal CI and merge
process completes. This decision does not admit a new content source, broaden
Runtime authority, or authorize a host deployment.

## Context

Kebui already has a conversation-first product plan above AgentBox's
privilege-separated execution foundation. Its 70-item capability inventory and
S00–S14 delivery plan include providers, workspaces, clients, automation and a
later Hub. T3 Code now supplies a further concrete implementation reference,
including capabilities that overlap those plans and additional detail such as
portable handoffs, multi-repository checkpoints and durable workflows.

T3 Code's server owns processes, files, credentials and persistent conversation
state as the server OS user. AgentBox assigns content and execution authority
to Runtime and keeps the Control Plane, Worker and narrow Root Helper separate.
Importing the complete upstream server would introduce conflicting authorities.

## Decision

1. Record every observed upstream capability, evidence level and limitation in
   the [feature matrix](../project/T3_CODE_FEATURE_MATRIX.md), mapped to existing
   capability IDs and stages. Audit sub-items are not a second roadmap.
2. Retain the existing stack, formal Project/WAW/conversation distinctions,
   current-owner/single-writer rules, immutable execution binding, exact Stop,
   Runtime Secret authority and content/control-plane separation from ADR 0009.
3. Reimplement suitable domain patterns behind typed AgentBox contracts. Web,
   CLI, MCP and automation share capability services; they do not each acquire
   an independent execution path or authority. No second daemon, Job queue,
   process supervisor, credential store or Stop owner is introduced by this ADR.
4. Declare provider capabilities per operation and version. Separate source
   research, implemented software and target qualification. Missing, stale or
   mismatched evidence cannot enable an operation. The first D01 module has no
   I/O, production caller or execution authorization result.
5. Use durable intent/receipt and projection patterns within the existing owner.
   Acknowledgment, accepted vendor turn, completion, background cleanup and
   checkpointing remain distinct. Unknown mutations are reconciled, not replayed.
6. Preserve upstream feature semantics as explicit design choices: native resume
   versus portable handoff; single turn versus queue/steer; worktree isolation
   versus OS isolation; file preview versus HTML sandbox versus agent browser;
   simple schedules versus durable workflows. Do not hide missing capabilities
   behind enabled controls or relabeled existing Jobs.
7. Implement multi-client and multi-environment access against one stable host
   identity and scoped authority. Routes are location hints, not identities.
   No implicit local-host fallback, protocol downgrade or permission expansion.
8. Use Kebui branding and AgentBox runtime identities. Keep MIT provenance and
   nested-license review for any later code port. T3 Connect accounts, branding,
   domains and hosted infrastructure are not part of the reusable deliverable.

## Alternatives considered

- Embedding T3 server/client-runtime as a second execution platform would create
  conflicting state, lifecycle and credential authorities.
- Rewriting Python services in Effect/TypeScript is unnecessary for adopting
  typed operations, receipts, state transitions and bounded projections.
- Treating a feature catalogue as implementation completion would obscure the
  actual K2 source-admission, real vendor and host qualification gaps.
- Dropping broad-permission features entirely would lose the Owner's full-scope
  goal. They stay in the matrix with constrained AgentBox equivalents and their
  individual contracts, dependencies and acceptance conditions.

## Consequences and validation

The [integration plan](../project/T3_CODE_INTEGRATION_PLAN.md) is the canonical
source-to-target design. The first software slice is the
[K2-D01 operation contract](../KEBUI_K2_ADAPTER_CAPABILITY_CONTRACT.md).
Its tests validate pure interpretation and fail-closed evidence handling, not
real vendor execution. Production conversation work continues through D02–D07.

The existing restriction on unsubmitted authenticated S03 material remains:
it is not read, recovered, rewritten, uploaded or delegated, nor bypassed with
an alternate admission design. Any later capability changing a trust boundary,
data authority or retention rule needs its own concrete implementation decision;
this ADR supplies no blanket exception. Ordinary authorized design, coding,
testing and repository integration continue without redundant permission gates.
