# WAW encrypted stream supplemental contract decision

Status: **ACCEPTED for software implementation — 2026-09-03**.

Decision authority: the Owner explicitly delegated software goal/plan/architecture
decisions to the Coding Agent (“继续啊，你可以启动目标修改目标，你都可以决定”).
The Coding Agent elects to accept this complete, independently reviewed supplement
under that delegation; see [GOVERNANCE](GOVERNANCE.md). This records delegated
acceptance, not a claim that the Owner separately approved each byte choice.

This is one reviewable supplement to the historical
[WAW architecture](../../WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md).
It retains that document's historical approval state. The words “must”, “exact”,
and “reject” below specify the accepted software contract, not already implemented
capabilities or host/production authority. Routine merge alone is not the basis
for acceptance; the explicit delegation and recorded decision above are.
The fixed Noise NX core, opaque AWCE codecs, and synthetic stream classes retain
their separate scopes; none demonstrates a working encrypted terminal.

Owner/reviewers should read sections 1–7 and the decision boundary in section 9.
Implementers should use sections 2–6 with the historical direction/schema tables;
testers should use section 8. [REMAINING_PLAN.md](REMAINING_PLAN.md) maps this
proposal to R3 and the dependent implementation slices.

## 1. Scope and conflict resolution

The previous proposal supplied three missing byte choices: `protocol_id`, final
transcript hash, and direction-label/AAD bytes. Those values are retained below.
A subsequent read-only assessment found additional conflicting wire, admission,
ACK, quota, size, and trust rules. This supplement consolidates those decisions;
the earlier review of the three-byte proposal is not a review of this expanded
contract and is not Owner authorization.

The accepted resolutions below take precedence only over the identified
contradictory passages. All other fixed frame types, direction restrictions,
resource ceilings, exact process/lease fences, cleanup proofs, and host gates
remain applicable. It does not authorize generic commands/filesystem access,
Provider authentication, plaintext API relay, or a different Noise pattern.

| Historical location | Accepted resolution |
| --- | --- |
| Streaming Frames key rows versus Complete key frames prose | `KEY_INIT`/`KEY_ATTEST` carry the flat `AdmissionTuple`; derive `HandshakeContext` by the exact rule in section 2. Freeze all four key schemas. |
| KEY_CONFIRM/ACK unnamed ciphertext and missing protocol version | Use `ciphertext`, exactly 48 decoded bytes; require numeric `protocol_version=1`; ACK hash is 64 lowercase hexadecimal characters. |
| WebSocket Admission, connection-state and Audit canary claims | Runtime verifies browser confirmation; browser verifies Runtime canary; API validates only authenticated Runtime metadata and ordering. Preserve queue-release admission. |
| Internal ACK quotes an unavailable browser hop | Runtime reports only its input hop and crypto reference; API supplies the browser reference from its bounded mapping. |
| Input Delivery Semantics versus Resource Limits | Dropping an encrypted frame at API immediately fences the channel, without ACK or continuation. Runtime post-decryption rejection is a separate result. |
| HELLO_ACK limits versus 48 KiB frame prose | 49,152 is the generic AWCE plaintext ceiling; active V1 chunks are at most 16,384 input / 32,768 output bytes. |
| Pin overview versus signed fixtures and JSON integer rules | Preserve signed dot-form pin literal; use exact safe JSON integer Numbers for the three signed revision fields, with explicit wire conversion. |
| Ticket response field list versus pre-message epoch requirement | Include the already implemented `runtime_epoch` field in the exact response list; no new endpoint or behavior. |

## 2. Context, encodings and exact key schemas

### Shared scalar and object rules

Every key frame is one flat JSON object within the existing 4 KiB control-payload
limit, depth 16, 64-key and decode-budget ceilings. Reject duplicate, missing,
unknown or extra keys, invalid types, non-finite numbers, invalid UTF-8 and trailing
non-JSON bytes. `AdmissionTuple` and `HandshakeContext` below name exact key sets;
they are not nested JSON keys. No field is inferred from an omitted wire value.

`U64+` means a JSON string matching `[1-9][0-9]{0,19}`, then range-checked in
`1..18446744073709551615`; no sign, whitespace, leading zero, exponent, Number,
rounding, wrapping or coercion. The binary Noise/ABWS counter exhaustion rules
still apply and can impose a smaller usable range. `HEX32` means exactly 64
lowercase `[a-f0-9]` characters representing 32 bytes. Public keys/ciphertexts use
canonical unpadded base64url: ASCII `[A-Za-z0-9_-]`, no `=`, whitespace or alternate
alphabet, exact decoded length, and zero unused trailing bits. An equivalent
non-canonical string is rejected rather than normalized.

