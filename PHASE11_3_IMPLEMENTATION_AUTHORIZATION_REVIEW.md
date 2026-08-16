# AgentBox Phase 11 Slice 3 — Secret Storage Boundary Implementation Authorization Review

Status: Architecture authorization review complete; implementation not started

Repository baseline: `c73306f8442a0b1451b5223642b1a057280d355a`

Review scope: Phase 11 Slice 3.1 Secret Store Foundation only

Decision date: 2026-08-16

This document converts the Accepted Phase 11 Secret decisions into a
repository-specific implementation contract. It does not implement a Secret
Store, add cryptographic dependencies, create keys, create a database migration,
or expose a provisioning, resolution, Provider, API, CLI, UI, or Runtime RPC
operation.

## 1. Current Repository State

The reviewed `main` baseline contains the completed non-secret Provider core and
read-only Runtime capability boundary:

- PR #35 is merged at the reviewed baseline;
- `0004_phase11_provider_core` remains the Alembic head and no `0005` exists;
- `provider_credentials` stores only `CredentialID`, Provider relationship,
  credential kind, lifecycle/revision data, and nullable opaque
  `runtime_secret_ref`/`secret_version` metadata;
- Slice 1 creation always produces `MISSING` with both Secret reference fields
  null;
- the Runtime capability implementation is observation-only;
- no Runtime Secret Store, Secret ciphertext persistence, master key,
  credential broker, Secret provisioning command, or Provider activation exists.

The existing `provider_credentials` columns are sufficient for a later typed,
Runtime-attested reconciliation. Slice 3.1 requires **no Control Plane schema
migration** and may not populate them.

The current deployment boundary already supplies the necessary ownership root:

- Runtime user and group: `agentbox-runtime:agentbox-runtime`;
- Runtime HOME: `/home/agentbox-runtime`, mode `0700`;
- `XDG_DATA_HOME`: `/home/agentbox-runtime/.local/share`;
- the Runtime systemd unit grants write access to `/home/agentbox-runtime` and
  uses `UMask=0077`;
- API/Worker cannot read Runtime HOME;
- the Root Helper has no Runtime Secret authority.

## 2. ADR Mapping and Acceptance

This review implements no new ADR and changes no Accepted decision.

| Decision    | Frozen consequence for Slice 3                                                                          |
| ----------- | ------------------------------------------------------------------------------------------------------- |
| P11-ADR-021 | `Credential` metadata and Runtime-owned Secret Material remain different identities and storage domains |
| P11-ADR-022 | plaintext or ciphertext Secret Material never enters normal Control Plane database fields               |
| P11-ADR-023 | Runtime Secret access is minimal, typed, operation-scoped, and never a generic read capability          |
| P11-ADR-024 | every lifecycle/use attempt produces non-secret audit evidence only                                     |
| P11-ADR-025 | Phase 11 v1 uses a local Runtime-owned Secret Store                                                     |
| P11-ADR-026 | authenticated envelope encryption protects every immutable Secret version                               |
| P11-ADR-027 | Secret ingress is local TTY-only; no Web/API Secret body exists                                         |
| P11-ADR-028 | Root Helper cannot reveal, decrypt, copy, export, or manage Secret Material                             |
| P11-ADR-029 | ordinary AgentBox backup excludes the store, keys, ciphertext, and plaintext                            |
| P11-ADR-030 | later Runtime consumption is transient and action-specific                                              |
| P11-ADR-073 | exact cryptographic primitives, canonical AAD, nonce, and key-use rules are mandatory                   |
| P11-ADR-074 | exact Runtime key custody, filesystem root, provisioning boundary, and recovery behavior are mandatory  |
| P11-ADR-076 | implementation must be split into narrow reviewed PRs with fail-closed security tests                   |

P11-ADR-031 onward remain binding where future Secret use meets validation,
transaction, activation, continuity, rollback, or recovery. Slice 3.1 does not
exercise those authorities.

## 3. Secret Authority Boundary

The permanent authority model is:

```text
Control Plane
    |  CredentialID + opaque Secret reference/version only
    v
agentbox-runtime
    |  fixed internal Secret Store operations only
    v
Runtime-owned encrypted Secret record
```

`agentbox-runtime` is the sole Secret authority in Phase 11 v1. Plaintext may
exist only:

1. in the local TTY input buffer owned by the explicitly invoked Runtime-user
   provisioning process;
