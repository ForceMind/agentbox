# A3 independent content schema and pure codecs

Status: software candidate on 2026-10-04, based on #139 merge
`587fe8eabf7e5d5e4d3a561091ec00c3e9f40881`. This refines the
[patch content contract](WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md) after the
[Runtime-only staged selector](WORKBENCH_A3_STAGED_READER.md). It implements
only independent Python/Web typed data validation, exact-byte codecs, an
all-or-nothing page planner and a pure single-read transcript model.

**No encrypted channel is implemented or opened.** There is no Noise handshake,
key loader, CipherState, RPC, socket, API/Worker relay, Runtime resolver, browser
controller, UI, persistence or host operation in this slice. A passing codec is
not authenticated content, trusted admission or working encryption. Existing
metadata v1, WAW frames and deployed routes are unchanged.

## Dedicated context and domain separation

Protocol ID is exactly `agentbox-a3-content/v1`, `protocol_version` is literal
integer `1`. The exact flat `ContentContext` fields are:

- `protocol_id`, `protocol_version`
- `project_id`: `prj_` plus 32 lowercase hexadecimal digits
- `project_revision`, `binding_revision`: positive canonical decimal uint64 strings
- `binding_digest`: 32 bytes in lowercase hexadecimal
- `runtime_host_installation_id`: `wri_` plus 32 lowercase hexadecimal digits
- `runtime_host_installation_revision`, `runtime_epoch`: positive decimal uint64 strings
- `session_scope`: 32-byte, noncredential, trusted API session scope, hex encoded
- `selector_commitment`: SHA-256 of ASCII `agentbox-a3-content/selector/v1`, one
  NUL byte, then the exact 156-character opaque selector's ASCII bytes
- `side`: exactly `staged`
- `request_nonce`: 32 bytes in lowercase hexadecimal

No path/relative key, arbitrary file ID, WAW Workspace/Agent identity or terminal
lease is admitted. The full internal binding includes `relative_key`; the
trusted resolver must verify its canonical binding digest against that full
current binding. A caller-supplied digest is not proof of a mapping.

`context_bytes` / `contextBytes` returns RFC8785 canonical UTF-8 JSON of this
complete context. Those exact bytes are the future dedicated Noise NX prologue.
`context_digest` is SHA-256 of those bytes. Existing reviewed uint64/hex helpers
and Web exact-data-property validation are reused; no new crypto algorithm or
configurable crypto suite is introduced.

The future application AAD is canonical flat JSON with exactly:
`domain="agentbox-a3-content/aad/v1"`, `context_digest`, `transcript_hash`
(full final 32-byte Noise handshake hash, lowercase hex), `kind`, `sequence`,
and `direction`. READ is `browser-to-runtime`; PAGE/END/ERROR are
`runtime-to-browser`. READ/ERROR use sequence zero, PAGE 0..15, END 1..16.
The exact kind is included even when numeric sequence values coincide.

These functions **define bytes only**. The later crypto profile must own a
fresh separately admitted Noise NX handshake and fresh directional CipherStates,
verify the independently trusted Runtime pin, specify its own confirmation
messages/domain/nonces and transport record authentication, and prove all of
that with crypto vectors. It must never pass this context through the WAW
application profile, use WAW INPUT/OUTPUT/AWCE framing or reset/reuse a WAW
CipherState. Page sequence is not a Noise nonce or permission to choose one.
A transport-envelope/key-exchange schema is deliberately not introduced here.

## Canonical wire and bounded parser

The message bytes in this slice are **future authenticated plaintext**, never
an API-visible JSON request/response. Each is a single canonical flat JSON
object. Keys are sorted; whitespace, escapes, duplicate keys, extra/missing
fields, nested containers, null, negative/float/exponent number spellings,
noncanonical base64url, invalid UTF-8 and unsupported versions are rejected.
All schema strings are ASCII; arbitrary UTF-8 patch bytes are unpadded canonical
base64url inside `data`. The narrow ASCII grammar is checked before JSON parse,
so nesting cannot enter the parser. Input length is checked first, key count is
at most 16, and only exact finite bounded scalar types survive validation.
Unknown values never appear in error messages.

