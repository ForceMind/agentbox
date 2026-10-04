# A3 independent encrypted single-read software slice

Status: inert software candidate, 2026-10-04, based on verified #140 merge
`57cb8cd643ca0531b805459998d71cbe13369823`, tree
`ef47c85676c36ce9bde730e7814d5628c5653fa3`. This implements the next bounded
[content contract](WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md), using the authoritative
[A3 context/plaintext codecs](WORKBENCH_A3_CONTENT_CODECS.md) and
[same-held-view staged reader/selector](WORKBENCH_A3_STAGED_READER.md).

The actual synthetic pipeline is:

`staged Git -> Runtime selector admission -> same held view/double patch read ->
all-capacity pagination preflight -> fresh A3 Noise session -> opaque-only
in-memory relay -> Web fully verified bytes`.

This is executable software evidence, not production admission or activation.
There is no Runtime RPC/socket/host key loader, API relay route, UI, Files/unstaged
read, alternate Project registry, generic command/file gateway, credential,
account, deploy or release operation. Production entrypoints import none of the
new channel/profile modules. Fixture READY/session/pin ports are explicitly
synthetic; they do not establish authentication, authorization or pin provenance.

## Dedicated handshake and strict envelope

Only the existing fixed `Noise_NX_25519_AESGCM_SHA256` primitives are reused.
No WAW application profile, context, AWCE, terminal frame or CipherState is
shared. Each role creates a fresh NX state using EXACT `context_bytes` /
`contextBytes` as prologue and obtains fresh directional CipherStates.

Every key record is canonical flat ASCII JSON with exactly:
`protocol_id="agentbox-a3-content/v1"`, integer `protocol_version=1`,
`context_digest`, `kind`, `data`. The first three kinds have no other fields;
ACK additionally contains `transcript_hash` (full 32-byte final Noise hash, hex).
The receiver validates kind, exact fields, context and length before a Noise step.

| Kind | Decoded data | Meaning |
| --- | --- | --- |
| `A3_KEY_INIT` | 32 bytes | NX message 1, empty payload |
| `A3_KEY_ATTEST` | 128 bytes | NX message 2 containing a fresh 32-byte challenge |
| `A3_KEY_CONFIRM` | 48 bytes | initiator confirmation ciphertext at n=0 |
| `A3_KEY_CONFIRM_ACK` | 48 bytes | responder confirmation ciphertext at n=0 |

`data` is canonical unpadded base64url. Entire key frames are at most 4096 bytes;
actual fixed schema sizes are 219/349/243/332 bytes respectively. There is no
wire-chosen algorithm, alternate suite or caller-controlled cryptographic nonce.
NX message 1 is unauthenticated until subsequent transcript confirmation;
changing its ephemeral key is detected by the initiator's message-2 verification.

Confirmation plaintext is SHA256 of ASCII
`agentbox-a3-content/noise-confirm/v1`, uint32 big-endian 32, the challenge, then
the final handshake hash. ACK plaintext is SHA256 of ASCII
`agentbox-a3-content/noise-confirm-ack/v1`. Both use empty AAD, preserving the
already reviewed challenge/final-hash confirmation pattern: context is in the
Noise prologue, the initiator verifies the independently supplied static pin,
and both fresh directions reserve n=0 solely for confirmation. This is a
domain-separated reuse of existing invariants, not a new security proof.
ACK's advertised hash must equal the local final hash before readiness.

Python's independent trust port supplies a SHA256 static-key fingerprint;
Web's typed trusted port supplies the raw 32-byte X25519 public key. Neither
learns its expected pin from a key frame. Pin/current-context drift, malformed
wire, timeout, replay or close permanently fences the role. Web rechecks after
every asynchronous primitive/hash completion, including final content digest.

Application records contain exactly canonical flat JSON fields:
`domain="agentbox-a3-content/record/v1"`, `context_digest`, `kind`, `sequence`,
`ciphertext`. Domain is an exact fixed constant. The authoritative application
AAD authenticates context digest, full final hash, kind, semantic sequence and
direction; decrypted inner context/kind/sequence/request nonce must match.
Internal Noise counters advance from n=1; semantic sequence is never a cipher
nonce. READ travels browser-to-Runtime, PAGE/END/ERROR Runtime-to-browser.

Parsers reject noncanonical JSON/base64, duplicate/unknown fields, nesting,
invalid UTF-8, escapes, unexpected numeric spellings and oversize input before
JSON/base64 allocation. Only bounded flat scalar schemas are admitted.

## Exact budgets and ownership

- Entire PAGE plaintext, including metadata, remains <=16384 bytes; <=16 PAGEs
  plus one END. Raw reader ceiling remains 262144 bytes/4096 lines, but not every
  reader result fits transport. `prepare_pages` checks ALL pages before the
  profile is created or any key/content frame is sent; TOO_LARGE emits no prefix.
- Maximum raw ciphertext is 16384+16=16400 bytes. Its unpadded base64 length is
  ceil(16400*8/6)=21867. A maximum PAGE envelope has exactly 176 bytes overhead,
  therefore 22043 bytes total, below the strict 24576-byte outer cap. A longest
  kind ERROR has one extra kind character but one fewer sequence digit, yielding
  the same parser maximum; actual ERROR plaintext is separately <=4096 bytes.
