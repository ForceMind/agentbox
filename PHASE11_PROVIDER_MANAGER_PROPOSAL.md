# AgentBox Phase 11 — Provider / Secret / Runtime Continuity Architecture Proposal

Status: **Planning proposal only — no implementation authorized**
Repository baseline: `ForceMind/agentbox` at `1c2005de59b1c5063b260591206a8411c7e5b1a5`
Release baseline: `v0.3.0-rc.1`
Audience: product owner, security reviewers, Runtime maintainers, and implementers

Governance note: This proposal preserves the original design context and open
alternatives. The accepted canonical decisions in `docs/adr/README.md` and the
supplemental closure in `PHASE11_10_PUBLIC_CONTRACT_EVIDENCE_CLOSURE.md`
control wherever this planning document presents an unresolved or broader
alternative.

## 1. Executive Recommendation

Phase 11 should add a runtime-neutral Provider domain without changing AgentBox's
accepted process or privilege architecture:

```text
Browser / ordinary CLI
        |
        | non-secret metadata, plans, status, confirmations
        v
agentbox API / Worker
        |
        | typed, versioned UDS requests; never raw keys or raw config
        v
agentbox-runtime
        +-- RuntimeProviderCoordinator
        +-- Runtime-specific ProviderConfigAdapter
        +-- RuntimeSecretBackend
        +-- ProviderTestExecutor
        +-- RuntimeContinuityProbe
        |
        +-- Codex / future supported Runtime

root Helper
        +-- unchanged fixed AgentBox lifecycle actions only
        +-- no Provider, Secret, config, model, or Runtime credential actions
```

The control plane owns Provider metadata, administrator intent, durable Jobs,
compatibility observations, and audit metadata. The Runtime identity owns Secret
material, generated Runtime configuration, Runtime process environment, Provider
requests, and continuity probes. A Provider activation is a revision-bound,
recoverable transaction. It is not a TOML editor and is not a Remote Control
operation.

The recommended first implementation scope is **Linux + Codex only**. The domain
and interfaces remain runtime-neutral, but Claude Provider support must remain
disabled until Claude exposes a suitable current public configuration contract.
OpenAI-compatible and local Providers may be represented in the domain, but may
only be activated after their individual capability and security gates pass.

This proposal does not authorize creating a Secret Store, reading an API key,
editing Codex configuration, restarting a Runtime, switching a Provider, changing
Remote Control, or migrating a session.

## 2. Architectural Invariants

Phase 11 must preserve the accepted architecture and the following invariants.

| Boundary | Invariant |
|---|---|
| Web/API | Runs as `agentbox`, binds to `127.0.0.1:8787` by default, and never receives or returns raw Provider credentials. |
| Worker | Runs as `agentbox`; coordinates typed Jobs and non-secret state but cannot read Runtime HOME or Provider Secret material. |
| Runtime Executor | Runs as `agentbox-runtime`; is the only AgentBox process allowed to inject a Provider Secret into a Runtime process. |
| Runtime HOME | Remains owned by `agentbox-runtime`; root and existing root Codex/Claude credentials are never copied, adopted, or changed. |
| Runtime UDS | Remains versioned, peer-authenticated, size-bounded, timeout-bounded, and typed. It accepts no executable, argv, shell, environment map, raw path, or raw config. |
| Root Helper | Retains only its fixed AgentBox lifecycle enum. It gains no Provider, Secret, package, file, systemctl-unit, or Runtime action. |
| Projects | Remain owned by `agentbox-runtime`; Provider activation does not change Project ownership or content. |
| Remote access | Remains user-managed through Tailscale, VPN, Cloudflare Tunnel, or an HTTPS reverse proxy. Phase 11 changes no SSH, firewall, proxy, or tunnel configuration. |
| Database | Remains SQLite owned by `agentbox`; it stores non-secret Provider state only. Runtime still does not open the application database. |

Any implementation that needs a new privileged identity, lets `agentbox` read
Runtime secrets, expands Helper actions, changes the loopback default, or gives
the Runtime direct database access requires a Proposed ADR and human approval.

## 3. Current Problem Analysis

### 3.1 Remote Control and Provider selection answer different questions

Remote Control answers:

- Is Codex installed and publicly capable of Remote Control?
- Can AgentBox start, stop, observe, or pair it through supported public CLI
  behavior?
- Is the Remote process connected, stopped, broken, or unknown?

Provider Management answers:

- Which service, endpoint, protocol, model, and credential should new Runtime
  requests use?
- Is that Provider reachable, authenticated, protocol-compatible, and usable by
  the selected Runtime?
- What configuration and lifecycle change is required to activate it?

These are independent axes. A Remote session can be connected while its Provider
is unavailable. A Provider API request can succeed while Codex Remote Control,
thread resume, context continuity, or discovery fails. Pairing authenticates the
Remote Control relationship and must not be treated as a model Provider
credential.

### 3.2 Coupling the two domains creates unsafe failure modes

