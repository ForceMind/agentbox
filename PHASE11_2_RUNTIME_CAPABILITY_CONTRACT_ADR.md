# AgentBox Phase 11.2 — Runtime Capability Contract Architecture Decision Record

Status: **Proposed — design only, awaiting human approval**
Scope: Phase 11.2 read-only Runtime capability contract
Governance acceptance: The decision content is canonically registered as
P11-ADR-011 through P11-ADR-019 and **Accepted** in `docs/adr/README.md`.
The document-local `ADR-011` through `ADR-019` labels and the status above are
historical drafting metadata. Acceptance becomes repository-effective only
after the Phase 11.10 governance change is reviewed and merged into `main`.
Contextual alternatives and open questions remain historical; supplemental
P11-ADR-071 through P11-ADR-076 provide their governing resolution.
Architecture sources: `PHASE11_PROVIDER_MANAGER_PROPOSAL.md`,
`PHASE11_IMPLEMENTATION_PLAN.md`, and
`PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md`
Repository baseline: `ForceMind/agentbox` at
`1c2005de59b1c5063b260591206a8411c7e5b1a5`

This document defines a read-only contract. It does not authorize production
code, IPC changes, migrations, Runtime probes on a real host, configuration
writes, Secret access, process control, Provider activation, session mutation,
or changes to Codex, Claude, tmux, Git, or GitHub CLI integration. Accepted
Phase 0–10 architecture and the Phase 11.1 domain decisions remain unchanged.

## 1. Problem Statement

### 1.1 Why Provider Manager needs Runtime awareness

Provider Manager describes an AI execution backend and a proposed Runtime
Profile, but it cannot safely assume that an installed Runtime can consume that
profile. Before a Provider can later be validated or bound, the control plane
needs bounded answers to questions such as:

- Is the target Runtime installation present?
- Which public version can be detected?
- Which public capabilities are advertised?
- Is the corresponding Provider adapter available for that Runtime?
- Can AgentBox safely inspect the Runtime's managed state?
- Is Remote Control available independently of Provider support?
- Is the evidence current enough to create a plan?

Without a Runtime Capability Contract, the control plane would either guess
from versions and Provider metadata or reach directly into Runtime files and
processes. Both approaches violate the existing trust boundary.

### 1.2 Runtime capability is separate from Provider abstraction

Provider capability and Runtime capability answer different questions:

```text
Provider capability
    "Does this backend expose streaming/tool/reasoning behavior?"

Runtime capability
    "Can this installed Runtime and adapter observe or use a supported
     feature through its current public contract?"
```

A Provider may advertise streaming while a specific Codex version or wire API
cannot consume it. Codex Remote Control may be supported even when no Provider
adapter is available. Claude/tmux session inspection may be available while
Claude Provider selection remains unsupported.

Provider capability therefore cannot substitute for Runtime evidence, and
Runtime capability cannot activate a Provider. Compatibility is derived later
from both domains plus independently verified execution evidence.

### 1.3 Why direct Runtime manipulation is unsafe

Allowing the control plane to inspect or manipulate Runtime internals directly
would create several unsafe interfaces:

- a Web/API path to arbitrary processes or command execution;
- direct access to Codex/Claude credentials in Runtime HOME;
- reliance on private config/session/database formats;
- caller-controlled executable, argv, environment, path, PID, or signal;
- cross-user access to tmux or Project state;
- a shortcut around the non-root Runtime Executor and its peer-authenticated
  typed protocol;
- version-specific behavior silently becoming a permanent product contract.

The control plane needs observations, not a remote shell. Runtime facts must be
collected inside `agentbox-runtime` by a runtime-specific adapter, reduced to a
bounded typed result, and returned through the existing security boundary.

### 1.4 Required outcome

Phase 11.2 establishes a common evidence vocabulary and a conceptual request/
response contract for read-only discovery. It intentionally excludes every
mutation. A future operation may consult capability evidence, but it requires a
separate action-specific contract, policy decision, authorization, fresh
revalidation, and recovery design.

## 2. Runtime Capability Definition

### 2.1 Definition

A `RuntimeCapability` is a declared or observed ability of one identified
Runtime environment, collected by an approved Runtime Adapter and represented
as versioned, bounded evidence.

Examples include:

- Codex installation detected;
- Codex public version detected;
- Codex installation classification observed as standalone, npm, conflict, or
  unknown;
