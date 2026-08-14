# AgentBox Phase 11.3 — Secret Boundary Architecture Decision Record

Status: **Proposed — design only, awaiting human approval**
Scope: AI Provider credentials on the Phase 11 Linux single-node architecture
Governance acceptance: The decision content is canonically registered as
P11-ADR-021 through P11-ADR-030 and **Accepted** in `docs/adr/README.md`.
The document-local `ADR-021` through `ADR-030` labels and the status above are
historical drafting metadata. Acceptance becomes repository-effective only
after the Phase 11.10 governance change is reviewed and merged into `main`.
Contextual alternatives and open questions remain historical; supplemental
P11-ADR-071 through P11-ADR-076 provide their governing resolution.
Architecture sources: `PHASE11_PROVIDER_MANAGER_PROPOSAL.md`,
`PHASE11_IMPLEMENTATION_PLAN.md`,
`PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md`, and
`PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md`
Repository baseline: `ForceMind/agentbox` at
`1c2005de59b1c5063b260591206a8411c7e5b1a5`

This document defines the Secret trust boundary and lifecycle. It does not
authorize code, storage creation, encryption-key generation, credential input,
database migrations, Runtime changes, Codex/Claude changes, config writes,
Provider activation, or real Secret tests. No Secret value was used to prepare
this design.

## 1. Problem Statement

### 1.1 Why Provider Manager requires Secret handling

Official OpenAI and most OpenAI-compatible Providers require authentication.
AgentBox therefore needs a way to associate a Provider with authentication
material and let an approved Runtime use that material without turning the
control plane into a credential reader.

Provider workflows eventually need to answer:

- Is a required credential configured?
- Which credential version is intended for this Runtime Profile?
- Is the credential active, staged for rotation, revoked, missing, or unknown?
- May a specific typed Runtime operation use it?
- Did activation or rollback restore the correct version?

None of those questions requires the Web/API, Worker, SQLite database, Audit,
or root Helper to see the plaintext value.

### 1.2 Why Secret management is separate from Provider identity

A Provider describes a backend endpoint, protocol, model, and capabilities. A
Credential describes the lifecycle metadata for authenticating to that
Provider. Secret Material is the sensitive value itself. They change for
different reasons:

- a credential can rotate without changing Provider identity;
- a Provider can be disabled without immediately deleting historical Secret
  versions needed for verified rollback;
- a Provider may require no credential;
- the same Provider metadata may remain valid after a compromised key is
  revoked and replaced;
- a Secret value must never become an identity input, label, diagnostic, or
  audit field.

Merging these concepts would make rotation appear to be Provider replacement,
encourage key-derived identifiers or hints, and spread Secret-bearing fields
through ordinary control-plane models.

### 1.3 Existing AgentBox boundaries remain authoritative

The accepted identity model determines Secret custody:

```text
agentbox
    owns: API, Web, Worker, SQLite, authorization, workflow, audit
    cannot: read Runtime HOME or Provider Secret Material

agentbox-runtime
    owns: Runtime HOME, Runtime execution, Provider Secret consumption
    cannot: read AgentBox DB/application secret or become root

root Helper
    owns: existing fixed AgentBox lifecycle actions only
    cannot: create, read, decrypt, export, rotate, or delete Provider Secrets
```

The Runtime Secret boundary must reinforce this separation. It must not create
a generic vault accessible to the Web, a generic Secret RPC, an arbitrary file
store, or a root decryption service.

### 1.4 Scope

Phase 11 v1 Secret scope is limited to AI Provider credentials such as:

- OpenAI API keys;
- OpenAI-compatible Provider tokens;
- future explicitly approved AI Provider credentials.

It excludes AgentBox administrator passwords and sessions, SSH keys, Git/GitHub
credentials, Codex/Claude login files, cloud credentials, database passwords,
TLS private keys, arbitrary server credentials, and general-purpose Secret
management.

## 2. Secret Domain Model

### 2.1 Credential

A `Credential` is non-secret control-plane metadata representing an
authentication relationship between one Provider and one opaque Secret record.

Credential owns:

- opaque CredentialID;
- Provider relationship;
- typed credential kind;
- opaque Runtime-owned Secret reference;
- active Secret version reference;
- lifecycle state and revision;
- safe validation state and freshness;
- creation, rotation, revocation, and retirement timestamps.

Credential does not own:

- plaintext Secret Material;
- ciphertext, nonce, authentication tag, wrapped data key, or master key;
- token prefix/suffix or reversible hint;
- Authorization header or Runtime environment variable value;
- Provider endpoint/model identity;
- user login, Runtime login, or OS identity.

Credential identity normally remains stable while its Secret version rotates.

### 2.2 Secret Material

`SecretMaterial` is the sensitive byte sequence supplied by a Provider or user
and required to authenticate a bounded AI Provider operation.

Secret Material owns no product identity or business metadata. It is treated as
opaque bytes with a typed maximum size and encoding policy. AgentBox does not
parse it for display, store a prefix/suffix, derive a public fingerprint from a
low-entropy token, or return it after provisioning.

Plaintext Secret Material may exist only transiently in these approved zones:

1. the local operator's protected input buffer during provisioning;
2. the `agentbox-runtime` Secret operation's private process memory;
3. a minimal child Runtime environment or another approved transient delivery
   mechanism;
4. the authenticated outbound request created for the selected Provider.

It must never exist in the Web browser, ordinary HTTP API, SQLite/WAL/SHM,
Job/Event payload, Audit, logs, reports, diagnostics, Git, URLs, argv, ordinary
Runtime config, shell history, clipboard automation, or default backup.

### 2.3 Provider Reference

A `ProviderCredentialReference` is the non-secret relationship from a Provider
to a CredentialID. The Provider never references Secret Material directly.