If Provider selection is added to the existing Remote lifecycle methods, a
single action could silently rewrite Runtime configuration, expose a key,
restart a process, invalidate a thread, and then report only “Remote connected.”
That would hide the most important compatibility failures and make rollback
ambiguous.

Coupling would also encourage unstable identities. A concrete Provider endpoint
or a current Codex `model_provider` name is not a durable Remote session identity.
Base URLs, protocols, model names, and public Codex configuration schemas can
change independently of an AgentBox-managed Remote connection.

### 3.3 Required separation

The domains therefore have distinct authorities:

```text
RemoteControlManager
    owns: detect / start / stop / pair / Remote state

ProviderManager
    owns: Provider definitions / active selection / test orchestration

RuntimeContinuityManager
    owns: switch impact / writer safety / resume-context-discovery evidence

RuntimeSecretBackend
    owns: Provider Secret material within the Runtime identity

ProviderConfigAdapter
    owns: mapping typed intent to the current public Runtime config contract
```

Provider activation may request a lifecycle transition from the existing Remote
Control Manager when current public evidence proves it is required. It does not
gain its own daemon manager and does not call the root Helper.

## 4. Provider Domain Model

### 4.1 ProviderDefinition

A `ProviderDefinition` is non-secret, administrator-visible metadata describing
one concrete Provider target. It is not a credential, session, Runtime process,
or config file.

Required conceptual fields:

- opaque `ProviderDefinitionID`;
- identity schema version;
- display name;
- typed Provider kind;
- normalized endpoint identity where applicable;
- explicit wire/API protocol;
- model identifier;
- supported Runtime types;
- versioned, adapter-specific typed options;
- credential requirement and opaque `CredentialID`, if any;
- enabled/lifecycle state;
- latest compatibility classification and evidence freshness;
- revision and timestamps.

Provider identity should include the Provider kind, normalized endpoint, and wire
protocol. Changing those identity inputs normally creates a new definition or a
reviewed migration; it must not silently reuse the old identity. Changing only
Secret material is credential rotation and does not change Provider identity.

There must be no generic option dictionary that can express arbitrary config
keys, headers, environment variables, file paths, executables, or command-line
arguments. Each adapter publishes a versioned typed options schema.

### 4.2 Credential and SecretRecord

The proposal distinguishes control-plane credential metadata from Secret
material:

```text
Credential metadata in AgentBox DB
        |
        | opaque secret reference only
        v
SecretRecord in RuntimeSecretBackend
        |
        | decrypted only inside agentbox-runtime for an allowed operation
        v
child Runtime environment or trusted in-memory Provider request
```

`Credential` is non-secret metadata describing a Provider authentication need:

- opaque `CredentialID`;
- credential kind, such as API key or no credential;
- Provider association;
- opaque Runtime Secret reference;
- Secret version, configured/missing/rotation state, and timestamps;
- revision and safe last-validation state.

It never contains the value, prefix, suffix, reversible hint, hash of a
low-entropy key, Authorization header, or environment value.

`SecretRecord` exists only inside the Runtime Secret backend. It contains a
versioned encrypted envelope and the minimum metadata needed to decrypt and
rotate it. The application database does not store the ciphertext. AgentBox
APIs and ordinary CLI output cannot retrieve a Secret, including immediately
after creation.

### 4.3 RuntimeProviderProfile

A `RuntimeProviderProfile` is a typed, generated configuration intent for one
Runtime installation. It binds:

- a `ProviderDefinitionID` and revision;
- a `CredentialID` and Secret version;
- a stable AgentBox `RuntimeBindingID`;
- a Runtime installation;
- an adapter and adapter schema version;
- a public Runtime config schema/capability observation;
- the expected config fingerprint and activation requirements.

It is not raw TOML or an arbitrary environment map. The database may store its
non-secret identity, revision, digest, and state. The rendered candidate,
unmanaged config snapshot, and any generated environment material stay inside
the Runtime transaction boundary because they may include data that is unsafe
for the control-plane database.

### 4.4 RuntimeProviderBinding

`RuntimeProviderBinding` represents the administrator's active Provider intent
for one Runtime installation. `RuntimeBindingID` is an AgentBox identity and must
never be permanently equated with a current Codex Provider block name.

Only one binding may be active for a Runtime installation. Activation is
explicit and persists across AgentBox restarts. Failure does not select another
Provider automatically.

The following states are recommended:

```text
unmanaged
pending
active
activation_failed
rollback_pending
rollback_verified
needs_attention
unknown
```

`unmanaged` means AgentBox has not taken ownership of Provider configuration. It
is the safe state for upgraded v0.3.0-rc.1 installations.

### 4.5 SessionProviderBinding

A session binding is an immutable, non-secret snapshot of which Runtime binding
revision was effective when an AgentBox-observed session or continuity test
started. It exists to prevent an active Provider selection from retroactively
rewriting the meaning of an existing session.

Conceptual fields:

- AgentBox `RuntimeSessionID`, when one exists;
- Runtime installation and `RuntimeBindingID`;
- Provider definition and profile revisions;
- public Runtime session/thread reference only when the current Runtime exposes
  one through a supported public contract;
