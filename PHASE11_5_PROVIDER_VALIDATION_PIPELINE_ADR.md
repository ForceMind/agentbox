# AgentBox Phase 11.5 — Provider Validation Pipeline Architecture Decision Record

Status: **Proposed — design only, awaiting human approval**
Scope: Provider validation evidence and activation eligibility for Phase 11
Governance acceptance: The decision content is canonically registered as
P11-ADR-042 through P11-ADR-049 and **Accepted** in `docs/adr/README.md`.
The document-local `ADR-11.5-041` through `ADR-11.5-048` labels and the status
above are historical drafting metadata. Acceptance becomes repository-effective
only after the Phase 11.10 governance change is reviewed and merged into
`main`.
Contextual alternatives and open questions remain historical; supplemental
P11-ADR-071 through P11-ADR-076 provide their governing resolution.
Architecture sources: `PHASE11_PROVIDER_MANAGER_PROPOSAL.md`,
`PHASE11_IMPLEMENTATION_PLAN.md`,
`PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md`,
`PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md`,
`PHASE11_3_SECRET_BOUNDARY_ADR.md`, and
`PHASE11_4_CONFIG_TRANSACTION_FRAMEWORK_ADR.md`
Repository baseline: `ForceMind/agentbox` at
`1c2005de59b1c5063b260591206a8411c7e5b1a5`

This document defines a future validation boundary. It does not authorize
production code, external Provider requests, real credential use, Secret
storage, Runtime or Codex/Claude mutation, database migrations, Provider
activation, a branch, or a commit. No real endpoint or credential was accessed
to prepare this design.

## 1. Problem Statement

### 1.1 Why Provider validation is required

A Provider definition is user intent, not proof that a Runtime can safely use
the Provider. Before activation, AgentBox needs bounded evidence about several
independent questions:

- Is the Provider type known and its definition structurally valid?
- Is a reviewed Provider adapter available for the target Runtime?
- Does fresh Runtime evidence show the required public capabilities?
- Does the required Credential reference exist in an eligible lifecycle state?
- Is the endpoint permitted by destination and transport policy?
- Does the endpoint appear reachable and authenticated when a separately
  approved live test is performed?
- Does the selected model and wire protocol satisfy the Provider profile?
- Can the Runtime use that Provider through its public contract?
- What remains `UNKNOWN`, `EXPERIMENTAL`, or `NOT_TESTED`?

These answers have different authorities, lifetimes, side effects, and failure
modes. Validation therefore produces a detailed evidence bundle rather than a
single permanent `healthy` flag.

### 1.2 Why activation without validation is unsafe

Activation without fresh, revision-bound evidence could:

- write malformed or unsupported Runtime configuration;
- bind a Runtime to a missing, revoked, or mismatched Credential;
- direct prompts, tool data, or credentials to a malicious or unintended host;
- access loopback, private networks, link-local addresses, or cloud metadata;
- send credentials across a redirect or downgrade transport security;
- choose a model or wire protocol the Runtime cannot use;
- interrupt Remote Control or existing sessions without an honest warning;
- record a Provider as active when only an endpoint ping succeeded;
- turn the Runtime into an internal-network scanner or credential oracle.

Validation is a required precondition for an activation plan, but validation
itself never performs activation or changes Runtime state.

### 1.3 Why validation is separate from execution

Validation is an observation workflow. Execution is the user's AI workload.
They differ in purpose and authorization:

- validation uses minimal, bounded probes and records evidence;
- normal execution carries prompts, tool data, conversation state, and user
  cost expectations;
- a validation request may be disallowed even when normal execution would be
  allowed, or require separate cost/data-destination confirmation;
- validation evidence can expire before a later request;
- a successful minimal request cannot guarantee future availability, cost,
  quota, model behavior, streaming, tools, conversation continuity, or Remote
  Control behavior.

The pipeline must not become a general Provider proxy, prompt runner, benchmark,
health-monitor daemon, or unrestricted outbound HTTP client.

### 1.4 Ownership boundary

```text
Control Plane (`agentbox`)
    owns: workflow, policy, authorization, approval, evidence metadata,
          activation eligibility, audit
    cannot: read Secret Material, issue arbitrary network requests, execute
            Runtime tools, or modify Runtime configuration

Runtime (`agentbox-runtime`)
    owns: local capability evidence, typed adapter probes, bounded Secret use,
          actual Runtime compatibility observations
    cannot: authorize itself, open AgentBox SQLite, expose raw results, become
            a generic HTTP client, or activate without a transaction

Root Helper
    remains: fixed lifecycle actions only
    cannot: validate Providers, resolve Secrets, connect to endpoints, or alter
            Provider/Runtime configuration
```

The Phase 11.2 capability contract remains read-only and does not itself run
Provider requests. A future live Provider validation operation is a separate,
typed, explicitly authorized Runtime contract.

## 2. Validation Model

### 2.1 Validation Pipeline

A `ProviderValidationPipeline` is a policy-driven sequence of independent
validators that evaluates one immutable validation scope and emits an immutable
evidence bundle.

Conceptually:

```text
Provider Definition
    -> Provider Definition Validation
    -> Runtime Capability Validation
    -> Credential Boundary Validation
    -> Endpoint Policy / Availability Validation
    -> Runtime Compatibility Validation
    -> Activation Eligibility Decision
```

Stages do not silently promote one another. Endpoint reachability cannot stand
in for authentication; authentication cannot stand in for model availability;
a direct Provider request cannot stand in for Runtime or Remote Control
compatibility.

### 2.2 Validation Scope

Every validation run is bound to an immutable scope containing safe identifiers
and revisions:

- ValidationRunID and policy/profile version;
- ProviderID, Provider revision, type, endpoint-policy class, protocol, and
  model identity;
- CredentialID, Credential revision, Secret-version reference, and lifecycle
  state, without Secret Material;
- RuntimeInstallationID and Runtime Profile revision;
- candidate Runtime Binding ID/revision when one exists;
- Runtime adapter and public-contract/schema version;
- required Runtime capability evidence IDs/revisions;
- validation-stage set, side-effect class, cost/data-boundary approval, and
  expiry policy;
- deterministic scope/evidence-bundle digest.

A change to any security- or compatibility-relevant field invalidates the
bundle for activation. Display-name-only changes may be excluded only after a
future schema explicitly classifies them as non-semantic.

### 2.3 Two validation modes

The pipeline distinguishes:

1. **Offline eligibility validation** — definition/schema, adapter presence,
   capability evidence, Credential lifecycle metadata, endpoint normalization,
   and destination policy. It performs no network request and never resolves a
   Secret.
2. **Live observation validation** — future typed DNS, connection, TLS,
   authentication, protocol, model, minimal Provider API, Runtime, and Remote
   observations. It requires separate authorization, bounded side effects, and
   Runtime-owned execution.

This ADR designs both modes but executes neither. An offline pass must leave all
unperformed live dimensions as `NOT_TESTED`, never `PASS`.

### 2.4 Validator contract

Each validator is reviewed AgentBox code selected server-side by Provider type,
Runtime type, and policy version. It declares:

- validator identity and immutable version;
- accepted typed input schema;
- evidence dimensions produced;
- prerequisites and dependency evidence;
- whether it is offline or live;
- whether it may resolve one Credential version;
- destination, redirect, timeout, output, concurrency, and cost bounds;
- retry classification and evidence TTL;
- sanitized finding-code vocabulary.

There is no uploaded validator, dynamic module name, caller-supplied executable,
script, command, argv, raw URL request, header map, proxy, environment, or
filesystem path.

### 2.5 Validation levels and compatibility

Detailed dimensions use the existing observation vocabulary:

```text
PASS | FAIL | UNSUPPORTED | EXPERIMENTAL | UNKNOWN | NOT_TESTED
```

The compatibility aggregate remains:

```text
SUPPORTED | COMPATIBLE | EXPERIMENTAL | DEGRADED | INCOMPATIBLE | UNKNOWN
```

Aggregation is deterministic, policy-versioned, and retains every detailed
dimension. It never turns an untested higher layer into a pass.

## 3. Validation Stages

### Stage A — Provider Definition Validation

This stage is control-plane, offline, non-secret, and side-effect free.

It checks:

- Provider type is a known fixed enum;
- the type is enabled by current product/platform policy;
- a reviewed typed Provider adapter is registered;
- required fields are present and forbidden/unknown fields are absent;
- Provider ID/revision and option-schema version are valid;
- base URL, model, protocol, and typed options are syntactically valid;
- Provider-type-specific constraints are satisfied;
- no credential, userinfo, control character, fragment, arbitrary header,
  environment variable, path, command, or executable is embedded in metadata;
- option sizes, Unicode normalization, and canonical forms are bounded;
- Official, OpenAI-compatible, Local, and Runtime-native Providers are not
  coerced into one fake common parameter set.

Examples of type-specific behavior:

- **Official OpenAI** uses a fixed, reviewed destination and supported public
  protocol/options; callers cannot replace it with an arbitrary host.
- **OpenAI-compatible HTTP** requires explicit endpoint normalization and
  destination classification.
- **Local Provider** is an explicit Provider type with a separate local-network
  policy; a private address is not smuggled through the compatible type.
- **Runtime-native/built-in** uses the Runtime adapter's public capability and
  may have no endpoint or Credential.

Failure is non-retryable for the same Provider revision. The user must correct
the definition or select a supported type/adapter.

### Stage B — Capability Validation

This stage consumes Phase 11.2 read-only capability evidence. It does not run a
Provider request or mutate the Runtime.

It checks:

- the target Runtime installation identity matches the intended scope;
- required Runtime and supporting components are detected;
- safe public versions are within the currently validated range;
- the Runtime adapter and Provider-profile adapter are available;
- required public config/provider/wire capabilities are declared or observed;
- prerequisite capability dependencies are satisfied;
- evidence is fresh, complete, correctly sourced, and generated by compatible
  adapter/schema versions;
- contradictions or installation conflicts are not hidden.

Capability information is evidence, not permission or a guarantee. Missing or
stale capability evidence yields `UNKNOWN`, `UNSUPPORTED`, or
`NEEDS_REVALIDATION`; the pipeline does not try an undocumented fallback.