The context and READ/END/ERROR are at most 4,096 bytes. Every complete PAGE
record, including all metadata and encoded content, is at most **16,384 bytes**.
No unbounded stream buffer, recursive parser, decompression or partial frame
accumulator exists. A future transport must enforce its own bounded ciphertext
length (including AEAD overhead) before allocating/decoding plaintext.

Every message has `protocol_id`, `protocol_version`, `context_digest`,
`request_nonce`, and `kind`, plus exactly the following:

| Kind | Additional fields | Meaning |
| --- | --- | --- |
| `PATCH_READ` | `selection_id` | One exact opaque 156-character internal selector, no path |
| `PATCH_PAGE` | `sequence`, `total_bytes`, `patch_digest`, `observed_at_ms`, `complete=false`, `data` | Sequence 0..15; nonempty content bytes |
| `PATCH_END` | `sequence`, `total_bytes`, `patch_digest`, `observed_at_ms`, `complete=true` | Sequence equals the number of pages, 1..16 |
| `PATCH_ERROR` | `code` | Fixed closed failure code, no free-form detail or patch |

`total_bytes` is the entire raw UTF-8 patch size, 1..262144, not JSON length or
page size. `patch_digest` is SHA-256 of the concatenated raw bytes.
`observed_at_ms` is a positive decimal uint64 Unix-millisecond observation time
chosen by Runtime after its stable reader observation; it is descriptive, not
a grant, trusted wall-clock proof or substitute for monotonic expiry. All PAGE
and END description fields must match exactly. Pages may split a UTF-8 character;
only complete concatenation is decoded. Line counting matches Python
`str.splitlines` including CRLF and Unicode line separators, with a 4096-line cap.

The closed errors preserve existing staged-reader codes: `PATCH_STALE`,
`PATCH_TIMEOUT`, `PATCH_TOO_LARGE`, `PATCH_UNAVAILABLE_BINARY`,
`PATCH_UNAVAILABLE_BUSY`, `PATCH_UNAVAILABLE_CONFIG`, `PATCH_UNAVAILABLE_ENCODING`,
`PATCH_UNAVAILABLE_GIT`, `PATCH_UNAVAILABLE_KIND`, `PATCH_UNAVAILABLE_MODE`,
`PATCH_UNAVAILABLE_PATH`, `PATCH_UNAVAILABLE_REPOSITORY`,
`PATCH_UNAVAILABLE_SENSITIVE_PATH`, `PATCH_UNAVAILABLE_STATUS`, plus
`PATCH_REVOKED` for future trusted admission loss. Malformed schema/transcript
causes local `PATCH_PROTOCOL_INVALID`, not a reflection of malformed content.

## Exact capacity and all-or-nothing delivery

The reader's 256 KiB is an **extraction ceiling**, not a promise every maximum
reader result fits the encrypted delivery protocol. The whole PAGE plaintext
budget remains 16 KiB; it has not been reinterpreted as a payload-only budget.

`prepare_pages` / `preparePages` validates the entire patch, computes the exact
canonical metadata overhead with sequence `15`, and reserves that maximum
sequence width for all pages. Raw capacity per page is
`floor((16384 - overhead) * 6 / 8)` for unpadded base64url. It computes page count
before constructing/returning any PAGE, rejects more than 16 with
`PATCH_TOO_LARGE`, then validates every encoded record and the final END.