- effective time and evidence class;
- state: `bound`, `legacy_unbound`, `rebind_required`, `continuity_unknown`, or
  `retired`.

This record must not contain conversation content, private thread metadata,
JSONL/rollout paths, or a Secret reference. Sessions that predate Phase 11 are
`legacy_unbound` unless public evidence safely identifies their effective
binding. AgentBox must not infer or backfill a Provider from private files.

Changing the active Provider affects only operations whose public Runtime
contract is proven to consume the new configuration. Existing sessions stay on
their recorded binding or require an explicit rebind/new-session decision. No
existing session is silently migrated.

## 5. Runtime-Neutral Adapter Architecture

The Provider domain remains independent of any one Runtime configuration file:

```text
ProviderManager
├── ProviderRegistry
├── CredentialCatalog                 # non-secret metadata
├── ProviderTestOrchestrator
├── RuntimeContinuityManager
└── ActivationCoordinator
        |
        v typed Runtime request
RuntimeProviderCoordinator            # agentbox-runtime process
├── RuntimeSecretBackend
├── ConfigTransactionManager
├── CodexProviderConfigAdapter
├── ClaudeProviderConfigAdapter       # disabled unless publicly supported
├── OpenAICompatibleProtocolAdapter
├── LocalProviderProtocolAdapter
└── FutureRuntimeProviderConfigAdapter
```

There is an important distinction between two adapter types:

1. A **Provider protocol adapter** knows how to test a Provider endpoint and
   wire protocol without pretending that a successful request proves Runtime
   compatibility.
2. A **Runtime Provider config adapter** knows how one supported Runtime can be
   configured using that Runtime's current public contract.

The combination is capability-driven. A Provider type does not automatically
work with every Runtime.

## 6. Secret Management Design

### 6.1 Custody and access boundary

Raw Provider Secrets must be owned by `agentbox-runtime`, not by `agentbox`,
SQLite, the root Helper, or the Web application. This matches the existing rule
that Runtime credentials live in Runtime HOME and are inaccessible to the
control plane.

The recommended initial Secret provisioning surface is a **local, interactive,
Runtime-identity operation**. It reads the value from a TTY or protected stdin,
never argv, environment, URL, browser request, or shell history. It writes the
Runtime backend and returns only an opaque Secret reference and configured
state. A Web secret-entry form is not recommended for the first Phase 11 slice
because it would put raw material inside the browser/API trust path.

The normal Runtime UDS must not gain a generic `secret.read`, `secret.write`,
file, or environment action. If a future dedicated local ingress is approved,
it requires a separate protocol/action allowlist, strict peer identity and TTY
authorization, bounded frames, non-replay semantics, and a dedicated security
review. It may return no Secret value.

### 6.2 Storage

For Linux, Secret records should live beneath a fixed, Runtime-owned directory
selected by deployment policy, not a caller path. The directory is `0700` and
records are `0600`; every ancestor, file type, owner, mode, link count, and
symlink condition is validated with no-follow operations. Writes use a
same-directory restrictive temporary file, fsync where appropriate, and atomic
replacement with concurrent modification detection.

The store uses a strict versioned binary or JSON envelope. It is never a shell
environment file and is never loaded with `source`. Filenames are opaque
server-generated IDs, not Provider names.

### 6.3 Encryption approach

Durable Secret values should be protected with a reviewed authenticated-
encryption library, not custom cryptography. The proposed envelope contains:

- schema and algorithm version;
- random nonce;
- ciphertext and authentication tag;
- Secret version;
- associated data binding the Secret ID, credential kind, Runtime identity,
  and envelope version.

An approved AEAD such as AES-256-GCM or XChaCha20-Poly1305 is suitable; the
exact library and algorithm require a security ADR before implementation. The
master key must be generated with a CSPRNG, stored separately from Secret
records, owned only by `agentbox-runtime`, and never placed in the application
database, ordinary config, logs, reports, or release backups.

A software master key on the same host does **not** protect against root, a
compromised `agentbox-runtime`, or full host compromise. Its value is narrower:
it prevents plaintext disclosure from an isolated Secret-record copy, detects
record substitution/tampering through associated data, and keeps Secret
material out of ordinary AgentBox backups. TPM, kernel keyring, or another
hardware/OS-backed key source could improve this boundary later but must not be
claimed until supported and recoverable on the qualified Linux platforms.

If the product chooses permission-only Linux storage instead, that is a weaker
but simpler design already contemplated by existing planning. The choice
between mandatory AEAD and permission-only storage is a human-approved security
decision and must be resolved before implementation.

### 6.4 Runtime injection

For Codex, the preferred mechanism is the current official ability, if still
publicly supported at implementation time, to refer to an environment variable
name such as an `env_key`. Runtime configuration contains only the variable
name. The Runtime Executor resolves and decrypts the Secret immediately before
spawning the exact allowlisted Runtime process and supplies a minimal child-only
environment.