The relationship proves only intended association. It does not prove the Secret
exists, decrypts, authenticates, is active, or is compatible with a Runtime.
Those are separate lifecycle and validation observations.

### 2.4 Secret Record and opaque Secret reference

A `SecretRecord` is a Runtime-owned encrypted-at-rest envelope for one Secret
version. It is not a control-plane database entity.

Conceptually it contains:

- opaque, random Secret record ID;
- envelope/schema and algorithm version;
- Secret version;
- ciphertext and authentication tag;
- nonce as required by the approved algorithm;
- encrypted/wrapped data-encryption key when envelope encryption is used;
- minimum non-secret integrity metadata;
- associated-data binding to CredentialID, Secret record ID, version, credential
  kind, Runtime identity, and schema version.

The opaque Secret reference identifies one record inside the fixed
Runtime-owned Secret backend. It is not a filesystem path, URL, filename from
the user, or bearer token.

### 2.5 Secret Version

A `SecretVersion` is an immutable generation of Secret Material for one
Credential. Rotation creates a new version; it never overwrites the active
record in place.

Version identity is server-generated and monotonic or otherwise collision-
resistant within the Credential. It is safe metadata, but it grants no access.
Only one version may be active in Phase 11 v1; another may be staged during a
rotation transaction, and a bounded prior version may be retained for rollback.

### 2.6 Secret Lifecycle

`SecretLifecycle` is the state machine governing provisioning, storage,
activation, rotation, revocation, retirement, and deletion. It is distinct from
Provider lifecycle and Runtime Binding state.

Lifecycle metadata can be held by the control plane, while the Runtime backend
is authoritative for record existence, integrity, and decryptability. A state
mismatch becomes `NEEDS_ATTENTION`; neither side silently repairs or invents a
record.

### 2.7 Audit Record

A Secret-domain `AuditRecord` reuses AgentBox's existing audit model. It records
an actor, action, Credential/Provider opaque IDs, Secret version number, request/
Job/transaction correlation, time, result, and sanitized error code.

Audit does not own the value, ciphertext, nonce, authentication tag, key
material, provider response, raw config, prompt, completion, or arbitrary
metadata.

## 3. Identity Separation

### 3.1 Identity matrix

| Identity | Represents | May authorize | Must not be merged with |
|---|---|---|---|
| ProviderID | One AI execution backend definition | Nothing by itself | Credential, user, Runtime, Secret value |
| CredentialID | Authentication lifecycle metadata for one Provider | Nothing by itself | ProviderID, admin identity, Secret Material |
| SecretRecordID/Version | One Runtime-owned encrypted Secret generation | Resolution only through an approved Runtime operation | Path, bearer token, CredentialID |
| RuntimeInstallationID | One Runtime installation | Target selection after policy approval | Provider or Credential identity |
| RuntimeBindingID | Control-plane intent selecting a Runtime Profile | Future activation only through a separate confirmed transaction | Credential, session, Codex Provider ID |
| User/Admin ID | Actor requesting a workflow | Control-plane authorization according to policy | Provider account identity, API key, Linux Runtime UID |
| Linux `agentbox-runtime` identity | Local execution and Secret-custody trust boundary | Read/decrypt only through approved local policy | User identity, Provider identity, root |

### 3.2 Provider identity versus Credential identity

Provider identity remains stable across credential rotation. A credential
cannot silently move to a different Provider because a display name or endpoint
looks similar. The relationship is explicit and revision-bound.

### 3.3 Credential identity versus User identity

The single AgentBox administrator authorizes workflows but is not the Provider
credential. A Web Session, password, CSRF token, or local OS identity cannot be
used as an AI Provider key. Deleting or rotating a Provider credential does not
change the administrator account.

### 3.4 Runtime identity versus Credential identity

`agentbox-runtime` is the Linux custody boundary that may use approved Secret
versions; it is not the credential itself. The same Runtime identity can use
different Credentials only through typed Provider/Runtime Binding policy. A
compromised Runtime UID is treated as a compromise of every Secret it can
decrypt, not as a legitimate new Credential identity.

### 3.5 Root identity

Root is a host-administration trust assumption, not a Provider/Credential actor.
On a conventional Linux host, root can ultimately inspect Runtime memory and
files; encryption with a same-host key cannot claim otherwise. AgentBox still
prevents normal Web/Worker/Helper workflows from using root to extract Secrets.

## 4. Storage Boundary Design

### 4.1 Evaluation criteria

An acceptable Phase 11 store must:

- keep plaintext and ciphertext outside ordinary control-plane database fields;
- be owned by `agentbox-runtime` and inaccessible to `agentbox`;
- use a fixed server-selected path and restrictive permissions;
- support atomic versioned writes, integrity validation, rotation, and exact
  deletion;
- survive AgentBox service restart and ordinary application update;
- remain excluded from default AgentBox DB backups and logs;
- avoid a mandatory cloud/vendor dependency;
- work on the qualified Linux single-server deployment.

### 4.2 Option A — Encrypted storage in the AgentBox database

**Description**

Store ciphertext in SQLite while keeping a separate encryption key outside the
database.

**Advantages**

- transactional relationship with Provider/Credential metadata;
- existing SQLite backup, migration, and revision mechanisms;
- fewer filesystem records and simpler inventory.

**Disadvantages**

- places Secret ciphertext inside the `agentbox` control-plane ownership and
  its backups;
- either requires `agentbox` to access decryption keys or requires ciphertext
  transport to Runtime, weakening the current process boundary;
- increases exposure from database copies, diagnostics, migrations, and ORM/
  serialization mistakes;
- couples Runtime Secret availability to control-plane database access even
  though Runtime must not open SQLite.

**Operational complexity**

Medium. Encryption and key separation appear simple, but safe Runtime-only
decryption requires an additional ciphertext/metadata protocol and cross-
authority transaction design.