2. in bounded Runtime process memory while encrypting, validating, or delivering
   the exact Secret to one later authorized operation;
3. in the third-party process memory that must use that credential.

Plaintext must never exist in Web/API/Worker memory, Control Plane SQLite,
Runtime UDS responses, argv, environment controlled by a caller, logs, Audit,
diagnostics, exceptions, traces, temporary files, crash reports, or backups.

A fully compromised `agentbox-runtime` UID is assumed capable of compromising
Runtime-usable Provider Secrets. File separation and fixed operation contracts
are defense in depth and workflow-integrity controls; they do not claim
isolation from a compromised Runtime identity.

## 4. Credential and Secret Separation

The canonical identities remain distinct:

- `CredentialID`: `crd_<32 lowercase hex>`, Control Plane metadata;
- `SecretRecordID` and opaque Runtime reference: `sec_<32 lowercase hex>`,
  generated by Runtime;
- Secret version: positive monotonic integer scoped to one Credential;
- RuntimeInstallationID: `rti_<32 lowercase hex>`;
- Runtime root/KEK key identifiers: non-secret cryptographic identifiers, never
  Credential or Secret identities.

The Runtime store record binds one exact RuntimeInstallationID, CredentialID,
credential kind, SecretRecordID, and Secret version. It does not copy Provider
definitions, endpoints, headers, model configuration, Runtime Profiles, or
Runtime Bindings.

The Control Plane may later transition a `Credential` from `MISSING` only after
an exact Runtime attestation proves that a newly generated `sec_*` reference and
version exist for the approved Credential revision. It receives neither the
record envelope nor any cryptographic field. Slice 3.1 implements no such
transition.

## 5. Cryptographic Contract

The encrypted record schema is `agentbox.provider-secret-envelope.v1`. The
algorithm identifier is `A256GCM-HKDF-SHA256-v1`.

### Primitives

- root key: 32 CSPRNG bytes;
- KEK: 32 bytes derived with HKDF-SHA-256;
- DEK: fresh 32 CSPRNG bytes for every immutable Secret version;
- payload encryption: AES-256-GCM;
- DEK wrapping: AES-256-GCM;
- payload nonce: fresh independent 12 CSPRNG bytes;
- wrap nonce: fresh independent 12 CSPRNG bytes;
- authentication tag: 16 bytes, as returned with the AESGCM ciphertext;
- canonical AAD and envelope metadata: RFC 8785 JCS UTF-8 bytes;
- binary envelope fields: unpadded base64url in the stored envelope and every
  serialized representation.

The implementation must use PyCA `cryptography` high-level `AESGCM` and `HKDF`
APIs. It may not implement AES, GCM, HKDF, tags, or random generation itself and
may not use unauthenticated encryption. `InvalidTag`, malformed data, unsupported
algorithm, or canonicalization failure is a closed failure.

### Dependency authorization baseline

The implementation PR must add and lock, with reviewed hashes:

- `cryptography==49.0.0` as the reviewed baseline cryptographic library;
- `rfc8785==0.1.4` as the reviewed RFC 8785 canonicalizer.

If either version is no longer current and non-vulnerable when implementation
starts, the implementation PR must select one exact reviewed replacement rather
than use a range or `latest`. That dependency-only update does not authorize an
algorithm change.

Both packages must enter the production lock, offline Linux x86_64 wheelhouse,
SBOM, `THIRD_PARTY_NOTICES.md`, nested-wheel Secret scan, license inventory, and
release manifest. `cryptography` is Apache-2.0 OR BSD-3-Clause and `rfc8785` is
Apache-2.0; final inventory must be generated from the exact installed wheels.
The wheelhouse must be verified on CPython 3.11, 3.12, and 3.13. Target hosts may
not compile cryptography, install Rust, or download it from PyPI. OpenCloudOS 9
requires an artifact-contained compatible manylinux x86_64 wheel and a real-host
load/encrypt/decrypt self-test before Slice 3.1 can be accepted.

Evidence reviewed on 2026-08-16:

- [PyCA installation and supported-platform documentation](https://cryptography.io/en/latest/installation/)
  lists Python 3.9+ testing, Ubuntu 24.04, Debian 12, and CentOS Stream 9 and
  documents manylinux wheels;
- [PyCA AESGCM documentation](https://cryptography.io/en/stable/hazmat/primitives/aead/)
  specifies accepted 256-bit keys, authenticated associated data, 96-bit nonce
  guidance, and nonce-reuse prohibition;
- [cryptography 49.0.0 package metadata](https://pypi.org/project/cryptography/)
  records Python 3.11/3.12/3.13 support and the Apache-2.0 OR BSD-3-Clause
  license expression;
- [rfc8785 0.1.4 package metadata](https://pypi.org/project/rfc8785/)
  records Python 3.8+ support, no runtime dependencies, and Apache-2.0 licensing;
- [GHSA-537c-gmf6-5ccf](https://github.com/pyca/cryptography/security/advisories/GHSA-537c-gmf6-5ccf)
  affects OpenSSL embedded in cryptography wheels before 48.0.1, which is why
  the implementation gate must audit the exact selected wheel rather than trust
  only an API-compatible version range.

### Randomness and zeroization

Random values come from the operating system CSPRNG through the reviewed library
or `secrets`/`os.getrandom`-backed APIs. Tests inject a fake random source only
through a private test seam. Production randomness is never deterministic.

Python cannot promise complete memory zeroization. Implementations must minimize
copies and lifetimes, use mutable buffers where practical, overwrite them in
`finally`, avoid interpolation/representation, and release references promptly.
This is best-effort defense in depth, not a formal zeroization guarantee.

## 6. Root Key and KEK Custody

### Fixed paths and permissions

The exact Runtime-owned root is:

`/home/agentbox-runtime/.local/share/agentbox/provider-secrets/v1`

Its fixed children are:

- `keys/<key-id>.key`: exactly 32 raw bytes;
- `keyset.json`: bounded non-secret key metadata;
- `store.sqlite3`: encrypted record metadata and envelopes.

Every ancestor from `/home/agentbox-runtime` through `v1` must be a real
directory, owned by `agentbox-runtime:agentbox-runtime`, mode `0700`, and not a
symlink. Root key, keyset, and store files must be regular, owner/group exact,
mode `0600`, and `st_nlink == 1`. Caller-provided paths, owners, groups, modes,
key IDs, or backends are forbidden.

The root-key file is raw binary; hex, base64, PEM, JSON, environment-variable,
or systemd-credential textual storage is prohibited for v1. The key identifier
is the first 128 bits of:

`SHA-256("agentbox/provider-secret/key-id/v1" || root-key)`

encoded as 32 lowercase hexadecimal characters. It is an identifier, not a
Secret verifier and not a bearer capability.

### Initialization

Startup health checks never create or replace a key. Initialization is a
separate fixed local Runtime-user action and is permitted only when the entire
fixed store is absent and no encrypted record evidence exists. It must:

1. verify effective, real, and saved UID/GID are `agentbox-runtime`;
2. set `umask 077`;
3. resolve every existing ancestor with no-follow checks;
4. build a same-parent private staging directory;
5. create the root key exclusively with no-follow semantics;
6. create and validate the keyset and empty store;
7. fsync every file and required directory;
8. atomically rename the complete staging tree to `v1`;
9. fsync the parent after the rename;
10. reopen and validate the committed store before reporting success.

If `v1`, a key, a keyset, a store, or an initialization remnant already exists,
initialization does not generate replacement material. A fully valid existing
store returns an idempotent `ALREADY_INITIALIZED` result; partial, inconsistent,
or corrupt state returns `SECRET_STORE_NEEDS_ATTENTION`.

Encrypted records plus a missing/corrupt root key or keyset always produce:

- Secret subsystem unavailable;
- affected Credentials unavailable in later reconciliation;
- all affected Provider operations blocked;
- explicit recovery or re-provisioning required.

There is no automatic replacement key, Provider fallback, deletion, or
best-effort decrypt.

## 7. Runtime-local Store Format

Phase 11 v1 uses the Accepted narrow Runtime-local SQLite file
`store.sqlite3`. This is not the Control Plane database and is not a generic
vault. SQLite is selected over one-file-per-Secret because a single local
transaction can enforce unique nonces, monotonic versions, key references, and
crash-consistent record replacement while isolating the store from all existing
AgentBox tables.

The implementation schema may contain only fixed tables for:

- one format/schema record;
- immutable Secret records;
- immutable DEK envelopes;
- non-secret key lifecycle metadata;
- bounded provisioning/recovery journal metadata when that later slice is
  authorized.

Slice 3.1 must not add provisioning journal rows or a generic key/value table.
No arbitrary JSON, metadata, headers, environment, command, path, Provider
response, prompt, completion, or Runtime config field is permitted.

Required SQLite policy:

- `journal_mode=DELETE`, `synchronous=FULL`, `foreign_keys=ON`,
  `trusted_schema=OFF`, and a fixed short busy timeout;
- no WAL mode or long-lived sidecar;
- every write in one immediate transaction;
- schema and row count bounds checked before use;
- store file maximum 128 MiB and at most 4096 Secret records;
- temporary data kept in memory and never in caller-selected directories;
- database and parent directory fsync after durable creation/replacement;
- a crash journal is accepted only as a regular, singly linked,
  Runtime-owned `0600` file in the exact store directory and is recovered by
  SQLite before integrity verification.

`PRAGMA quick_check`, schema version, invariant queries, key presence, envelope
shape, and nonce uniqueness are startup health inputs. A failed check makes the
store unavailable; startup does not delete, rebuild, or salvage rows.

## 8. Secret Envelope and Associated Data

### Bounded record

The v1 Provider credential plaintext is one line of 1–16384 visible ASCII bytes.
NUL, CR, LF, controls, non-ASCII, empty, truncated, and over-limit values are
rejected before encryption. This 16 KiB ceiling accommodates API credentials
without turning the Store into arbitrary blob storage.

The payload AESGCM result is exactly plaintext length plus a 16-byte tag. The
wrapped DEK AESGCM result is exactly 48 bytes. Both nonces are exactly 12 bytes.
The canonical serialized envelope is capped at 32 KiB; keyset metadata is capped
at 16 KiB. All identity and algorithm fields use exact enums/grammars.

The fixed record fields are:

- envelope schema version;
- algorithm identifier;
- RuntimeInstallationID;
- CredentialID;
- credential kind;
- SecretRecordID (`sec_*`);
- positive Secret version;
- DEK envelope ID (`dek_<32 lowercase hex>`), Runtime-generated;
- KEK key ID and positive KEK version;
- payload nonce and ciphertext-with-tag;
- wrap nonce and wrapped-DEK-with-tag;
- creation timestamp in UTC;
- associated-data schema version.

No Provider request, endpoint, header, model, profile, Binding, prompt, output,
arbitrary metadata, caller path, or Secret hint is stored.

### Exact associated data

Payload AAD is RFC 8785 canonical bytes of exactly:

1. envelope schema;
2. algorithm ID;
3. RuntimeInstallationID;
4. CredentialID;
5. SecretRecordID;
6. credential kind;
7. Secret version;
8. DEK envelope ID.

Wrap AAD is RFC 8785 canonical bytes of exactly:

1. envelope schema;
2. algorithm ID;
3. RuntimeInstallationID;
4. SecretRecordID;
5. Secret version;
6. DEK envelope ID;
7. KEK key ID;
8. KEK version.

The store retains the two bounded canonical JCS AAD byte strings as unpadded
base64url fields and also retains their typed source columns. Before any use,
Runtime reconstructs both AAD values from those columns and requires byte-for-
byte equality with the stored canonical values. They are never caller-supplied
or arbitrary blobs. Substitution of any bound identity, revision, version,
algorithm, or key reference must fail authentication.

## 9. HKDF, Nonce, and Key-use Rules

For v1 the 32-byte Provider Secret KEK is derived from the exact root key using:

- HKDF hash: SHA-256;
- length: 32 bytes;
- salt:
  `SHA-256("agentbox/provider-secret/hkdf-salt/v1" || canonical RuntimeInstallationID)`;
- info: `"agentbox/provider-secret/kek/v1"`.

The root key never encrypts payloads or DEKs directly. Every immutable Secret
version receives a new DEK. Every payload and wrap operation receives a new,
independent nonce. The store enforces uniqueness of `(kek_key_id, wrap_nonce)`;
one DEK envelope maps to exactly one payload. Collision, uncertain write result,
or counter/inventory contradiction fails closed and enters
`SECRET_STORE_NEEDS_ATTENTION`.

A KEK is retired before `2^32` successful wraps. Key rotation must be scheduled
earlier by policy; reaching the limit without a verified successor blocks new
writes. Nonce uniqueness is never inferred solely from probability after a
crash with uncertain commit state.

## 10. Provisioning and Control Plane Handshake

Secret provisioning is **not** part of Slice 3.1. The future separately reviewed
provisioning slice must preserve this exact authority flow:

1. Control Plane authorizes one Credential revision and RuntimeInstallation
   revision for purpose `PROVIDER_SECRET_PROVISION`.
2. It sends a fixed typed, non-secret provisioning intent over the existing
   peer-authenticated Runtime UDS. No second transport is created.
3. Runtime durably stages one bounded, expiring, single-use authorization bound
   to RuntimeInstallationID/revision, ProviderID/revision, CredentialID/revision,
   credential kind, expected `MISSING` state, intent ID, lease epoch, approval
   digest, issued time, and expiry.
4. A local operator invokes the fixed root-owned executable as
   `agentbox-runtime`:

   `/opt/agentbox/current/venv/bin/agentbox-runtime-provider-secret provision --credential <CredentialID> --expected-revision <revision>`

5. Runtime resolves the staged authorization server-side. The CLI accepts no
   path, Provider endpoint, destination, command, environment, Secret reference,
   bearer capability, or Secret-bearing argv.
6. It requires a real TTY on stdin, disables echo, restores terminal state on
   every exit, reads exactly one bounded line, and never accepts a pipe, file,
   environment variable, clipboard channel, or non-interactive input.
7. Before reading plaintext, Runtime atomically changes the intent to
   `CONSUMING`; replay or uncertain crash state can never return it to usable.
8. Runtime generates the SecretRecordID/version, encrypts and commits one record,
   reopens and authenticates it, then returns only the opaque reference, version,
   Credential/revision echo, and bounded result code.
9. Control Plane rechecks its revision and updates only the existing non-secret
   Credential metadata through a future typed Runtime-attested operation.

The intent expires at the earliest of five minutes, lease loss, Credential or
Runtime revision change, approval cancellation, first consumption attempt,
Runtime restart during `CONSUMING`, or recovery/`NEEDS_ATTENTION`. A crash after
plaintext input but before a certain commit requires a new intent and new
operator entry; there is no blind replay. The Control Plane never receives the
Secret, envelope, key, nonce, tag, or ciphertext.

No Control Plane migration is required for Slice 3.1. If durable Control Plane
provisioning intent state is later required, that schema belongs to the
separately reviewed provisioning slice.

## 11. Secret Store Operation Surface

Slice 3.1 may expose only Runtime-internal foundation operations:

- initialize the fixed empty store explicitly;
- inspect bounded health/state;
- seal/open an envelope through a private module boundary for self-test and
  tests;
- verify store/key/envelope integrity without releasing plaintext externally.

It must not expose `get`, `list`, `reveal`, `export`, `dump`, arbitrary `put`,
caller-selected decrypt, or a UDS Secret operation. There is no Web/API/CLI
provision command in Slice 3.1; the executable described above belongs to the
later provisioning slice.

The one permitted local foundation entry point is fixed as:

`/opt/agentbox/current/venv/bin/agentbox-runtime-provider-secret initialize`

It accepts no options, paths, values, stdin, or environment-derived settings;
requires real/effective/saved Runtime UID/GID; creates only the fixed empty
store; and returns a bounded non-secret state code. It is an operator
maintenance action, not a public Provider CLI or a generic Secret interface.

Future operations must be separately typed:

- provisioning;
- direct Provider live validation;
- candidate Codex activation verification;
- committed active use;
- rotation;
- revocation and verified deletion;
- recovery health/reconciliation.

An authorization for one operation cannot be reused by another. Secret
references and intent IDs are identifiers, not bearer capabilities. The fixed
Codex credential-broker contract remains governed separately by
`COMMITTED_ACTIVE_USE` and `CANDIDATE_ACTIVATION_VERIFICATION`; Slice 3.1 does
not implement either.

## 12. Backup, Restore, Upgrade, Rollback, and Uninstall

Ordinary AgentBox backup continues to exclude:

- `/home/agentbox-runtime/.local/share/agentbox/provider-secrets/v1`;
- all root keys, keyset data, encrypted records, ciphertext, nonces, tags, and
  recovery journals;
- plaintext and Secret-bearing process state.

The normal backup manifest records only that Provider Secrets are excluded. It
does not enumerate Secret references, key IDs, or record counts.

Update, rollback, reinstall, and default uninstall preserve the Runtime HOME and
therefore preserve the fixed store byte-for-byte. They may validate its health
but may not rotate, rewrite, import, export, or delete it. A software rollback
that cannot read the store format must block Provider operations and request a
forward recovery; it must not downgrade or rewrite the store.

Cross-host Secret backup/export is not authorized for Slice 3.1. Disaster
recovery therefore requires re-provisioning Provider credentials on the
destination Runtime. A future encrypted export design would require a separate
ADR/security review and must never place key and ciphertext under the same
ordinary backup authority.

Recovery cases are explicit:

| Condition                          | Required behavior                                                                                |
| ---------------------------------- | ------------------------------------------------------------------------------------------------ |
| valid store and key                | health available; no Secret released by health check                                             |
| store absent and no prior evidence | `UNINITIALIZED`; explicit initialization may be offered locally                                  |
| records exist, key/keyset missing  | `UNAVAILABLE`; no key generation; operator re-provisions or restores an approved key out of band |
| key exists, store missing/corrupt  | `NEEDS_ATTENTION`; preserve evidence; no deletion/rebuild                                        |
| tag/AAD/decrypt failure            | mark affected record unusable; block dependent operation; no alternate Secret                    |
| software too old/new for format    | fail closed; preserve bytes; use compatible forward recovery                                     |
| host lost                          | restore non-secret AgentBox state, initialize a new Runtime store, and re-provision credentials  |

## 13. Rotation, Revocation, and Deletion Boundaries

Provider Secret rotation and master-key rotation are different transactions.
Neither is implemented in Slice 3.1.

Provider Secret rotation creates a new immutable Secret version with a new DEK,
validates it through separately authorized flows, updates Control Plane metadata
only after Runtime attestation, and retains an eligible previous version only
while rollback policy requires it. Revocation blocks new use immediately.
Physical deletion occurs only after reference scanning and verified terminal
transaction state; failure retains the record and reports a bounded finding.

Master-key rotation creates a new root key/KEK version and rewraps verified DEKs;
it does not decrypt/re-encrypt Provider payloads merely to rotate the KEK. Both
old and new key material remain until every envelope is authenticated under the
new key and recovery state is durable. Interrupted or contradictory rotation is
`NEEDS_ATTENTION`, never automatic key replacement.

The accepted activation recovery policy remains: exactly one verified
pre-activation generation per Runtime may be retained for 7 x 24 hours after a
successful commit. A previous Secret/key is eligible only while referenced,
verified, and not revoked/deleted. Retention does not authorize generic Secret
history or automatic fallback.

## 14. Corruption, Logging, Diagnostics, and Audit

All parse, permission, ownership, link, schema, key, nonce, canonicalization,
AAD, tag, integrity, or revision contradictions fail closed. Diagnostics may
report only bounded machine codes such as:

- `SECRET_STORE_UNINITIALIZED`;
- `SECRET_STORE_UNAVAILABLE`;
- `SECRET_STORE_PERMISSION_INVALID`;
- `SECRET_STORE_KEY_MISSING`;
- `SECRET_STORE_KEYSET_INVALID`;
- `SECRET_STORE_INTEGRITY_FAILED`;
- `SECRET_RECORD_UNUSABLE`;
- `SECRET_STORE_NEEDS_ATTENTION`.

Logs, Audit, diagnostics, exceptions, Job results, API responses, CLI output,
test reports, and release artifacts must never contain:

- plaintext, ciphertext, nonce, tag, DEK, KEK, root key, wrapped DEK;
- key/Secret bytes, prefix/suffix, hashes or reversible hints;
- Authorization header, Provider request/response, prompt, completion;
- Secret file contents, raw record, canonical AAD bytes, TTY input;
- environment, argv containing Secret Material, or private Runtime paths.

Audit may contain only allowlisted fields: actor class, action/result code,
CredentialID, RuntimeInstallationID, SecretRecordID as an opaque reference where
operationally necessary, Secret version, non-secret key ID/version, lifecycle
transition, request/transaction ID, timestamp, and sanitized finding code.
Routine successful Secret resolution records identity/version and purpose only,
never value-dependent data.

## 15. Threat Model and Required Verification

The repository threat model is updated with Secret-specific threats T-92 through
T-101. Slice 3.1 implementation cannot be accepted without adversarial tests for:

- path traversal, parent/final symlink, hard-link, owner/group/mode, and race
  substitution;
- exclusive atomic initialization, fsync order, interruption after every durable
  step, and no replacement-key generation;
- AES-GCM known-answer/round-trip and wrong-key/nonce/AAD/tag/ciphertext tests;
- RFC 8785 canonicalization vectors and rejection of unsupported values;
- payload/wrap nonce collision and wrap-count bounds;
- missing/corrupt keyset/store/record and format-version mismatch;
- exact size/record-count limits and malformed SQLite schema;
- secret canaries across Control Plane SQLite/WAL/SHM, Runtime UDS, Audit,
  logs, diagnostics, exceptions, argv, environment, temporary files, backups,
  release artifacts, and test reports;
- API/Worker/Root Helper permission denial for the entire Runtime store;
- no network, Provider call, Runtime config access, credential broker, or
  activation path;
- CPython 3.11/3.12/3.13 and OpenCloudOS 9 artifact-wheel/runtime validation.

Cryptographic tests prove implementation conformance, not formal certification
or resistance to a fully compromised Runtime UID.

## 16. Slice 3.1 Implementation Boundary

### Authorized for a future separately approved implementation PR

- a focused module under `agentbox-runtime` for the fixed Runtime-owned store;
- exact path/owner/mode/link validation;
- explicit empty-store/root-key initialization;
- fixed store schema and integrity checks;
- P11-ADR-073 envelope encryption/decryption primitives;
- internal encrypt/decrypt self-test without external plaintext output;
- bounded health state and sanitized finding codes;
- dependency locks, offline wheels, SBOM/license/release metadata;
- unit, property, fault-injection, privilege, package, and canary tests;
- technical documentation for initialization and recovery status.

### Explicitly not authorized in Slice 3.1

- Control Plane or Runtime database migration;
- Secret provisioning command or TTY ingress;
- provisioning authorization/attestation UDS action;
- credential broker or Secret delivery to Codex;
- direct Provider validation or any Provider network request;
- Codex/Claude config access or mutation;
- Provider activation, Runtime Binding changes, transaction executor, admission
  fence, rollback execution, or session migration;
- Provider Secret rotation, root-key rotation, export, import, backup integration,
  reveal, generic list, or generic decrypt operation;
- Web/API/CLI/UI Secret input or Provider management surface;
- Root Helper action or privileged filesystem operation;
- Phase 11 Slice 4 or later work.

Slice 3.1 must be unreachable from current public product surfaces. Its only
operator reachability is the fixed local Runtime-user `initialize` action
defined in Section 11; that action creates no Provider, Credential, or Secret
record and accepts no Secret input.

## 17. Open Questions and Final Decision

### Closed before implementation authorization

- Secret authority: Runtime only.
- Control Plane migration for foundation: none.
- algorithm and envelope: AES-256-GCM, HKDF-SHA-256, per-version DEK, exact JCS
  AAD.
- library family: PyCA `cryptography`; exact reviewed baseline above.
- root key: raw 32 bytes, Runtime-owned fixed path and restrictive permissions.
- store: fixed Runtime-local SQLite, bounded and non-generic.
- ingress: future local Runtime-user TTY only.
- ordinary backup: excludes store and all key/ciphertext material.
- upgrade/rollback/uninstall: preserve store; never silently rewrite it.
- missing key with records: fail closed; never auto-generate.
- Root Helper, Web/API, Control Plane SQLite: no Secret authority.

### May be resolved in the separately reviewed implementation PR

- exact SHA-256 hashes and transitive wheels selected for CPython 3.11/3.12/3.13;
- the private Python module/class layout and exact sanitized exception class
  names;
- exact SQLite table/index names that realize this contract without expanding
  the operation surface;
- property/fault-injection framework details.

These are bounded engineering choices. None may alter key custody, algorithms,
AAD, paths, authority, backup policy, or operation scope without renewed review.

### Final decision

**READY FOR IMPLEMENTATION AUTHORIZATION**

The accepted architecture can be implemented as Slice 3.1 without changing an
Accepted ADR, adding a Control Plane migration, expanding Root Helper, exposing
Secret Material to Web/API/Control Plane, or starting Provider activation.

Slice 3.1 Secret Store Foundation may be separately authorized. Do not implement
it as part of this review.