The Secret is never placed in argv, a URL, an ordinary generated TOML value,
the Runtime UDS response, or a long-lived AgentBox service environment. It may
be visible to processes within the same `agentbox-runtime` UID, which is an
explicit consequence of the existing Runtime trust boundary. Phase 11 must not
claim isolation between mutually trusted same-UID Runtime tools.

Direct Provider tests use an in-process HTTP client with a non-logging
Authorization header. They do not execute `curl` with a key and do not persist
raw response bodies.

### 6.5 Rotation

Rotation is a versioned transaction:

1. provision a new Secret version through the protected local ingress;
2. verify envelope integrity and ownership;
3. validate authentication and protocol with the new version;
4. produce a Provider activation impact plan;
5. atomically change the Credential's active Secret reference;
6. perform any approved Runtime lifecycle action;
7. verify Provider, Runtime, Remote, and applicable continuity dimensions;
8. commit or restore the prior Secret reference and verify rollback;
9. retire the old Secret only after the rollback window and explicit policy.

Rotation does not change Provider identity, base URL, model, wire protocol, or
RuntimeBindingID. It never automatically falls back to an older key after a
later unrelated authentication failure.

### 6.6 Audit and diagnostics

Audit may record:

- Credential ID and Provider ID;
- action, actor, request ID, Job ID, time, and outcome;
- old/new Secret version numbers;
- test kind and sanitized error code;
- whether rollback was attempted and verified.

It must not record a Secret value, prefix/suffix, Authorization header,
ciphertext, nonce, master-key metadata, complete endpoint URL where it reveals
an internal host, request/response body, prompt, or model output. Doctor reports
`configured`, `missing`, `permission_error`, `backend_locked`, or `unknown`, not
the content.

## 7. Provider Types and Capabilities

### 7.1 Official OpenAI

- Provider type has a fixed official endpoint policy; an administrator does not
  override it with an arbitrary URL.
- Supported wire APIs, models, configuration keys, auth references, and reload
  behavior are obtained from current public contracts.
- Official status does not imply that every model works with every Codex or
  Remote capability.

### 7.2 OpenAI-compatible HTTP Provider

- Requires a normalized `https` endpoint by default, an explicit supported wire
  protocol, model, and typed capabilities.
- URL userinfo, fragments, control characters, unsupported schemes, implicit
  credentials, arbitrary headers, and redirects to another authority are
  rejected.
- TLS verification remains enabled. A custom CA, if ever supported, is an
  administrator-installed trust object selected by an opaque ID, never a
  caller-supplied path.
- DNS, connection, redirect, response-size, timeout, and streaming behavior are
  bounded and independently tested.
- A successful minimal HTTP request is only Provider API evidence. It is not
  Codex Runtime, Remote Control, or continuity evidence.

### 7.3 Local Provider

- Local is a distinct Provider type, not an exception that disables endpoint
  validation globally.
- Allowed endpoints are restricted to an approved loopback or explicitly
  configured local/LAN policy. Cloud metadata and link-local destinations are
  denied.
- Phase 11 Provider Manager does not accept an executable, model file path,
  container operation, package name, or arbitrary local-process lifecycle
  command.
- A local endpoint may require no Credential, but all protocol and Runtime
  compatibility checks still apply.

### 7.4 Runtime-native / built-in Provider

Some Runtimes may expose a built-in Provider selection without an external URL
or AgentBox-managed Secret. That is a typed Provider capability, not a fake
OpenAI-compatible endpoint. The Runtime adapter owns its schema.

### 7.5 SSRF and data-boundary policy

Provider endpoints are an outbound data-exfiltration boundary. The activation
plan must display the Provider type, normalized destination authority, TLS
policy, model, whether prompts/tool data leave the host, and expected cost
class. Official, compatible, and local endpoint policies must not share a
single permissive validator.

Whether private RFC1918/ULA endpoints are allowed for the compatible type, or
only through the explicit local type, is a product/security decision. The
recommended default is to require the local type and a separate confirmation
for non-loopback private addresses. DNS rebinding and redirect handling require
dedicated tests.

## 8. Provider Testing and Compatibility Model

Tests are layered and each layer retains its own state:

| Layer | Evidence |
|---|---|
| Endpoint resolution | normalized endpoint and allowed destination class |
| Network | DNS, connection, TLS, timeout, redirect policy |
| Authentication | credential accepted/rejected/unknown |
| Model | model advertised or usable, when the protocol supports proof |
| Wire protocol | required request, streaming, event, and completion semantics |
| Provider API | bounded minimal direct Provider request |
| Runtime | bounded minimal request executed through the selected Runtime |
| Remote Control | Remote can recover or remain connected after the binding change |
| Thread resume | an existing public thread/session reference can resume |
| Context continuity | the resumed request actually uses prior context |
| Thread discovery | the thread remains visible through normal public discovery |

Each dimension is one of:

```text
PASS | FAIL | UNSUPPORTED | EXPERIMENTAL | UNKNOWN | NOT_TESTED
```