**Security implications**

Encryption limits plaintext exposure after a database-only leak if the key is
separate, but the ciphertext enters many control-plane operational paths. The
design conflicts with the stronger goal that Provider Secret records remain
outside the normal database entirely.

**Phase 11 recommendation**

Rejected for initial implementation.

### 4.3 Option B — Dedicated local Runtime-owned Secret store

**Description**

Store versioned encrypted Secret records beneath one fixed Runtime-owned Linux
directory, with the master-key material stored separately under the same
Runtime identity or an approved OS key provider.

**Advantages**

- aligns with the existing `agentbox-runtime` credential boundary;
- keeps Secret records out of SQLite, Web/API, Worker, and ordinary backups;
- allows restrictive directory/file ownership and no-follow atomic operations;
- supports versioned rotation and exact rollback references;
- no network/vendor dependency;
- can be packaged and validated for the current single-node Linux product.

**Disadvantages**

- requires a separate consistency protocol between control-plane metadata and
  Runtime record state;
- requires careful filesystem, crash, symlink, permission, and key-loss design;
- a compromised Runtime UID or root can access both use path and local store;
- backup/recovery is separate from SQLite.

**Operational complexity**

Medium, but contained to one explicit Runtime trust boundary and compatible
with AgentBox's current deployment model.

**Security implications**

This offers the clearest separation from a compromised Web/API or database. It
does not protect against full Runtime/root compromise and must state that
residual risk honestly.

**Phase 11 recommendation**

Recommended baseline, combined with authenticated encryption and separate key
custody. The exact fixed path is a deployment decision; it must reside under a
Runtime-owned state root, not `/etc/agentbox`, `/var/lib/agentbox`, the Project
root, `/root`, or a caller-supplied location.

### 4.4 Option C — Operating-system protected storage

**Description**

Use a Linux OS facility such as a desktop Secret Service, kernel keyring,
TPM-backed key, or systemd credential mechanism.

**Advantages**

- may improve key isolation or reduce plaintext-at-rest exposure;
- TPM/OS policies may bind use to a host, boot state, or service identity;
- some mechanisms can provide strong lifecycle and audit integration.

**Disadvantages**

- headless server support, boot-time unlock, session availability, recovery,
  and distro behavior vary;
- kernel keyrings are not durable by themselves;
- hardware-backed keys complicate migration/disaster recovery;
- systemd credentials primarily solve delivery and do not automatically provide
  a full versioned Secret CRUD store;
- root remains a powerful host trust actor.

**Operational complexity**

High for the currently qualified OpenCloudOS/Ubuntu/Rocky/Debian spectrum.

**Security implications**

Potentially stronger master-key custody, but only after platform-specific
validation. Treating an unqualified OS mechanism as portable would create
availability and recovery failures.

**Phase 11 recommendation**

Retain as a future `MasterKeyProvider` or storage backend extension. Do not make
it mandatory for v1 without a separate platform ADR and real-host evidence.

### 4.5 Option D — External Secret manager

**Description**

Use a product such as a cloud vault or externally managed key/Secret service.

**Advantages**

- centralized rotation, policy, audit, and hardware-backed key options;
- avoids long-lived Provider Secret ciphertext on the AgentBox host;
- may fit future enterprise/multi-host deployments.

**Disadvantages**

- introduces network availability, bootstrap credential, vendor, tenant,
  billing, and access-policy dependencies;
- the bootstrap credential itself needs secure local custody;
- expands AgentBox beyond its single-node, single-administrator scope;
- complicates offline recovery and Provider availability.

**Operational complexity**

High and provider-specific.

**Security implications**

Can improve centralized custody but creates another remote trust boundary and a
new high-value credential. Incorrect policy can expose all Providers.

**Phase 11 recommendation**

Deferred. A future typed backend interface may allow it without changing the
Credential domain, but AgentBox v1 must not become a universal cloud vault
client.

### 4.6 Recommended Phase 11 direction

Use Option B:

```text
Control-plane Credential metadata
        |
        | opaque SecretRecordID + version only
        v
Runtime-owned dedicated local Secret store
        |
        | AEAD-protected versioned record
        v
separately held Runtime master-key provider
```

The baseline must preserve a future key-provider/backend abstraction, but no
external or OS-specific backend is implemented merely for abstraction's sake.

## 5. Encryption Design

### 5.1 Security goals

Encryption at rest should:

- prevent plaintext disclosure from a copied Secret record when the master key
  is not also compromised;
- detect ciphertext, identity, version, or metadata substitution;
- allow key rotation without reusing nonces or overwriting active records;
- separate Secret records from master-key custody;
- make corruption explicit and fail closed.

It does not protect against root, a compromised `agentbox-runtime`, live process
memory inspection by an equally privileged actor, or a malicious destination
that legitimately receives its credential.

### 5.2 Envelope encryption model

The recommended conceptual design uses envelope encryption:

1. Generate a random data-encryption key (DEK) for each Secret version.
2. Encrypt Secret Material with a reviewed AEAD algorithm and a unique nonce.
3. Bind CredentialID, SecretRecordID, Secret version, credential kind, Runtime
   identity, and envelope schema as associated data.
4. Encrypt/wrap the DEK with a master key (KEK) from the approved
   `MasterKeyProvider`.
5. Store ciphertext, tag, nonce, wrapped DEK, and versioned non-secret envelope
   metadata in the Runtime Secret record.
6. Zero/shorten plaintext and key-buffer lifetime on a best-effort basis after
   use; do not claim guaranteed erasure in a managed-language Runtime.

The implementation must use a mature reviewed cryptography library. No custom
cipher, KDF, nonce construction, padding, or authentication protocol is allowed.
AES-256-GCM and XChaCha20-Poly1305 are candidate AEADs; exact algorithm/library
selection remains an approval item.

