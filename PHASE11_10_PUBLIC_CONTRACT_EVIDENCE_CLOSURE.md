# AgentBox Phase 11.10 — Public Contract Evidence and Supplemental Decision Closure

Status: **Technical contract closure complete — repository persistence pending**
Architecture decision: **BLOCKED pending review and merge of this governance change**
Repository baseline: `ForceMind/agentbox` at
`1c2005de59b1c5063b260591206a8411c7e5b1a5`
Release baseline: `v0.3.0-rc.1`
Evidence review date: **2026-08-14**

This document closes the Phase 11.9 **technical** architecture blockers by recording current
public Codex evidence and defining supplemental decisions P11-ADR-071 through
P11-ADR-076. It authorizes no code, migration, Secret creation, Provider
request, or Runtime/Codex/Claude mutation.

The contracts in this branch do not become durable repository governance until
the documentation PR is reviewed, passes protected checks, and is merged into
`main`. Therefore the Phase 11 Implementation Gate remains `BLOCKED`. Even
after that merge, implementation requires separate authorization and the
milestone gates in P11-ADR-076; this review itself authorizes no production
engineering.

## Canonical numbering note

`PHASE11_CONTRACT_FREEZE_REVIEW.md` provisionally reserved P11-ADR-071 through
P11-ADR-076 for six unresolved decision areas. The Phase 11.10 task provides the
final titles and allocation below. Those final allocations supersede only the
provisional, unaccepted titles in the Phase 11.9 review:

| Canonical ID | Final title in this review |
|---|---|
| P11-ADR-071 | Codex Contract Evidence Boundary |
| P11-ADR-072 | Codex Managed Configuration Scope |
| P11-ADR-073 | Secret Cryptography Contract |
| P11-ADR-074 | Key Custody and Recovery Contract |
| P11-ADR-075 | Activation and Recovery Policy |
| P11-ADR-076 | Implementation Governance Contract |

The accepted P11-ADR-001 through P11-ADR-070 decisions are unchanged. Their
security requirements are incorporated into these supplemental decisions,
including the previously open Secret ingress/backup/retention, Provider network
policy, existing-session policy, transaction locking, crash recovery, and
rollback-retention questions.

# 1. Public Contract Evidence Review

## 1.1 Evidence method and boundaries

This review used only:

1. official OpenAI Codex documentation;
2. the official public Codex configuration schema;
3. read-only public CLI help from the installed Codex CLI;
4. the accepted AgentBox Phase 11 design documents.

It did not:

- read `~/.codex/config.toml` or any Codex credential/session file;
- inspect private Codex databases, JSONL, rollout, thread, or process state;
- call OpenAI or any third-party Provider API;
- use, create, validate, or display a real credential;
- start, stop, pair, restart, or reconfigure Codex;
- treat observed implementation details as public contracts.

Public documentation is time-varying. The evidence below is dated and must be
snapshotted into sanitized fixtures before an affected implementation is
enabled. A current documentation URL is not a permanent protocol version.

## 1.2 Evidence sources

