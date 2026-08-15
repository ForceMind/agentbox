# AgentBox Architecture Decision Records

ADRs record decisions that change AgentBox's trust boundaries, deployment, data ownership, or long-term engineering constraints. Every record started as `Proposed` in Phase 1. The authorized maintainer accepted ADRs 0001–0008 during Phase 2 finalization on 2026-08-09; acceptance records the decision but does not authorize work outside the current phase.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-deployment-model.md) | Native systemd is the default deployment | Accepted |
| [0002](0002-privilege-separation.md) | Non-root services plus a narrow root Helper | Accepted |
| [0003](0003-project-directory-model.md) | `/srv/agentbox/projects` is the default project root | Accepted |
| [0004](0004-runtime-user-model.md) | A separate `agentbox-runtime` user owns Runtimes and projects | Accepted |
| [0005](0005-job-execution-model.md) | SQLite-backed Jobs plus one systemd Worker and SSE | Accepted |
| [0006](0006-frontend-stack.md) | React, TypeScript, Vite, Tailwind, selective shadcn/ui | Accepted |
| [0007](0007-database-choice.md) | SQLite, SQLAlchemy, Alembic, and WAL for the MVP | Accepted |
| [0008](0008-license-choice.md) | Apache-2.0 is the initial project license | Accepted |

## Phase 11 canonical decision registry

This is the sole canonical registry for Phase 11 decision identifiers. The rows
below are `Accepted` governance in any protected `main` revision containing this
change. Before that merge, a branch-only copy is a candidate: the Phase 11.10
documentation PR must pass protected checks and receive human architecture and
security approval. These decisions authorize no implementation by themselves.

Identifiers `P11-ADR-010`, `P11-ADR-020`, `P11-ADR-050`, and `P11-ADR-060` are
reserved separators and must not be reused. A future reversal requires a new
identifier and an explicit successor link; accepted identifiers are never
renumbered.

### Provider domain

| ADR | Decision | Status | Source |
|---|---|---|---|
| P11-ADR-001 | Provider abstraction is separate from Runtime control | Accepted | [Phase 11.1](../../PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md) |
| P11-ADR-002 | Credentials are separate from Provider identity | Accepted | [Phase 11.1](../../PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md) |
| P11-ADR-003 | Claude remains Runtime-only initially | Accepted | [Phase 11.1](../../PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md) |
| P11-ADR-004 | Phase 11 does not modify active sessions | Accepted | [Phase 11.1](../../PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md) |
| P11-ADR-005 | Runtime Binding owns Provider selection | Accepted | [Phase 11.1](../../PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md) |
| P11-ADR-006 | Session Binding is immutable effective-state evidence | Accepted | [Phase 11.1](../../PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md) |
| P11-ADR-007 | Provider capabilities are evidence, not promises | Accepted | [Phase 11.1](../../PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md) |
| P11-ADR-008 | Foundational domain model is database-agnostic and non-secret | Accepted | [Phase 11.1](../../PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md) |
| P11-ADR-009 | Provider types use typed extensions, not a universal option bag | Accepted | [Phase 11.1](../../PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md) |

### Runtime capability contract

| ADR | Decision | Status | Source |
|---|---|---|---|
| P11-ADR-011 | Runtime capability information is contract based | Accepted | [Phase 11.2](../../PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md) |
| P11-ADR-012 | Control Plane does not directly modify Runtime internals | Accepted | [Phase 11.2](../../PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md) |
| P11-ADR-013 | Read-only capability discovery precedes mutation | Accepted | [Phase 11.2](../../PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md) |
| P11-ADR-014 | Capability outcome and evidence lifecycle are separate | Accepted | [Phase 11.2](../../PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md) |
| P11-ADR-015 | Existing peer-authenticated Runtime UDS remains the transport | Accepted | [Phase 11.2](../../PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md) |
| P11-ADR-016 | Runtime Adapters use public contracts and fixed probes | Accepted | [Phase 11.2](../../PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md) |
| P11-ADR-017 | Capability evidence never authorizes mutation | Accepted | [Phase 11.2](../../PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md) |
| P11-ADR-018 | Capability reports minimize sensitive Runtime information | Accepted | [Phase 11.2](../../PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md) |
| P11-ADR-019 | Claude capability remains Runtime/session scoped | Accepted | [Phase 11.2](../../PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md) |

### Secret boundary