### 5.3 Master-key custody

The master key must:

- be generated locally with a CSPRNG as `agentbox-runtime`, not supplied by Web
  or embedded in a release;
- be stored separately from Secret records;
- be readable only by the approved Runtime identity or future key-provider
  mechanism;
- never enter SQLite, ordinary config, environment files, logs, Audit, reports,
  Git, artifacts, or default backups;
- have its own identity/version and restrictive atomic lifecycle;
- never be returned through API, CLI output, Runtime UDS response, or Helper.

A software master-key file under the same Runtime identity is an initial
availability/security tradeoff, not protection from Runtime/root compromise.
This limitation must remain visible in security documentation.

### 5.4 Master-key rotation

Master-key rotation should rewrap DEKs under a new KEK without changing Provider
Credential values where supported by the approved library/design:

```text
create new KEK version
    -> verify custody/permissions
    -> rewrap each referenced DEK into new record generation
    -> verify every envelope
    -> atomically publish new KEK version/reference
    -> retain old KEK for bounded rollback
    -> retire only after complete verification
```

Rotation is serialized and crash-recoverable. Partial rotation cannot delete the
old key or report success. Missing/corrupt records become `NEEDS_ATTENTION`.

### 5.5 Provider credential rotation versus master-key rotation

- **Provider credential rotation** replaces Secret Material and creates a new
  Secret version. It normally requires Provider authentication validation and
  Runtime Binding coordination.
- **Master-key rotation** changes local at-rest protection while preserving the
  Provider credential value and Credential identity.

The two operations have separate Audit events, revisions, rollback windows, and
failure handling.

### 5.6 Compromise response

| Suspected compromise | Required response |
|---|---|
| Database only | No Secret ciphertext is present; rotate application auth as appropriate and verify Credential references. |
| Secret-record copy only | Treat AEAD/master key separation as protection, inspect access, and rotate affected Provider credentials if confidence is insufficient. |
| Master key exposed | Assume every record encrypted by it is exposed; revoke/rotate all affected Provider credentials and replace the KEK. |
| `agentbox-runtime` compromised | Assume all usable Provider credentials, Runtime auth, and Project data in that UID boundary are exposed; stop use, investigate, revoke externally, rebuild trust. |
| root/host compromised | Assume full host compromise; AgentBox encryption is not a containment guarantee. Rebuild host and rotate all credentials. |
| One Provider credential exposed | Revoke at Provider when supported, stage a new Secret version, validate, activate, and retire the old version. |

AgentBox must never claim that deleting local ciphertext revokes a token at the
Provider. Provider-side revocation is a separate external fact.

## 6. Secret Access Flow

### 6.1 Provisioning flow is separate from ordinary Web/API

The Secret-bearing provisioning flow is local and Runtime-scoped:

```text
Local administrator with approved OS authority
        |
        | protected TTY/stdin, never argv or shell history
        v
local Secret provisioning entry point running as agentbox-runtime
        |
        | validate size/type; encrypt immediately
        v
Runtime-owned Secret store
        |
        | returns opaque SecretRecordID/version/configured state only
        v
Control-plane Credential metadata registration
```

The exact local authorization mechanism remains an open decision, but the
plaintext does not traverse the browser, HTTP API, Worker, SQLite, Audit, or
normal Runtime capability UDS contract.

### 6.2 Runtime-use flow

The later, non-secret user workflow is:

```text
Authenticated administrator
        |
        | Provider/Runtime intent, no Secret
        v
Control Plane authorization, policy, plan, recent auth, confirmation
        |
        | typed operation + CredentialID/Secret version + revisions
        v
peer-authenticated Runtime boundary
        |
        | resolve opaque record; verify policy/envelope; decrypt just in time
        v
minimal Runtime consumption mechanism
        |
        | authenticated request
        v
selected AI Provider
```

The control plane authorizes use of an identity/revision; it does not receive
the value. The Runtime resolves the fixed record server-side and returns only a
sanitized success/failure observation.

### 6.3 Plaintext existence windows

Plaintext may exist only:

- in the operator's protected input buffer during local provisioning;
- in short-lived Runtime process memory during encryption/decryption;
- in the selected child Runtime's minimal environment or another approved
  delivery buffer;
- in the TLS-protected Provider request process memory.

Plaintext must never exist:

- in browser DOM/storage, URL, clipboard automation, screenshot, or trace;
- in HTTP/API request/response or OpenAPI examples;
- in SQLite/WAL/SHM, Job/Event, Audit, reports, diagnostics, or metrics;
- in argv, process title, shell history, or long-lived service environment;
- in ordinary TOML, `/etc/agentbox/environment`, Project files, Git, release
  artifacts, source maps, or backups;
- in root Helper request/response or logs.

### 6.4 Authorization and replay boundary

Secret use is allowed only as part of a typed Provider validation or activation
operation bound to Provider, Credential, Secret version, Runtime Profile,
Runtime Binding, target revision, and plan digest. A generic “get Secret” or
“use Secret with this URL/command” operation does not exist.

Uncertain/crashed mutations are not blindly replayed. A new operation
revalidates Credential state, record integrity, Provider destination, and user
authorization.

## 7. Runtime Interaction

### 7.1 Minimal delivery principle

Runtime receives only the one Credential version required for one approved
Provider/Runtime operation. It does not preload all Secrets, copy them into
Runtime HOME credential directories, or expose a generic enumeration/retrieval
interface.

The Runtime parent service should not keep Provider Secrets in its long-lived
environment. Resolution and decryption happen immediately before use, with
bounded lifetime and no caller-provided variable names or destinations.

### 7.2 Option 1 — Child-only environment injection

**Description**

Runtime config contains a non-secret environment-variable reference when the
current public Runtime contract supports one. `agentbox-runtime` decrypts the
selected Secret and provides the value only in the exact child process
environment.