### Stage C — Credential Boundary Validation

This stage has two deliberately separate checks.

#### C1 — Metadata eligibility check

The control plane checks only that:

- the Provider type requires, optionally uses, or forbids a Credential;
- the required CredentialID exists and is explicitly related to the Provider;
- Credential and Secret-version references match expected revisions;
- lifecycle is eligible, such as stored/staged/active according to operation;
- the reference is not missing, revoked, deleted, or in unresolved rotation;
- safe presence/integrity evidence is fresh enough for the requested operation.

It does not access, decrypt, compare, fingerprint, partially reveal, or return
the Secret value. Metadata eligibility does not prove authentication.

#### C2 — Future Runtime-owned authentication observation

Only a separately authorized live validation may ask Runtime to use exactly one
Credential version for exactly one Provider scope. Runtime resolves the opaque
record locally under the Phase 11.3 action-bound Secret-use contract.

The request is bound to Provider, Credential, Secret version, Runtime Profile,
ValidationRunID, destination policy, validator version, and evidence-scope
digest. No generic `get secret`, `test this token against this URL`, or Secret
enumeration operation exists.

Runtime returns only typed outcomes such as accepted, rejected, unavailable, or
unknown, plus a sanitized finding code. It never returns a token, prefix/suffix,
header, raw Provider error, request dump, or timing oracle intended to reveal
Secret content.

### Stage D — Endpoint Validation

Stage D consists of offline policy validation and an optional future live
availability observation.

#### D1 — Endpoint policy validation

Before any DNS or connection attempt, validate:

- allowed scheme and canonical authority;
- IDNA/Unicode normalization and control-character rejection;
- no userinfo, fragment, credential-bearing query, or ambiguous URL form;
- normalized port and path rules for the Provider type;
- no path traversal or alternate-IP numeric notation bypass;
- destination class: official, public compatible, explicitly local, private,
  link-local, loopback, multicast, unspecified, broadcast, or prohibited;
- TLS policy, certificate-verification requirement, and minimum supported
  transport behavior;
- redirect and proxy policy;
- policy treatment of IPv4, IPv6, DNS CNAMEs, and mixed address sets.

Official Provider policy should use a fixed reviewed authority. Compatible
Provider policy should default to HTTPS public destinations. Local/private
destinations require their explicit Provider type and approved policy; cloud
metadata and link-local destinations remain denied.

#### D2 — Future live endpoint observation

A live validator may conceptually perform bounded:

1. DNS resolution under destination policy;
2. address classification for every answer;
3. connection to an approved resolved address;
4. TLS handshake and certificate/hostname verification;
5. bounded protocol request where the next stage requires it.

Security rules include:

- reject if any selected/resolved address violates policy;
- mitigate DNS rebinding by binding validation and connection evidence to the
  approved resolution and rechecking as required;
- disable redirects by default; if a Provider protocol requires them, validate
  every hop and never forward credentials across a changed authority;
- ignore ambient/user-controlled proxy variables unless a future typed proxy
  policy explicitly approves them;
- never follow downgrade redirects;
- enforce connect/read/total timeouts, response/header/body/stream limits, and
  decompression limits;
- do not return DNS inventories, raw certificates, response bodies, or internal
  network details to the control plane.

A TCP/TLS success is only network evidence. It is not authentication, protocol,
model, Runtime, or Remote compatibility.

This design task performs no D2 request.

### Stage E — Runtime Compatibility Validation

Stage E preserves independent subdimensions:

1. **Authentication** — the exact Credential version is accepted, rejected, or
   unknown.
2. **Model** — the configured model is advertised or usable when the protocol
   provides safe proof.
3. **Wire protocol** — required request, streaming, event, error, completion,
   and tool semantics meet the typed profile.
4. **Provider API** — a bounded minimal direct Provider request succeeds when
   explicitly authorized.
5. **Runtime** — a bounded minimal request succeeds through the selected Runtime
   and public Provider contract.
6. **Remote Control** — pairing/connection remains available or can recover
   according to public evidence.
7. **Thread resume** — an existing public thread/session reference can resume.
8. **Context continuity** — a resumed request uses prior context.
9. **Thread discovery** — the thread remains visible through public discovery.

Provider API `PASS` cannot promote Runtime, Remote, or continuity dimensions.
Runtime and Remote observations remain `NOT_TESTED` until the later Codex
adapter, activation, and continuity phases supply reviewed public-contract
evidence.

Claude remains Runtime-oriented in v1 and does not acquire a Provider
abstraction through this pipeline. Claude/tmux capability evidence may be shown
separately, but it cannot satisfy a Codex Provider activation gate.

### Activation Eligibility Derivation

Activation eligibility is a policy decision derived from the immutable evidence
bundle; it is not another network test and does not activate anything.

Suggested states are:

- `ELIGIBLE` — every mandatory stage/dimension passed with fresh matching
  evidence and no unresolved policy finding;
- `ELIGIBLE_WITH_CONFIRMATION` — policy permits an explicit high-impact or
  experimental activation despite visible non-blocking uncertainty;
- `INELIGIBLE` — a mandatory check failed or an incompatible/security-policy
  finding exists;