The aggregate is one of:

```text
SUPPORTED | COMPATIBLE | EXPERIMENTAL | DEGRADED | INCOMPATIBLE | UNKNOWN
```

Aggregation is deterministic and never hides the detailed matrix. Provider API
`PASS` cannot promote Remote or continuity dimensions. “Thread not listed” is
not reported as “thread deleted.” Tests that make a paid model request require
an explicit cost/data-boundary confirmation and use a bounded prompt/output.

An A/B fake-provider harness should test switching without real credentials or
private Runtime state. Real Provider credentials, paid inference, Remote
restart, and continuity claims remain human-approved test gates.

## 9. Codex Integration Design

### 9.1 Public contract only

Before implementation, Phase 11 must revalidate the then-current Codex public
CLI help, public configuration documentation/schema, Provider options, wire API,
authentication reference mechanism, reload/restart behavior, Remote lifecycle,
active-writer signals, and public thread/resume/discovery behavior.

Observed current file shapes or identifiers are fixtures, not permanent
contracts. AgentBox never edits Codex SQLite, JSONL, rollout, conversation, or
thread files.

### 9.2 CodexProviderConfigAdapter

The adapter accepts a typed `RuntimeProviderProfile`, never raw TOML, config
keys, path, environment, or Provider block name. It must:

1. resolve the config target server-side within Runtime HOME using the approved
   public contract;
2. reject symlinks, unsafe ownership/modes, replacement races, and duplicate
   managed blocks;
3. parse the complete existing TOML;
4. preserve all settings outside the explicitly AgentBox-managed scope;
5. render a candidate using the current public schema;
6. validate the complete candidate before any write;
7. compare the expected revision, inode/fingerprint, and content digest;
8. write a restrictive same-directory temporary file, fsync as appropriate,
   atomically replace, and verify content/mode/owner;
9. retain a bounded protected snapshot for rollback;
10. verify rollback before reporting it as successful.

The snapshot may contain unrelated user configuration or Secrets and therefore
stays in short-lived Runtime-owned protected transaction storage, not SQLite,
Job output, Audit metadata, or reports.

### 9.3 Activation and Remote Control

Activation is coordinated in this order:

```text
non-secret plan and revision check
    -> Provider and Credential preflight
    -> active turn/writer/Remote state assessment
    -> complete Runtime config snapshot
    -> render and validate candidate
    -> atomic apply
    -> approved existing Remote lifecycle transition, if required
    -> Provider test
    -> Codex Runtime test
    -> Remote recovery test
    -> applicable session continuity tests
    -> commit or verified rollback
```

Pairing is not repeated, deleted, or changed by Provider activation. Codex login
state and Provider API-key state remain separate observations. The Provider
Manager never calls Pair automatically.

When public behavior proves a config change affects only new requests, AgentBox
may preserve the Remote process but still records the new effective binding only
after a Runtime request verifies it. When a restart is required, the plan must
state that impact and use the existing Remote lifecycle manager. When behavior
is unknown, AgentBox must not promise a hot switch. An active writer or an
unverifiable active session causes `needs_attention` unless the operator first
quiesces work and explicitly confirms the bounded plan.

### 9.4 Existing sessions

- No existing session is rewritten.
- No private session file is inspected to infer its Provider.
- A pre-Phase-11 session is `legacy_unbound` unless supported public evidence
  proves otherwise.
- Changing the active Provider does not rewrite a session binding.
- Resume under a new Provider is an explicit action with separate thread,
  context, and discovery results.
- If a continuity dimension cannot be proven, it remains `UNKNOWN` or
  `EXPERIMENTAL`; the UI must offer a new session rather than promise continuity.

## 10. Claude Compatibility Analysis

Claude should continue to use **Runtime management only** in the initial Phase
11 implementation.

The Provider domain may expose a future `ClaudeProviderConfigAdapter` interface,
but no Claude Provider behavior should be enabled unless the then-current
official Claude Code contract explicitly supports external Provider selection,
credential reference, configuration validation, and safe lifecycle semantics.
AgentBox must not infer support from private Claude files, environment variables
observed on the host, unofficial proxies, or generic OpenAI-compatible behavior.

The recommended division is:

| Concern | Initial Phase 11 treatment |
|---|---|
| Claude installation/auth status | Existing Claude Runtime Adapter |
| Claude/tmux Remote sessions | Existing Claude Session Manager |
| Anthropic/Claude credential custody | Existing official CLI auth in Runtime HOME; not imported into Provider Manager |
| External Claude Provider selection | `UNSUPPORTED` unless a public contract is separately approved |
| Shared Provider domain interfaces | Allowed for future adapter compatibility |
| Shared option schema or wire assumptions | Prohibited |

This keeps the architecture runtime-neutral without falsely claiming that Codex
and Claude accept the same endpoint, credential, model, or lifecycle parameters.

## 11. Proposed Database Changes

All changes are additive logical proposals. No migration is authorized by this
document.

### 11.1 `provider_definitions`