- Codex Remote Control command family advertised;
- individual Remote start, stop, pair, or status observation available;
- Codex Provider adapter available for the detected public contract;
- Claude installation and public version detected;
- Claude Remote Control command family advertised;
- tmux available;
- AgentBox-managed Claude session inspection available;
- Runtime authentication status observable through a public command;
- Runtime Profile validation supported;
- active-writer observation supported;
- public session/resume/discovery observation supported.

The v1 contract is extensible by capability name and schema version, but callers
cannot invent names. Every capability name belongs to a reviewed AgentBox enum
and one Runtime Adapter contract.

### 2.2 Capability is evidence, not permission

A capability observation does not authorize an action. For example:

```text
codex.remote.start = SUPPORTED
```

means the approved adapter found current evidence that the public operation is
advertised. It does not mean:

- the caller is authorized to start it;
- the operation will succeed now;
- no active session will be affected;
- the evidence is still fresh;
- Provider activation is safe;
- the Runtime is authenticated;
- a root or arbitrary process action is permitted.

Authorization remains a control-plane concern. Execution remains a later typed
Runtime operation. Every mutation must revalidate the required capabilities and
target state at execution time.

### 2.3 Capability is not a success guarantee

Capability discovery usually relies on public help, version, status, or
AgentBox-managed state. Those signals prove only their defined scope:

| Evidence | Proves | Does not prove |
|---|---|---|
| Public version | A bounded version probe succeeded | Authentication, compatibility, or mutation success |
| Public help | A command/option is advertised | The command will succeed on this host |
| Public auth status | Current public command reported an auth state | Provider credential validity or future session success |
| Managed marker/state | AgentBox-owned state matches expected identity | External process correctness or third-party service availability |
| Provider adapter available | AgentBox has an adapter for the observed contract | Provider endpoint or model compatibility |
| Session inspection available | Approved bounded managed-session inspection exists | Conversation continuity or private session visibility |

### 2.4 Capability observation structure

A capability observation should conceptually contain:

- capability contract/schema version;
- RuntimeInstallationID;
- Runtime type;
- stable capability name;
- capability outcome;
- evidence lifecycle;
- evidence class and adapter schema version;
- safe source version/fingerprint reference;
- observed time and expiry;
- bounded sanitized evidence/error codes;
- dependencies on other named capabilities, when relevant.

It must not contain raw stdout/stderr, file contents, credentials, process
environment, arbitrary process details, complete config, pane content, Project
content, private session identifiers, or caller-defined metadata.

### 2.5 Capability outcome and evidence lifecycle are separate

The contract uses two axes.

**Capability outcome** describes the observed result:

```text
SUPPORTED
UNSUPPORTED
UNAVAILABLE
UNAUTHENTICATED
BROKEN
UNKNOWN
```

**Evidence lifecycle** describes the quality/freshness of that result:

```text
UNKNOWN
DETECTED
VALIDATED
EXPIRED
```

Examples:

```text
Outcome: UNSUPPORTED
Lifecycle: VALIDATED
Meaning: current public evidence reliably says the feature is absent.

Outcome: SUPPORTED
Lifecycle: EXPIRED
Meaning: support was previously observed, but the evidence is too old for a
new plan or mutation.

Outcome: UNKNOWN
Lifecycle: DETECTED
Meaning: the Runtime was found, but the approved adapter could not safely
determine this capability.
```

This separation prevents `VALIDATED` from being mistaken for “supported” and
prevents stale support from remaining actionable.

## 3. Ownership Boundary

### 3.1 Control Plane ownership

The `agentbox` control plane owns:

- administrator intent;
- workflow state and policy;
- requested capability names from a fixed allowlist;
- RuntimeInstallationID and Provider-domain references;
- user approval and ConfirmationChallenge state;
- capability cache/read models and freshness policy;
- Job coordination and safe retry classification;
- Audit records and sanitized operator-facing diagnostics;
- decisions about whether evidence is sufficient to offer a future plan.

The control plane does not decide how to execute a probe and cannot submit a
command, path, environment, or parser rule.

### 3.2 Runtime ownership

The `agentbox-runtime` layer owns:

- installed Runtime tools and their resolved executable policy;
- Runtime HOME and local environment;
- public CLI probing through reviewed fixed operations;
- Runtime process and AgentBox-managed session observations;
- local tmux ownership and managed markers;
- Runtime Adapter selection and output parsing;
- raw transient probe output until it is reduced and discarded;
- current local evidence and observation time.

Runtime does not own control-plane authorization, user approval, Provider
selection intent, Audit policy, or the AgentBox SQLite database.