| ADR | Decision | Status | Source |
|---|---|---|---|
| P11-ADR-021 | Secrets are separate from Provider identity | Accepted | [Phase 11.3](../../PHASE11_3_SECRET_BOUNDARY_ADR.md) |
| P11-ADR-022 | Plaintext Secrets never use normal database fields | Accepted | [Phase 11.3](../../PHASE11_3_SECRET_BOUNDARY_ADR.md) |
| P11-ADR-023 | Runtime Secret access is controlled and minimal | Accepted | [Phase 11.3](../../PHASE11_3_SECRET_BOUNDARY_ADR.md) |
| P11-ADR-024 | Secret operations require Audit records | Accepted | [Phase 11.3](../../PHASE11_3_SECRET_BOUNDARY_ADR.md) |
| P11-ADR-025 | V1 uses a dedicated Runtime-owned local Secret store | Accepted | [Phase 11.3](../../PHASE11_3_SECRET_BOUNDARY_ADR.md) |
| P11-ADR-026 | Stored Secret versions use authenticated envelope encryption | Accepted | [Phase 11.3](../../PHASE11_3_SECRET_BOUNDARY_ADR.md) |
| P11-ADR-027 | Secret provisioning is local and outside ordinary Web/API | Accepted | [Phase 11.3](../../PHASE11_3_SECRET_BOUNDARY_ADR.md) |
| P11-ADR-028 | Root Helper has no Secret authority | Accepted | [Phase 11.3](../../PHASE11_3_SECRET_BOUNDARY_ADR.md) |
| P11-ADR-029 | Ordinary backup excludes Secret records and master keys | Accepted | [Phase 11.3](../../PHASE11_3_SECRET_BOUNDARY_ADR.md) |
| P11-ADR-030 | Plaintext delivery is transient and action-specific | Accepted | [Phase 11.3](../../PHASE11_3_SECRET_BOUNDARY_ADR.md) |

### Configuration transactions

| ADR | Decision | Status | Source |
|---|---|---|---|
| P11-ADR-031 | Runtime changes require transaction boundaries | Accepted | [Phase 11.4](../../PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md) |
| P11-ADR-032 | Validation precedes mutation | Accepted | [Phase 11.4](../../PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md) |
| P11-ADR-033 | Failed Runtime changes require verified rollback | Accepted | [Phase 11.4](../../PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md) |
| P11-ADR-034 | Snapshots exclude separately managed Secret Material | Accepted | [Phase 11.4](../../PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md) |
| P11-ADR-035 | Planning and execution are separate contracts | Accepted | [Phase 11.4](../../PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md) |
| P11-ADR-036 | Transaction persistence is split across trust boundaries | Accepted | [Phase 11.4](../../PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md) |
| P11-ADR-037 | Multi-resource atomicity uses a recoverable state machine | Accepted | [Phase 11.4](../../PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md) |
| P11-ADR-038 | Transactions serialize per Runtime and detect external edits | Accepted | [Phase 11.4](../../PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md) |
| P11-ADR-039 | Active Runtime Binding commits only after required verification | Accepted | [Phase 11.4](../../PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md) |
| P11-ADR-040 | Interrupted transactions reconcile and are never blindly replayed | Accepted | [Phase 11.4](../../PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md) |
| P11-ADR-041 | Runtime owns local configuration application | Accepted | [Phase 11.4](../../PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md) |

### Provider validation

| ADR | Decision | Status | Source |
|---|---|---|---|
| P11-ADR-042 | Provider activation requires validation evidence | Accepted | [Phase 11.5](../../PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md) |
| P11-ADR-043 | Validation does not equal an execution guarantee | Accepted | [Phase 11.5](../../PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md) |
| P11-ADR-044 | Validation evidence contains no Secret Material | Accepted | [Phase 11.5](../../PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md) |
| P11-ADR-045 | Expired or invalidated evidence requires revalidation | Accepted | [Phase 11.5](../../PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md) |
| P11-ADR-046 | Validation stages remain independently observable | Accepted | [Phase 11.5](../../PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md) |
| P11-ADR-047 | Offline and live validation are distinct operations | Accepted | [Phase 11.5](../../PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md) |
| P11-ADR-048 | Endpoint validation is Provider-type-specific and fail closed | Accepted | [Phase 11.5](../../PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md) |
| P11-ADR-049 | Validation eligibility never activates a Runtime | Accepted | [Phase 11.5](../../PHASE11_5_PROVIDER_VALIDATION_PIPELINE_ADR.md) |

### Codex Provider Adapter and dry-run

| ADR | Decision | Status | Source |
|---|---|---|---|
| P11-ADR-051 | Codex integration uses an adapter boundary | Accepted | [Phase 11.6](../../PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md) |
| P11-ADR-052 | Dry-run precedes Provider activation | Accepted | [Phase 11.6](../../PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md) |
| P11-ADR-053 | Existing sessions are not implicitly migrated | Accepted | [Phase 11.6](../../PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md) |
| P11-ADR-054 | Unknown Codex compatibility fails closed | Accepted | [Phase 11.6](../../PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md) |
| P11-ADR-055 | Configuration changes are semantic and scope-limited | Accepted | [Phase 11.6](../../PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md) |
| P11-ADR-056 | Dry-run never resolves Provider Secret Material | Accepted | [Phase 11.6](../../PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md) |
| P11-ADR-057 | Runtime reconstructs the private candidate at apply time | Accepted | [Phase 11.6](../../PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md) |
| P11-ADR-058 | Codex pairing and Provider authentication remain separate | Accepted | [Phase 11.6](../../PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md) |
| P11-ADR-059 | Apply remains a Phase 11.4 Runtime transaction | Accepted | [Phase 11.6](../../PHASE11_6_CODEX_PROVIDER_ADAPTER_DRY_RUN_ADR.md) |