Stores typed non-secret Provider metadata, normalization schema, model,
protocol, options schema/options, lifecycle state, compatibility summary,
timestamps, and revision.

Constraints include unique identity under the active identity schema, bounded
labels/options, and no Secret-shaped columns.

### 11.2 `provider_credentials`

Stores `CredentialID`, Provider relationship, credential kind, opaque Secret
reference, active Secret version, configured/rotation state, last safe
validation state, timestamps, and revision. It contains no plaintext,
ciphertext, key hint, Authorization material, or master-key metadata.

A Provider can have zero or one active Credential in the first implementation.
Sharing one Credential across multiple Providers should be disabled by default
because it expands rotation and compromise blast radius.

### 11.3 `runtime_provider_bindings`

Stores Runtime installation, Provider definition, stable RuntimeBindingID,
adapter type/schema, active flag, prior rollback reference, state, timestamps,
and revision. A partial unique constraint permits one active binding per Runtime
installation. Absence of a row, or an explicit unmanaged representation, means
AgentBox has not taken control.

### 11.4 `runtime_session_provider_bindings`

Stores an immutable binding snapshot for an AgentBox Runtime session when a
publicly supported relationship exists. It references the Runtime session,
Runtime binding, Provider/profile revisions, effective time, evidence class, and
binding state. It stores no conversation, model output, private thread metadata,
or Secret reference.

If Codex does not expose a stable public session identity, no synthetic private
mapping is created; the result remains `legacy_unbound` or `continuity_unknown`.

### 11.5 `provider_compatibility_observations`

Stores the independent result matrix, adapter/evidence schema versions,
observed time, expiry, test kind, bounded cost class, and sanitized evidence
codes. Raw HTTP bodies, prompts, completions, headers, and Runtime output are
prohibited.

### 11.6 `provider_config_transactions`

Stores the expected Provider/Credential/Binding revisions, plan digest,
transaction phase, config fingerprint/digest, backup opaque reference, original
existence/mode metadata, lifecycle intent, sanitized outcome, and rollback
attempted/verified timestamps.

Raw config and snapshots stay in the Runtime-owned transaction store. Jobs and
AuditEvents correlate by opaque transaction ID.

### 11.7 Relationships

```text
ProviderDefinition 1 ---- 0..1 active ProviderCredential
ProviderDefinition 1 ---- * ProviderCompatibilityObservation
RuntimeInstallation 1 --- * RuntimeProviderBinding
RuntimeProviderBinding 1 - * ProviderConfigTransaction
RuntimeProviderBinding 1 - * RuntimeSessionProviderBinding
RuntimeSession 1 -------- 0..1 effective RuntimeSessionProviderBinding
Job 1 ------------------- 0..1 ProviderConfigTransaction
Job 1 ------------------- * AuditEvent
```

Secret records are deliberately absent from this schema.

### 11.8 Migration strategy

- Use one reviewed additive Alembic revision with foreign keys, unique
  constraints, revision fields, and bounded enums.
- Do not create Provider rows from existing Codex config automatically.
- Do not read or import existing credentials.
- Do not create an active binding during schema migration.
- Older application binaries should ignore the added tables; the migration must
  not change existing Project, Session, Job, auth, or Runtime data.
- Destructive schema downgrade is not a normal rollback mechanism. Before
  rolling an activated Phase 11 deployment back to v0.3.0-rc.1, restore the
  pre-management Runtime config through a verified Phase 11 transaction, then
  roll back application code while leaving additive metadata inert.

## 12. Security Review

### 12.1 Credential leakage

Threats include request/response logging, argv/process listings, environment
dumps, SQLite/WAL/backups, diagnostics, browser state, error text, Provider
redirects, and malicious model responses.

Required controls:

- local protected Secret ingress;
- Runtime-only custody and decryption;
- no Secret in Web/API/DB/Job/Audit/report/Git;
- minimal child environment and no argv/URL placement;
- exact log field allowlists and canary scans across DB/WAL/SHM, journal,
  browser artifacts, reports, config snapshots, and Runtime errors;
- no raw Provider response persistence;
- redaction as defense in depth, never as permission to log a Secret.

### 12.2 Privilege escalation

A compromised Web/API process must still be unable to retrieve a key, edit a
Runtime config, select an arbitrary path, run a command, or ask root to perform a
Provider action. Runtime UDS actions contain opaque IDs and revisions; the
Runtime resolves fixed config locations, adapters, and executable policy.

The root Helper receives no new actions. Provider work runs as
`agentbox-runtime`, so compromise is contained to the existing Runtime/project
trust boundary rather than root or application secrets.

### 12.3 Malicious Provider configuration

Threats include SSRF to metadata services, DNS rebinding, TLS downgrade,
credential-bearing URLs, redirect-based credential exfiltration, oversized or
malformed responses, streaming hangs, model/option injection, internal network
discovery, and arbitrary header/config injection.