### 3.3 Adapter ownership

Each Runtime Adapter owns the mapping between stable AgentBox capability names
and the then-current public Runtime contract. It defines:

- fixed allowable probes;
- executable validation and fixed working directory;
- minimal environment policy;
- timeout and output bounds;
- conservative parsers;
- evidence class and expiration suggestions;
- capability dependencies;
- sanitized failure codes.

Adapters do not accept arbitrary operations from the control plane and do not
grant authorization.

### 3.4 Root Helper ownership remains unchanged

The root Helper owns only its already accepted fixed AgentBox lifecycle action
set. It is not part of Runtime capability discovery and gains no probe, command,
path, Provider, Secret, config, tmux, Codex, or Claude operation.

## 4. Read-Only First Contract

### 4.1 Contract purpose

The first contract answers only “what can be safely observed now?” It is not a
combined discover-and-fix operation.

Conceptually:

```text
Control Plane
    -> RuntimeCapabilityQuery
       - protocol version
       - request ID
       - RuntimeInstallationID
       - fixed capability names or approved capability set
       - cache/refresh intent from a small enum

Runtime
    -> RuntimeCapabilityReport
       - protocol version
       - RuntimeInstallationID
       - Runtime type
       - adapter ID/schema version
       - bounded safe Runtime version/classification
       - observation collection state
       - capability observations
       - observed/expires timestamps
       - sanitized finding codes
```

The exact wire schema is a later implementation artifact. This ADR fixes the
semantic boundary only.

### 4.2 Information Runtime may report

The read-only report may include:

- installed/not installed/unknown component state;
- bounded public version;
- safe installation classification;
- adapter availability and adapter schema version;
- public command-family capabilities;
- authentication state only when a public status operation supports it;
- AgentBox-managed Runtime/session count or state when exact ownership can be
  verified;
- Runtime service health in bounded categories;
- current capability outcome, evidence lifecycle, evidence class, and
  freshness;
- sanitized conflict/finding codes.

### 4.3 Information Runtime must not report

The contract excludes:

- raw command output or stderr;
- arbitrary executable or full caller-visible command line;
- credential/auth file contents or paths;
- environment variables or process environments;
- raw Runtime config or arbitrary config keys;
- general filesystem paths/listings;
- arbitrary PID/process lists or signals;
- unmanaged tmux session names, pane output, or socket paths;
- Project file content;
- prompts, completions, conversation history, JSONL, rollout, private Runtime
  database content, or private thread/session metadata;
- Secrets, tokens, Pair Codes, cookies, headers, or credential hints;
- root service state unrelated to the exact existing diagnostic policy.

### 4.4 Intentionally absent mutation

There is no capability-contract action for:

- start, stop, restart, kill, signal, attach, or send keys;
- edit, write, repair, chown, chmod, delete, or migrate files;
- create/activate/disable a Provider;
- create, read, rotate, revoke, or delete a Secret;
- change Runtime config or environment;
- install/update/remove a Runtime or package;
- accept Workspace Trust;
- run a Provider request;
- resume/rebind/migrate a session;
- invoke root Helper.

Existing Phase 5–8 typed operations remain separate and are not widened by this
contract.

### 4.5 Read-only does not mean harmless

Even observation can leak sensitive data or cause resource exhaustion. Every
probe must therefore use a fixed operation, minimal environment, fixed Runtime
HOME/cwd policy, bounded time/output/concurrency, no stdin, conservative
parsing, and sanitization. Expensive network/model requests are not capability
discovery and remain outside this contract.

## 5. Runtime Adapter Model

### 5.1 Definition

A `RuntimeAdapter` is a runtime-specific policy and translation component inside
`agentbox-runtime`. It turns a fixed AgentBox capability query into reviewed
public Runtime probes and converts their transient output into typed evidence.

Conceptually, an adapter provides:

- Runtime identity/type description;
- installation and version observation;
- capability discovery for a fixed enum;
- health/auth observation where public contracts permit;
- managed-session observation where AgentBox ownership can be proved;
- adapter/schema version and evidence metadata.

This is not a general-purpose plugin execution API. Adapters are reviewed
AgentBox code selected server-side, not uploaded code, caller scripts, dynamic
module names, or user-defined commands.

### 5.2 Why adapters are preferred

Adapters provide:

- isolation of third-party CLI behavior from stable control-plane models;
- capability detection rather than version-only enablement;
- independent Codex and Claude public-contract handling;
- conservative degradation when output changes;
- deterministic sanitized fixtures and parsers;
- one place to enforce executable, argv, environment, cwd, timeout, output, and
  cleanup policy;