| Evidence ID | Source | Evidence used | Authority and limitation |
|---|---|---|---|
| CE-001 | [Official Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) | User-level/project-level config locations, Provider-key placement rules, documented Provider fields | Public documentation as observed on 2026-08-14; not a version-pinned promise for future Codex releases |
| CE-002 | [Official Codex configuration schema](https://learn.chatgpt.com/docs/config-schema.json) | Machine-readable `model_provider`, `model_providers`, `env_key`, `base_url`, and `wire_api` definitions | Public schema as observed on 2026-08-14; must be captured and hashed per adapter profile before implementation |
| CE-003 | [Official Codex developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli) | CLI maturity and documented `remote-control` start/stop/pair/JSON behavior | Public CLI documentation; explicitly classifies `remote-control` as Experimental |
| CE-004 | [Official Codex configuration basics](https://learn.chatgpt.com/docs/config-file/config-basic) | Configuration precedence: CLI, project, profile, user, system, defaults | Public documentation observed on 2026-08-14 |
| CE-005 | [Official Codex advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced) | Custom Provider IDs, fixed Provider fields, `env_key`, command-backed authentication, and exclusions between authentication modes | Public documentation observed on 2026-08-14 |
| CE-006 | [Official Codex authentication documentation](https://learn.chatgpt.com/docs/auth) | ChatGPT login, OpenAI API-key login, Codex access tokens, local login cache, Provider authentication distinctions | Public documentation observed on 2026-08-14; AgentBox never reads the documented cache |
| CE-007 | [Official managed configuration documentation](https://learn.chatgpt.com/docs/enterprise/managed-configuration) | Requirements and managed-default behavior and precedence | Public documentation observed on 2026-08-14; support differs by client/version |
| CE-008 | [Official Codex app-server documentation](https://learn.chatgpt.com/docs/app-server) | app-server is an experimental development/integration surface | Public documentation observed on 2026-08-14; Phase 11 adds no app-server protocol dependency |
| CE-009 | Installed `codex-cli 0.147.0` public `--help` output | Local corroboration of `--strict-config`, `$CODEX_HOME/<name>.config.toml` profiles, Provider-related global options, and Experimental command families | Read-only host evidence; SHA-256 `729c716c961be6575059274ad202aca4ff470a0a0ce556afa9fa7bad5fe9d333` |
| CE-010 | Installed `codex-cli 0.147.0 remote-control --help` and subcommand help | Local corroboration of start, stop, pair, and JSON output option | Read-only evidence; command digest `fd1a2980f3aa4251e1151614255d07ef777f6e240ce3a9c8e3684bd88fd02d7c`; no lifecycle operation was executed |
| CE-011 | Installed `codex-cli 0.147.0 login --help` | Local corroboration that login credentials enter through stdin and are separate from custom Provider authentication | Read-only evidence; SHA-256 `bb7b92fefb72286906fb54638a4e0bc5717ab44cde155f4a2ffb454941e82c8e` |
| CE-012 | Installed `codex-cli 0.147.0 app-server --help` | Local corroboration that app-server is Experimental | Read-only evidence; SHA-256 `97a371dd6b3fbb165f46a5f1309f872689fe335068dbdccb3cc932002c0a6e20` |

The schema fetched from CE-002 on 2026-08-14 has SHA-256
`b9105f17442d5c41ba5d4d82603259d3cc0ceb38aeb3badf9e5ca20da328ae6e`.
The Remote `start`, `stop`, and `pair` help digests are respectively
`82231212562b8bb2f30b884d5087f79217e7405d7d8c08006c2a078b3c9d56ee`,
`d20d86402b83294c5ae427906e2698289e1de2d270572d978365dd5c777d1413`,
and `4824d567f71e720031140bb4890a7921638c883a50921a021a92551bf4c4fbe0`.

The future fixture record for each supported Codex adapter profile must include
source URL, retrieval time, content digest, Codex version/help digest, fixture
schema, sanitization statement, and review status. Real credentials, host paths,
account identifiers, Pair Codes, and private Runtime state are prohibited.

## 1.3 Confirmed public behavior

The following facts are confirmed only within the scope stated.

### Configuration location and precedence

- The public configuration reference documents user-level configuration at
  `~/.codex/config.toml`.
- Project-level `.codex/config.toml` exists, but public documentation states
  that Provider and authentication selection keys such as `model_provider` and
  `model_providers` are ignored there. Provider selection is therefore a
  user-level/profile concern, not a Project-controlled value.
- Public profile files are documented next to the user configuration as
  `$CODEX_HOME/<name>.config.toml` and are selected explicitly with
  `--profile <name>`.
- Ordinary configuration precedence is CLI/`--config`, trusted Project layer,
  selected profile, user config, system config, then built-in defaults.
- Admin-enforced `requirements.toml` can constrain supported settings, and
  managed defaults can be reapplied on process start. AgentBox must validate
  the effective qualified profile and never attempt to override a requirement.

These facts allow AgentBox to design a server-resolved, Runtime-user-owned
target. They do not authorize a write or establish that every CLI/daemon/session
path applies a profile identically.

### Authentication identities

The public contract distinguishes four identities that AgentBox must never
merge:

| Identity | Public behavior | Phase 11 treatment |
|---|---|---|
| ChatGPT login | Browser/device sign-in cached by Codex | Runtime-owned and untouched |
| OpenAI API-key login | `codex login --with-api-key`, key read from stdin and cached by Codex | Runtime-owned and untouched; not Provider Manager ingress |
| Codex access token | Enterprise automation token supplied to Codex login | Out of Phase 11 Provider credentials |
| Custom Provider authentication | `env_key`, mutually exclusive command-backed auth, `requires_openai_auth`, or discouraged bearer field | Only the fixed command-backed AgentBox broker contract below is allowed for managed compatible Providers |

Pairing is a fifth, independent Remote Control capability. It is not login or
Provider authentication.

### Provider schema

The current public reference and schema document:

- `model_provider` as a Provider ID selected from `model_providers`;
- `model_providers.<id>` as a custom Provider definition;
- `model_providers.<id>.name`;
- `model_providers.<id>.base_url`;
- `model_providers.<id>.env_key` as the environment-variable name supplying an
  API key;
- `model_providers.<id>.wire_api`, for which `responses` is currently the only
  documented supported value and the default;
- additional Provider fields, including command-backed authentication, direct
  bearer token, static/dynamic headers, query parameters, retry, streaming, and
  transport options.

Public availability of a field does not put that field in AgentBox's allowed
scope. In particular, command-backed authentication, direct bearer tokens, raw
headers, arbitrary query parameters, caller-selected environment names, and
unreviewed transport options are not generic AgentBox inputs. P11-ADR-072
allows only one root-owned executable path and fixed argument schema for the
AgentBox credential broker; users can supply neither command nor arguments.

The reference explicitly discourages direct bearer-token configuration. V1
also rejects `env_key`: a long-lived environment would be inherited by Codex
tool children, while per-session environment behavior is not a sufficiently
isolated public contract. The reviewed command-backed contract instead obtains
a bearer value on demand from one fixed Runtime-owned broker and keeps the
value out of TOML, argv, Control Plane, and long-lived process environment.

### Provider-field qualification matrix

| Public field/capability | Evidence class | AgentBox V1 use |
|---|---|---|
| `model` | `PUBLIC_DOCUMENTED` | Allowed, typed model identifier; exact value revision-bound |
| `model_provider` | `PUBLIC_DOCUMENTED` | Allowed only in an AgentBox-owned profile |
| `model_providers.<id>` | `PUBLIC_DOCUMENTED` | Allowed only for a generated `agentbox_p_<32 lowercase hex>` ID after collision check |
| `name` | `PUBLIC_DOCUMENTED` | Fixed sanitized display value generated from Provider metadata |
| `base_url` | `PUBLIC_DOCUMENTED` | Allowed only after P11-ADR-075 public-HTTPS validation |
| `wire_api` | `PUBLIC_DOCUMENTED` | Fixed to `responses` |
| `env_key` | `PUBLIC_DOCUMENTED` | Excluded from V1 credential delivery |
| `auth.command` | `PUBLIC_DOCUMENTED` | Fixed root-owned AgentBox broker executable only |
| `auth.args` | `PUBLIC_DOCUMENTED` | Fixed verb plus typed Runtime Binding ID and revision only; never caller-provided |
| `auth.cwd` | `PUBLIC_DOCUMENTED` | Excluded |
| `auth.timeout_ms` | `PUBLIC_DOCUMENTED` | Fixed to 2000 ms |
| `auth.refresh_interval_ms` | `PUBLIC_DOCUMENTED` | Fixed to 0; no proactive paid/Secret refresh loop |
| `requires_openai_auth` | `PUBLIC_DOCUMENTED` | Fixed false/omitted for AgentBox custom Providers; AgentBox never changes Codex login |
| `experimental_bearer_token` | `PUBLIC_DOCUMENTED`, discouraged/experimental | Excluded |
| headers/query/retry/stream/WebSocket/search capability fields | `PUBLIC_DOCUMENTED` with field-specific maturity | Excluded from V1 |
| `--strict-config` | `PUBLIC_DOCUMENTED` | Required validation signal, not proof of effectiveness |
| `remote-control` | `PUBLIC_EXPERIMENTAL` | Existing separate Phase 5 path only; not Provider activation evidence |
| app-server transports/protocol | `PUBLIC_EXPERIMENTAL` | No new Phase 11 dependency |

### Public validation signals

- The current official CLI documents `--strict-config` as a way to reject
  fields not recognized by that Codex version.
- The public JSON schema is available for structural validation.

These are useful validation inputs. They do not by themselves prove lossless
round-trip editing, config effectiveness, Provider reachability, authentication,
model availability, or Runtime/session continuity. A candidate-validation
method that would require writing the active config remains unsupported until a
safe public mechanism is proven.

### Remote Control

- Official documentation and local public help expose `remote-control` with
  start, stop, and short-lived Pair Code operations and a machine-readable JSON
  option.
- Official documentation classifies `remote-control` as **Experimental**, not
  Stable.
- The public command documentation describes a short-lived manual Pair Code and
  its machine-readable fields.

AgentBox may continue its existing conservative, versioned Remote integration.
The evidence does not make Remote Control a stable dependency for Provider
activation and does not prove Provider-switch continuity.

## 1.4 Stable supported behavior versus documented current behavior

For Phase 11 purposes, evidence classes are:

| Class | Meaning | Current evidence |
|---|---|---|
| `PUBLIC_STABLE` | Official source explicitly marks the relevant behavior stable | No Phase 11 Provider-activation lifecycle/continuity behavior is established in this class by the reviewed sources |
| `PUBLIC_DOCUMENTED` | Official reference/schema currently documents the field or command | User config/profile concepts; Provider-selection schema; `env_key`; `base_url`; `responses`; strict-config behavior |
| `PUBLIC_EXPERIMENTAL` | Official source documents the behavior and marks it experimental | `codex remote-control` |
| `LOCAL_CORROBORATED` | Current installed public help agrees with reviewed documentation | Codex CLI 0.147.0 help and Remote subcommand shape |
| `UNCONFIRMED` | No reviewed public evidence proves the required behavior | Reload/restart/session/Remote continuity and effective-binding questions listed below |

`PUBLIC_DOCUMENTED` is not promoted to `PUBLIC_STABLE`. An implementation may
support it only through a versioned adapter contract, sanitized fixtures, and a
fail-closed response to change.

## 1.5 Unconfirmed and prohibited assumptions

The reviewed public evidence does **not** establish:

- that config changes hot-reload;
- whether changes apply to a new request, new process, new session, existing
  session, Remote daemon, or all Runtime work;
- whether selecting a profile affects foreground CLI, app-server, and
  `remote-control` identically;
- whether Provider changes require restart, reauthentication, new session, or
  new pairing;
- whether an existing Remote connection, pairing, thread, history, context,
  tools, streaming, Responses behavior, or discovery survives a change;
- a public active-writer/idle signal sufficient for safe mutation;
- a stable public effective-Provider observation for a session;
- a public AgentBox ownership marker for a Provider block or profile;
- lossless preservation of comments, ordering, unknown future keys, or other
  unrelated TOML content by any particular library;
- a supported atomic update command or no-write candidate validation command;
- that a successful direct Provider request proves Codex Runtime or Remote
  compatibility;
- that a dynamically published schema will remain compatible with Codex CLI
  0.147.0 or any future version;
- that private Codex files or internal identifiers are safe product contracts.

These remain `UNKNOWN` until public evidence and deterministic fixtures prove a
narrower result. Private files, reverse engineering, live credential behavior,
or successful observation on one host cannot fill the gap.

## 1.6 Evidence conclusion

The current public contract is sufficient to begin:

- non-secret Provider-domain implementation;
- read-only Runtime capability contracts;
- versioned public-contract fixture tooling;
- an offline, feature-disabled Codex mapping prototype/dry-run against sanitized
  fixtures.

It is not sufficient to enable live Codex configuration activation or claim
session/Remote continuity. Those remain gated by P11-ADR-071, P11-ADR-072, and
P11-ADR-075.

# 2. P11-ADR-071 — Codex Contract Evidence Boundary

**Status:** Accepted in the candidate canonical registry; repository-effective
only after this governance change is reviewed and merged into `main`.

## Decision

AgentBox may depend only on a versioned `CodexPublicContractProfile` built from:

1. then-current official OpenAI Codex documentation;
2. the official public Codex configuration schema;
3. public CLI help from the exact supported Codex executable;
4. sanitized deterministic fixtures derived from those sources;
5. explicit AgentBox compatibility tests for the exact adapter profile.

Each dependency must identify the exact fact being relied upon. The adapter
profile records its evidence date, source/content digests, supported Codex
version/help fingerprints, schema version, allowed features, and maturity
classification.

AgentBox must treat as unstable:

- any behavior marked Experimental, including current Remote Control;
- a dynamic `latest` schema not captured by content digest;
- undocumented file formats, internal identifiers, processes, reload timing,
  caches, databases, thread stores, JSONL, or rollout data;
- output not covered by a conservative fixture/parser contract;
- version proximity or semantic-version range without matching public evidence;
- successful behavior observed only with a real credential or one host;
- assumptions about session, pairing, Remote, or context continuity.

## Contract rules

- Exact profile match is required; no nearest-version or optimistic fallback.
- Missing, changed, malformed, incomplete, or contradictory evidence yields
  `UNKNOWN`/`UNSUPPORTED` and blocks the affected operation.
- Public fields are not automatically allowed AgentBox inputs. An explicit
  typed allowlist is still required.
- Experimental behavior may support read-only diagnostics or an explicitly
  experimental plan, but cannot satisfy an unconditional activation guarantee.
- Every implementation/release revalidates the public contract; fixtures are
  invalidated when Codex executable/help or schema digest changes.
- The current local 0.147.0 observation is evidence for planning only. This ADR
  does not declare it the permanent supported range.
- No Provider API or real credential is needed to qualify static public-contract
  syntax and capability evidence.

## Consequences

- Phase 11 can implement contract registries and fail-closed adapters without
  binding the domain to today's observed schema forever.
- Live activation remains disabled when lifecycle/continuity facts are not
  publicly proven.
- Existing Remote Control behavior is preserved as a separate experimental
  integration and is never used as proof of Provider compatibility.

# 3. P11-ADR-072 — Codex Managed Configuration Scope

**Status:** Accepted in the candidate canonical registry; repository-effective
only after this governance change is reviewed and merged into `main`.

## Decision

AgentBox never owns the complete Codex configuration. It may manage only a
versioned, adapter-declared semantic scope after explicit administrator adoption
and a read-only dry-run.

The v1 boundary is an AgentBox-namespaced public profile file selected
explicitly for AgentBox-managed **new work**. Its fixed name is
`$CODEX_HOME/agentbox-<32-lowercase-hex-profile-id>.config.toml`; the profile ID
is generated by AgentBox and cannot be supplied by a user. Every managed Codex
invocation uses the reviewed `--profile` argument with that exact generated
name. The adapter enables this contract only when the exact Codex profile proves
that:

- Provider keys are valid in that profile layer;
- the exact AgentBox-started Codex path selects it consistently;
- the profile does not alter existing/unmanaged work;
- Remote Control impact is known or separately blocked;
- a collision-free AgentBox-owned profile identity can be proven.

If those facts are not proven, the adapter must report the profile strategy as
`UNSUPPORTED`/`UNKNOWN`. It must not silently fall back to taking over
`~/.codex/config.toml`.

## Initial AgentBox-managed semantic fields

For an accepted Codex contract profile, the complete V1 managed scope is:

- the selected `model_provider` for AgentBox-managed work;
- the selected `model` for AgentBox-managed work;
- one AgentBox-generated, collision-checked custom Provider entry when a custom
  Provider is required;
- within that entry: generated `name`, validated `base_url`, fixed
  `wire_api = "responses"`, and a fixed command-backed `auth` table;
- `auth.command =
  "/opt/agentbox/current/venv/bin/agentbox-runtime-provider-credential"`;
- `auth.args = ["codex", "<RuntimeBindingID>", "<binding-revision>"]`, where
  both variable values are server-generated typed non-secret identifiers from
  the approved plan;
- `auth.timeout_ms = 2000` and `auth.refresh_interval_ms = 0`.

Official OpenAI API-key use follows the same AgentBox-owned custom-Provider
profile with the fixed official HTTPS authority. AgentBox does not overwrite
the reserved built-in `openai` Provider and does not call `codex login`.
`requires_openai_auth` is false/omitted so Codex login remains untouched.

The credential broker is a root-owned immutable release executable running as
`agentbox-runtime`. It accepts only the literal `codex` verb, one UUID-shaped
Runtime Binding ID, and one positive integer revision. It returns a Secret only
when that exact Binding/revision is active, verified, not fenced, and maps to
one usable Secret version. It accepts no command, path, environment, Provider
ID, Credential ID, Secret ID, or output-format selector. It receives no stdin,
emits the token only on stdout to Codex, emits sanitized errors on stderr, and
never involves the Root Helper. Same-UID Runtime compromise remains an explicit
residual risk; this broker creates no Control Plane or cross-UID reveal API.

The initial scope explicitly excludes:

- caller-selected command-backed authentication; only the fixed broker shape
  above is allowed, while `auth.cwd` remains excluded;
- `env_key` and long-lived Provider credential environment injection;
- direct bearer tokens;
- arbitrary/static/environment-derived headers;
- arbitrary query parameters;
- caller-controlled environment-variable names;
- retry/streaming/WebSocket/search options;
- raw TOML, arbitrary keys, arbitrary Provider IDs, paths, commands, or values;
- requirements/admin policy, sandbox, tools, hooks, profiles owned by the user,
  MCP, telemetry, notifications, Projects, sessions, or credentials.

## User-owned configuration

All existing base configuration, project configuration, non-AgentBox profiles,
unrelated Provider entries, comments, ordering, extensions, permissions, and
unknown future fields remain user/Codex-owned.

AgentBox must:

- use a server-generated namespace and reject an existing/colliding object;
- record ownership outside Codex configuration in its Runtime journal and
  control-plane metadata, never through an undocumented TOML marker;
- `lstat` and digest the user base config, system config if present, selected
  managed requirements evidence, and target profile metadata before planning;
- parse the AgentBox target profile with a lossless TOML parser and reject any
  field outside the exact allowlist before planning;
- preserve user-owned files and values byte-for-byte when it does not own the
  target;
- never import or adopt an existing Provider block by matching names/URLs;
- never remove or rewrite unrelated entries;
- detect an out-of-band edit by fingerprint/revision and fail closed;
- use fixed Runtime-resolved targets with no-follow/trusted-parent protection;
- snapshot only the exact AgentBox-owned, allowlist-validated, non-secret
  profile bytes plus its prior nonexistence/existence, digest, owner/group/mode,
  inode metadata, and parent fingerprints;
- block if target ownership, public profile semantics, preservation, or Remote/
  session impact cannot be proven.

The user base config is never copied into an AgentBox journal. Its contents,
comments, ordering, unknown keys, and any user-managed Secret-bearing values
remain untouched. The transaction stores only its SHA-256 fingerprint and safe
stat metadata. A changed fingerprint invalidates the plan and an external edit
during apply/recovery yields `NEEDS_ATTENTION`; AgentBox never overwrites the
external edit. Because the target profile is wholly AgentBox-owned and is
rejected if it contains non-allowlisted content, exact profile preimage bytes
are safe to retain and sufficient for rollback without duplicating unmanaged
Secret Material.

Profile publication uses a same-directory `0600` temporary regular file opened
with no-follow/exclusive semantics, full validation, file `fsync`, atomic
`rename`, and parent-directory `fsync`. The fixed `$CODEX_HOME` parent and every
ancestor must be owned by `agentbox-runtime`, non-group/world-writable, and not
a symlink. A prior non-existent target is removed during rollback only if the
current inode and digest exactly match the transaction postimage.

## Activation relationship

Creating or updating an AgentBox-owned profile is not activation. New work must
select the exact profile through a reviewed public invocation contract, and the
Runtime Binding becomes active only after required verification.

Existing sessions, foreground work, unmanaged Codex invocations, login state,
and Remote pairing are never relabeled, migrated, or modified. If an exact
public profile cannot isolate new work, v1 activation is blocked pending a new
ADR rather than editing the user's base config.

The current `remote-control` command does not expose a public `--profile`
contract. Therefore V1 does not attach an AgentBox Provider profile to the
existing Remote daemon and does not claim Provider-managed Remote sessions.
The existing Experimental Remote capability continues unchanged with its
existing user/Codex-owned configuration. This exclusion is what prevents
Provider activation from restarting, re-pairing, or silently changing it.

## Consequences

- Full configuration takeover is prohibited by construction.
- The safest supported outcome on an unqualified Codex version is read-only
  evidence and a blocked dry-run.
- A future decision may approve a different public update mechanism, but it
  must supersede this ADR explicitly and retain the non-takeover invariant.

# 4. P11-ADR-073 — Secret Cryptography Contract

**Status:** Accepted in the candidate canonical registry; repository-effective
only after this governance change is reviewed and merged into `main`.

## Decision

Every stored Provider Secret version uses envelope schema
`agentbox.provider-secret-envelope.v1` implemented only through the PyCA
`cryptography` hazmat `AESGCM` and `HKDF` APIs. The implementation dependency
must be exact-version/hash locked and vulnerability-reviewed in the Secret PR;
changing the library family or primitives requires a superseding ADR. The
frozen cryptographic profile is:

- a 32-byte CSPRNG root/master key;
- HKDF-SHA-256 deriving one 32-byte Provider Secret KEK with no caller input;
- HKDF salt `SHA-256("agentbox/provider-secret/hkdf-salt/v1" ||
  canonical-runtime-installation-id)` and info
  `"agentbox/provider-secret/kek/v1"`;
- one fresh 32-byte CSPRNG DEK per immutable Secret version;
- AES-256-GCM for Secret payload encryption under the DEK;
- AES-256-GCM for DEK wrapping under the derived KEK;
- independent CSPRNG-generated 12-byte nonces for payload and wrap operations;
- a 16-byte GCM authentication tag produced/verified by the library;
- RFC 8785 JSON Canonicalization Scheme bytes for associated-data objects and
  envelope metadata; no ad-hoc string concatenation;
- Base64url without padding for binary envelope fields and lowercase UUID text
  for identities.

Payload associated data contains exactly: envelope schema, algorithm ID
`A256GCM-HKDF-SHA256-v1`, RuntimeInstallationID, CredentialID, SecretRecordID,
credential kind, Secret version, and DEK envelope ID. DEK-wrap associated data
contains exactly: envelope schema, algorithm ID, RuntimeInstallationID,
SecretRecordID, Secret version, DEK envelope ID, and KEK key ID/version. Any
identity transplant therefore fails authentication.

No caller supplies a nonce. The store enforces a unique index on
`(kek_key_id, wrap_nonce)` and refuses a duplicate before publication. Each DEK
encrypts exactly one payload, so its payload nonce is single-use by
construction. A KEK is retired before `2^32` successful wrap operations;
counter uncertainty or nonce collision yields `NEEDS_ATTENTION`, never retry
with the same material.

Plaintext, DEKs, and unwrapped keys exist only for one action-bound lifetime and
are excluded from logs, exceptions, dumps, audits, metrics, Codex config,
Control Plane DB, argv, reports, and IPC responses. Best-effort buffer clearing
is required where the library permits, but AgentBox makes no guaranteed memory-
erasure claim for Python. Unknown algorithms/schemas, authentication failure,
wrong key/AAD, malformed/duplicate envelopes, truncation, or corruption fail
closed before any Secret use and place the affected Credential in
`NEEDS_ATTENTION`.

## Key separation

The domains are independent:

```text
Provider Secret DEKs
    wrapped by Provider Secret KEK version

Configuration transaction snapshots
    contain only allowlist-validated non-secret AgentBox profile bytes
    and therefore do not use or reuse Provider Secret keys

AgentBox application secret
    unrelated control-plane key

Codex / Claude / GitHub credentials
    externally owned and never imported
```

No key is derived from the AgentBox application secret, administrator password,
Provider token, host identity, or another Runtime credential.

## Rotation expectations

- Provider credential rotation and KEK rotation are different transactions.
- Credential rotation validates a new immutable Secret version before switching
  the reference and retains the prior version only for the bounded rollback
  window.
- Root-key rotation creates a new root/key ID and derived KEK, rewraps every DEK
  with a new nonce and AAD through a crash-recoverable journal, verifies every
  new wrapper, atomically changes the current-key manifest, and retains the old
  key until all live and rollback references are proven migrated.
- Partial rotation never deletes the prior key/record or reports success.
- Revocation prevents new use immediately but does not falsely claim that the
  remote Provider revoked the credential.

## Implementation conformance gate

The Secret PR may choose only the then-current non-vulnerable exact version of
PyCA `cryptography` that implements the frozen APIs on supported Python/Linux;
that version and hashes are build inputs, not an architecture choice. CI must
include published-vector/known-answer, tamper, wrong-key, wrong-AAD, identity-
transplant, duplicate-nonce, rotation-crash, corruption, and unsupported-schema
tests. Failure to lock or qualify the dependency blocks that PR.

# 5. P11-ADR-074 — Key Custody and Recovery Contract

**Status:** Accepted in the candidate canonical registry; repository-effective
only after this governance change is reviewed and merged into `main`.

## Decision

For the initial single-server Linux implementation, the Provider Secret master
key and encrypted store are owned exclusively by the `agentbox-runtime`
identity through a dedicated local `MasterKeyProvider`. They are not owned by
the control plane or Root Helper.

## Initialization and storage

- The key is generated locally with a CSPRNG only after an explicit local
  Secret-store initialization action.
- It is not supplied through Web/API, CLI argv, environment files, release
  artifacts, installation logs, or default config.
- The fixed state root is
  `/home/agentbox-runtime/.local/share/agentbox/provider-secrets/v1`.
  `keys/<key-id>.key` stores exactly one 32-byte root key; `keyset.json` stores
  only schema, current key ID, non-secret fingerprints, and rotation state;
  `store.sqlite3` stores metadata, wrapped DEKs, ciphertext, nonces, tags, and
  AAD but no plaintext. Callers cannot provide any path, filename, UID/GID,
  mode, or backend.
- Parent directories require trusted ownership, restrictive mode, `lstat`/
  no-follow validation, and no hardlink/symlink ambiguity.
- Initial creation uses Linux `getrandom` through the standard CSPRNG, exclusive
  no-follow creation, file and directory `fsync`, and atomic manifest publish.
  Every directory is `0700`; root-key, manifest, and store files are `0600`,
  owned by `agentbox-runtime:agentbox-runtime`, regular, single-link files.
- Key ID is the first 128 bits of SHA-256 over
  `"agentbox/provider-secret/key-id/v1" || root-key`, rendered lowercase hex;
  it is an identifier/fingerprint, not a recovery value.
- Reinstall, application update, rollback, and default uninstall preserve the
  key and Runtime Secret store. Phase 11 defines no purge operation.
- Root installer may create only the empty fixed Runtime-owned parent directory;
  root Helper cannot create, read, rotate, export, or recover the key.
- If `store.sqlite3` contains any Secret record while `keyset.json` or its
  referenced key is missing, malformed, mismatched, or untrusted, startup does
  not generate a key. The Secret subsystem and affected bindings remain
  unavailable pending explicit recovery.

The same-host software key is an explicit availability/security tradeoff. It
protects against a control-plane DB/Web compromise and a copied Secret record
without the key; it does not protect against root or a compromised
`agentbox-runtime` identity.

## Recovery policy

Default AgentBox DB/config backups exclude:

- master keys;
- Provider Secret envelopes;
- Runtime credentials;
- Runtime transaction journals and non-secret profile snapshots.

Loss of the master key makes the encrypted Provider Secret records
unrecoverable. AgentBox must not derive a replacement from the application
secret, provide an escrow backdoor, or reset metadata to pretend recovery.

The recovery workflow is:

1. mark affected Credentials `NEEDS_ATTENTION`/unavailable;
2. prevent resolution and Provider activation;
3. instruct the administrator to revoke/rotate affected credentials at each
   Provider;
4. initialize a new master-key generation under explicit local authorization;
5. provision new Provider Secret versions locally through protected stdin/TTY;
6. revalidate and activate using a new approved transaction.

Restoring only SQLite never activates a Credential. Restored non-secret metadata
starts unavailable until the Runtime proves matching key/record integrity and a
fresh Provider validation succeeds.

## Secret ingress

- V1 provisioning is the fixed local entry point
  `/opt/agentbox/current/venv/bin/agentbox-runtime-provider-secret provision
  --credential <CredentialID> --expected-revision <revision>`.
- It refuses unless real/effective/saved UID and GID exactly match the installed
  `agentbox-runtime` identity, the executable/release chain is root-owned and
  immutable to that UID, and the Credential/revision already exists as
  non-secret control-plane intent.
- A controlling TTY is mandatory; stdin must be that TTY. Echo is disabled
  before reading and restored on every signal/error path. V1 rejects pipes,
  redirected files, environment values, clipboard automation, and
  non-interactive use.
- The Secret is one line of 1–16384 visible ASCII bytes. NUL, CR/LF inside the
  value, other controls, non-ASCII, truncation, and over-limit input are
  rejected before storage. It is never accepted in argv or an option value.
- The entry point creates a new immutable Secret version and returns only
  opaque record/version IDs and sanitized lifecycle state. It has no reveal,
  list-value, export, or generic decrypt action.
- An OS administrator may use the host's existing privilege mechanism to start
  that fixed entry point as `agentbox-runtime`; AgentBox itself calls no `sudo`,
  `su`, Root Helper, shell, or arbitrary executable.
- Non-interactive automation and external vault import are out of V1 and need a
  separate ADR.

## Backup and export

- Initial V1 recovery is re-entry only.
- There is no implicit Secret backup and no plaintext export/reveal operation.
- An optional encrypted export with an independently held recovery key is out of
  scope and requires a separate ADR, format, custody policy, and restore test.
- Backup metadata must state that Provider credentials are excluded; it must
  never imply that an AgentBox DB backup is sufficient for Provider recovery.

## Compromise response

- Runtime-key compromise means all records protected by it are assumed exposed;
  rotate/revoke affected Provider credentials and rebuild key custody.
- Runtime UID compromise means every Secret it can use is assumed exposed.
- Root/host compromise requires rebuilding the host trust boundary and rotating
  Runtime and Provider credentials.
- Local ciphertext deletion is not remote Provider revocation.

# 6. P11-ADR-075 — Activation and Recovery Policy

**Status:** Accepted in the candidate canonical registry; repository-effective
only after this governance change is reviewed and merged into `main`.

## Decision

Provider activation is an explicit, revision-bound, new-session-first
transaction. Control Plane owns intent, approval, durable binding state, and
recovery policy. Runtime owns local locking, snapshots/journal, apply, Secret
use, lifecycle evidence, and restoration. Neither side may declare success
without agreement and required verification.

## Activation approval

Activation requires:

- authenticated administrator authorization and recent authentication;
- a fresh validation evidence bundle;
- an immutable, unexpired Codex dry-run plan;
- exact Provider, Credential/Secret version, Profile, Binding, Runtime,
  adapter/schema, policy, config fingerprint, and evidence revisions;
- explicit confirmation of destination, model/protocol, cost/data boundary,
  config-field names, lifecycle impact, and rollback readiness;
- a verified prior state and snapshot capacity;
- one control-plane per-Runtime lease, one Runtime-local lock, and an
  AgentBox-managed work admission fence.

Recent authentication must still be valid under the existing AgentBox setting;
the activation approval itself expires after 10 minutes and is single-use. Any
Provider, endpoint, model, Secret version, Codex evidence, config fingerprint,
policy, price/data warning, or session-state change invalidates it.

Durable Job retry cannot reuse expired approval, change a Provider/Secret/model,
or broaden the approved lifecycle action.

## Initial session and Remote policy

- Existing and legacy sessions are never migrated, rebound, relabeled, resumed,
  stopped, or restarted by Provider activation.
- Initial activation is allowed only for future AgentBox-managed new work when
  the public contract proves isolation from existing work.
- An active or unobservable affected session/writer blocks activation.
- A change requiring Runtime/Remote restart, reauthentication, or re-pairing is
  unsupported in the first activation class. It requires a later explicit
  maintenance ADR and public evidence.
- Pairing and Provider authentication remain separate. Pair is never called
  automatically.
- Remote Control being Experimental means continuity is never assumed. When an
  active Remote state could be affected and no public evidence proves safety,
  activation blocks.

## Initial Provider network policy

This policy closes the network decisions previously left open by Phase 11.9:

- Official OpenAI uses only the fixed authority defined by the reviewed public
  adapter contract; callers cannot override it.
- Initial OpenAI-compatible Providers are public HTTPS destinations only.
- V1 permits DNS hostnames on TCP port 443 only and rejects all IP-literal URLs.
  Base URLs contain scheme, IDNA-normalized hostname, optional fixed path, and
  no userinfo, query, fragment, or percent-encoded authority characters.
- Userinfo, fragments, credential-bearing queries, ambiguous IP forms, and
  control characters are rejected.
- Loopback, RFC1918/private, ULA, link-local, cloud metadata, multicast,
  unspecified, broadcast, and mixed prohibited DNS results are denied.
- Every resolution must return 1–8 A/AAAA addresses and every address must be a
  globally routable unicast address. IPv4-mapped IPv6 and alternate numeric
  encodings are normalized before policy evaluation. A single forbidden,
  malformed, or excess answer rejects the destination.
- Each connection pins one address from that approved set while preserving the
  validated hostname for SNI and certificate verification, then compares the
  connected peer address with the approved set. A client unable to provide
  this DNS-rebinding defense is unsupported.
- Redirects are disabled. Credentials are never forwarded to another authority.
- Ambient proxy variables and caller-provided proxies/custom CAs are ignored or
  rejected. The platform trust store and hostname verification remain enabled.
- Local Provider activation remains disabled; it needs a separate local-network
  and process-lifecycle ADR.
- Live Provider tests are separate and explicitly authorized. V1 sends exactly
  one non-streaming Responses request with fixed input `Reply with OK.`, no
  user/project/session data, no tools/files/web search, and at most 8 output
  tokens. Request body is capped at 16 KiB, response at 256 KiB, connect at 10
  seconds, and total wall time at 30 seconds. There is no automatic retry,
  redirect, recurring/background probe, or second model/list request. The UI/
  CLI must warn that the one request may consume paid Provider usage. Refusal,
  timeout, ambiguous outcome, or stale evidence blocks activation.

Live evidence expires after 10 minutes and is bound to exact destination,
resolved-address set, model, protocol, Credential/Secret version, adapter, and
policy revisions. Activation re-resolves/rechecks the destination; a changed
answer requires a new explicitly authorized live test.

These conservative defaults may reduce compatibility. Ordinary confirmation
cannot bypass a destination or TLS security rule.

## Transaction and crash-recovery policy

The state machine from P11-ADR-031 through P11-ADR-041 remains authoritative.
The following policy is frozen:

- one mutating transaction per Runtime;
- fixed lock order: control-plane Runtime lease, binding/Credential revision
  reservation, Runtime-local lock, then admission fence;
- durable checkpoint before each non-idempotent transition;
- control plane stores non-secret orchestration; Runtime stores protected local
  journal/snapshot;
- timeouts yield `INTERRUPTED`/unknown, never assumed failure;
- startup reconciliation runs before accepting another mutation;
- no blind repeat of config publication, lifecycle operation, Secret use, paid
  request, or rollback;
- `COMMIT_PENDING` can finish commit only when exact plan/revisions, applied
  state, all required evidence, unique-binding constraint, and Runtime journal
  still agree; otherwise verified rollback or `NEEDS_ATTENTION` is required;
- an external edit prevents automatic overwrite or rollback over that edit.

The control-plane lease is 60 seconds and renews every 20 seconds. Lease loss
closes admission and marks the transaction `INTERRUPTED`; another owner cannot
take over until Runtime reconciliation proves the journal state. The Runtime
uses a kernel `flock` on the fixed regular file
`/home/agentbox-runtime/.local/state/agentbox/provider-transactions/v1/runtime.lock`;
there is no PID-file stale-lock deletion. Journal/snapshot directories are
`0700`, files `0600`, fixed and owned by `agentbox-runtime`, with the same
no-follow/trusted-parent rules as the Secret store.

The admission fence is durably set before profile publication and blocks every
new AgentBox-managed Provider-sensitive session. A complete activation has a
five-minute wall limit; config publication has a 30-second limit, the approved
live request its separate 30-second limit, and post-verification 60 seconds.
Exceeding any limit records `INTERRUPTED`; it never infers success or blindly
replays the step.

Startup reconciliation is deterministic:

| Last durable point | Recovery action |
|---|---|
| Before snapshot/preimage | Abort; verify no mutation; release fence/lock |
| Snapshot durable, before publication | Verify preimage unchanged; abort; retain audit only |
| Publication begun/applied, before verified commit | Never silently commit; restore exact preimage and run full rollback verification |
| `COMMIT_PENDING` | Commit only if exact plan/revisions, profile digest, Binding uniqueness, Secret/key reference, lifecycle evidence, and both journals agree; otherwise verified rollback |
| Rollback begun | Resume idempotent exact restoration, then verify |
| External edit, corrupt/missing journal/snapshot, contradictory state, or failed verification | `NEEDS_ATTENTION`; retain evidence and block mutation/admission |

## Rollback ownership and retention

- Runtime performs exact local restoration; Control Plane decides the approved
  recovery transition and reconciles binding truth.
- Automatic rollback targets only the exact pre-transaction state. No automatic
  Provider fallback exists.
- An incomplete, `INTERRUPTED`, rollback-pending, or `NEEDS_ATTENTION`
  transaction and all referenced material are retained without age/count
  pruning until explicit verified recovery.
- After a successful commit and two-sided acknowledgement, exactly one verified
  pre-activation recovery generation per Runtime is retained for 7 x 24 hours
  from commit. A later successful activation atomically replaces that single
  generation only after its own new recovery generation is verified; the older
  generation is then pruned if unreferenced.
- A prior Secret is usable for rollback only while not revoked/deleted and while
  its key/envelope is verified. Otherwise rollback cannot be promised and
  activation is blocked or recovery becomes `NEEDS_ATTENTION`.
- Manual rollback is a new approved transaction targeting an opaque eligible
  snapshot; users cannot provide paths or bytes.
- A previous Secret version and root key remain retained for the same 7-day
  window only when still referenced, locally valid, and not marked revoked or
  deleted. At expiry they become ineligible and are physically pruned only
  after a reference scan and verified terminal journal. A revoked/unusable
  prior Secret makes rollback unavailable; AgentBox reports that fact and never
  substitutes another Provider/Credential.
- After the 7-day window, manual rollback is unavailable and a new activation
  plan is required. Non-secret Audit events follow the existing 90-day AgentBox
  Audit retention and are not reversible state. Pruning failure retains the
  object and reports a sanitized finding; it never deletes unknown material.

## Rollback verification

`Rollback verified` requires all policy-required evidence:

- snapshot/transaction/target integrity;
- exact config content or prior nonexistence and managed semantic state;
- owner/group/mode, trusted parent, and required metadata;
- prior Binding/Profile/Credential/Secret-version reference;
- expected Runtime process/socket, health, readiness, and public-contract state;
- prior Provider behavior where safely required;
- Remote and session expectations applicable to the prior state;
- control-plane and Runtime journal agreement.

Restored bytes, an exit code, a successful restart, or a database update alone
is insufficient.

## `NEEDS_ATTENTION`

`NEEDS_ATTENTION` is mandatory when any effective state, snapshot, Secret
reference, lifecycle, binding, or rollback verification is unknown or
contradictory.

In this state:

- all new Provider mutations for the Runtime are blocked;
- no automatic retry, fallback, pair, restart, Secret substitution, or root
  escalation occurs;
- existing work is not killed or relabeled;
- evidence, journal, and snapshots are retained;
- read-only sanitized diagnosis remains available;
- recovery requires a newly authorized, typed procedure or human-guided local
  recovery; no generic repair shell/path/config endpoint is introduced.

# 7. P11-ADR-076 — Implementation Governance Contract

**Status:** Accepted in the candidate canonical registry; repository-effective
only after this governance change is reviewed and merged into `main`.

## Decision

Phase 11 implementation is incremental, feature-gated, and traceable to the
canonical P11-ADR registry. No PR may weaken an Accepted invariant or combine a
safe foundational slice with a later Secret/config/activation capability merely
to make the feature appear complete.

## Required implementation sequence

1. **Governance/evidence** — make P11-ADR-001 through P11-ADR-076 authoritative,
   add sanitized public-contract fixtures, and update threat/test plans.
2. **Non-secret Provider core** — additive domain schema/repositories with
   default `UNMANAGED`; no Secret, Runtime RPC, network request, config, or UI
   mutation.
3. **Read-only Runtime contract** — exact schemas, peer/auth/frame bounds,
   versioned capability evidence, and no mutation verbs.
4. **Secret boundary** — only after the exact cryptographic implementation
   profile and key-custody tests are approved.
5. **Offline Provider validation** — no network/Secret use; live validation is a
   later separately reviewed operation.
6. **Codex Adapter dry-run** — versioned public-contract profile, fixed target,
   managed-scope preservation, no write or Secret resolution.
7. **Transaction and activation** — disabled until public lifecycle/session/
   Remote evidence and the complete fault-injection/rollback gate pass.
8. **API/CLI/Web** — typed non-secret workflows only; no Web Secret input or
   generic Runtime/config/HTTP primitive.

## PR requirements

Every Phase 11 PR must:

- identify the canonical ADRs implemented and invariants deliberately not yet
  implemented;
- state feature flags/default-disabled behavior and exact out-of-scope items;
- be based on current `main`, use a feature branch and Draft PR, and preserve
  squash-merge workflow;
- contain one trust-boundary-sized change with an explicit migration/rollback
  impact statement;
- use only typed, exact, versioned request/data schemas;
- include a Secret/config/command/path/header field review;
- preserve root Helper, non-root identities, loopback bind, Secure Cookie/proxy,
  Runtime HOME, Projects, existing sessions, and Remote separation;
- avoid real credentials and external Provider requests in ordinary CI;
- update public-contract evidence when Codex behavior is affected;
- receive architecture/security review before enabling a mutation;
- leave no unresolved P0/P1 issue or blocking review thread.

## Security review gates

At minimum, the relevant PR must prove:

- no plaintext/ciphertext/key enters normal DB/API/Web/Job/Audit/log/report/Git;
- Runtime UDS peer credentials, exact fields, protocol version, frame/time/
  concurrency bounds, and fail-closed unknown actions;
- no shell, executable, argv, environment map, cwd, path, PID, signal, package,
  systemd unit, chmod/chown, arbitrary URL/header/query field;
- fixed server-side Provider/Runtime/config/Secret target resolution;
- symlink/hardlink/special-file/untrusted-parent/concurrent-edit protection;
- endpoint/TLS/DNS/redirect/proxy/cost policy for any live request;
- no root Helper Phase 11 authority;
- canary absence across DB/WAL/SHM, Runtime state, artifacts, diagnostics,
  frontend traces, and CI outputs;
- rollback false-positive rejection and `NEEDS_ATTENTION` behavior.

## Test requirements

Relevant milestones require:

- domain/revision/lifecycle/uniqueness and additive migration tests;
- v0.3.0-rc.1 upgrade with no automatic Provider adoption or Runtime change;
- public-doc/schema/help fixture provenance, change, malformed, unknown, and
  unsupported tests;
- exact Runtime protocol adversarial tests;
- cryptographic known-answer/tamper/wrong-key/wrong-AAD/rotation/key-loss tests;
- Secret ingress and full-surface canary tests;
- fake Provider endpoint, SSRF/DNS/TLS/redirect/timeout/stream/cost tests;
- semantic preservation, conflict, no-follow, atomicity, fsync, and external-edit
  tests;
- crash/fault injection at every transaction checkpoint;
- Provider/Runtime/Remote/continuity dimensional evidence tests;
- verified rollback, corrupt/missing snapshot, revoked prior Secret, and
  reconciliation tests;
- existing Backend, Frontend, Security, E2E, Deployment, deployment-gate, and
  release-gate regressions as applicable.

## Release governance

- Phase 11 features remain disabled by default until their own gate passes.
- No Ruleset change is bundled with a Phase 11 feature PR.
- A Phase 11 aggregate check becomes required only through a later independent
  governance task after stable evidence.
- Current Codex public contracts are revalidated before implementation, release
  candidate, and release.
- Platform/support claims describe actual fixture/CI/real-host evidence.
- No tag or Release is created without separate human authorization.

# 8. Phase 11.9 Blocker Closure Matrix

| Prior blocker | Result | Closure evidence |
|---|---|---|
| 1. ADR acceptance durable through repository governance | **BLOCKED** | Canonical registry and source documents are present on this branch, but not yet reviewed/merged into protected `main` |
| 2. Codex public Provider/config/lifecycle contract qualified | **CLOSED** | CE-001 through CE-012 and P11-ADR-071; unsupported lifecycle facts fail closed |
| 3. Secret cryptography frozen | **CLOSED** | P11-ADR-073 fixes AES-256-GCM, HKDF-SHA-256, sizes, nonce/AAD/envelope behavior and PyCA library family |
| 4. Key custody frozen | **CLOSED** | P11-ADR-074 fixes Runtime ownership, paths, modes, initialization, key loss, rotation, and no auto-replacement |
| 5. Secret ingress/provisioning contract frozen | **CLOSED** | P11-ADR-074 fixes the local Runtime-identity TTY-only command and input limits |
| 6. Backup/recovery/retention frozen | **CLOSED** | No automatic Secret backup/export; re-entry recovery; exact 7-day reversible-state policy in P11-ADR-074/075 |
| 7. Codex managed configuration scope frozen | **CLOSED** | P11-ADR-072 fixes generated profile/Provider namespace and complete field allowlist |
| 8. Lossless user config preservation frozen | **CLOSED** | Base config is fingerprint-only and never copied/modified; only wholly AgentBox-owned non-secret profile bytes are reversible |
| 9. Provider endpoint/private-network policy frozen | **CLOSED** | Public HTTPS port 443 only, all-address validation/pinning, no redirects/proxies/custom CA/private/local destinations |
| 10. Paid/live test policy frozen | **CLOSED** | Single explicit fixed 8-token request, fixed byte/time bounds, no retry/background probe |
| 11. Activation/active-session policy frozen | **CLOSED** | New AgentBox-managed work only; affected active/unobservable work blocks; no Remote/session migration/restart/pair |
| 12. Transaction lock/admission policy frozen | **CLOSED** | 60-second lease/20-second renewal, kernel lock, fixed order, durable admission fence |
| 13. Crash recovery behavior frozen | **CLOSED** | Exact checkpoint reconciliation table; uncertainty/external edit becomes `NEEDS_ATTENTION` |
| 14. Rollback retention frozen | **CLOSED** | One generation per Runtime for 7 days; unresolved state exempt; audit remains 90 days |
| 15. Implementation governance frozen | **CLOSED** | P11-ADR-076 fixes ADR, PR, security, test, release, and supersession gates |

Technical contract closure is complete. Item 1 is a repository-state blocker,
not an unresolved security design choice.

# 9. Contradiction and Scope Review

No Accepted P11-ADR-001 through P11-ADR-070 decision is reversed. The following
clarifications resolve earlier open alternatives:

- P11-ADR-030 required transient action-specific Secret delivery; the fixed
  command-backed broker satisfies it and excludes the earlier `env_key`
  alternative.
- P11-ADR-034 prohibited Secret-bearing snapshots; the selected profile-only
  transaction avoids copying user config and permits exact non-secret rollback.
- P11-ADR-053/063 prohibited implicit session migration; profile activation is
  limited to future managed work and cannot affect Remote or historical work.
- P11-ADR-065 required explicit recovery for unknown state; the crash table
  preserves that behavior and never promotes uncertainty to success.
- Phase 11.8 and 11.9 remain historical `BLOCKED` reviews. This document closes
  their technical blockers; it does not rewrite their outcomes.
- The provisional P11-ADR-071 through 076 titles in Phase 11.9 are superseded
  only as allocations by the final titles required for Phase 11.10. No accepted
  decision ID is renumbered or reused.

V1 scope remains Linux single-node/single-administrator, Codex, Official OpenAI
and typed OpenAI-compatible public HTTPS Providers, explicit activation,
new-session-only behavior, explicit adoption, and verified rollback. Claude
Provider management, Local Provider activation, private-network Providers,
automatic fallback/failover, live session migration, Web Secret ingress,
multi-server/SaaS, generic vault, and infrastructure automation remain out.

# 10. Remaining Unknowns and Residual Risks

## Must resolve before coding

The sole remaining pre-coding blocker is repository governance persistence:
this documentation PR must receive human architecture/security review, pass all
required protected checks, and merge into `main`. Separate human authorization
is then required before creating any implementation feature branch.

## Bounded engineering choices

The following choices do not define new security policy and may be made inside
the relevant ADR-conforming PR with tests and review:

- physical control-plane table/index/module names for the already defined
  non-secret model;
- numeric Runtime protocol message IDs and evidence cache TTLs, provided stale
  evidence never authorizes mutation;
- exact non-vulnerable/hash-locked PyCA `cryptography` release compatible with
  the frozen primitives;
- TOML parser library capable of the frozen preservation contract;
- sanitized error-code names and UI layout;
- release version/name for completed Phase 11 capabilities.

These are not permission to weaken the fixed schemas, paths, budgets, locks,
retention, cryptography, session rules, network policy, or trust boundaries.

Residual risks remain explicit:

- root or `agentbox-runtime` compromise exposes Provider Secrets usable by that
  Runtime;
- Remote Control and app-server are Experimental upstream surfaces;
- an unknown Codex/schema/help digest disables the affected adapter profile;
- V1 has no built-in Secret recovery export and key loss requires credential
  revocation/re-entry;
- Provider/API success does not prove Remote, tools, streaming, history, or
  broad compatibility; those dimensions remain `UNKNOWN`/`EXPERIMENTAL` unless
  separately evidenced.

# 11. Repository Governance Status

`docs/adr/README.md` is the existing repository ADR registry and is extended by
this change rather than replaced. It maps every P11-ADR ID, title, status,
source, aliases, and the Phase 11.10 provisional-title supersession. Source ADR
documents carry an acceptance-authority note pointing to that canonical
registry. Phase 11.8/11.9 history remains unchanged.

Current persistence state:

```text
Technical contract closure: COMPLETE
Repository governance persistence: PENDING MERGE
Phase 11 implementation: NOT STARTED
```

# 12. Implementation Gate Re-evaluation

## Decision

```text
BLOCKED
```

Sole remaining blocker: the Phase 11.10 governance PR must be reviewed, pass
all required CI, and merge into protected `main`. The existence of these files
on a local/remote branch is not durable acceptance.

After that merge and a read-back verification of the registry, a separate gate
review may report `READY FOR IMPLEMENTATION`. It still must not start work
without explicit authorization.

The first separately authorized engineering slice remains strictly limited to:

```text
non-secret Provider core model
    + additive metadata schema
    + explicit UNMANAGED state
    + revisions/relationships/repositories
    + audit-safe metadata
    + migration and forbidden-field tests
```

It contains no Secret storage/cryptography, Provider request, Runtime mutation,
Codex config access, activation/rollback executor, Provider-switch API/UI,
Claude Provider behavior, automatic adoption, or Root Helper change.

## Next action

Review this documentation/governance PR and merge it only after all protected
checks pass. Do not begin the next action automatically.