Required controls include type-specific endpoint policy, normalized identity,
fixed schemes, TLS verification, redirect restrictions, destination
classification, bounded DNS/connect/read/stream limits, strict typed options,
no arbitrary headers, and independent compatibility evidence. The activation
confirmation must make the data destination and privacy boundary visible.

### 12.4 Config and transaction integrity

Threats include symlink/replacement races, concurrent manual edits, duplicate
blocks, lost unrelated settings, partial fsync, restart failure, stale binding
state, and false-positive rollback.

Required controls are server-resolved fixed paths, no-follow checks, ownership
and mode validation, expected fingerprint/revision, same-directory atomic
replace, complete snapshot, lifecycle coordination, fault injection at every
phase, and post-rollback config/permission/process/Provider/Remote verification.

Only a fully verified restoration is `Rollback verified`. Otherwise the Job is
`needs_attention` and automatic retry is prohibited.

### 12.5 Session and continuity integrity

Threats include switching during an active turn, attributing an old session to
the new Provider, losing discovery, reusing context across a different privacy
boundary, or rewriting private files to manufacture continuity.

Required controls are per-Runtime serialization, writer preflight, immutable
session binding snapshots, explicit rebind/new-session choice, public APIs only,
and separate Remote/resume/context/discovery results. No automatic failover or
private session mutation is allowed.

### 12.6 Tenant isolation

AgentBox v0.3.0-rc.1 is single-server and single-administrator with one shared
`agentbox-runtime` identity. Phase 11 must not claim tenant isolation. Provider
definitions and Runtime bindings are global to that administrator and Runtime
identity.

Adding multiple administrators or tenants later requires a new authorization
and execution architecture: owner-scoped database rows, per-tenant or
per-project Runtime identities/secret namespaces, quotas, audit principals,
and cross-tenant negative tests. Adding a nullable `tenant_id` now would not
provide isolation and is not recommended.

### 12.7 Residual risks

- Root and a fully compromised Runtime UID can access Runtime Secrets.
- A Provider necessarily receives prompts and applicable tool/context data sent
  to it.
- Third-party Runtime behavior can change between releases.
- Same-UID Runtime tools are not isolated from each other's process
  environment.
- Unsigned third-party/provider responses and endpoint ownership are outside
  AgentBox's trust guarantee.
- Cross-provider conversation semantics may remain experimental or unsupported.

## 13. Safe Migration from v0.3.0-rc.1

### 13.1 Upgrade defaults

After installing a future Phase 11 build:

- existing Codex, Claude, tmux, GitHub auth, Projects, Remote sessions, and root
  state remain untouched;
- Provider Manager starts disabled/unmanaged for every Runtime;
- no Secret backend is initialized until an explicit local setup action;
- no existing config is adopted, rewritten, or normalized;
- no Provider is auto-created from observed config;
- no active Provider binding exists;
- Remote Control continues using the existing Phase 5 behavior.

The initial read model should say `Provider management: Unmanaged`, not infer
“OpenAI” merely because Codex works.

### 13.2 Opt-in adoption

An administrator may later perform an explicit sequence:

1. run read-only capability discovery against the installed public Codex
   contract;
2. receive a sanitized ownership/conflict report without config contents;
3. create non-secret Provider metadata;
4. provision a new Provider Secret locally as `agentbox-runtime` rather than
   importing root or existing Codex credentials;
5. run config/network/auth/protocol tests;
6. create a revision-bound activation preview;
7. quiesce active work and approve any restart/session impact;
8. take a protected pre-management config snapshot;
9. activate and verify the layered compatibility matrix;
10. commit the managed binding or restore and verify the exact pre-management
    state.

AgentBox should manage only a clearly marked, versioned config scope after
opt-in. Unrelated settings remain user-owned.

### 13.3 Existing sessions

Existing Codex and Claude sessions remain running and are not rebound. They are
shown as `legacy_unbound` or `continuity_unknown`. The safe default is to finish
the current turn/session and create a new session after activation. Resume under
a new Provider is offered only when the public Runtime contract and an explicit
continuity test support it.

### 13.4 Backup and rollback

Before first activation, save the original existence state, owner, mode,
fingerprint, content, active lifecycle state, and binding absence. Snapshot data
stays protected in the Runtime boundary. SQLite online backup covers the new
metadata but does not silently include Secret material or the master key.

Application uninstall preserves Runtime HOME and the Secret backend by default.
There is no Phase 11 purge until a separate destructive-data design is approved.
Loss of the encryption master key requires credential re-entry; AgentBox must not
invent a recovery path.

## 14. Proposed Implementation Sequence and Gates

This is a future sequence, not authorization to begin work.

1. **Contract validation and ADRs** — revalidate current public Runtime behavior;
   approve Linux Secret encryption/key custody, config ownership, and local
   Secret ingress.
2. **Non-secret domain/schema** — add Provider/Credential/Binding/Observation/
   Transaction metadata with no activation and no Secret backend.
3. **Runtime Secret backend** — implement local provisioning, storage, rotation,
   canary scans, permissions, and recovery tests behind a disabled feature flag.