- a future extension point without coupling the Provider domain to a specific
  config file.

Direct integrations would spread public/private Runtime assumptions across API,
Worker, UI, and database code, making security review and compatibility
degradation unreliable.

### 5.3 Adapter families

**Codex Runtime Adapter**

Observes Codex installation, public version/help/status, Remote Control command
capabilities, safe auth state, and future Provider-adapter availability.

**Claude Runtime Adapter**

Observes Claude installation, public version/help/auth capabilities, tmux
availability, and exact AgentBox-managed Claude session state. It does not
expose a Claude Provider abstraction in v1.

**Supporting tool adapters**

tmux, Git, and GitHub CLI retain their existing bounded adapter contracts. They
may contribute prerequisite observations but do not become AI Providers.

### 5.4 Adapter capability dependency

Capabilities may declare dependencies, for example:

```text
codex.remote.pair
    requires codex.installed
    requires codex.remote_control

claude.session.inspect_managed
    requires claude.installed
    requires tmux.available
    requires agentbox_managed_session_marker_contract

codex.provider_profile.validate
    requires codex.installed
    requires codex.provider_adapter.available
    requires current public config schema evidence
```

A missing dependency yields a typed unsupported/unavailable/unknown result; it
does not cause the adapter to try an undocumented fallback.

## 6. Codex Capability Contract

### 6.1 Reused known behavior

Phase 11.2 may conceptually reuse the already reviewed Phase 5 observation
boundary:

- resolve Codex from Runtime-owned fixed PATH policy;
- validate the selected executable and recheck its fingerprint;
- run bounded public `--version` and help probes with fixed argv;
- classify installation evidence conservatively as standalone, npm, conflict,
  or unknown;
- observe `remote-control` only when public help advertises it;
- observe start, stop, pair, and status independently;
- observe authentication only through a detected public status command;
- use strict same-UID/managed evidence where a bounded process observation is
  already approved;
- degrade changed, malformed, localized, timed-out, or incomplete evidence to
  unknown/unsupported rather than guessing.

This ADR documents the boundary; it does not execute those probes or modify the
existing Codex integration.

### 6.2 Conceptual Codex capability names

Potential stable AgentBox capability names include:

```text
codex.installed
codex.version.detectable
codex.installation.classifiable
codex.authentication.observable
codex.remote_control.available
codex.remote.start
codex.remote.stop
codex.remote.pair
codex.remote.status
codex.provider_adapter.available
codex.provider_profile.validate
codex.active_writer.observe
codex.session.resume.observe
codex.session.discovery.observe
```

Names after the existing Remote capabilities are future design candidates and
remain `UNKNOWN` or `UNSUPPORTED` until then-current public contracts are
validated. Their presence in this ADR does not enable an operation.

### 6.3 Known behavior versus future assumptions

**Known/reviewed conceptual evidence boundary**

- Public version/help can identify installation and advertised command
  capabilities.
- Remote start/stop/pair/status are independent capabilities.
- Successful version/help does not prove authentication.
- Remote state may remain unknown when public status is absent and strict
  process evidence is insufficient.
- Installation classification is best-effort evidence, not ownership.

**Future assumptions explicitly prohibited**

- a particular Codex Provider/config TOML field or block is permanent;
- an observed `model_provider` ID is a stable AgentBox identity;
- config changes are hot-reloaded;
- a restart preserves Pairing, Remote, thread, or context state;
- a thread belongs to a Provider because a private file says so;
- active writer, session resume, discovery, or context continuity can be
  inferred from private SQLite/JSONL/rollout data;
- version alone enables a Provider mutation.

### 6.4 Codex evidence trust

Public CLI output is untrusted third-party text until bounded and parsed. A
successful conservative parser can produce scoped evidence; raw text is then
discarded. The control plane trusts the typed report came from the expected
Runtime peer, but must still evaluate its evidence class, age, adapter version,
and executable fingerprint before relying on it.

## 7. Claude Capability Contract

### 7.1 Runtime-oriented scope

Claude remains a Runtime/session concern. The capability contract may observe:

- Claude installed and public version detectable;
- public Remote Control command family advertised;
- public auth status observable or unknown;
- tmux available;
- project path resolvable by the existing Project Registry boundary;
- an exact AgentBox-managed session present, absent, needs interaction, broken,
  or unknown;
- managed-session inspection available.