**Advantages**

- matches the preferred public-reference approach already planned for Codex;
- avoids plaintext in ordinary config and argv;
- no persistent temporary file;
- simple child lifecycle and cleanup.

**Disadvantages/security implications**

- same-UID processes may inspect child environments under Linux policy;
- child processes may propagate the environment to descendants;
- crash dumps/debug tooling can expose memory;
- must not leak into logs or environment diagnostics.

**Recommendation**

Preferred for Codex v1 only if the then-current official public config contract
supports a Secret environment reference. The variable name is fixed/generated
by the adapter, not caller-controlled.

### 7.3 Option 2 — Restrictive ephemeral file

**Description**

Write plaintext or a one-time generated credential document to a Runtime-owned
`0600` temporary file and provide a fixed reference to the child.

**Advantages**

- supports tools that accept credential-file references;
- can avoid child environment propagation.

**Disadvantages/security implications**

- creates crash-residue, path, symlink, deletion, and backup/inspection risk;
- a same-UID process can read it while present;
- secure unlink timing is tool/platform dependent;
- requires explicit public Runtime support.

**Recommendation**

Not the default. Permit only if a supported Runtime requires it and a separate
typed design proves fixed path policy, no-follow creation, short lifetime,
cleanup/recovery, and no log/backup inclusion.

### 7.4 Option 3 — File descriptor, memfd, stdin, or dedicated IPC delivery

**Description**

Deliver Secret bytes over a non-persistent descriptor or supported authenticated
local channel.

**Advantages**

- can minimize filesystem/environment exposure;
- supports explicit lifetime and close semantics.

**Disadvantages/security implications**

- only usable when the third-party Runtime publicly supports the mechanism;
- descriptor inheritance and process lifecycle are complex;
- inventing a wrapper/proxy protocol can become a new credential service;
- stdin may conflict with interactive Runtime operation.

**Recommendation**

Future option only when the public Runtime contract supports it. AgentBox must
not invent an undocumented Codex credential channel.

### 7.5 Rejected delivery methods

- raw Secret in Codex/Claude config;
- API/CLI argv;
- caller-provided environment map;
- long-lived systemd environment or `/etc/agentbox/environment`;
- Project `.env` or source files;
- shell expansion or `source`;
- WebSocket/browser relay;
- root Helper decryption;
- copying root, Codex, Claude, GitHub, or user credential directories.

## 8. Root Helper Boundary

### 8.1 Permitted Helper behavior

The existing root Helper may continue only its already accepted fixed AgentBox
lifecycle actions. Phase 11.3 adds no Helper action.

During a future root installer operation—not Helper RPC—the installer may create
an empty fixed parent directory with approved owner/group/mode when required by
the accepted deployment design. It must not receive, generate, decrypt, import,
export, rotate, inspect, back up, or delete Provider Secret Material.

### 8.2 Permanently forbidden Helper behavior

The Helper must never accept or provide:

- `secret.read`, `secret.decrypt_all`, `secret.export`, or generic vault access;
- Secret Material, ciphertext, master key, nonce, wrapped key, or credential
  file content;
- Secret/credential filesystem path;
- Provider endpoint, header, request body, or key;
- arbitrary user/UID/GID, mode, owner, path, command, executable, argv, env,
  PID, signal, package, or unit name;
- Codex/Claude/GitHub auth inspection or copying;
- Provider tests or Runtime execution as root.

### 8.3 Why root does not improve the design

Using root as the routine decryptor would make Web/API compromise a path to all
Provider credentials, broaden Helper far beyond fixed lifecycle actions, and
destroy Runtime credential isolation. Root's theoretical ability to inspect the
host is a residual trust assumption, not a reason to expose a product API for
it.

## 9. Secret Lifecycle

### 9.1 Lifecycle states

| State | Meaning |
|---|---|
| `CREATED` | Opaque identity/version allocated; record is not yet durable or usable. |
| `STORED` | Envelope was atomically written and integrity/ownership verified; not selected for use. |
| `STAGED` | Stored version is the candidate for a specific rotation/activation plan. |
| `ACTIVE` | Credential metadata selects this version for approved new Runtime use. |
| `ROTATING` | Credential-level transaction retains the old active version while validating a staged new version. |
| `RETIRING` | Version is no longer active but retained for the approved rollback window. |
| `REVOKED` | Version is prohibited from new local resolution; remote Provider revocation may still be unknown. |
| `DELETED` | Exact local record was removed and only non-secret tombstone/audit metadata remains. |
| `NEEDS_ATTENTION` | Metadata/record/key/integrity state is inconsistent or recovery is uncertain. |

`ROTATING` is principally a Credential transaction state; individual Secret
versions remain staged, active, or retiring. State is explicit rather than
inferred from file presence.

### 9.2 Creation and storage

```text
ABSENT
  -> CREATED
  -> encrypt and authenticate
  -> restrictive atomic write
  -> read-back/envelope/owner/mode verification
  -> STORED
```

Failure before verified storage removes only the transaction's exact temporary
object when identity is proven. It does not create Credential metadata that
claims configured success.

### 9.3 Activation

`STORED` becomes `STAGED` for an exact Provider/Credential/Profile plan.
Authentication/protocol validation occurs through a separate approved
operation. Only a confirmed Runtime Binding/rotation transaction may select it
as `ACTIVE`.

Secret activation does not automatically activate a Provider or migrate a
session. The relevant transaction must commit all required metadata or roll
back the reference.

### 9.4 Rotation

```text
old ACTIVE + new STORED
        -> ROTATING / new STAGED
        -> validate new version
        -> atomically change active reference
        -> new ACTIVE / old RETIRING
        -> verify Runtime/Provider state
        -> retain old for rollback window
        -> revoke/retire according to policy
```

