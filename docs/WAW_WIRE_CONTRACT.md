# WAW full wire profiles

R5 implements the closed direction-specific schemas, framing and observed
four-leg transcript rules from the historical architecture and
[accepted supplement](project/WAW_ENCRYPTED_STREAM_DECISION.md). It handles
metadata and opaque ciphertext; it neither decrypts a channel nor grants a lease.

## API and scope

Python `agentbox_protocol.waw_wire` and Web `features/workspace/wawWire.ts`
provide `Leg`, frame types, payload validation, encode/decode/forward helpers,
redacted `WireFrame` values and `WireSession`. There are 27 frame types and 50
allowed direction/type profiles across browser→API, API→browser, API→Runtime
and Runtime→API. Other combinations are rejected.

Control payloads are exact RFC 8259 objects with closed fields and conditional
result/reason rules. Parsing enforces the 4 KiB control limit, depth/key limits,
UTF-8 and duplicate/escaped-duplicate rejection, with no trailing bytes or
non-finite numeric extensions. The existing 24-byte ABWS codec is reused in
Python; Web uses the same binary layout and fixed public bounds.

Every uint64-domain JSON value remains a canonical decimal string. Raw
`protocol_version` and `crypto_envelope_version` tokens must be literal `1`.
Other explicitly bounded JSON Number integers are checked by exact decimal
arithmetic: `2.4e1` can represent 24, while rounding a non-integer into an integer
is rejected. Huge exponents are bounded without decimal-context overflow or
unbounded powers. Timestamp syntax remains exact ASCII UTC with six fractional
digits and valid Gregorian calendar/time fields.

Key JSON forwarding preserves the original bytes, including legal whitespace
and key order. INPUT/OUTPUT validate only AWCE framing, direction and active
size limits; their ciphertext is opaque. The forward helper is limited to these
key/opaque profiles and changes only the outer hop header. Other metadata
translations require an explicit owning coordinator and are not generic relay.

## Observed transcript and failure rules

`WireSession` is an API-side observer because it sees all four legs. Browser and
Runtime endpoints instead use the directional codecs and their own controllers.
The constructor binds an independently supplied AdmissionTuple, Runtime epoch,
private connection token and original monotonic start time. Times are integer
nanoseconds; each leg begins at hop 1 and stays contiguous.

- The fixed handshake prerequisites and equal echoes are checked before normal
  data. Observed `committed`/`admitted` flags prove only the corresponding metadata
  frames were observed; they do not prove durable Audit, browser canary checking,
  active authority or queue publication.
- The specific WAIT_HELLO_ACK/WAIT_KEY_ATTEST failure rule takes precedence over
  general failure prose: only the expected ERROR followed by native transport
  close is allowed there. Browser phase depends on the browser's observed
  KEY_ATTEST, not merely an internal Runtime frame awaiting relay.
- After KEY_ATTEST, only the defined context-bound negative STATE/ERROR and
  CLOSE profiles may interrupt admission. RUNNING STATE cannot masquerade as
  admission failure or reopen a failed/exited trace. Active NEEDS_INTERACTION is
  metadata; input eligibility remains an owning lease/process decision.
- ADMISSION_COMMIT and its cached ACK permit one exact same-stream, original-hop,
  byte-identical retry within the original five seconds. Internal DETACH permits
  one identical request retry while its terminal ACK has not been observed and
  its original cleanup window remains open. No DETACH_ACK duplicate exception is
  invented; a completed cleanup request cannot be retried as a new operation.
- Key relay and opaque INPUT/OUTPUT must have an observed source and unchanged
  payload. Opaque witnesses are FIFO: input ≤64 KiB/256 entries, output ≤64 KiB
  before ADMITTED and ≤256 KiB afterward, also at most 256 entries. These are
  bounded transcript copies, not a network queue or an ACK-lifecycle map.
- Python serializes acceptance, close and public state with an `RLock`; two
  threads cannot both consume the same hop. Web is a synchronous single-JavaScript-
  thread object, not shared memory across workers. Failure closes the observer
  and clears pending witnesses.

These implementation decisions were made under the Owner's explicit software
decision delegation and reviewed independently. They preserve the real
authority, cryptography and cleanup requirements in the remaining plan.

## Parser budget and measured correction

Python uses per-thread CPU time for the unchanged 5 ms validation budget. Web
uses `performance.now()` elapsed time because browser thread-CPU measurement is
unavailable; scheduling/GC can therefore cause conservative rejection. Structural
tests with a controlled clock are distinct from actual-clock budget evidence.

Integration initially exposed valid-frame rejection: the Python parser created a
dataclass inside every decode, causing cyclic garbage and expensive collection;
the first timestamp also lazily imported `_strptime`. The token type is now one
module-level immutable slotted type, and calendar validation directly constructs
`datetime` after the unchanged strict lexical check. No GC setting or budget was
relaxed, and no warmup is needed for the first valid ADMITTED frame.

With the same local workload, cold ADMITTED changed from 5/5 failures at
12.405–17.304 ms to 5/5 passes at 0.517–1.176 ms. A 5,000-decode mix changed from
one failure/P95 0.876 ms to zero failures/P95 0.191 ms. Independent review measured
six fresh-process successes at 0.594–1.141 ms, and another 5,000 calls with no
rejection, P95 0.185 ms, maximum 1.430 ms. Injected >6 ms CPU work still failed.
These are local measurements, not a guarantee for every deployment.

## Validation and remaining integration

- Frozen schema/FSM suites: Python 279 cases (including three cold/stress cases)
  and Web 274 cases. Independent review covered schema, source pairing, exact
  capacities, numeric/calendar boundaries and concurrency; final result PASS.
- Combined R6/API/ticket/wire regression: 496 passed after the performance fix.
  Earlier budget failures are retained as resolved evidence, not hidden passes.
- `check-waw-wire-interop.mjs`: both-language encode/decode and immutable relay
  across all 50 profiles, shared malformed-input negatives, four actual-clock
  probes and a separately labelled controlled-clock structural matrix. Peer
  requests use a bounded reader and fixed operation/request/response limits.
- Scoped type/lint/format and documentation checks passed. Exact-head CI/merge
  evidence is maintained in CURRENT_STATE. This slice changes no visible UI.

Actual network ownership/queues, ACK correlation and terminal progression, PING
tracking, rate limits, authentication watchers, lease freshness and durable Audit
remain R6–R8 responsibilities. A passing wire observer must not be used as an
authorization substitute or proof of a connected terminal.