- `UNKNOWN` — required evidence is unavailable, untested, contradictory, or too
  weak to decide;
- `NEEDS_REVALIDATION` — previously usable evidence no longer matches current
  revisions, validators, policy, capabilities, or time bounds.

Eligibility is scoped to one exact candidate Runtime Binding and transaction
plan. It is not a Provider-global `active` or `healthy` flag.

## 4. Evidence Model

### 4.1 Validation Evidence

`ValidationEvidence` is an immutable, non-secret observation produced by one
validator for one dimension and scope.

It contains:

- opaque EvidenceID and ValidationRunID;
- Provider/Credential/Profile/Binding/Runtime IDs and expected revisions as
  applicable;
- dimension and stage;
- validator identity/version and evidence schema version;
- policy version and Provider adapter/Runtime adapter version;
- evidence source class: static definition, cached capability, fixture, or
  explicitly approved live observation;
- observation outcome and compatibility classification;
- performed, observed, and expiry timestamps;
- safe destination class/authority identity where necessary, without userinfo,
  query, Secret, or internal resolution details;
- bounded sanitized finding/error codes;
- retryability and whether the dimension is mandatory for activation;
- correlation ID, scope digest, and integrity/provenance metadata.

Evidence does not grant permission. Its presence does not authorize Secret use,
activation, Runtime mutation, or future Provider requests.

### 4.2 Evidence prohibited content

Evidence, SQLite, Audit, Jobs, logs, reports, diagnostics, and UI read models
must not contain:

- Secret Material, ciphertext, keys, nonces, tags, token hints, or credential
  values;
- Authorization, Cookie, proxy-auth, or arbitrary Provider headers;
- request/response bodies, prompts, completions, streamed output, tool data, or
  conversation/thread content;
- raw DNS answer inventories, certificate dumps, internal network maps, or
  connection traces;
- raw Runtime output/stderr, process environments, command lines, paths, config,
  snapshots, or private Runtime state;
- caller-supplied arbitrary metadata or unbounded Provider error text.

Finding codes are server-defined enums. Provider strings are normalized,
bounded, and mapped to safe categories rather than copied verbatim.

### 4.3 Evidence bundle

A `ValidationEvidenceBundle` is an immutable set of stage evidence plus:

- exact scope and scope digest;
- aggregation-policy version;
- detailed matrix;
- aggregate compatibility;
- activation-eligibility decision;
- earliest relevant expiry;
- unresolved warnings and confirmation requirements;
- superseded/invalidation relationship.

The bundle digest binds all included evidence IDs, revisions, outcomes,
validator/policy versions, and required-stage set. A transaction plan references
the digest rather than copying or reinterpreting evidence.

### 4.4 Evidence authority and trust

Different evidence has different authority:

- Control Plane is authoritative for Provider/Credential metadata revisions,
  policy, authorization, and stored evidence lifecycle.
- Runtime is authoritative for local installed components, capabilities, Secret
  record presence/integrity, and Runtime-executed observations.
- A Provider response is only external observation, never authority over local
  policy, Runtime Binding, or activation.
- User declaration may describe intent but cannot create `PASS` evidence.

Conflicting authorities result in `UNKNOWN` or `NEEDS_REVALIDATION`, not a
preference chosen silently.

### 4.5 Evidence immutability and freshness

Evidence records are append-only. Refresh creates new evidence and supersedes
the old record; it never rewrites the observation time or result.

Evidence becomes unusable for activation when:

- its TTL expires;
- any bound revision or identity changes;
- validator, adapter, public contract, or policy changes incompatibly;
- Runtime capability evidence expires or contradicts it;
- Credential lifecycle/Secret version changes;
- endpoint normalization/destination class changes;
- the transaction plan requires a stronger validation stage;
- a relevant security advisory invalidates the result.

Historical evidence may remain for bounded audit/diagnosis but is clearly
expired and cannot satisfy a new activation.

## 5. Validation Result Model

### 5.1 Pipeline states

The user-facing validation lifecycle is:

```text
UNKNOWN
    -> PENDING
    -> PASSED | FAILED

PASSED
    -> EXPIRED | NEEDS_REVALIDATION

FAILED
    -> PENDING after an allowed retry or corrected revision

PENDING
    -> UNKNOWN when outcome cannot be established safely
```

- **UNKNOWN** — no usable evidence exists, evidence conflicts, or an attempted
  operation has an indeterminate outcome.
- **PENDING** — a bounded validation run is accepted or executing; it confers no
  eligibility.
- **PASSED** — all checks required by that exact policy/scope completed with
  acceptable evidence at that moment.
- **FAILED** — at least one required check completed with a negative or blocking
  finding. The failure category determines whether correction or retry is
  appropriate.
- **EXPIRED** — the bundle's time-bound evidence is no longer fresh.
- **NEEDS_REVALIDATION** — a bound identity, revision, capability, validator,
  adapter, policy, or security premise changed before ordinary expiry.

Cancellation before a side-effecting probe returns to `UNKNOWN` or a separate
safe operational `CANCELLED` status; it never produces `PASSED`. A timeout or
lost Runtime response is `UNKNOWN`, not proof of failure or success.

### 5.2 Stage outcome versus pipeline state