Any failure restores the old reference and verifies it. The old record is not
deleted until the transaction and rollback window complete.

### 9.5 Revocation

Local revocation blocks new Secret resolution immediately after revision/state
validation. It does not claim Provider-side revocation. If the Provider exposes
a separately approved public revoke operation, its result is independent and
audited; otherwise documentation directs the operator to revoke externally.

An active version cannot be revoked without a replacement/disable plan that
protects current Runtime state.

### 9.6 Deletion

Deletion is a separate destructive local operation and requires:

- version is not active, staged, retiring within rollback retention, or
  referenced by an unresolved transaction;
- explicit recent authorization/confirmation under the future approved flow;
- exact opaque record identity and revision;
- server-resolved fixed path;
- owner/type/mode/link-count/no-follow verification;
- deletion of only that exact AgentBox-owned record;
- post-delete verification and non-secret tombstone/audit record.

Deletion of ciphertext is not Provider-side token revocation. There is no bulk
delete, arbitrary path, default uninstall purge, or automatic cleanup of
unknown files.

## 10. Backup and Recovery

### 10.1 Default backup policy

The recommended Phase 11 v1 policy is:

- AgentBox SQLite backup contains Credential metadata and opaque references but
  no Secret ciphertext or master key;
- ordinary AgentBox config/release backups exclude the Secret store and master
  key;
- Runtime HOME/project backup policy does not silently include Provider Secrets;
- loss of the store or master key requires Provider credential re-entry and
  external rotation/revocation as appropriate.

This prioritizes a small, understandable Secret boundary over convenient but
unsafe implicit backup.

### 10.2 Optional encrypted Secret backup analysis

A future export could include encrypted Secret records protected by an
operator-held recovery key that is not stored on the AgentBox host. Such a
design would require:

- a separate explicit command and confirmation;
- versioned manifest and integrity protection;
- independent recovery-key custody;
- no stdout/log exposure;
- destination no-follow/new-file policy;
- tested restore on the qualified platforms;
- clear distinction from ordinary DB backup.

It is deferred from the initial direction because recovery-key management would
otherwise recreate the same unsolved Secret problem.

### 10.3 Restore process

A future restore must reconcile three authorities:

1. control-plane Credential metadata;
2. Runtime Secret record store;
3. master-key provider/version.

Restore flow:

```text
restore non-secret metadata
    -> mark credentials unavailable/unverified
    -> restore approved Secret records and key custody separately, if available
    -> validate manifest, owner/mode, envelope, associated data, and references
    -> revalidate Provider authentication
    -> require explicit activation plan
```

Restoring metadata never auto-activates a credential. A missing record, missing
key, wrong version, failed authentication tag, or reference mismatch becomes
`NEEDS_ATTENTION`.

### 10.4 Key loss

If the master key is lost, locally encrypted records are intentionally
unrecoverable. AgentBox must not provide a backdoor, derive a replacement from
the application secret, or silently reset records. The operator must revoke or
rotate credentials at each Provider and provision new Secret versions.

### 10.5 Disaster recovery

For host loss or root compromise:

- build a new trusted host using the reviewed AgentBox release;
- restore only approved non-secret AgentBox data;
- reauthenticate Codex/Claude/GitHub independently as `agentbox-runtime`;
- revoke/rotate Provider credentials externally;
- provision new Provider Secrets locally;
- validate and activate through fresh plans;
- do not copy root credentials or an untrusted Secret/master-key store.

## 11. Audit Requirements

### 11.1 Required events

Audit should record at least:

- `credential_metadata_created`;
- `secret_provisioning_started/succeeded/failed`;
- `secret_stored`;
- `secret_validation_requested/succeeded/failed`;
- `secret_rotation_requested/succeeded/failed`;
- `secret_version_activated`;
- `secret_version_retiring`;
- `secret_revoked_local`;
- `secret_provider_revocation_observed` when independently supported;
- `secret_deletion_requested/succeeded/failed`;
- `master_key_rotation_requested/succeeded/failed`;
- `provider_binding_changed`;
- `secret_rollback_attempted/verified/failed`;
- `secret_recovery_needs_attention`.

### 11.2 Allowed audit fields

- actor type/ID;
- ProviderID, CredentialID, opaque Secret version number, RuntimeBindingID;
- request ID, Job ID, transaction ID;
- action, timestamp, outcome, sanitized error code;
- confirmation required/completed;
- old/new version numbers;
- rollback attempted/verified booleans;
- backend type/version and safe evidence class where required.

### 11.3 Prohibited audit/log fields

- Secret value or any substring/hint;
- ciphertext, nonce, tag, DEK, wrapped DEK, KEK/master key;
- Authorization header, HTTP body, raw Provider response;
- local Secret path or credential filename;
- raw Runtime config/environment/argv;
- prompt, completion, tool output, Pair Code, auth file content;
- arbitrary exception object or unbounded third-party message.

Helper logs contain no Secret event because Helper has no Secret operation.

### 11.4 Audit is not Secret custody

Audit proves that AgentBox observed a workflow event; it does not prove remote
Provider revocation, absence of root access, or secure deletion from SSD/media.
Those claims must remain separate and evidence-based.

## 12. Security Threat Model

### 12.1 Threat matrix