It does not define a Claude AI Provider, endpoint, model, Credential, Runtime
Profile, or Provider Binding.

### 7.2 tmux relationship

tmux is a supporting Runtime capability and session owner, not a Provider.
Observation is limited to the current `agentbox-runtime` user's exact
AgentBox-managed session name and marker policy. The contract does not expose:

- general tmux server/socket selection;
- unmanaged session names;
- pane content;
- terminal input or key sending;
- arbitrary tmux commands;
- root or another user's tmux state.

Recent Claude pane output remains a separate sensitive authenticated flow and
is not capability evidence.

### 7.3 Future extension boundary

A future Claude Provider adapter remains disabled until an official public
Claude Code contract supports external Provider selection, credential
references, config validation, lifecycle effects, and continuity. It requires a
separate ADR and typed capability namespace; Codex/OpenAI capability names do
not automatically apply.

## 8. Capability Lifecycle

### 8.1 Evidence lifecycle states

| Lifecycle | Meaning | Permitted use |
|---|---|---|
| `UNKNOWN` | No acceptable current evidence exists. | Display unknown; do not plan or mutate. |
| `DETECTED` | A component or evidence source was found, but the capability has not met the validated evidence rule. | Diagnostics and follow-up probing only. |
| `VALIDATED` | An approved adapter produced evidence satisfying the capability's current contract. | May inform a plan while fresh; still not authorization. |
| `EXPIRED` | Previously accepted evidence exceeded TTL or was invalidated. | Display historical state with timestamp; refresh before planning. |

`VALIDATED` can accompany an outcome of `SUPPORTED`, `UNSUPPORTED`,
`UNAVAILABLE`, `UNAUTHENTICATED`, or `BROKEN`. It describes confidence in the
observation, not a positive result.

### 8.2 Refresh

Refresh is a fixed contract operation, not an arbitrary command. The control
plane may request:

```text
CACHE_ACCEPTABLE
REFRESH_IF_EXPIRED
FORCE_FRESH_READ_ONLY
```

The Runtime Adapter decides the fixed probes. A caller cannot supply commands,
flags, paths, timeouts, or parser patterns. Force refresh remains bounded and
rate-limited.

Every future mutation rechecks its required capabilities and target state even
if cached observations are still within TTL.

### 8.3 Caching and freshness

The control plane may later cache non-secret observations. Each record retains
observation time, expiry, evidence class, adapter version, and Runtime
fingerprint reference. There is no timeless capability flag.

TTL should be capability-specific:

- installation/version can generally live longer;
- process, auth, Remote, active-writer, and session observations expire quickly;
- unsupported public help evidence expires when executable/adapter version
  changes;
- any Runtime executable fingerprint change invalidates dependent evidence;
- Runtime service restart, adapter upgrade, config ownership change, or clock
  anomaly may invalidate affected observations.

Exact TTL values remain an open policy decision. Stale evidence is visible but
cannot satisfy a future action precondition.

### 8.4 Partial and changed evidence

Capability collection is per capability. One failed probe does not erase valid
independent observations, and one successful probe does not fill missing ones.
If the Runtime version or public output changes beyond the adapter fixture, the
affected capability becomes `UNKNOWN`/`EXPIRED`; AgentBox does not try an old or
private fallback.

### 8.5 Cache authority

Cached data is a control-plane projection, not the source of Runtime truth. The
Runtime owns current observation. A future plan binds the exact cached evidence
revision but mutation must obtain a fresh Runtime report and reject changed
state.

## 9. Security Model

### 9.1 Arbitrary command execution prevention

The capability query contains only protocol version, request ID,
RuntimeInstallationID, fixed capability enum, and small refresh policy enum. It
cannot express:

- shell or script;
- executable or argv;
- environment or cwd;
- file/config path or content;
- PID, signal, tmux target, or key input;
- systemd unit or package;
- URL, Provider request, or arbitrary network destination.

Adapters map fixed names to reviewed internal probes. Unknown names and fields
fail closed.

### 9.2 Privilege escalation prevention

Discovery runs as `agentbox-runtime`, never root. The existing Runtime socket
requires filesystem permissions plus peer UID/GID verification through
`SO_PEERCRED`, protocol versioning, exact message shape, frame cap, timeout, and
bounded connection behavior. Runtime does not call the root Helper, sudo,
setuid, arbitrary systemctl, or package managers.

The API/Worker continues as `agentbox` and receives only typed observations. It
cannot traverse Runtime HOME or manipulate Runtime processes/files directly.