The pipeline state does not replace the detailed matrix. For example:

```text
Endpoint policy: PASS
Network:         PASS
Authentication: PASS
Model:           PASS
Provider API:    PASS
Codex Runtime:   NOT_TESTED
Remote Control:  UNKNOWN
Aggregate:       EXPERIMENTAL or UNKNOWN (policy-defined)
Eligibility:     INELIGIBLE or ELIGIBLE_WITH_CONFIRMATION (policy-defined)
```

This result must never be displayed simply as `Provider ready` without the
untested/unknown dimensions.

### 5.3 Deterministic aggregation

Aggregation uses a versioned table, not ad hoc UI or adapter logic. At minimum:

- a required `FAIL`, security-policy violation, or `INCOMPATIBLE` dimension
  makes the scope ineligible;
- a required `UNKNOWN`, `UNSUPPORTED`, `NOT_TESTED`, expired, or missing
  dimension cannot yield unconditional `ELIGIBLE`;
- `EXPERIMENTAL` and `DEGRADED` remain visible and require policy treatment;
- optional dimensions never hide required failures;
- higher-layer status is never inferred from lower-layer success.

## 6. Failure Classification

### 6.1 Categories

| Category | Examples | Retry default | Typical user action |
|---|---|---|---|
| Configuration Error | Missing field, invalid model/base URL, unknown option, type mismatch | No, until revision changes | Correct Provider/Profile definition |
| Credential Error | Missing/revoked version, authentication rejected, rotation conflict | No automatic retry for same version | Provision/rotate/select an eligible Credential locally |
| Endpoint Policy Error | Prohibited scheme/destination, userinfo, metadata/private-network violation, unsafe redirect | No | Correct endpoint/type or obtain explicit policy approval where supported |
| Network Error | DNS timeout, connect timeout, transient TLS/network failure | Bounded retry may be allowed | Check Provider/network; retry after cooldown |
| TLS Error | Certificate/hostname failure, downgrade, unsupported TLS | Normally no automatic retry | Correct endpoint/certificate/network interception |
| Capability Error | Runtime/adapter/capability missing or stale | No until capability refresh/change | Install/upgrade supported Runtime or refresh evidence |
| Compatibility Error | Unsupported protocol/model/streaming/Runtime behavior | No for same versions | Select compatible Provider/profile/Runtime |
| Security Policy Error | SSRF classification, credential forwarding risk, excessive response, malicious redirect | No | Change definition; security policy cannot be bypassed by ordinary retry |
| Provider Limit Error | Rate limited, quota exhausted, service unavailable | Policy-bounded | Wait, restore quota, or retry with explicit cost policy |
| Runtime Error | Runtime unavailable, public command changed, bounded probe failed | Bounded after capability refresh | Restore Runtime health; do not activate blindly |
| Approval/Cost Error | Confirmation missing/expired, paid test not authorized | No | Obtain new per-run approval |
| Validator Internal Error | Parser/schema mismatch, invariant failure | No automatic activation | Upgrade/fix validator; evidence remains unknown |

### 6.2 User-action versus system-action failures

User-actionable findings identify only safe remediation categories. They do not
echo tokens, Provider bodies, internal addresses, or raw Runtime errors.

System-actionable transient failures may be retried only under the policy in
section 7. Security-policy, invalid-definition, rejected-authentication, and
version-incompatibility findings are not converted into retry storms.

### 6.3 Partial and indeterminate failure

A pipeline can finish with a mix of passed, failed, untested, and unknown
dimensions. It preserves that matrix. If a live request may have reached the
Provider but the response was lost, the outcome is indeterminate; AgentBox does
not immediately repeat a potentially paid request or claim it failed.

## 7. Retry Policy

### 7.1 Retryable failures

Potentially retryable findings include transient DNS/connect/read timeouts,
bounded `429` responses honoring a safe `Retry-After`, selected `5xx` service
errors, and temporary Runtime unavailability after a fresh health check.

Retries require:

- the same immutable validation scope and authorization;
- evidence that the operation is safe to repeat;
- bounded attempts, exponential backoff with jitter, and a maximum elapsed
  window;
- per-Provider, Credential, Runtime, destination, and administrator rate limits;
- preserved cost/data-boundary approval for each paid or data-bearing attempt;
- cancellation and deadline propagation;
- a new evidence attempt record rather than rewriting the prior failure.

### 7.2 Non-retryable failures

No automatic retry occurs for:

- malformed or prohibited Provider configuration;
- endpoint-policy/SSRF/TLS-policy violation;
- authentication rejection for the same Secret version;
- missing/revoked/deleted Credential state;
- unsupported Runtime/adapter/protocol/model version;
- validator invariant/schema error;
- missing approval or expired plan;
- response/body/stream limit or malicious-behavior violation;
- unknown outcome of a potentially paid or non-idempotent request.

The controlling revision, policy, capability, Credential version, or approval
must change before a new run.

### 7.3 Cooldown and rate limiting

The control plane owns scheduling and persisted cooldown metadata; Runtime
enforces local concurrency and bounded execution. The first implementation
should use conservative fixed caps, not Provider-supplied arbitrary retry loops.