The fixed vector's 13-digit observation time and six-digit total size give
425 bytes of metadata overhead, 11,969 raw bytes/page, and 191,504 raw bytes
across 16 pages. Exact-capacity two-digit-sequence pages are 16,384 bytes;
191,505 raw bytes is TOO_LARGE under those same fields. Other valid time/size
widths change the effective capacity; it is computed, not a global constant.
Tests cover exact acceptance/rejection and UTF-8/line limits. No truncation,
`complete=false` preview result, empty substitute or successful partial result
is exposed. Encoded PAGE plaintext across a read is at most 262144 bytes;
READ plus terminal control add at most 8192. Retained raw patch is separately
bounded to 262144; Python/JS allocation and hash copies are not zeroization or
a hard process RSS guarantee.

## Single-read ordering, fences and authority still required

`ContentRead` is a pure transcript checker:

1. Construct with independently expected context and a caller-supplied monotonic
   millisecond time/deadline, at most 30,000 ms apart.
2. Accept exactly one READ whose nonce/context/selector commitment matches.
3. Accept zero-based consecutive PAGEs only. No PAGE returns content to the caller.
4. Accept one END only after at least one page, matching page count, exact total,
   all metadata and digest. Validate complete UTF-8 and line count, then return
   complete bytes once and permanently close.
5. ERROR, replay, gap, changed metadata, bad hash/encoding, regression, exact
   deadline (`now >= deadline`), current-context mismatch or explicit close
   permanently closes and drops the held page references. A retry on that
   instance cannot recover it. No automatic read retry exists.

The Web checker fences concurrent accepts and checks close after every pending
hash; a close/deadline notification during an await prevents publication. Both
implementations require their owner to call `check` during idle periods, pass
fresh trusted context/time on every operation, and recheck authority/deadline
immediately before actual encrypted send or browser publication. They do not
run timers, resolve session/READY state or obtain trusted time themselves.
Dropping Python references/JS arrays does not promise memory zeroization.

The future production owner MUST provide and prove all of the following:

- API session authentication and active authorization, exact Origin, trusted
  client/pin/currentness, revocation and admission lifetime; opaque-only relay
- Runtime's CURRENT READY formal Project/full binding, host revision/epoch and
  active noncredential session scope, from one trusted resolver, not browser data
- Selector same-held-view validation/read under the already implemented TTL,
  epoch, full snapshot and path-policy constraints; selector is not authority
- Fresh CSPRNG request nonce, atomic one-shot admission consumption/replay
  rejection across channels, and no reuse of selector/nonce after close or retry
- Deadline bounded by the original selector/admission expiry and rechecks before
  read, every send and final publication; timer-driven idle closure
- Fail-closed propagation for pin/binding/Project/session/epoch change, revocation,
  document visibility loss, tab close/unmount, disconnect, cancellation, transport
  loss/gap or uncertain delivery/ACK; erase the volatile patch view, never replay
- No content in API/Worker plaintext, Audit/logs/database/analytics/cache/Service
  Worker, and no prefetch; later UI requires an explicit deliberate read action

The checker prevents replay **within one instance**; it is not a global nonce
ledger. Syntactically valid context, caller `current_context`, fixture resolvers
or matching commitments cannot provide any of these production authorities.
There is no ACK/resume protocol in these four plaintext types. A later transport
must resolve delivery uncertainty by closing, not invent an ACK or reuse WAW ACK.

## Evidence and next gate

Both implementations consume the same [literal codec fixture](../tests/fixtures/a3_content/v1.json)
and [provenance note](../tests/fixtures/a3_content/NOTICE.md). Focused tests and
`node scripts/check-a3-content-interop.mjs` compare exact context/AAD/message
bytes, both directions' encoding and shared malformed vectors, plus sizes,
sequence/replay/nonce/currentness/deadline/digest/line fences. These are software
codec/transcript tests, not Noise interoperability or production transport tests.

The next independent slice is the dedicated reviewed crypto-profile and
admission/transport composition contract, followed by implementation and crypto
vectors. Production resolver/relay, deliberate diff UI, Files/unstaged, actual
host/physical clients and release acceptance remain separate unimplemented or
NOT RUN gates. No enabled feature flag, production route or support claim follows
from this slice's merge.