### 9.3 Secret exposure prevention

Probe environments are rebuilt from the existing minimal allowlist. Token- or
key-bearing control-plane variables are not inherited. Adapters do not read
private auth/config files to infer capability. Public auth status, when
available, is reduced to authenticated/unauthenticated/unknown without raw
output.

The report excludes credential values, hints, auth paths, Pair Codes, raw
Provider responses, pane output, prompts, completions, and config. Logs and
Audit record capability name, evidence class, safe code, age, and result only.

### 9.4 Runtime takeover prevention

The contract has no mutation verbs and no generic dispatch primitive. Capability
names cannot be transformed into executable names or action strings. The
control plane cannot select a Runtime path, tmux server, process, or session
target.

A compromised same-UID Runtime process remains a residual risk under the
existing `agentbox-runtime` trust model. Peer authentication proves the server
identity expected by AgentBox, not that every same-UID third-party process is
non-malicious. Dedicated Runtime identity, fixed executable policy, and
systemd/filesystem boundaries remain required.

### 9.5 Information minimization

Capability reports expose the minimum facts needed for orchestration. Detailed
diagnostics remain separately authenticated and sanitized. The UI must not
display evidence text as trusted HTML or convert unknown into a positive state.

## 10. Failure Handling

### 10.1 Runtime unavailable

If the Runtime service/socket cannot be reached or the expected peer cannot be
verified:

- collection state is `RUNTIME_UNAVAILABLE` or `PEER_REJECTED`;
- cached observations remain historical and become expired according to policy;
- no capability is changed to unsupported merely because Runtime is down;
- no direct local fallback is used for Provider planning or mutation;
- existing separately approved diagnostic-only fallback behavior is not
  expanded by Phase 11.2.

### 10.2 Capability mismatch

If Provider/Profile requirements do not match Runtime capabilities:

- report each mismatched capability independently;
- classify compatibility as unsupported/incompatible/unknown according to
  evidence;
- do not coerce options, substitute a model, change wire protocol, or select a
  different Provider;
- do not call an undocumented fallback.

### 10.3 Unsupported operation

If the public Runtime contract does not advertise a capability, return a stable
`UNSUPPORTED` outcome with validated evidence when possible. The control plane
does not offer the corresponding future operation. Unsupported is not an error
that triggers a legacy/private probe.

### 10.4 Version incompatibility

If the Runtime can be identified but no reviewed adapter schema supports its
public behavior:

- safe installation/version facts may remain detected;
- affected capabilities become unknown or unsupported, never guessed from the
  version number;
- Provider activation remains unavailable;
- diagnostics identify the adapter/contract mismatch without raw output;
- a new reviewed fixture/adapter version is required.

### 10.5 Timeout, malformed, or excessive output

Timeout, decode/parser failure, non-zero status, or output cap produces a stable
bounded finding. The affected capability becomes `UNKNOWN` or `BROKEN` based on
its contract. The adapter cleans up only the process group it created and does
not kill an existing Runtime/session.

### 10.6 Partial collection

A report may be partially successful. Each capability retains its own outcome
and lifecycle. Overall collection state cannot mask partial failure, and the
control plane must not infer one capability from another.

### 10.7 Stale or changed state

If executable fingerprint, adapter schema, Runtime service instance, or other
bound evidence changes, dependent observations expire. A future plan is stale
and must be regenerated. No mutation is replayed automatically.

## 11. Future Mutation Boundary

### 11.1 Capability discovery is not a mutation protocol

The capability contract may inform whether a future action is available, but it
cannot carry that action. A future mutation requires a separate contract with:

- one fixed action enum;
- exact target IDs and expected revisions;
- fresh required capabilities;
- policy and authorization decision;
- recent authentication and user confirmation where appropriate;
- deterministic preflight and impact plan;
- per-Runtime serialization;
- bounded execution and output;
- idempotency/crash semantics;
- audit and recovery/rollback verification.

### 11.2 Provider activation

Provider activation requires a distinct Config Transaction/Runtime Binding
contract. It must validate Provider, Credential, Runtime Profile, current config
fingerprint, active writer/session state, lifecycle impact, and rollback scope.
No raw config or Secret enters the capability report.

### 11.3 Runtime configuration update

Configuration mutation belongs to a typed Runtime-specific Provider Config
Adapter plus shared Config Transaction Manager. It must preserve unrelated
settings and use atomic, revision-bound, rollback-verified behavior. The
capability contract only reports whether a validated adapter capability exists.

### 11.4 Controlled restart