The exact flat `AdmissionTuple` (`A`) is:

| Keys | Type / value |
| --- | --- |
| `attachment_id` | `att_[a-f0-9]{32}` |
| `workspace_id` | `aws_[a-f0-9]{32}` |
| `project_id` | `prj_[a-f0-9]{32}` |
| `agent_type` | String `claude` or `codex` |
| `runtime_host_installation_id` | `wri_[a-f0-9]{32}` |
| `runtime_host_installation_revision`, `auth_epoch`, `api_authority_epoch`, `lease_number`, `generation`, `binding_revision` | `U64+`, exactly equal to the bound admission values |
| `mode` | String `writer` |
| `binding_digest` | `HEX32` |

`runtime_epoch` is `U64+`, issued by Runtime and already bound by API before ticket
issuance. All echoes must equal that epoch; a new epoch cannot be learned from a
nominal success frame. API-only Session/admin/scope data, ticket, capability,
replay hints and origin are not members of `A` or the crypto context.

The exact flat `HandshakeContext` (`C`) has these 15 keys:

```text
protocol_id, crypto_envelope_version,
runtime_host_installation_id, runtime_host_installation_revision,
runtime_epoch, api_authority_epoch, workspace_id, project_id, agent_type,
generation, attachment_id, lease_number, auth_epoch, binding_revision,
binding_digest
```

Derivation is exact: copy every member of validated `A` except the fixed `mode`,
then add the already-bound `runtime_epoch`, `protocol_id="agentbox-waw/v1"` and
numeric `crypto_envelope_version=1`. `mode` is validated as `writer` before it is
omitted. The fixed protocol has no viewer/alternate-mode interpretation. No
`protocol_version`, `noise_protocol`, fingerprint, key, challenge, transcript
hash, ticket, capability, cursor or origin is added to `C`. Encode `C` once using
RFC 8785 canonical UTF-8 before Noise message 1; all its uint64 values remain
quoted decimal strings. Those complete bytes are the Noise prologue.

The ticket response's exact keys, matching the existing
[WAWAttachmentTicketResponse](../../apps/api/src/agentbox_api/waw_admission.py), are
`{protocol_version,request_id,ticket,workspace_id,project_id,agent_type,attachment_id,mode,lease_number,generation,binding_revision,binding_digest,auth_epoch,api_authority_epoch,runtime_host_installation_id,runtime_host_installation_revision,runtime_epoch,expires_at}`.
This repairs the historical response-list omission. Existing field types and
six-digit RFC3339Z expiry formatting remain unchanged. Browser gets the epoch
from this response, not from a fabricated new API field or a later key frame.

### Four direction-specific key frame key sets

In this table `A + {...}` and `C + {...}` mean the **flat union of exactly the
listed keys**, never an `A`, `C`, `context`, or `HandshakeContext` wrapper. A key
appearing in `C` is serialized once. All four require JSON Number
`protocol_version=1` and String `noise_protocol="Noise_NX_25519_AESGCM_SHA256"`.
`crypto_envelope_version` is JSON Number `1`, never a string.

| Frame | Complete flat key set | Additional value contract |
| --- | --- | --- |
| `KEY_INIT` | `A + {protocol_version,noise_protocol,crypto_envelope_version,runtime_epoch,browser_ephemeral_public_key,noise_message_1}` | Public key is 32 raw X25519 bytes / 43 base64url characters. NX message 1 is exactly `e` with empty payload: 32 bytes / 43 characters. No `protocol_id` key. |
| `KEY_ATTEST` | `A + {protocol_version,noise_protocol,crypto_envelope_version,runtime_epoch,runtime_attestation_x25519_fingerprint,runtime_ephemeral_public_key,noise_message_2}` | Fingerprint is `HEX32`; ephemeral key is 32 bytes / 43 characters. NX message 2 contains 32-byte `e`, 48-byte encrypted static key and 48-byte encrypted challenge: exactly 128 bytes / 171 characters. Challenge plaintext is exactly 32 Runtime CSPRNG bytes. No `protocol_id` key. |
| `KEY_CONFIRM` | `C + {protocol_version,noise_protocol,ciphertext}` | `ciphertext` is the first initiator transport message: exactly 48 bytes / 64 base64url characters, including its 16-byte tag. No `mode`, `status`, `transcript_context_hash` or separate counter. |
| `KEY_CONFIRM_ACK` | `C + {protocol_version,noise_protocol,status,transcript_context_hash,ciphertext}` | `status` is exactly String `verified`; hash is `HEX32`; `ciphertext` is the first responder transport message: exactly 48 bytes / 64 characters including tag. No `mode` or separate counter. |