- Each read retains one complete raw observation and <=16 encoded pages plus
  END; transcript validators separately retain <=262144 raw bytes. A relay port
  admits one complete bounded opaque record at a time. No unbounded stream
  accumulator, persistent patch store, log/Audit payload or partial plaintext
  accessor is introduced. Python/JS hash/encoding copies exist; dropping
  references is neither memory zeroization nor a hard RSS guarantee.
- The single `GitStagedSelectors` owner owns the nonce ledger alongside its
  ephemeral selector MAC key/process identity, not per channel. At most 128 live
  32-byte nonce burns are retained through ORIGINAL authenticated selector expiry.
  Full ledger is `PATCH_UNAVAILABLE_BUSY`; no live eviction. Expired burns may
  retire on a later valid admission. Closing/replacing a channel never clears
  burns; constructing a new selector owner rotates its key and invalidates old
  selectors. Fork/clock regression/owner close fences admissions. Independent
  live fixture owners do not jointly enforce a global replay ledger. Production
  composition must enforce one active selector authority and explicitly close/
  invalidate its old owner plus epoch/key on replacement or restart; there is no
  new global singleton or parallel registry in this inert software slice.
- The existing four active-operation limit is shared by observation, legacy
  internal reads and admitted channels. A channel holds its slot/snapshot until
  its admission scope exits; no waiting admission queue extends token life.

## Runtime admission and send/currentness fences

`GitStagedSelectors.admit` validates the signed token and original issuance/
expiry, resolves trusted CURRENT READY binding/session/epoch, atomically burns
one nonce, opens one held view, and validates the full sorted snapshot/entry
against that view. It yields only a sealed `AdmittedStagedRead` carrying a copied
A3 context, original verified expiry and currentness guard. The channel never
parses unverified token fields and cannot mint or refresh an expiry.

The handle is valid only inside that owner admission scope, reads once, and
closes irreversibly. Its actual read uses the same held snapshot and existing
fixed Git commands, descriptor/object checks and two observations. Currentness
is checked after each reader await and before each subsequent child/publication;
closing a handle during a child prevents starting the second patch. The existing
mutable-object/stable-observation limitation remains; this is not a filesystem
transaction.

`serve_admitted_staged_read` composes that handle with full pagination preflight,
a new NX responder and an `OpaqueContentPort`. It receives INIT, sends ATTEST,
receives CONFIRM, sends ACK, receives encrypted READ, then sends preflighted
PAGEs and END. It enforces a conservative fixed <=5s handshake deadline through
ACK publication (start captured before profile construction) and a read deadline
bounded by the original selector expiry. Millisecond conversion floors expiry;
it never extends it. Idle receive/send waits are bounded. Every awaited return,
key/content send and final END is guarded; close/cancel/error destroys the
profile, closes the handle/port and discards references without auto replay.

A guarded coroutine rechecks AFTER scheduling, immediately before port entry.
`send(record, check_current)` additionally MUST call the supplied guard after
backpressure, immediately before actual insertion/publication, with no await in
between. Port close synchronously invalidates pending I/O. Send completion is
not proof of peer receipt. A failure even after insertion is uncertain delivery:
close permanently, retain nonce burn, send no END/retry. This port contract is
proven by bounded in-memory fixtures only; no production network implementation
is claimed.

Only Web END returns complete bytes after order/count/size/digest/UTF-8 validation
and the final live guard. PAGE returns no bytes. ERROR closes without success.
Browser roles destroy terminal state immediately after final validation. Python
Runtime remains checkable between encrypted END construction and its final send;
its transcript is already closed (a second response fails), and the session's
`finally` destroys keys. The fixture-only Web Runtime closes when returning its
terminal envelope; an external owner would need its own final-send guard.

## Evidence and remaining gates

The [public crypto fixture](../tests/fixtures/a3_content/crypto-v1.json) has a
separate PyCA-based test oracle that first rechecks the existing upstream Noise-C
vector, then derives all four A3 key frames and three application records without
importing product A3/Noise/WAW profiles. Both languages compare exact bytes.
All keys/challenges in deterministic vectors are published synthetic test values.
The real-Git interoperability harness uses a separate synthetic static key and
fresh random ephemeral sessions, and an explicitly fixed test clock.

`node scripts/check-a3-crypto-interop.mjs` runs actual staged Git with native
`ControlledProcessRunner`, holds admission through double observation and
preflight, relays only key/ciphertext records through bounded local fixture
pipes, and checks Web's complete bytes against an independently observed fixture
Git diff hash. It also proves lost-page/tamper/visibility failures never publish
partial bytes. Fixture bootstrap metadata is deliberately out-of-band trusted
test input, not a shipped bootstrap/authentication protocol. Frontend CI runs
both the independent reference checker and this live cross-language harness.

Focused Python/Web tests cover pin/scope/epoch/nonce drift, replay, strict lengths,
valid AEAD with inconsistent inner metadata, close during hash, original/handshake
expiry, exact page/envelope capacity, ledger full/retirement, shared active limit,
held-view cleanup, revocation after scheduling/backpressure, uncertain insertion
and cancellation. Test/CI status is recorded separately in
[current state](project/CURRENT_STATE.md); source self-review is not independent
review or native/physical-client production qualification.

Production READY/session/Origin/trust/pin resolver and revocation delivery,
Runtime key custody, actual relay endpoints, deliberate patch UI/visibility
wiring, host/physical clients and release qualification remain separate gates.
The pre-existing metadata API and WAW production frames are unchanged.
