# S03 submit-only synthetic profile

Revision: `s03-submit-synthetic-v1-candidate-3`, 2026-10-10.
This isolated candidate follows [K2 §§4/10](KEBUI_K2_CONVERSATION_ARCHITECTURE.md)
and [immutable synthetic admission](KEBUI_S03_INERT_CONTENT_ADMISSION.md).
Its sole consumer is the existing fixed `SyntheticBodyConsumer`. It is not a
production authenticated S03 source, U3 activation, vendor adapter or host qualification.

## 1. Exact base and design boundary

Base is [PR173](https://github.com/ForceMind/agentbox/pull/173), head
`cb90601037e4c4fad17b449f774e6850cd05cb42`, tree
`3537cd0db92bfce282a452ab9e21f9ff9138bb7f`, on PR172. PR173's six first-attempt
workflows passed; 27 jobs comprise 25 successes and two prescribed RC skips.
Its actual PR test-merge `64a52168bf7ce262ee18386967b44ad9f6883b54` has the
same tree. These are base results, not qualification of this new source.
PR169–173 remain separately unmerged; main remains
`9f8d20e325b6a17173a223bff7a2d14f0059fdd6`. No old head is amended or retargeted.

The independent preimplementation design review cleared the exact contract
SHA256 `d28ed6fcdb8e6afb8e02ae4d51dde3f41aec139aa8995fc2a7f08bd9d8a89ff6`.
That is a design-input identity, not a test result or this document's digest.
Four review clarifications are normative here: local versus remote expiry;
an actual single deadline driver; trusted original-journal recovery catalog;
and whole-channel reservation across idle and pending continuations. A later
reviewed revision separately accounts for permanent Web tombstone metadata and
records the unchanged accept-commit-before-return uncertainty window accurately.

The one integrated path is TypeScript sender → bounded opaque binary pipe →
Python receiver → unchanged issuer/owner/journal → unchanged fixed consumer.
Existing Noise NX, A3/WAW profiles, body issuer, admission owner and journal/schema
stay byte-identical. No production import, route, DB, authenticated relay, real
credential, CLI, user prompt, host activation, release or deployment is introduced.

## 2. Authority and source lifetime

`kebui-synthetic-adapter-v1` supports only one `submit_turn` attempt.
Noise NX proves responder static-key possession; initiator confirmation proves
only this handshake-key possession. Neither authenticates a user/browser.
Public fixture keys, tuple equality, a pin, context digest or KEY_READY cannot
mint a real source capability.

The fixed test composition separately creates each endpoint's sealed local
permit from independently loaded fixture metadata, before any wire exchange.
The Python root owns one current-scope/execution guard, journal, issuer, admission
owner and fixed dispatch/consumer. It cannot bind a caller-supplied arbitrary
owner after the fact. Root guard is reentrant and checks frozen execution as well
as all 16 scope fields. Endpoint identity and original source lease are required;
wire/bootstrap data is never authority. Copy, pickle, subclass, fork/PID changes,
second composition and forged/serialized permits fail closed.

At most one live material-bearing root/channel and one flight per accounting
domain. The fixed Node harness authorizes exactly one Web realm/module instance;
these bounds do not cover arbitrary additional vm/iframe/worker/module realms.
The process-local request tombstone key is `(scope,execution,request_id)`; up to
255 entries of at most 1,024 ASCII bytes persist for process lifetime, including
failed attempts. Web holds at most 255 private ordinary Uint8Array records, each
the first 20 context fields joined by ASCII `|` (627 bytes maximum). Validators
exclude the delimiter. A bounded byte-span scan independently rejects a repeated
scope/execution/request prefix, channel ID OR source lease. No string map, second
copy, body or hash index is retained. Capacity 255 rejects before joining/encoding
the next record. Its at-most-2,508-byte construction overlap remains within the
existing 65,536-byte transient workspace; the one retained array transfers to its
separate realm-lifetime metadata lane. Channel close does not clear tombstones.
This is synthetic miswiring protection, not cross-realm/restart authenticated
identity or deduplication. Pending old work cannot free capacity merely by close.

## 3. Context, primitive and nonce separation

Only existing `Noise_NX_25519_AESGCM_SHA256` primitives are reused; no new cipher,
KDF or signature is implemented. Existing A3/WAW keys, pin bootstrap, domains,
selectors, source authority and deadlines are not reused.

`LP(s)` is two-byte big-endian ASCII length followed by ASCII bytes. Context C is
`agentbox-s03-submit/context/v1` + NUL, then 21 LP fields in this exact order:

1. owner_scope, auth_epoch, project_id, project_revision, binding_revision,
   binding_digest, host_id, host_revision, runtime_epoch, api_authority_epoch,
   agent_type, execution_kind, conversation_id, conversation_revision, generation,
   turn_id (the original 16-field scope validators)
2. execution_id (`kexe_` + 32 lowercase hex), request_id (`kreq_` + 32 lowercase hex),
   channel_id (`ks03c_` + 32 lowercase hex), source_lease_id (`ks03l_` + 32 lowercase hex),
   adapter_profile (exact `kebui-synthetic-adapter-v1`)
3. Finally the trusted 32 raw pin bytes, without LP

Canonical positive uint64 values remain decimal strings, never JSON numbers or
coerced values. Maximum C is 739 bytes. CD is SHA256(C), not a body digest and not
authentication. Prologue is `agentbox-s03-submit/noise-prologue/v1` + NUL + C,
maximum 777 bytes. With HH from the actual NX transport, AAD is
`agentbox-s03-submit/aad/v1` + NUL + CD + HH + direction-u8 + kind-u8 + sequence-u64be,
exactly 101 bytes. Direction is 0 Web→Runtime or 1 Runtime→Web; kind is 3 CONFIRM,
4 READY or 5 SUBMIT. Sequence must equal the actual directional nonce.

The public static private fixture is 32 bytes of 0xd0; its public pin is
`b25dc5485163369e179437bb72fe4bd4a142482682c302d66a3a2d4865c3fd0b`.
Deterministic 0xd1/0xd2 ephemeral fixtures are solely non-admitting known-answer
vectors. Actual integrated channels use the unchanged primitive's fresh ephemeral
generator, with no public ephemeral-injection constructor. Different prologue/HH
alone does not give different transport keys when DH inputs repeat; fresh
session ephemerals are required separately, not inferred from domain separation.

## 4. Five exact records

Canonical ASCII JSON has these six keys in exactly this order:

`{"context":"<64 lowercase hex>","data":"<unpadded Base64URL>","domain":"agentbox-s03-submit/frame/v1","kind":"<kind>","seq":0,"version":1}`

SUBMIT alone has seq 1. Reject whitespace, BOM, escapes, duplicate/extra keys,
nesting, suffixes, noncanonical numbers, padding, nonzero Base64 unused bits,
wrong context/domain/version, direction, phase, sequence and replay before effect.
The raw cap is checked before text conversion or decode. No unbounded JSON parser.

| Order | Direction / kind | Seq | Decoded payload bytes | Raw JSON bytes |
| --- | --- | --- | --- | --- |
| 1 | Web→Runtime KEY_INIT | 0 | Empty-payload NX message1: 32 | 209 |
| 2 | Runtime→Web KEY_ATTEST | 0 | Empty-payload NX message2: 96 | 296 |
| 3 | Web→Runtime KEY_CONFIRM | 0 | Ciphertext: 111 | 317 |
| 4 | Runtime→Web KEY_READY | 0 | Ciphertext: 109 | 313 |
| 5 | Web→Runtime SUBMIT | 1 | Ciphertext: 17..16,400 | 187..22,031 |

CONFIRM plaintext is `agentbox-s03-submit/confirm/v1` + NUL + CD + HH (95 bytes);
READY uses `agentbox-s03-submit/ready/v1` (93 bytes). Confirmation/ready consume
nonce 0 in their respective direction, then SUBMIT consumes Web-send/Runtime-receive
nonce 1. There is no nonce-2 application record, output, ACK, error or interrupt
wire. KEY_READY is channel readiness, not durable acceptance.

Browser phases: NEW → INIT_SENT → CONFIRM_SENT → READY → SUBMIT_ATTEMPTED → CLOSED.
Runtime phases: NEW → ATTEST_SENT → READY_SENT → SUBMIT_ATTEMPTED → CLOSED.
Spend each attempt before crypto/publication. Any fault, duplicate, cancellation,
wrong phase or loss closes both directions irreversibly; no retry/rekey/rollback.
Normal consumed transport closes keys but does not revoke an accepted body lease.

## 5. Original bytes and independent deadlines

SUBMIT plaintext is the complete original 1..16,384 strict UTF-8 bytes, including
NUL/BOM/CRLF and exact normalization form. No inner JSON/base64/hash/text conversion.
A 16KiB NUL JSON string would be 98,306 bytes and exceed NX's bound; raw plaintext
instead yields 16,400 cipher bytes, 21,867 Base64URL characters, 22,031 JSON bytes
and 22,035 bytes including the transport prefix.

Web takes one synchronous owned snapshot of an exact ordinary Uint8Array with a
fixed, nonshared, attached ArrayBuffer before an await. Reject Buffer, subclass,
shared/resizable/detached buffers and accessors before payload copies. Strict
UTF-8 validation discards the validation string; no normalization/reencoding.
No claim is made that all transparent JavaScript Proxies can be distinguished.
Python passes the exact immutable decrypted built-in bytes object to the original
issuer.prepare; only the existing opaque handle survives the synchronous bridge.

Role clocks are exact unsigned uint64 nanoseconds, Python int excluding bool or
Web bigint, nondecreasing and independent. Actual fixture clocks advance from
Runtime 100,000,000,000 with original deadline 112,000,000,000, and Web
9,000,000,000,000 with deadline 9,008,000,000,000. Handshake deadline is the minimum
of the original role deadline and channel-start + 2s; overflow rejects, never
rebases the source. Equality expires. Invalid/throwing/regressing clocks are sticky.
These 12s/8s fixture windows are not production retention policy.

One bounded DeadlineOwner per role owns one scheduled handle, shared expiry signal
and protocol/IO wait. Missing frames, held capacity and readiness expire without
new input; early wakes reschedule remaining time, never extend the deadline.
Pending WebCrypto stays charged until settlement. Runtime source expiry closes
issuer and wakes the fixed readiness port; the old worker performs original final
checks and remains UNKNOWN when uncertain. It is not a vendor interrupt or Stop.

Web checks only locally observable state. If Runtime alone expires while Web's
local window is valid, Web may publish once; Runtime must still prepare/effect
zero. There is no instant cross-host revocation or remote-clock feed claim.
Source-only expiry/clock faults must not invalidate still-current metadata guards;
body-independent reads and receipts remain usable without consulting source clock.

## 6. Budgets and actual ownership

These are owned payload/fixed container budgets, not RSS, allocator/object headers,
JIT/rope/OpenSSL/WebCrypto internal memory, OS pipe capacity or secure erasure.

| Reservation | Bytes | Lifetime |
| --- | --- | --- |
| Existing retained+staging body | 4,194,304 | Unchanged issuer ownership |
| Existing UTF-8 workspace | 81,920 | Unchanged issuer validation |
| Python S03 | 1,048,576 | Before first context/pin/key allocation through actual retirement |
| Web S03 | 1,048,576 | Same, including idle and all pending continuations |
| Fixed relay/parser/catalog | 262,144 | One pending frame/accumulator per direction; bounded metadata |
| Python tombstone metadata | 261,120 | 255 × 1,024, process lifetime |
| Web tombstone metadata | 261,120 | 255 × 1,024, fixed realm lifetime; never released by channel close |

Combined declared payload/metadata reservation is 7,157,760 bytes across endpoints/relay.
Fixed single-realm Node endpoint+relay+metadata ≤1,571,840; Python
issuer+S03+tombstones ≤5,585,920. Journal/disk
limits remain separate. Whole-channel capacity is not a per-method temporary lane;
close signals alone do not release retained callbacks/crypto/IO. Concurrent work
returns BUSY before copying, including before existing TS primitive pre-busy copies.

With P=16,384, E=16,400, B=21,867, W=22,031, C=739, A=101, conservative copy-class
ceilings are Web `4P + 2P + 3E + 8B + 10W + 8C + 8A + 65,536 = 615,006`, and Python
`10W + 12B + 4E + 3P + P + 8C + 8A + 65,536 = 686,106`. Test oracle bytes are counted.
Each class limit and actual copy/retention site must be audited. Counters are
observed-size conservative charged peaks, not physical allocation profiling.
Assertions combine those real payload sizes with the copy-site audit; arithmetic
or a final zero counter alone is insufficient. After channel drain, persistent
Web metadata still reports 261,120 reserved capacity and its bounded used bytes.

Lock nesting is root/current → short S03 state → existing pool → journal, with no
lock across await. A lane may be reserved before current guard only after releasing
its own lock. One 4-byte big-endian length prefix precedes a raw record; reject
length outside 1..22,031 before allocating payload. Mid-prefix/body EOF fails closed.
No readline, wire hex, nested JSON wrapper, transcript or collect-all stdout.

## 7. Publication, handoff and recovery

Every crypto/read/capacity await is followed by exact local currentness, original
deadline, cancellation, phase and reservation checks. Publication is await capacity
→ final check → one synchronous whole-frame write. No intervening await/callback.
Attempt is spent first; false/throw/partial write is uncertain and never resent.
Post-write drain is not evidence that publication never happened.

Python's synchronous receive/decrypt/prepare operation holds the reentrant exact
scope/execution guard, passes the original bytes object to issuer, then clears all
plaintext/raw/cipher/parser/exception locals and key references before awaiting
original owner.submit. The async frame must hold only handle and safe metadata.
Preaccept cancellation cleans prepared ownership; accepted waiter cancellation
leaves the original shielded worker owning resources. Final original owner guard,
body lease, pool and journal CAS determine effect after the last dispatch await.

Lost ACK, EOF, crash, new endpoint/issuer or identical body never grant resubmission.
UNKNOWN retains execution occupancy. One pre-return uncertainty window differs:
if journal.accept commits but throws before returning, the unchanged owner has
not set its local durable flag. An unrecognized injected failure returns safe
store_unavailable, creates no witness/effect, and may leave live ACCEPTED occupied;
reopening that original journal makes the unfinished record UNKNOWN. Existing
allowlisted error codes retain their original sanitizer rules. ACCEPTED here is
not vendor ACK, terminal evidence or new send permission. Old handle, new root
and identical bytes cannot revive it. This differs from guard-exit after effect,
which conservatively returns UNKNOWN with effect already 1. No frozen owner is
changed to make these windows look identical. A fixed bounded parent catalog (≤4,096 bytes,
charged in relay lane) supplies original journal path/identity and exact metadata
for a fixed recovery constructor. Missing/mismatched catalog/path/identity rejects.
This trusted startup obligation does not make the unchanged schema detect arbitrary
fresh-empty-journal substitution outside the harness. Independent fixture reruns
are new test universes, not old-request recovery or global deduplication evidence.

## 8. Redacted errors and fixed test harness

Only `s03_unavailable`, `s03_invalid`, `s03_busy`, `s03_revoked` are new public codes.
Existing admission UNKNOWN is preserved; it cannot become an unaccepted S03 error.
Drop private exceptions and payload locals, leave handlers, then construct fixed
errors. Python context/cause/tracebacks and JavaScript cause/console/stderr must not
retain arbitrary original errors, body, body digest, pin/key or wire bytes.
Diagnostics contain only fixed enums, lengths/counts, booleans and numeric test
identity. No arbitrary callback, body reader, browser storage or logs are added.

The fixed interop runner only starts its known Python peer with an allowlisted
scenario. Content stdin/stdout uses binary frames only. Inherited fd3 carries one
≤4,096-byte metadata JSON with exact keys scenario, phase, effects, bytes,
original_identity_match, pool_drained, safe_errors. stderr is independently bounded
to 4,096 bytes. Fixed wall watchdog and temporary-directory cleanup only contain a
hung test; passing idle expiry must come from the real role-local DeadlineOwner.

## 9. Qualification and remaining gates

Local verification uses CPython 3.12.14 and Node 24.19.0; CI's Python matrix and
Node 22 are separate. Actual source and test evidence:

- 1,019 focused Python tests passed: 815 previous Kebui tests plus 132 new
  codec/root tests, 32 new integration tests and 40 source-boundary tests. This
  includes the unchanged nine real SIGKILL admission recovery windows. After the
  final Web iterator fix and fixture revision-label synchronization, the affected
  172 Python codec/root/boundary tests passed again. Full repository collection
  found 6,482 tests; collection is not full execution.
- Full Web suite: 89 files / 2,267 passed; extension suite: six passed. Full
  ESLint, Prettier, TypeScript and production builds passed for both packages;
  the extension remains inert. The existing bundle-size warning remains.
- Repository Ruff passed; strict mypy checked 412 files; sequential Black checked
  425 files. Documentation links, secret patterns, existing source boundaries,
  54 pinned workflow action references and the built extension gate passed.
- Existing cached dependencies match the lockfile. Local pnpm's stale copied
  workspace state attempted an install and stopped before execution at an
  unavailable HOME store path. No install/download or permission workaround was
  used; all package checks above ran the already-installed declared CLI entrypoints
  directly in the correct package directories. CI retains normal frozen-lockfile
  installation. One first collection invocation omitted the worktree PYTHONPATH
  and failed against the older editable checkout; the corrected explicit-current
  invocation collected all 6,482. Neither setup failure is a product regression.
- The actual cross-language runner executes 29 fixed scenarios with one sender
  module/realm. It covers exact 16KiB ASCII/NUL/four-byte UTF-8 and identity,
  both-direction length-prefix/EOF rejection, missing frames/held capacity with
  actual deadline expiry, waiter cancellation, source-only expiry, and catalog
  recovery. A full-size slow-reader case observes Node write(false): Web stays
  uncertain/no retry while Runtime may ACK exactly one effect. A separate actual
  effect/ACK followed by exit-crash before metadata delivery reopens the original
  journal as UNKNOWN without a new issuer/effect. The final exact input hashes
  and terminal run result are recorded with the candidate PR.

Actual development failures were preserved and fixed with the original probes:

| Finding | Fix and permanent regression |
| --- | --- |
| Waiter error traceback retained a completed Future with foreign exception | Clear task/result/done/operation holders before fixed public raise |
| Web typed error code accepted runtime arbitrary data | Runtime closed-code validation, immutable safe error, exact descriptor normalization |
| Late timer allowed a frame at handshake-deadline equality | Synchronous phase deadline check on every operation, independent of timer scheduling |
| Retired Runtime lane retained context/pin buffers | Clear encoded/digest/pin before capacity release, keep body-independent scope metadata |
| Outward source gate missed bare Web and dynamic Python imports | Static side-effect/from/export coverage and closed dynamic-import rejection; 34 inward/outward mutations |
| Recovery catalog serialized an oversized unvalidated reference | Exact field type/length validation before any serialization |
| External-thread source revoke directly resolved a loop-bound Future | At most one coalesced metadata-only loop notification; retain reservation through callback retirement |
| Web raw iterator override ran outside the bounded scan | Reject own Symbol.iterator without invoking it; use intrinsic length and indexed ASCII scan |

The first seven independent review findings (including the source gate) and the
separate implementation thread-revoke failure have original RED and precise
fix-GREEN evidence. Initial missing-module tests, the Node/jsdom cross-realm test
provider mismatch, the candidate-3 budget migration assertion, a byte-span callsite
refactor failure and the corrected accounting-evidence field label remain
separately documented; none is relabeled as a released-product defect. The earlier
all-UNKNOWN assertion was corrected to the actual frozen ACCEPTED/recovery behavior
in section 7, without modifying the original owner.

Independent probes also exercised full binding mutation, real fake-consumer
ownership and metadata lifetime, C3 capacity/OR deduplication and error/retirement
paths. Final source-review identity and this new candidate's exact-head six-workflow
qualification are recorded in its Draft PR. Remote checks are pending at commit
preparation; local/source/base results do not substitute for them. Full local native
execution and browser E2E were not rerun through the previously observed AF_UNIX
sandbox limitation; CI must supply those results. No new UI/pixel qualification is
claimed. No docs-only follow-up head is needed just to record CI terminal status.

Runnable entrypoints:

- [Codec tests](../tests/unit/test_s03_submit.py),
  [root tests](../tests/unit/test_kebui_s03_submit.py),
  [consumer integration](../tests/integration/test_kebui_s03_submit_inert.py),
  [source-boundary/mutation tests](../tests/unit/test_kebui_s03_boundaries.py)
- [Web sender tests](../apps/web/src/features/conversation/s03Submit.test.ts)
- [Actual binary interop](../scripts/check-kebui-s03-submit-interop.mjs) with
  `AGENTBOX_S03_TEST_PYTHON` set to the checked absolute installed interpreter;
  the existing Frontend workflow now runs it after Python setup

Production gaps remain: authenticated user/browser/session/source identity;
Runtime static key custody and trusted pin/bootstrap/rotation; API/Worker opaque
relay authority and budgets; real current-owner/single-writer and persistent recovery
catalog; fixed vendor executable behavior/outcomes/approvals/interrupt; actual host
and retention; output/history/U3 UI and release/deployment. Nothing in fixture NX
or fake-consumer success establishes those capabilities. This slice stops at one
independently reviewed and software-qualified Draft; old merge gates remain.