### Runtime Binding, activation, continuity, and rollback

| ADR | Decision | Status | Source |
|---|---|---|---|
| P11-ADR-061 | Runtime Binding is separate from Provider identity | Accepted | [Phase 11.7](../../PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md) |
| P11-ADR-062 | Activation requires the transaction lifecycle | Accepted | [Phase 11.7](../../PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md) |
| P11-ADR-063 | Existing sessions are not implicitly migrated | Accepted | [Phase 11.7](../../PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md) |
| P11-ADR-064 | Rollback requires verification | Accepted | [Phase 11.7](../../PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md) |
| P11-ADR-065 | Unknown Runtime state requires explicit recovery | Accepted | [Phase 11.7](../../PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md) |
| P11-ADR-066 | Only one Runtime Binding may be active per Runtime | Accepted | [Phase 11.7](../../PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md) |
| P11-ADR-067 | Active state commits only after layered verification | Accepted | [Phase 11.7](../../PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md) |
| P11-ADR-068 | Activation never performs automatic Provider fallback | Accepted | [Phase 11.7](../../PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md) |
| P11-ADR-069 | Activation uses a per-Runtime lock and admission fence | Accepted | [Phase 11.7](../../PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md) |
| P11-ADR-070 | Pairing and Provider activation remain independent | Accepted | [Phase 11.7](../../PHASE11_7_RUNTIME_BINDING_ACTIVATION_CONTINUITY_ROLLBACK_ADR.md) |

### Supplemental contract closure

| ADR | Decision | Status | Source |
|---|---|---|---|
| P11-ADR-071 | Codex Contract Evidence Boundary | Accepted | [Phase 11.10](../../PHASE11_10_PUBLIC_CONTRACT_EVIDENCE_CLOSURE.md) |
| P11-ADR-072 | Codex Managed Configuration Scope | Accepted | [Phase 11.10](../../PHASE11_10_PUBLIC_CONTRACT_EVIDENCE_CLOSURE.md) |
| P11-ADR-073 | Secret Cryptography Contract | Accepted | [Phase 11.10](../../PHASE11_10_PUBLIC_CONTRACT_EVIDENCE_CLOSURE.md) |
| P11-ADR-074 | Key Custody and Recovery Contract | Accepted | [Phase 11.10](../../PHASE11_10_PUBLIC_CONTRACT_EVIDENCE_CLOSURE.md) |
| P11-ADR-075 | Activation and Recovery Policy | Accepted | [Phase 11.10](../../PHASE11_10_PUBLIC_CONTRACT_EVIDENCE_CLOSURE.md) |
| P11-ADR-076 | Implementation Governance Contract | Accepted | [Phase 11.10](../../PHASE11_10_PUBLIC_CONTRACT_EVIDENCE_CLOSURE.md) |

Human review of PR #33 corrected P11-ADR-072/P11-ADR-075 without changing their
identifiers or titles. The broker now has two typed eligibility modes:
`COMMITTED_ACTIVE_USE` and the transaction-local
`CANDIDATE_ACTIVATION_VERIFICATION`. Candidate authorization never marks a
Binding active, never opens ordinary session admission, expires within 60
seconds, permits at most two durably counted broker invocations/resolutions,
and is never reconstructed after crash or uncertain Secret use.

### Historical aliases and superseded provisional allocations

Document-local labels in the Phase 11 design sequence are historical aliases,
not additional decisions:

- `ADR-001`–`ADR-009` map one-to-one to `P11-ADR-001`–`P11-ADR-009`.
- `ADR-011`–`ADR-019` map one-to-one to `P11-ADR-011`–`P11-ADR-019`.
- `ADR-021`–`ADR-041` map one-to-one to `P11-ADR-021`–`P11-ADR-041`.
- `ADR-11.5-041`–`ADR-11.5-048` map one-to-one to
  `P11-ADR-042`–`P11-ADR-049`.
- `ADR-051`–`ADR-059` map one-to-one to `P11-ADR-051`–`P11-ADR-059`.
- `ADR-061`–`ADR-070` map one-to-one to `P11-ADR-061`–`P11-ADR-070`.

The six provisional, unaccepted P11-ADR-071–076 titles recorded by
`PHASE11_CONTRACT_FREEZE_REVIEW.md` are superseded as allocations by the final
P11-ADR-071–076 titles above. No accepted decision is superseded, renumbered,
or reused. The Phase 11.8 and Phase 11.9 `BLOCKED` findings remain unchanged as
historical point-in-time reviews.

## Process

An ADR PR contains the context and evidence, not only the preferred option. A decision becomes `Accepted` only after the authorized maintainer approves it. Reversal creates a new ADR; the old one remains in history and points to its successor. Implementation must not silently contradict an Accepted ADR.