A required Codex restart remains an existing Remote lifecycle concern and must
use the approved non-root typed manager. The capability report may state that
restart support is observed; it cannot restart anything. Claude/tmux sessions
remain separate.

### 11.5 Rollback

Rollback requires a distinct transaction and verification contract restoring
config, binding, Secret reference, permissions, lifecycle, and applicable
continuity state. `rollback.available` capability evidence would not itself
prove that a particular rollback snapshot is valid.

### 11.6 No generic future mutation interface

Future operations are separate allowlisted contracts. AgentBox will not add
`runtime.execute`, `runtime.command`, `runtime.write_file`, `runtime.signal`, or
a generic `runtime.mutate` endpoint.

## 12. Architecture Decisions

The decisions below are **Proposed** until human approval. Their numbering is
scoped to the Phase 11 architecture series requested for this document and does
not alter the repository's existing accepted ADR numbering.

### ADR-011 — Runtime capability information is contract based

**Status:** Proposed

**Decision**

Runtime capability observations use stable AgentBox capability names, versioned
typed reports, explicit evidence classes, bounded values, timestamps, and
sanitized finding codes. Runtime-specific adapters produce the evidence.

**Rationale**

A contract isolates changing third-party behavior from the control plane and
prevents UI/API/Worker code from parsing raw Runtime output or relying on
private state.

**Consequences**

- Unknown capability names and fields fail closed.
- Public-contract fixtures and adapter schema versions are required.
- Raw Runtime output is transient and never becomes the control-plane model.

### ADR-012 — Control Plane does not directly modify Runtime internals

**Status:** Proposed

**Decision**

The control plane cannot read or write Runtime files, execute Runtime tools,
inspect arbitrary processes/tmux state, or supply paths/commands/environments.
All approved Runtime interaction remains behind `agentbox-runtime` adapters and
typed protocols.

**Rationale**

Direct access would collapse the accepted UID, credential, process, Project,
and root boundaries and turn AgentBox into an unrestricted remote controller.

**Consequences**

- Runtime owns local evidence collection and output reduction.
- Root Helper gains no capability-discovery action.
- Provider Manager remains orchestration, not execution.

### ADR-013 — Read-only capability discovery precedes Runtime mutation

**Status:** Proposed

**Decision**

The first Phase 11 Runtime contract is observation-only. Provider activation,
config update, controlled restart, and rollback require later separate contracts
and cannot be embedded in discovery.

**Rationale**

Read-only evidence allows compatibility and security boundaries to be tested
before any active Runtime or config can be affected.

**Consequences**

- Phase 11.2 exposes no mutation.
- Capability presence never grants permission.
- Later mutation must refresh and revalidate capability evidence.

### ADR-014 — Capability outcome and evidence lifecycle are separate

**Status:** Proposed

**Decision**

Every observation records an outcome independently from evidence lifecycle and
freshness.

**Rationale**

“Validated” can reliably mean unsupported, and previously supported evidence
can expire. Combining these axes would produce unsafe positive states.

**Consequences**

- Stale support cannot satisfy action preconditions.
- Unsupported and broken results can still carry validated evidence.
- UI/API must present result and freshness separately.

### ADR-015 — The existing peer-authenticated Runtime UDS remains the transport

**Status:** Proposed

**Decision**

Capability reports use the existing Unix Domain Socket trust boundary with
protocol versioning, exact schemas, frame/time bounds, filesystem permissions,
and `SO_PEERCRED` UID/GID validation. Phase 11.2 does not introduce an HTTP
Runtime endpoint or a second privileged socket.

**Rationale**

The accepted single-host architecture already separates control plane and
Runtime with a non-network, peer-authenticated typed channel. A new transport
would add attack surface without solving a Phase 11.2 problem.

**Consequences**

- The open implementation choice is message-family/version evolution within
  the existing boundary, not Unix socket versus HTTP.
- Capability requests cannot cross into Helper protocol.
- No public listener or proxy setting changes.

### ADR-016 — Runtime Adapters use public contracts and fixed probes

**Status:** Proposed

**Decision**

Codex and Claude capability evidence comes only from reviewed public CLI/status
contracts and exact AgentBox-managed state. Adapters use fixed probes and
conservative parsers; private files and caller-defined commands are prohibited.

**Rationale**

Runtime behavior changes independently. Adapters allow safe degradation and
fixture review without making private formats product contracts.

**Consequences**

- Version alone never enables a capability.
- Changed/unknown output degrades to unknown/unsupported.
- Codex and Claude capability namespaces and parsers remain separate.