Rate limits must prevent:

- credential guessing or an authentication oracle;
- internal-network scanning across endpoint variants;
- cost amplification;
- Runtime/Provider resource exhaustion;
- many simultaneous streaming connections.

Provider `Retry-After` is capped by AgentBox policy and never parsed as a shell,
date command, or arbitrary scheduling expression.

### 7.4 Refresh is not retry

Refreshing expired static/capability evidence is a new validation run. Repeating
a live Provider request is a retry with potential side effects. The UI/API must
not blur these operations behind one automatic `refresh` action.

## 8. Activation Relationship

### 8.1 Required order

```text
Provider definition/revisions
    -> Validation Pipeline
    -> immutable Evidence Bundle + Eligibility
    -> Config Transaction Plan
    -> user approval/confirmation
    -> transaction revalidation
    -> snapshot/apply/verify
    -> Runtime Binding commit or verified rollback
```

Validation never writes Runtime configuration, changes the active Runtime
Binding, restarts Codex, or migrates a session.

### 8.2 Transaction binding

The Phase 11.4 transaction plan binds:

- exact evidence-bundle digest and policy version;
- Provider, Credential, Secret-version reference, Runtime Profile, Runtime
  Binding, and Runtime capability revisions;
- required validation matrix and expiry;
- endpoint destination/data boundary and cost class;
- expected Runtime/Remote/session impact.

Immediately before mutation, the transaction framework verifies that the
bundle remains fresh and all scope revisions match. It does not silently run a
different validation, accept a newly rotated Secret, or reinterpret evidence
under a new policy inside the approved plan.

### 8.3 Activation and post-validation

Pre-activation validation establishes eligibility. After configuration is
applied, transaction post-validation must gather the operation-specific Runtime,
Remote, and continuity evidence required by the plan. A pre-activation direct
Provider `PASS` cannot replace that post-application evidence.

The active Runtime Binding is committed only after all mandatory post-validation
passes. Failure invokes the Phase 11.4 verified rollback path. There is no
automatic Provider fallback.

### 8.4 Existing sessions

Validation evidence does not rewrite, reattribute, or migrate existing
sessions. Existing sessions remain bound to their recorded effective state or
remain explicitly legacy/unbound. If public evidence cannot prove continuity,
the result is `UNKNOWN` or `EXPERIMENTAL`, and policy decides whether activation
is blocked or requires a new session and stronger confirmation.

## 9. Audit Model

### 9.1 Recorded events

The existing audit model should record safe events such as:

- `provider_validation_requested`;
- `provider_validation_started`;
- `provider_validation_stage_completed`;
- `provider_validation_completed`;
- `provider_validation_failed`;
- `provider_validation_cancelled`;
- `provider_validation_expired`;
- `provider_validation_invalidated`;
- `provider_validation_retry_scheduled`;
- `provider_activation_eligibility_derived`.

Events may include actor, ValidationRunID, Provider/Credential/Profile/Binding/
Runtime opaque IDs, expected revisions, stage/dimension, validator/policy
version, sanitized result/finding code, timestamps, retry count/cooldown, cost
approval class, and transaction correlation.

### 9.2 Never recorded

Audit, Jobs, logs, reports, metrics, and ordinary API/UI output never record:

- Secret values, ciphertext, keys, token hints, headers, cookies, or auth files;
- raw request/response/provider error bodies;
- prompts, completions, tools, streamed content, or conversation history;
- raw DNS answers, certificate dumps, internal network scan details, or proxy
  credentials;
- raw Runtime output, config, paths, environments, process data, or snapshots;
- arbitrary labels/metadata without bounding and sanitization.

### 9.3 Audit and evidence distinction

Audit proves who requested which workflow and what safe result AgentBox recorded.
Evidence supports a time-bound compatibility/eligibility decision. Audit does
not duplicate the evidence payload, and evidence does not replace authorization
or approval audit.

## 10. Security Model

### 10.1 Malicious Provider endpoint and SSRF

Provider endpoints are an outbound data-exfiltration and network-reachability
boundary. Controls include:

- Provider-type-specific endpoint policies;
- fixed Official Provider authorities;
- canonical URL parsing and IDNA/Unicode handling;
- prohibition of userinfo, fragments, credential-bearing queries, ambiguous IP
  forms, and control characters;
- explicit destination classification for loopback/private/local use;
- denial of link-local/cloud metadata, multicast, unspecified, and prohibited
  ranges;
- policy across every IPv4/IPv6 DNS answer and redirect hop;
- redirect disabled by default and no credential forwarding across authority;
- DNS-rebinding-resistant resolution/connection handling;
- HTTPS and certificate/hostname verification by default;
- no ambient proxy/environment trust;
- strict time, response, streaming, redirect, decompression, and concurrency
  bounds.

The Runtime cannot accept a caller-provided arbitrary URL request. The endpoint
comes only from a validated Provider revision and typed adapter.

### 10.2 Secret leakage

The control plane validates only Credential metadata and safe presence/lifecycle
evidence. Live authentication, if approved later, resolves exactly one Secret
version inside Runtime for one bound validator operation. Plaintext is never
returned or persisted in SQLite, evidence, audit, logs, argv, URLs, config,
snapshots, or reports.