| Threat | Consequence | Required mitigation | Residual risk |
|---|---|---|---|
| AgentBox database leak | Provider/Credential metadata exposed | No plaintext/ciphertext/master key in DB; opaque references only; bounded endpoint data | Metadata and Provider relationships remain visible |
| Compromised Web/API process | Attempts to read/export or misuse credentials | Separate UID/store; no Secret API; typed reference-only operations; recent auth/confirmation/rate/cost controls; audit | Compromised authenticated control plane may request permitted model use until contained |
| Compromised Worker | Attempts generic Runtime/Secret operations | Exact action contracts; no generic Secret read/write; Runtime resolves fixed records; peer auth/revisions | Permitted operations may be abused within their bounded purpose |
| Compromised `agentbox-runtime` | Reads records/key/memory and uses Providers | Dedicated UID limits root/application-secret access; incident response assumes all Runtime-usable Secrets exposed | All Provider Secrets in that Runtime boundary can be compromised |
| Root/host compromise | Reads all files/memory or changes binaries | No product API for extraction; hardening and integrity checks; rebuild/rotate response | Root remains ultimate host authority |
| Malicious Provider endpoint | Steals supplied credential/data or redirects auth | Typed endpoint policy, TLS, redirect/destination controls, no arbitrary headers, binding to Provider identity, bounded response | Configured Provider receives its own credential and submitted data by design |
| Credential confused across Providers | Secret sent to wrong authority | Provider/Credential identity separation; associated data; plan/revision/destination binding; redirect auth stripping/rejection | Administrator can intentionally choose a malicious Provider |
| Secret record substitution/tamper | Wrong key used or decryption oracle | AEAD, associated data, opaque identity, owner/mode/no-follow, fail closed | Same-UID/root can replace code and state under broader compromise |
| Logs/diagnostics leak | Long-lived credential disclosure | Field allowlists, no raw output, canary scans, no environment dumps, bounded errors | Pattern redaction cannot detect every possible Secret; prevention is primary |
| Process argv/environment leak | Same-host user observes key | Never argv; child-only minimal environment if used; separate UID; short lifetime | Same Runtime UID and root may inspect environment/memory |
| Backup exposure | Offline credential theft | Default backup excludes store/key; future export separately encrypted | Re-entry is operationally costly after loss |
| Insider/operator misuse | Authorized host admin extracts or sends Secrets | Least privilege, no reveal function, audit, provider-side rotation, organizational controls | Root/OS administrator cannot be technically excluded on a single host |
| Master-key loss | All local records unavailable | Honest re-entry policy; optional future recovery-key design | No backdoor recovery |
| Partial rotation/crash | Old/new reference mismatch or outage | Immutable versions, serialized transaction, durable phase, rollback retention/verification | Manual recovery may be required |
| Local delete without remote revoke | Token remains valid at Provider | Distinguish local revoke/delete from Provider-side revocation; explicit status | Provider may offer no supported revoke API |

### 12.2 Security invariants

The later implementation must prove:

- `agentbox` cannot traverse/read Secret storage;
- `agentbox-runtime` cannot read AgentBox DB/application secret;
- root Helper cannot express a Secret operation;
- SQLite/WAL/SHM, Job/Event, Audit, logs, reports, diagnostics, browser
  artifacts, Git, argv, and ordinary config contain no canary Secret;
- every record write is restrictive, no-follow, atomic, and revision-bound;
- unknown/corrupt/missing/key-loss states fail closed;
- Provider redirects cannot forward credentials to another authority;
- rollback cannot report verified without restoring the exact Secret reference
  and all related binding state.

## 13. ADR Decisions

The decisions below are **Proposed** until human approval. Their numbering is
scoped to the Phase 11 architecture sequence requested for this document and
does not alter the repository's existing accepted ADR numbering.

### ADR-021 — Secrets are separate from Provider identity

**Status:** Proposed

**Decision**

ProviderID, CredentialID, SecretRecordID/version, Runtime identity, and user
identity remain independent. Provider references Credential metadata; Credential
references an opaque Runtime Secret record.

**Rationale**

Independent identities support rotation and rollback without key-derived
Provider identities or Secret leakage into ordinary metadata.

**Consequences**

- Secret rotation does not replace Provider identity.
- A Secret cannot be reassigned by label/path matching.
- Every use binds exact Provider/Credential/Secret revisions.

### ADR-022 — Plaintext Secrets are never stored in normal database fields

**Status:** Proposed

**Decision**

SQLite and ordinary control-plane persistence contain only non-secret Credential
metadata and opaque references. They contain neither plaintext nor encrypted
Secret records/master keys.

**Rationale**

Keeping ciphertext out of the control plane narrows database/backup exposure
and preserves the existing Runtime credential boundary.

**Consequences**

- Secret availability is reconciled separately from DB metadata.
- Ordinary DB backups do not restore Provider credentials.
- Encrypted-in-database storage is rejected for Phase 11 v1.

### ADR-023 — Runtime access is controlled and minimal

**Status:** Proposed

**Decision**

Only `agentbox-runtime` may resolve/decrypt a specific Secret version for one
approved typed Provider operation. There is no generic enumerate/read/export/
decrypt API and no permanent copying into Runtime credential/config files.

**Rationale**

The Runtime needs use access, not unrestricted vault semantics. Exact scoping
reduces exposure from a compromised control-plane process.

**Consequences**

- Runtime resolves opaque references server-side.
- Child-only environment injection is preferred only when publicly supported.
- Same-UID/root exposure remains an explicit residual risk.

### ADR-024 — Secret operations require Audit records

**Status:** Proposed

**Decision**

Provisioning state, validation, activation, rotation, revocation, deletion,
master-key rotation, rollback, and recovery outcomes require allowlisted
non-secret Audit records.

**Rationale**

Secret lifecycle changes are security-significant and must be attributable
without recording the Secret.

**Consequences**

- Audit stores opaque IDs/versions/results only.
- Raw values, cryptographic material, paths, and Provider bodies are prohibited.
- Audit does not substitute for Provider-side revocation evidence.

### ADR-025 — Phase 11 v1 uses a dedicated Runtime-owned local Secret store

**Status:** Proposed

**Decision**

The initial Linux direction is a fixed, dedicated `agentbox-runtime`-owned local
store outside SQLite, Projects, ordinary config, and default backup. The exact
path is selected by deployment policy, never by a caller.