### ADR-017 — Capability evidence never authorizes mutation

**Status:** Proposed

**Decision**

Capability discovery can inform planning and UI availability but cannot approve
or execute an operation. Authorization, confirmation, target revisions,
preflight, fresh revalidation, and recovery belong to each future mutation
contract.

**Rationale**

Support evidence can be stale and says nothing about actor authority or current
session safety.

**Consequences**

- No “supported means allowed” shortcut exists.
- Cached evidence is never sufficient alone for mutation.
- Every future action remains explicitly typed and audited.

### ADR-018 — Capability reports minimize sensitive Runtime information

**Status:** Proposed

**Decision**

Reports contain bounded statuses, versions/classifications, evidence metadata,
and safe codes only. They exclude raw output, private paths/config/session
state, process environments, Secrets, Pair Codes, prompts, and model output.

**Rationale**

Observation is itself an information boundary. The control plane does not need
raw Runtime data to orchestrate safely.

**Consequences**

- Detailed diagnostics remain separate and sanitized.
- Capability Audit metadata is allowlisted.
- Secret/pane/config canary scans remain mandatory in later implementation.

### ADR-019 — Claude capability remains Runtime/session scoped

**Status:** Proposed

**Decision**

Phase 11.2 may report Claude installation, public capability, tmux prerequisite,
and exact managed-session inspection capability, but it defines no Claude
Provider capability or binding.

**Rationale**

Claude Provider selection lacks an approved public contract and must not inherit
Codex/OpenAI assumptions.

**Consequences**

- Claude remains Runtime-only as decided in ADR-003.
- Future Provider support needs a separate ADR and contract namespace.
- Codex Provider activation cannot affect Claude state.

## 13. Open Questions

The following decisions remain unresolved for later design or implementation
approval:

1. **Capability schema versioning:** Is there one Runtime report schema with
   independently versioned capability payloads, or a version per adapter family?
2. **Message-family evolution:** Should Phase 11 capability queries extend the
   current Runtime V1 action family or introduce a new versioned read-only
   message family over the same UDS?
3. **Cache lifetime:** What TTL applies to installation, version, auth, Remote,
   process, active-writer, session, and Provider-adapter evidence?
4. **Invalidation:** Which Runtime restart, executable/config fingerprint,
   adapter upgrade, clock, or ownership events invalidate which capabilities?
5. **Refresh rate:** What per-capability rate limits and concurrency budget
   prevent read-only probes from exhausting the Runtime?
6. **Runtime authentication:** Which current public Codex/Claude auth status
   operations are sufficiently stable, and how is `unknown` represented when no
   public status exists?
7. **Trust policy:** Which evidence classes may be shown diagnostically, used in
   a plan, or required to be freshly validated before a later mutation?
8. **Compatibility policy:** Which Runtime capabilities are mandatory for an
   Official OpenAI versus OpenAI-compatible Runtime Profile?
9. **Provider adapter capability:** What current public Codex evidence is
   sufficient to report `codex.provider_adapter.available`?
10. **Active-writer evidence:** Does Codex expose a supported public signal, and
    what happens when it remains unknown?
11. **Session inspection:** Which public session/resume/discovery evidence is
    safe to expose without using private state?
12. **Safe version detail:** Should exact patch/build versions be persisted, or
    only bounded normalized values plus a fingerprint reference?
13. **Diagnostic detail:** Which installation conflict information is useful
    without exposing absolute paths or unrelated process state?
14. **Cache persistence:** Should observations survive AgentBox restart, and if
    so must every persisted observation start expired until Runtime revalidation?
15. **Local Provider future:** Which local endpoint prerequisites belong to
    Runtime capability without introducing process/model lifecycle management?
16. **Real-host validation:** Which probes are safe on an existing production
    Runtime, and which require a dedicated fixture/test Runtime identity?

The IPC transport question is resolved by the accepted architecture: use the
existing peer-authenticated Runtime UDS. HTTP is not proposed. The remaining IPC
question concerns schema/message versioning within that boundary.

## Decision Outcome if Approved

Approval authorizes only this semantic contract and the Proposed ADR decisions.
It does not authorize code or live Runtime observation. The recommended next
phase is **Phase 11.3 — Secret Boundary Design**, beginning with architecture
decisions for Linux Secret storage, encryption/key custody, local Secret
ingress, backup, rotation, revocation, and deletion. No Secret implementation
should begin until that design is separately approved.