Each receiver compares the exact context fields to its existing bound context,
not merely to another field in the same untrusted frame. Endpoints decode each
Noise `e` and require equality with the duplicate public-key metadata before
advancing/decrypting that message. Browser requires the decrypted static key's
SHA-256 to equal both the independently trusted pin and the claimed fingerprint.
API can validate metadata, encoded lengths/alphabet/canonical trailing bits and
ordering; it does not decode/parse the opaque Noise message or create a key frame.
It forwards the original complete key JSON payload bytes unchanged, rewriting
only the outer hop header. Parsing metadata is not permission to reserialize it.

### Retained byte choices and confirmation formulas

| Item | Exact accepted bytes / formula |
| --- | --- |
| `protocol_id` | ASCII JSON string `agentbox-waw/v1` |
| Noise prologue | Complete RFC 8785 UTF-8 `C` bytes above |
| `transcript_context_hash` | Exact 32-byte final Noise handshake hash `h` after message 2 and its challenge payload; no additional hash or concatenation |
| Browser→Runtime direction label | ASCII `browser-to-runtime`, no NUL or length prefix |
| Runtime→browser direction label | ASCII `runtime-to-browser`, no NUL or length prefix |
| AWCE associated data | `header_44_bytes || transcript_context_hash_32_bytes || direction_label_bytes` |
| KEY_CONFIRM / KEY_CONFIRM_ACK associated data | Empty bytes, using the standard Noise transport operation |
| KEY_CONFIRM plaintext | `SHA-256(ASCII("agentbox-waw/noise-confirm/v1") || uint32_be(32) || challenge_32_bytes || transcript_context_hash_32_bytes)` |
| KEY_CONFIRM_ACK plaintext | `SHA-256(ASCII("agentbox-waw/noise-confirm-ack/v1"))` |
| Fixed ACK canary SHA-256 | `fbb2854eb233e77bae587d1480d40192379527e27de780b24010ec97714490c3` |