**Rationale**

This best matches the accepted process boundary and avoids mandatory cloud or
unqualified OS-keyring dependencies.

**Consequences**

- Storage consistency and recovery are separate from SQLite.
- OS/external backends remain future typed extensions.
- Runtime/root compromise is not solved by this local store.

### ADR-026 — Stored Secret versions use authenticated envelope encryption

**Status:** Proposed

**Decision**

Each Secret version is encrypted with a unique DEK under a reviewed AEAD and the
DEK is wrapped by a separately held versioned master key. Identity/version
metadata is authenticated as associated data.

**Rationale**

AEAD protects a copied record from plaintext disclosure when key custody remains
separate and detects record/identity substitution. Envelope encryption supports
master-key rotation without changing Provider credentials.

**Consequences**

- Exact algorithm/library and key provider require approval.
- No custom cryptography is permitted.
- This does not claim protection from root or Runtime compromise.

### ADR-027 — Secret provisioning is local and outside ordinary Web/API

**Status:** Proposed

**Decision**

V1 Secret Material enters through an approved local interactive operation in
the `agentbox-runtime` identity using protected TTY/stdin. Browser and ordinary
HTTP API receive only configured state and opaque references.

**Rationale**

Excluding the browser/API prevents plaintext from crossing the largest remote
attack surface and existing control-plane logs/persistence.

**Consequences**

- V1 Web UI has no key paste/reveal field.
- Exact local OS authorization/automation behavior remains to be designed.
- Provisioning returns no Secret value.

### ADR-028 — Root Helper has no Secret authority

**Status:** Proposed

**Decision**

Root Helper neither stores nor accesses Provider credentials and gains no Secret
action. Future installer work may create an empty approved directory only; it
does not handle Secret Material or keys.

**Rationale**

A root decryption broker would convert Web/API compromise into host-wide Secret
extraction and violate the fixed-action Helper boundary.

**Consequences**

- No decrypt-all/export/path interface exists.
- Runtime Secret work remains non-root.
- Root compromise remains a host-level residual risk, not a product feature.

### ADR-029 — Ordinary backup excludes Secret records and master keys

**Status:** Proposed

**Decision**

Phase 11 v1 DB/config backups do not contain Secret records or master keys. Loss
requires external Provider revocation/rotation and local re-provisioning. A
future encrypted export needs a separate ADR.

**Rationale**

Implicit backup would multiply credential copies and require another recovery
key before that custody problem is solved.

**Consequences**

- Disaster recovery is less convenient but explicit.
- Restored metadata starts unavailable/unverified.
- Key loss has no AgentBox backdoor.

### ADR-030 — Plaintext delivery is transient and action-specific

**Status:** Proposed

**Decision**

Plaintext is decrypted just in time for one exact typed Runtime operation and is
delivered through the narrowest current public mechanism. It never enters argv,
ordinary config, long-lived service environment, Project files, or generic IPC.

**Rationale**

Runtime needs temporary use of one credential, not permanent possession of all
credentials in multiple formats.

**Consequences**

- Child-only environment is the preferred Codex candidate if publicly
  supported.
- File/descriptor mechanisms need separate proof and are not assumed.
- Same-UID process visibility remains a documented risk.

## 14. Open Questions

The following decisions require product/security/platform approval before
Secret implementation:

1. **AEAD library and algorithm:** AES-256-GCM, XChaCha20-Poly1305, or another
   reviewed option; nonce and serialization rules.
2. **MasterKeyProvider:** Runtime-owned software key file for v1, OS-protected
   mechanism, or a qualified combination/fallback policy.
3. **Exact storage paths:** Runtime HOME versus a dedicated FHS state root,
   owner/group/modes, systemd sandbox access, and installer creation policy.
4. **Local provisioning authorization:** exact executable/entry point, allowed
   OS principals, TTY/stdin requirements, peer checks, and whether controlled
   automation is ever supported.
5. **Memory handling:** selected language/library guarantees, buffer lifetime,
   fork/child behavior, dump policy, and honest zeroization claims.
6. **Codex delivery:** whether the then-current public config supports an
   environment-variable Secret reference and whether a Runtime restart is
   required.
7. **Compatible Provider delivery:** whether all v1 Providers use the same
   approved credential reference or need typed per-adapter methods.
8. **Master-key rotation:** rollback window, batch size, crash journal, old-key
   retention, and rewrap verification.
9. **Provider credential rotation:** required authentication/protocol/Runtime/
   Remote tests and old-version retention.
10. **Provider-side revocation:** whether AgentBox ever calls an official revoke
    API or only records operator-confirmed external revocation.
11. **Secret deletion:** retention/tombstone policy and whether local
    cryptographic erasure claims are supportable on target filesystems.
12. **Backup:** keep re-entry-only policy for v1 or design an operator-held
    encrypted export/recovery key.
13. **Store reconciliation:** which authority repairs metadata/record mismatch,
    and must repair always require explicit confirmation?
14. **Credential sharing:** continue prohibiting one Credential across multiple
    Providers in v1.
15. **Rate/cost controls:** limits on authenticated Provider tests using an
    active Secret.
16. **Incident response:** exact supported workflow and audit retention after
    Runtime, master-key, or host compromise.
17. **OS/external backends:** criteria that would justify TPM, systemd
    credentials, Secret Service, or external vault support in a later release.

## Decision Outcome if Approved

Approval authorizes only the Secret-domain boundaries and Proposed ADR
decisions above. It does not authorize a Secret Store or key generation. The
recommended next phase is **Phase 11.4 — Config Transaction Framework Design**,
defining parser-preserving, revision-bound, atomic Runtime configuration plans,
protected snapshots, crash recovery, and verified rollback before any live
Codex configuration mutation.
