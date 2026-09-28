# ADR 0009: AgentBox 工作台身份与内容边界

## Status

Accepted as a software architecture decision on 2026-09-28 under the Owner-approved
[workbench integration plan](../project/WORKBENCH_INTEGRATION_PLAN.md).
This ADR does not admit a content transport or a new host capability. Exact A3
wire schemas, content budgets, sensitive-file policy, and client qualification
remain separate acceptance work.

## Context

AgentBox already has a formal Project, one durable Web Agent Workspace (WAW)
record for each Project/AgentType, a separate administrator Web Session, and
Runtime-owned Project and process authority. The workbench must show tabs,
files, changes, and later conversations without treating a UI tab or a local
filesystem path as an authorization grant. Upstream workspace and agent record
semantics differ, so importing their IDs or persistence directly would create
competing authorities.

## Decision

### Identity and ownership

- A READY Project ID remains the only workbench entry point to code. The
  Runtime resolves the Project's registered relative path under its fixed root.
  A request cannot supply a host cwd, executable, argv, shell, environment map,
  arbitrary file root, or Provider Secret.
- Project identity, WAW identity, conversation identity, and a browser tab are
  distinct. The existing deterministic WAW ID continues to represent one
  Project/AgentType pair. A tab is local navigation state only; opening or
  restoring one never starts, resumes, adopts, connects, or stops a Runtime.
- A future conversation records its Project, AgentType, execution kind,
  generation, Runtime binding, vendor handle reference, and current turn as
  separate typed fields. It cannot reuse the administrator login Session row
  or change the meaning of the current WAW record. Its persistent Control
  Plane metadata excludes prompt and terminal bytes.
- Existing Project, Job, WAW generation, binding revision, epoch, and exact
  Stop authorities are the source of truth. A new UI list can project them;
  it cannot create a second Job queue, supervisor, or stop owner.
- ProviderDefinition and credential reference belong to Phase 11. A Claude or
  Codex AgentType is not a Provider Definition and does not grant credential
  configuration authority.

### Workbench observation

- The client may display a cached bounded status with its observation time,
  but marks it stale after interruption and reconciles from the server on
  return. A cached row never authorizes an action. Late observations from an
  older request, generation, or binding cannot re-enable controls.
- Workbench tabs may point to Project overview, WAW session, Changes, and later
  conversation views. Closing a tab changes navigation only. Detach,
  interrupt turn, archive, Resume, and exact Stop remain explicit distinct
  actions with their own response states and failure handling.
- Attention is a read-only bounded projection of existing Job and Runtime
  observations until a later structured Approval contract is implemented. A
  terminal string is never parsed into a fabricated approval or test result.

### Content authority

- The A1 Changes tree is a pure in-memory renderer. Its file path is display
  data, not filesystem authority. It accepts only a future A3 typed, validated
  Diff summary; A1 introduces no API, file access, or Runtime process path.
- Future Files/Changes requests name a registered READY Project and a bounded
  relative path or opaque Runtime file ID. The Runtime owns descriptor-bound
  resolution and rejects traversal, symlink escape, nonregular objects, and
  access outside the approved Project. The exact A3 API and schema will state
  size, pagination, binary, encoding, cancellation, and sensitivity limits.
- Content bodies, file text, patch text, prompts, tool arguments, CLI output,
  and vendor history are not Control Plane metadata or Audit payloads.
  API/Worker never read Runtime HOME or Provider Secret material. A3 requires
  a separately versioned content admission and encrypted path compatible
  with the existing WAW authority boundary; it cannot reuse terminal frame
  types with different meanings or enable a plaintext fallback.
- Git content extraction never accepts free-form command strings or git
  arguments and must disable external diff, textconv, hooks, and pager effects.
  A3 starts read-only. Editing, deletion, staging, commit, and generic shell
  capabilities are outside this ADR.

### Persistence and recovery

- New database changes are additive, use explicit Alembic migrations, and
  preserve existing Project and WAW rows. Content retention lives in the
  Runtime authority domain; the exact A3/A6 policy must precede storage.
- Client input with uncertain acknowledgment is queried, not replayed.
  History discovery alone does not grant attach/Resume/Stop. A returned vendor
  handle is verified against the current Project, Runtime, execution kind,
  generation, and vendor capability before any operation.
- exact Stop success requires the existing owned process scope and cleanup
  proof. A provider turn/interrupt response is insufficient.

## Alternatives considered

- Adopting an upstream daemon, database, workspace ID, and mobile app as a
  second product would conflict with AgentBox's single administrator,
  privilege-separated Runtime, and current deployment/update path.
- Letting the browser send a cwd or command to a general terminal service
  would bypass the registered Project and fixed Runtime action boundary.
- Storing full chat and file content in the Control Plane would widen API,
  Worker, backup, and audit exposure beyond their accepted authority.

## Consequences and validation

The first migrated code is limited to the Changes tree and ordering behavior.
It uses an AgentBox-local typed Diff summary, preserves caller metadata, and
does not import an upstream protocol or executable service. A3 and A6 must
each produce their exact schemas, source/permission tests, negative cases,
recovery evidence, and host qualification as applicable before claiming a
user-visible content or structured-session feature.

The first A3 implementation slice is the
[Project-scoped Git Changes metadata contract](../WORKBENCH_A3_GIT_CHANGES.md).
It returns bounded path/status observations only; it does not grant content
authority or close this ADR's patch, sensitive-file and client requirements.

The acceptance evidence for this ADR is the Owner-approved plan and current
code-boundary review. It is not an independent security review or a real-host
qualification. Security-critical implementation will follow the repository's
review and CI requirements before merge.