Raw Provider errors are treated as hostile and mapped to bounded codes. Redirects
cannot carry credentials to a different authority.

### 10.3 Unauthorized activation

Validation evidence is not authorization. Activation separately requires an
authenticated/authorized transaction, current plan, expected revisions, fresh
evidence digest, impact/cost/data-boundary confirmation, and Phase 11.4
transaction controls. Runtime cannot self-activate based on its own test result.

### 10.4 Unsafe Runtime change and privilege escalation

The validation contract contains no file write, config, shell, executable,
argv, environment, path, PID, signal, sudo, package, or systemd operation. Live
probes run as non-root `agentbox-runtime` through fixed reviewed adapters. Root
Helper is not involved.

Validation cannot attach to tmux, edit Codex/Claude private files, manipulate
sessions, or widen the Phase 11.2 observation contract.

### 10.5 Resource, cost, and data-exfiltration abuse

All live probes have fixed minimal payloads, maximum output/stream duration,
deadlines, concurrency caps, and cost/data-boundary classifications. Paid or
data-bearing tests require per-run approval. CI uses deterministic fake Provider
fixtures and no real credentials.

The pipeline is not a generic uptime monitor. Continuous health monitoring,
automatic retry/failover, and background paid requests require separate product
and security decisions.

### 10.6 Evidence tampering, replay, and confusion

Immutable IDs/revisions, validator and policy versions, expiry, scope digest,
append-only evidence, transaction plan binding, and Runtime peer authentication
prevent stale evidence from being replayed for a different Provider, Credential,
model, destination, Runtime, or Secret version.

Fixture/simulated evidence is explicitly classified and cannot satisfy a real
activation policy unless that policy deliberately permits that evidence class.

### 10.7 Tenant isolation

The current product is single-server and single-administrator; Phase 11 does not
claim multi-tenant isolation. Nevertheless every evidence record is scoped to
opaque Provider, Credential, Runtime, and transaction identities so a future
tenant model cannot rely on display names or global Provider state. Adding
multi-tenancy requires a separate architecture and authorization review.

### 10.8 Residual risks

- A compromised `agentbox-runtime` or root can observe live Secret use and forge
  local execution evidence within that trust boundary.
- Provider behavior, DNS, certificates, availability, quota, pricing, and models
  can change immediately after validation.
- Public Runtime contracts and compatibility behavior can change by version.
- A minimal request cannot prove all prompts, streaming, tools, or continuity.
- Network classification and DNS rebinding defenses require platform-specific
  implementation tests.
- False-positive/negative compatibility remains possible; detailed evidence and
  uncertainty must stay visible.

## 11. ADR Decisions

### 11.1 Decision-numbering note

The task specification proposed `ADR-041` through `ADR-044`. The authoritative
Phase 11.4 ADR already uses `ADR-041` for “Runtime owns local configuration
application.” Reusing that global identifier would make architecture references
ambiguous. This document therefore uses the qualified canonical identifiers
`ADR-11.5-041` through `ADR-11.5-048`. The first four preserve the requested
decision numbers within the Phase 11.5 namespace. A project-wide ADR registry
and final renumbering policy remain approval items; no existing ADR is silently
renumbered here.

### ADR-11.5-041 — Provider activation requires validation evidence

**Status:** Proposed

**Decision:** An activation transaction must reference a fresh immutable
validation-evidence bundle bound to the exact Provider, Credential/Secret
version reference, Runtime Profile, Runtime Binding, Runtime installation,
capability evidence, adapters, and policy revisions.

**Consequence:** A configured Provider cannot become active merely because its
record exists or an endpoint once responded.

### ADR-11.5-042 — Validation does not equal an execution guarantee

**Status:** Proposed

**Decision:** Validation is time-bound evidence about explicit dimensions. It
does not guarantee future availability, quota, cost, model behavior, arbitrary
requests, Runtime behavior, Remote Control, or session continuity.

**Consequence:** Detailed outcomes and expiry remain visible; Provider API
`PASS` cannot promote untested higher layers.

### ADR-11.5-043 — Validation evidence contains no Secret Material

**Status:** Proposed

**Decision:** Evidence stores only opaque IDs/revisions, typed outcomes,
versions, times, provenance, and sanitized finding codes. Secret values,
ciphertext, headers, payloads, raw Provider errors, and Runtime output are
prohibited.

**Consequence:** Evidence can support policy and audit without turning SQLite or
the Web/API into a credential or Provider-data exposure path.

### ADR-11.5-044 — Expired or invalidated evidence requires revalidation

**Status:** Proposed

**Decision:** Evidence is immutable and time/revision bound. Expiry or a change
to any relevant identity, revision, validator, adapter, policy, capability,
Credential version, endpoint, protocol, or model removes activation eligibility
until a new run succeeds.

**Consequence:** AgentBox never refreshes timestamps or reinterprets stale
evidence to preserve a desired activation.

### ADR-11.5-045 — Validation stages remain independently observable

**Status:** Proposed

**Decision:** Definition, capability, Credential boundary, endpoint/network,
authentication, model, wire, Provider API, Runtime, Remote, resume, context, and
discovery dimensions retain separate evidence and outcomes.