On wire the ACK's hash is lowercase hexadecimal; when used in the confirmation
formula, context ID or AAD it is the decoded 32 bytes, never 64 ASCII characters.
Final Noise `h` binds protocol name, prologue and both messages through the frozen
Noise revision-34 processing rules. Header/hash fixed lengths make the AAD
concatenation unambiguous. Direction byte and label must agree; outer ABWS and
WebSocket bytes are excluded. The published rules are
[Noise processing](https://noiseprotocol.org/noise.html#processing-rules) and
[channel binding](https://noiseprotocol.org/noise.html#channel-binding).

Confirmation consumes `n=0` separately in each split CipherState; first INPUT and
OUTPUT use `n=1`. There is no third handshake message, exported channel key,
manually selected nonce, counter skip, alternative pattern or plaintext fallback.
No failed decrypt is retried with the same or a different counter. Channel close,
epoch change or reconnect destroys the old states; reconnect creates fresh ones.

## 3. Verification authority and admission ordering

| Actor | Positive evidence it can verify | Evidence it cannot claim |
| --- | --- | --- |
| Runtime | Exact UDS-bound context, browser Noise confirmation plaintext at initiator `n=0`, its own process/PTY/lease fences | Browser receipt/decryption of ACK or ADMITTED |
| API | Provenance-checked Runtime stream, exact metadata/schema/sequence/epoch, `status=verified`, positive ready/commit responses and durable Audit/queue operations | Noise decryption, final `h` cryptographic correctness, canary equality or browser receipt |
| Browser | Independent root/pin validation, Noise static key, own final `h`, ACK AEAD/canary, and exact ADMITTED tuple/epoch/order | API's durable Audit write or receipt by the CLI |

Runtime emits `KEY_CONFIRM_ACK` only after it decrypts and verifies the exact
browser confirmation and successfully creates its canary ciphertext. API validates
that frame's metadata against the authenticated Runtime context, then relays it
unchanged before any `ADMITTED`. `status=verified` asserts Runtime's confirmation
check; it is not proof that the browser has verified the ACK. API does not derive,
read or export Noise keys. It can check the hash grammar, not reproduce final `h`.

After that metadata check, the existing sequence remains: durable
`workspace.attachment_prepared` → `STREAM_READY` → positive `STREAM_READY_ACK` →
quarantined complete `ADMITTED` → `ADMISSION_COMMIT` → positive
`ADMISSION_COMMIT_ACK` → durable `workspace.attachment_admitted` → atomic release
of quarantined `ADMITTED` into the bounded browser queue. Runtime repeats the
existing exact process/PTY/tuple/epoch/lease checks under its attachment lock.
The server writer becomes ACTIVE at that queue release, not at browser receipt.
No OUTPUT is visible to browser before ADMITTED; committed pre-admission output
still obeys the existing complete-frame quarantine and 64 KiB budget.

Browser keeps input/terminal presentation closed until **both** its local ACK
verification has succeeded and the expected ADMITTED has arrived and passed exact
context validation. Local ACK verification requires AEAD at responder `n=0`, the
32-byte canary and equality of received hash with the browser's own final `h`.
The UI cannot mark CONNECTED from a metadata-only `status=verified`. A pending
asynchronous verification cannot be bypassed by receiving ADMITTED; a late crypto
completion after close cannot reopen the gate. Existing bounded receive handling
must not turn this wait into an unbounded output queue.

No new browser receipt/confirmation frame is added. The unchanged hop sequences
are:

| Leg | Admission frame sequences | First ACTIVE frame |
| --- | --- | --- |
| Browser→API | WS_HELLO 1, KEY_INIT 2, KEY_CONFIRM 3 | 4 |
| API→Runtime | RUNTIME_HELLO 1, KEY_INIT 2, KEY_CONFIRM 3, STREAM_READY 4, ADMISSION_COMMIT 5 | 6 |
| Runtime→API | HELLO_ACK 1, KEY_ATTEST 2, KEY_CONFIRM_ACK 3, STREAM_READY_ACK 4, ADMISSION_COMMIT_ACK 5 | 6 |
| API→browser | KEY_ATTEST 1, KEY_CONFIRM_ACK 2, ADMITTED 3 | 4 |

The single byte-identical same-stream commit retry/ACK replay remains at hop 5
within the shared five-second admission deadline. No other new retry exists.

The historical phrases “API verifies the canary”, “API derives transport keys”,
and “prepared Audit follows canary verification” are replaced by the actor-specific
rules above. An invalid confirmation detected by Runtime prevents the prepared
Audit/ready path. A failure detected **only by browser** prevents local input and
closes its transport; API may already have written prepared/admitted Audit or
released ADMITTED before observing that close. Such a server lease is cleaned up
through the existing disconnect/grace and positive-cleanup rules, with no claim
of browser receipt and no rollback of truthful Audit. Browser cannot send a typed
ERROR/STATE/CLOSE to grant authority. A corrupted ACK cannot enable its input gate.
This is a deliberate consequence of retaining the four key frames, not an API
ability to observe end-to-end verification.

Premature INPUT receives no ACK, is never forwarded or retained, and closes the
pre-admission channel. Queue-release/Audit/commit failure retains the existing
`ADMITTED_DELIVERY_FAILED` path, transport 1013 and cleanup proof. A missing proof
keeps the reservation fenced/UNKNOWN; it does not silently release a writer slot.

## 4. INPUT ACK translation and rejection contract

The input result type stays frame 18 (`ACK`). No browser sequence is added to
INPUT/AWCE or to API→Runtime data. Runtime knows only its bound stream and the
Runtime-leg INPUT header; this supplement replaces the impossible internal schema.

| Direction | Exact JSON keys |
| --- | --- |
| Runtime→API | `{protocol_version,runtime_input_hop_sequence,crypto_sequence,result,reason_code}` |
| API→browser | `{protocol_version,browser_input_hop_sequence,runtime_input_hop_sequence,crypto_sequence,result,reason_code}` |

`protocol_version` is numeric `1`. Referenced hops are `U64+`; `crypto_sequence` is
a decimal string in the terminal CipherState range `1..18446744073709551614`.
They must equal a previously forwarded INPUT in this exact attachment and stream;
they are references, never newly allocated input counters. The outer ACK header
uses the next return-leg hop. Cross-connection/context or unknown references close
as `PROTOCOL_INVALID`/`ATTACHMENT_STALE` without creating a map entry.

API reserves its existing bounded mapping before forwarding INPUT: attachment,
original browser hop, allocated Runtime hop, immutable crypto sequence, zero input
cursor, and resolution state. It contains no plaintext or response-loss payload.
A validated Runtime ACK selects exactly that entry by Runtime hop and crypto
sequence. API adds its stored `browser_input_hop_sequence`, preserves all Runtime
result fields, and allocates the next API→browser hop. Runtime does not guess or
receive the browser hop. At most 256 entries exist per attachment, including any
retained terminal replay metadata; no timeout/terminal result grows that bound.
Existing five-second resolution and one byte-identical terminal-result replay
bounds remain; a replay changes no input state and never resends input bytes.

| `result` | Exact `reason_code` | State / authority |
| --- | --- | --- |
| `accepted` | JSON `null` | Runtime authenticated/decrypted the INPUT and admitted its bytes to the bounded PTY write queue; only nonterminal result. |
| `written_to_pty` | JSON `null` | Terminal result after accepted; bounded PTY write completed, not proof of CLI processing. |
| `write_uncertain` | `INPUT_WRITE_UNCERTAIN` | Terminal result after accepted; completion cannot be proved. Never automatic resend. |
| `rejected` | Exactly one of `INPUT_RATE_LIMITED`, `ATTACHMENT_STALE`, `WORKSPACE_NOT_RUNNING`, `WORKSPACE_EXITED`, `WORKSPACE_STOPPED`, `RECONCILIATION_REQUIRED` | Terminal pre-write result only after a syntactically valid, in-order INPUT successfully passed Runtime AEAD verification. |

The rejection set is closed; prose examples do not add reasons. `accepted` may
transition once to written/uncertain; it cannot become rejected. Rejected bytes
never enter the PTY. Successful AEAD consumes that Runtime receive CipherState
counter even if a subsequent queue/state check rejects the plaintext. A temporary
Runtime queue-cap rejection may retain an otherwise healthy attachment and accept
the next contiguous crypto sequence; stale/state/reconciliation reasons follow
the existing fence and CLOSE/EXIT rules. No rejected frame is retried. Malformed,
out-of-order, wrong-context, or unauthenticated ciphertext gets no ACK and destroys
the channel. A state fence that prevents decryption also gets no input ACK.

Input/exit locking stays unchanged: if an already authenticated input is rejected
by the exit fence before queue insertion, its rejected/WORKSPACE_EXITED result
precedes EXIT/CLOSE; accepted input resolves before EXIT, with partial writes
uncertain. Nothing emits an ACK after EXIT/CLOSE. On API loss/close unresolved
entries become local bounded `input_uncertain` metadata; API does not forge a
Runtime `write_uncertain` ACK for an unobserved result.

## 5. Ciphertext drop, rate and queue precedence

The first API rejection that discards an INPUT ciphertext because of the 8 KiB/s
rate / 16 KiB burst, 64 KiB encoded pending-input budget, or 256-entry ACK-map cap
immediately fences that attachment. It never waits for three over-limit windows.
It sends no ACK, allocates no Runtime INPUT hop/map for the discarded frame,
forwards no bytes from it, and accepts no later ciphertext on that channel. A
syntactically valid frame may consume its browser **hop** sequence; this is not
consumption/decryption of a Noise message by API. The browser has already advanced
its sending CipherState, so continuation or counter skip is forbidden.

For this quota/queue/map failure the existing normalized ERROR code is
`INPUT_RATE_LIMITED`. Where trusted metadata can still be queued, the exact ERROR
schema is `{protocol_version:1,code:"INPUT_RATE_LIMITED",retryable:false,request_id}`
with a fresh `wreq_[a-f0-9]{32}` server correlation ID. `retryable=false` forbids a
same-channel/input retry; a new attachment may be requested after cleanup. API
sends the already-allowlisted authenticated internal `CLOSE code=CONTROL_RATE_LIMITED`
with the exact current workspace-state snapshot, and closes the browser transport
with 4429. It does **not** invent `CLOSE code=INPUT_RATE_LIMITED` or an API-originated
browser typed close absent from the origin matrix. If trusted ERROR cannot fit,
close without it; no metadata-delivery failure justifies channel continuation.
No new error code or API→Runtime ERROR profile is introduced.

A browser may throttle before encryption/sending within its existing local limits;
that is not an API ciphertext drop. Runtime may reject after successful decryption
under section 4; that is not an API quota ACK. The historical Resource Limits
input-rate persistence paragraph and pending-input “ACK rejected” rule are
superseded only for API-dropped ciphertext. Existing control/resize/parser and
producer persistence rules continue where they do not discard ciphertext and
continue the same channel.

Likewise API's first unqueueable OUTPUT fences immediately with
`OUTPUT_BACKPRESSURE`, never a synthetic GAP or skipped crypto sequence. Runtime
can omit eligible ring records **before** encryption, emit an exact cursor GAP,
and encrypt the selected records consecutively. After encryption a selected frame
is indivisible. Any ciphertext loss requires fresh-key attachment/replay.
All closure paths retain the workspace, drop only attachment-owned transient
queues, and require positive exact cleanup before slot reuse.

## 6. Layered frame and chunk limits

| Layer / field | Plaintext bytes | Ciphertext including 16-byte tag | AWCE payload including 44-byte header | Complete ABWS including 24-byte header |
| --- | ---: | ---: | ---: | ---: |
| Generic AWCE protocol maximum | 49,152 | 49,168 | 49,212 | 49,236 |
| Active V1 INPUT / `HELLO_ACK.input_limit=16384` | 16,384 | 16,400 | 16,444 | 16,468 |
| Active V1 OUTPUT / `HELLO_ACK.output_limit=32768` | 32,768 | 32,784 | 32,828 | 32,852 |

Each plaintext is at least one byte. The ABWS parser's 65,512-byte payload /
65,536-byte complete-frame ceiling is a parser allocation bound, not permission
for a larger WAW frame. Historical “64 KiB ciphertext” wording does not enlarge
the 49,168-byte generic ciphertext bound. The HELLO_ACK numeric limits are fixed
V1 per-chunk ceilings, not rates or caller negotiation. ADMITTED acquires no new
limit fields: browser uses these fixed profile constants, and API requires the
exact Runtime HELLO_ACK values before admitting.

Opaque codec validation can accept up to the generic AWCE maximum. The active
channel layer also enforces its smaller directional bound: browser chunks before
encryption at 16,384; Runtime checks INPUT declared encrypted size before bounded
allocation and checks authenticated size before writing; Runtime selects/chunks
producer records before cursor assignment/encryption at 32,768; API checks the
appropriate ciphertext size on both legs; browser checks OUTPUT size before
accepting/decrypting/rendering. An already cursor-assigned/encrypted frame is not
split. Rate cost is the plaintext-equivalent length inferred as encrypted length
minus the fixed tag; API does not decrypt it. Encoded queue accounting still
includes the actual headers and tags, not only that rate cost.

A valid generic envelope of 16,385 INPUT bytes or 32,769 OUTPUT bytes is therefore
invalid for an active V1 channel. Reject it before forwarding with transport 1009
and exact attachment cleanup, without ACK, splitting or continuation. The 64 KiB
pre-admission queue still counts complete frames plus GAP metadata and cannot
assume two maximum OUTPUT frames fit: `2 × 32,852 = 65,704 > 65,536` even before
GAP metadata. Existing deterministic crop/select-before-encrypt rules apply.

## 7. Signed trust records and deployment boundary

### Preserve the public signature fixtures

The historical pin fixture actually signs `schema_version="waw-runtime-pin.v1"`;
the overview instead names `waw-runtime-pin-v1`. Read-only verification of all
three embedded fixture signatures and their domain-prefixed hashes succeeded on
2026-09-03 using the existing Python `cryptography` Ed25519 verifier:

| Public fixture | Exact signed-bytes SHA-256 | Result |
| --- | --- | --- |
| Pin revision 7, dot-form schema | `04dbc42b5d277c452be1789428870db91787a67a30f04da4b70c430ebdb9f5d6` | Hash and signature verified with `root-2029` fixture public key |
| Root revision 1 | `a76caf4891cb708e69a586def82a89a26a45ca5f0c8fa7ccf910183a689b9752` | Hash and signature verified with bootstrap fixture public key |
| Root successor revision 2 | `0a55c4152914ea09136ae20441fa5b82678b6f1dc6c9aaf031bedbb6bf7a4ad2` | Hash and signature verified with preceding root fixture public key |

This verifies only the embedded ASCII fixture bytes, not a complete RFC 8785
implementation, trust-store lifecycle or present-day deployment validity. The
fixtures' validity begins in 2030; use an explicit test clock, not today's clock,
for positive validity tests. No private key was read, generated or used to sign.

The accepted compatibility rule is to use **only** `waw-runtime-pin.v1` as the pin schema
literal and preserve the existing signed pin bytes/signature. Dash-form pin
literal is rejected. Root remains `waw-runtime-root-v1`; bootstrap remains
`waw-runtime-bootstrap-v1`. Do not silently accept aliases, normalize a signed
schema string, relabel the fixture, or re-sign with an unknown Owner key.

### Exact signed schemas and numeric representation

Pin keys are exactly
`{schema_version,repository,origin,pin_revision,runtime_host_installation_id,runtime_host_installation_revision,runtime_attestation_x25519_fingerprint,valid_from,valid_until,revoked_at,supersedes_fingerprint,signature_algorithm,key_id,signature}`.
`schema_version` is `waw-runtime-pin.v1`, repository is `ForceMind/agentbox`,
algorithm is `Ed25519`, fingerprint is `HEX32`, and supersedes fingerprint is
`HEX32` or null. There is **no** pin `state` key: null/non-null `revoked_at` gives
the derived active/revoked condition. Existing exact canonical origin, host-ID,
key-ID and millisecond-precision UTC time rules remain.

Root keys are exactly
`{schema_version,root_revision,key_id,public_key,signer_key_id,state,valid_from,valid_until,revoked_at,supersedes_key_id,signature_algorithm,signature}`.
Use the historical frozen root schema, including `signer_key_id` and `state`,
not its earlier shorthand. `state` is ACTIVE or REVOKED; revoked timestamp is null
iff ACTIVE. `supersedes_key_id` is null only for the bootstrap-signed revision 1.
Bootstrap keys are exactly `{schema_version,key_id,public_key}`, with the frozen
bootstrap schema and `key_id="bootstrap-2029"`; no signature or added key.
Public Ed25519 keys are 32 bytes / 43 canonical base64url characters; signatures
are 64 bytes / 86 characters. Key IDs match `[a-z0-9._-]{1,64}`.

In **signed trust records only**, `root_revision`, `pin_revision` and
`runtime_host_installation_revision` are JSON integer **Numbers** with the exact
range `1..9007199254740991` (`2^53-1`). Canonical serialization uses decimal integer
digits, not quoted strings. Reject out-of-range values before binary64 rounding,
fractions, exponent spellings in a purported canonical record, and negative zero.
This explicit safe-range exception preserves every existing signed fixture while
removing the impossible promise of lossless arbitrary uint64 JSON Numbers.

In WAW HTTP/control/ABWS/context objects all revisions remain canonical uint64
**strings**, as in section 2. Compare the pin's host revision and wire host
revision by exact mathematical integer equality without lossy Number conversion.
A wire host revision above `2^53-1` has no valid V1 signed pin and must fail browser
trust; it is never truncated or accepted by rounding. An Owner deployment using
this profile must rotate host identity before that signed range is exhausted.
Root/pin revision allocation fails closed at the maximum; no wrap, reset, or
schema coercion. Other WAW uint64 domains are not reduced by this exception.

Signed pin bytes remain
`ASCII("agentbox-waw/runtime-pin/v1") || 0x00 || RFC8785(record_without_signature)`;
root uses the distinct `agentbox-waw/runtime-root/v1` domain. Algorithm/key-ID and
all declared fields are signed. The bootstrap policy digest remains
`87e70aac507cf4a4a230d4910cc8c864a0d585974ad71949fcdbc6754cc8cb72`.
Unknown/duplicate/missing keys, padding or field mutations fail closed before
trust installation or Noise advancement.

### Trust authority that software tests do not supply

All existing independent provisioning, root successor/revocation signatures,
atomic revision-floor persistence, no rollback, pin supersession, origin binding,
trusted-clock/300-second skew, expiry and no active use of revoked/superseded
records remain required. A valid signed revocation may update the trust store but
can never authorize attachment. Invalid/replayed/substituted records leave the
accepted record and floors unchanged. API/Runtime/served frontend cannot install,
replace or silently revoke a root/pin; their metadata is not trust authority.

The actual independently administered browser trust provider is still a deployment
choice: the Owner must name a platform/policy or independently controlled import
mechanism that supplies authenticated bootstrap/pins, atomic rollback-resistant
revision floors, trustworthy time, and the required origin/network-policy checks.
A normal mutable API response, served frontend configuration, localStorage or
IndexedDB alone does not meet that contract. An in-memory test provider can test
verification logic, but cannot prove persistent rollback resistance or deployment
authority. This supplement adds no provider API, automatic enrollment or fake
production trust source. The deployment choice and its evidence remain an explicit
R9/R12 gate; software crypto/schema work can proceed after this supplement is
accepted without claiming that gate has passed.

## 8. Required acceptance vectors and evidence

The fixtures below describe required tests for the eventual accepted implementation;
except the public-signature/hash check above, these are **not yet run evidence**.
Freeze byte artifacts with public test material and exact provenance in the
implementation PR. Do not claim a generated same-implementation round trip as an
independent vector. The full application profile needs independent read-only
Architecture/Security/Test review and supported Python/browser interoperability.

| Vector group | Required positive case and rejection / race cases |
| --- | --- |
| Exact schemas | Each flat key set parses; missing/duplicate/extra fields, context wrapper, INIT/ATTEST `protocol_id`, CONFIRM `mode`, string version, unknown algorithm, boolean/Number revision, invalid decimal and uint64 overflow fail. Existing ticket response includes exact epoch. |
| Context | Both languages derive byte-identical canonical `C` and fixed SHA-256 before message 1. Mutate every tuple/epoch/context field, including `mode`; reject before an invalid-mode context exists. No origin/cursor/bearer/extra field enters prologue. |
| Noise and confirmation | Fixed message lengths 32/128, duplicated `e` equality, challenge 32, final `h`, both 48-byte confirmations, exact canary, hex decoding and empty confirmation AD. Padded/noncanonical base64, one-byte key/ciphertext/tag/hash mutation, wrong static pin, wrong nonce/direction or late close completion fails closed. |
| AWCE | n=0 only for confirmations, first directions n=1; exact AAD/context ID/header/cursor; changing outer hop only succeeds, changing any immutable byte fails. No unauthenticated counter skip, same-key reconnect or application payload at n=0. |
| Admission actors | API needs no decryption key; valid Runtime metadata can precede browser ACK verification. Pause/fail browser decrypt while ADMITTED arrives: no input/render/CONNECTED. If API already committed, disconnect cleanup is truthful and Audit does not claim browser verification. No added browser frame/sequence. |
| Admission fences | State/epoch/lease/process drift before ready/commit, shared timeout, one exact commit retry, lost ACK, Audit failure, queue-release failure and post-release disconnect; never early writer/OUTPUT or slot reuse before positive cleanup. |
| ACK mapping | Interleave browser controls and internal health frames so browser INPUT hop differs from Runtime hop. Internal ACK has no browser reference; translated ACK returns the original mapped hop. Reject unknown/mismatched references, extra internal browser key, illegal result/reason transitions and cross-stream replay. Preserve accepted→terminal and input/exit ordering. |
| API drop | At the first rate, 64 KiB encoded-queue or 256-entry map violation: no ACK/Runtime INPUT allocation/forwarding/continuation, 4429 cleanup. OUTPUT first overflow requires fresh-key replay and emits no API GAP. Three-window quota prose cannot delay these fences. |
| Runtime rejection | Successful decrypt followed by queue rejection consumes n and yields only rejected/INPUT_RATE_LIMITED; next legal n can continue if state remains healthy. Failed decrypt/no read authority produces no ACK; exit/state rejection follows exact terminal ordering. |
| Size layers | Generic codec boundaries 1/49,152 pass and 0/49,153 fail; active INPUT 16,384 and OUTPUT 32,768 pass, next byte fails at channel layer. Check ciphertext/tag/header arithmetic, total queue accounting and the two-max-OUTPUT pre-admission overflow. |
| Signed records | The three existing hashes/signatures stay exact; dash-form pin and altered domain/NUL fail. At trusted synthetic time test ACTIVE intervals and skew edges, signed revocations/import versus attachment use, supersession, rollback and atomic failure. |
| Signed numbers | Public test-key vectors for `2^53-1` accepted where lifecycle permits, `2^53` and `2^64-1` rejected before rounding, quoted/exponent/fraction variants rejected; wire decimal-string equality with the signed Number remains exact. Never use an unknown Owner key to manufacture replacement fixtures. |
| Trust provider | Missing/ambiguous/untrusted provider, time rollback, stale floor, API replacement, origin mismatch and partial rotation deny attachment. Mock-provider tests are explicitly distinct from real policy-store/host qualification. |

## 9. Accepted decision and remaining limits

The Coding Agent accepts the **complete supplemental contract** for software
implementation and verification under the Owner's explicit current-task decision
delegation. The decision covers the flat context/key schemas and ciphertext
field, separate verification authorities, ACK translation/rejection, immediate
ciphertext-drop behavior, layered limits, preserved signed pin literal and safe
signed-number range, together with the original three byte choices. Earlier
ordinary “continue” events, core/codec tests, review and routine merge were not
approval; the latest explicit delegation supplies the authority to decide.

Real host activation, production Runtime key custody/rotation, Provider Secret
handling, the concrete independent trust-provider deployment, publication and
production support claims remain separately authorized/evidenced. This document
does not rewrite historical root architecture, approve existing synthetic classes
as full wire, or mark the encrypted terminal delivered. Implementation status and
subsequent exact-head CI/merge evidence belong in
[CURRENT_STATE.md](CURRENT_STATE.md) and [REMAINING_PLAN.md](REMAINING_PLAN.md), under
[GOVERNANCE.md](GOVERNANCE.md).