4. **Config transaction framework** — implement parser-preserving, revisioned,
   atomic writes and fault-injected rollback using fixtures only.
5. **Provider protocol tests** — implement fake Provider A/B and layered direct
   tests without real credentials or paid requests.
6. **Codex adapter** — map typed profiles to the newly validated public Codex
   contract; keep activation disabled until the complete matrix passes.
7. **Continuity harness** — independently validate Runtime, Remote, resume,
   context, and discovery behavior.
8. **Activation CLI/API/Web** — expose plans first, then gated Jobs and safe
   read models. Secret entry remains outside the browser in the recommended
   first slice.
9. **Real Provider validation** — only with explicit credentials, cost approval,
   backup, restart plan, and human authorization.

Mandatory implementation gates include:

- public-contract fixtures for every enabled Runtime version;
- distinct-UID permission tests;
- UDS exact-schema/peer/oversize/malformed tests;
- Secret canary scans across all persistent and output surfaces;
- malicious endpoint/redirect/DNS tests;
- config symlink/concurrent-edit/fault-injection tests;
- active-writer and duplicate-Runtime tests;
- verified rollback at every failure point;
- no open P0/P1 security issue or unresolved blocking review thread.

## 15. Decisions Recommended by This Proposal

1. Preserve the current process model; add no Provider root daemon or Helper
   action.
2. Keep Provider metadata in the control plane and Secret/config execution in
   the `agentbox-runtime` boundary.
3. Implement Linux + Codex first while keeping runtime-neutral domain
   interfaces.
4. Treat Claude as Runtime management only until an official public Provider
   contract is separately approved.
5. Make all v0.3.0-rc.1 installations `unmanaged` by default; never auto-import
   existing config or credentials.
6. Use distinct ProviderDefinition, Credential, RuntimeBinding, and immutable
   SessionBinding identities.
7. Prefer local Runtime-identity Secret provisioning over Web secret entry for
   the first implementation.
8. Use typed config adapters and full verified transactions; never expose a raw
   config editor.
9. Make Provider activation explicit with no automatic fallback.
10. Report Provider, Runtime, Remote, resume, context, and discovery evidence
    independently.

## 16. Unresolved Architecture Decisions

The following require an ADR, security review, or current public-contract
evidence before implementation:

1. Linux Secret protection: mandatory AEAD with a software master key,
   permission-only storage, or an OS/hardware-backed key source.
2. Master-key recovery and backup: re-entry-only, operator-managed encrypted
   backup, or a qualified platform mechanism.
3. Exact local Secret ingress and authorization model without putting raw
   material through the Web/API trust boundary.
4. Exact Codex managed config scope, ownership marker, public validation method,
   and reload/restart semantics at implementation time.
5. Whether an active Remote with unknown writer state blocks activation
   absolutely or permits a separately confirmed, experimental maintenance
   workflow.
6. Retention duration for old Secret versions and protected config snapshots.
7. Whether compatible Providers may target private LAN addresses or must use the
   explicit Local Provider type.
8. Custom CA support without accepting arbitrary filesystem paths.
9. Whether credentials may ever be shared across Provider definitions.
10. Paid test budget, consent lifetime, and minimum prompt/data disclosure.
11. Availability of a public Codex session identity adequate for durable
    SessionProviderBinding records.
12. Whether any Claude Provider contract exists that satisfies the same safety
    and continuity gates.

## 17. Product Decisions Requiring Approval

Before implementation begins, the product owner should answer:

1. Is the first Phase 11 release explicitly **Codex on Linux only**, with Claude
   Provider selection deferred?
2. Is local-only Secret entry acceptable for the first release, even though the
   Provider metadata and activation plan are visible in Web/CLI?
3. Should encrypted Secret backup be excluded initially, making re-entry the
   documented recovery path if the Runtime master key is lost?
4. Should changing Provider while any existing session is active be blocked by
   default, even when that makes switching less convenient?
5. Are LAN/private OpenAI-compatible endpoints permitted, and if so must they be
   declared as Local Providers with an explicit data-boundary warning?
6. Which compatibility level is sufficient for activation: Provider + Runtime,
   or must Remote recovery also pass? The recommendation is to require Remote
   recovery for Codex Remote-managed use and show higher continuity dimensions
   separately.
7. May paid tests ever run from the Web, or should they remain local CLI-only
   with per-run confirmation?
8. How long should rollback snapshots and prior Secret versions remain
   available?

## 18. Explicit Non-Goals of This Proposal

- no Provider, Secret, config, API, CLI, UI, migration, or systemd implementation;
- no real Provider creation or test;
- no API-key read, import, copy, or rotation;
- no Codex or Claude config edit;
- no Runtime restart, Pair operation, session migration, or Remote change;
- no root credential migration;
- no automatic Provider fallback or failover;
- no multi-tenant claim;
- no public network, SSH, firewall, proxy, tunnel, container, or multi-server
  management.

Implementation must wait for approval of this proposal and the unresolved
security/product decisions above.