**Consequence:** Lower-layer success cannot conceal a failed, unknown, or
untested higher layer.

### ADR-11.5-046 — Offline and live validation are distinct operations

**Status:** Proposed

**Decision:** Offline validation performs no network or Secret use. Live
validation is a separate typed Runtime operation with explicit authorization,
destination/cost policy, bounds, and Secret-use scope.

**Consequence:** Planning and routine metadata checks cannot unexpectedly spend
money, disclose data, or contact an external Provider.

### ADR-11.5-047 — Endpoint validation is Provider-type-specific and fail closed

**Status:** Proposed

**Decision:** Official, compatible, local, and Runtime-native Providers use
separate typed endpoint policies. Unsafe or ambiguous schemes, addresses,
redirects, proxy behavior, or transport evidence fail closed.

**Consequence:** Provider validation cannot be repurposed as arbitrary outbound
HTTP, credential forwarding, metadata access, or internal-network scanning.

### ADR-11.5-048 — Validation eligibility never activates a Runtime

**Status:** Proposed

**Decision:** Eligibility is input to a Phase 11.4 configuration transaction.
Only that separately approved transaction may snapshot, apply, post-validate,
commit a Runtime Binding, or perform verified rollback.

**Consequence:** Control-plane evidence, Runtime execution ownership, and
configuration mutation remain separate trust and lifecycle boundaries.

## 12. Open Questions

The following require product, security, or implementation approval before any
live validation work begins:

1. **ADR numbering:** Should the project adopt qualified IDs such as
   `ADR-11.5-041`, create a central registry, or renumber the extra Phase 11.4
   decisions before these ADRs become Accepted?
2. **Validation frequency:** Which stages run on create/edit, before every plan,
   before execution, on demand, or periodically?
3. **Evidence TTL:** What TTL applies independently to definition, capability,
   DNS/TLS, authentication, model, Provider API, Runtime, and Remote evidence?
4. **Invalidation policy:** Which product/security advisories or policy changes
   immediately invalidate stored evidence?
5. **Activation threshold:** Which detailed dimensions are mandatory for
   Official, compatible, local, and Runtime-native Provider classes?
6. **Experimental activation:** May `UNKNOWN`, `EXPERIMENTAL`, `DEGRADED`, or
   `NOT_TESTED` Remote/continuity evidence proceed with confirmation, or must it
   block v1 activation?
7. **Endpoint policy:** Are public OpenAI-compatible endpoints HTTPS-only, and
   which private/loopback destinations are permitted exclusively for Local
   Providers?
8. **DNS rebinding:** Which resolver/connection binding mechanism is portable
   and verifiable across the qualified Linux platforms and IPv4/IPv6?
9. **Redirects:** Are any redirect status codes required by supported public
   Provider contracts, and under what same-authority rules?
10. **Proxy support:** Is a future typed outbound proxy allowed, and where would
    its credential boundary live? Ambient proxy variables should remain denied.
11. **Live payload:** What fixed minimal request, maximum token/output size, and
    non-user content can validate each wire protocol without leaking data?
12. **Cost approval:** Which checks can incur charges, how is maximum cost
    communicated, and does every retry require renewed confirmation?
13. **Rate limits:** What per-Provider/Credential/Runtime/destination limits and
    cooldowns prevent auth or network scanning abuse?
14. **Credential rejection:** How many rejected-auth observations are allowed
    before cooldown, and when does rejection change Credential lifecycle state?
15. **Evidence storage:** What future database tables, retention, pruning, and
    aggregate materialization are required without storing sensitive payloads?
16. **Health monitoring:** Is periodic Provider monitoring a later feature, or
    should validation remain strictly on-demand for v1?
17. **Offline behavior:** Can a Provider ever be activation-eligible with only
    offline evidence, especially for a Runtime-native or disconnected Local
    Provider?
18. **Fixture provenance:** Which fake-provider evidence classes can satisfy CI
    gates but never real activation eligibility?
19. **Public Codex contract:** Which then-current public Codex capabilities prove
    Provider profile validation, minimal Runtime use, Remote recovery, and
    continuity without private-state access?
20. **Claude boundary:** Should future official Claude Runtime Provider support
    use a separate adapter only when the Runtime exposes a public contract, while
    v1 remains Runtime/session-only?
21. **User approval:** Which validation stages require recent authentication,
    explicit data-destination confirmation, or maintenance-window approval?
22. **Error disclosure:** Which safe finding codes and remediation guidance are
    useful without revealing internal addresses, Provider bodies, or Secret
    validity oracles?
23. **Cancellation and unknown outcomes:** How long must the control plane wait
    before declaring a run indeterminate, and when may a paid test be retried?
24. **Post-activation evidence:** Which pre-validation evidence can be reused in
    transaction verification, and which must always be recollected after apply?

## Recommended Next Design Phase

Proceed only after human approval to **Phase 11.6 — Codex Provider Adapter and
Dry-run Plan Design**. That phase should map typed Provider intent and the
approved validation evidence contract to the then-current public Codex
configuration capability, generate safe revision-bound dry-run plans, preserve
unrelated settings, and keep all real activation disabled.
