# Runtime encrypted attachment stream

R7 implements the Runtime side of the accepted
[application crypto](WAW_APPLICATION_CRYPTO.md), [wire](WAW_WIRE_CONTRACT.md)
and [staged admission](WAW_STAGED_ADMISSION.md) contracts. Its current status is
**in implementation/review**, not a deployed terminal or host qualification.
The [remaining plan](project/REMAINING_PLAN.md) tracks the separate R8–R12 work.

## Components and authority

| Component | Responsibility |
| --- | --- |
| `WAWEncryptedRegistry` | Runtime-only bounded prepare/capability authority, exact current peer/tuple/epoch binding, one-time burn and positive cleanup records |
| `WAWEncryptedSession` | Real Noise/AWCE endpoint, Runtime wire hops, ready/commit, encrypted input/output, ACK and terminal fences |
| `WAWEncryptedServer` | Bounded raw Unix stream reads/writes on the verified inherited listener; authenticated peer callback and timeout/worker lifecycle |
| `WAWEncryptedAttachmentService` | Fixed control prepare/detach integration; no arbitrary command/path or API Secret authority |
| Supervisor/executor/bootstrap | Shared exact workload and lease identity, same-lock rechecks and trusted deployment ports |

Runtime imports neither API admission classes nor API-only session/admin/origin
identity. `RuntimeAttachmentLease` binds the wire tuple, Runtime epoch, monotonic
expiry and a trusted current-authority predicate. Control and stream verification
must refer to the same authenticated process-lifetime identity; a PID number,
UID match or unqualified boolean is insufficient deployment evidence.

## Admission, data and cleanup rules

The random Runtime capability is consumed before accepting a matching hello.
It is never a browser ticket, deterministic tuple hash or generic PREPARED cache.
The actual Runtime crypto profile verifies browser confirmation. Ready and
commit repeat exact process/tuple/epoch/lease checks under the supervisor lock
through the required trusted transport; actual PTY readiness remains evidence
from the qualified adapter. Key readiness alone cannot publish output or grant an active writer.

Output is selected from bounded ring provenance before encryption. New PTY data
is split into at most 32 KiB chunks before cursor allocation. An old oversized
cursor-bearing record is rejected rather than silently split under its assigned
cursor. Normal detach/reconnect retains the eligible volatile ring; explicit
crypto/epoch/exit/Stop clearing preserves cursor-domain gap information. The
redraw port admits only a bounded 24-row, 60 KiB result from a qualified marked
pane capture, not a default whole-pane capture.

Input is decrypted once, then receives the appropriate accepted and terminal
written/uncertain/rejected result. Rejection after successful decryption retains
nonce continuity. A cached terminal ACK may be replayed at most once within its
original five-second lifetime, preserving its immutable input/crypto references
and result body while using the next fresh Runtime outer hop. No input resend,
nonterminal accepted-ACK duplicate or post-EXIT/CLOSE ACK is introduced. This
clarifies the historical ACK retry wording under delegated software authority;
it does not add a same-hop retry to the wire codec.

Cleanup requires fixed `close_attachment` evidence for the **same exact**
`RuntimeAttachmentLease` object, matching the full tuple/epoch/lease and proving
closed PTY plus zero remaining attachment members. The legacy boolean tmux
detach result cannot qualify an encrypted transport. Revocation may initiate
cleanup of the old exact lease, but cannot clear a replacement lease. Missing,
late or mismatched proof keeps ownership fenced.

## Transport and resource boundaries

The listener is an already verified, close-on-exec Unix stream descriptor.
Runtime does not bind/unlink a caller pathname. Raw socket reads request only
the remaining bounded header/payload bytes; there is no hidden StreamReader
read-ahead. Connection count, kernel buffers, frame assembly, admission and
write deadlines are bounded. Timed-out worker work remains observed and cannot
be treated as cancellation or successful cleanup.

Runtime independently checks its ten-second health fence and absolute lifetime.
API/browser thirty-second stale, sixty-second grace, fifteen-minute idle and
current HTTP authorization checks remain required R8 responsibilities. The
R6 authority slot expiry alone is not live input permission.

Each actual nonblocking socket write uses the same session permission lock and
rechecks after waiting for socket writability. A fixed trusted publication port
binds only that connection's send/shutdown operations. External detach/invalidate
shuts down its sending side before positive cleanup releases the reservation.
Internal terminal metadata may drain for at most one second while ownership is
retained; OUTPUT never receives that exception. Partial writes cannot be followed
by a newly generated complete failure frame.

The exact Runtime lease also owns a nonblocking publication invalidator. Entering
STOPPING fences its pending/active socket without acquiring the registry lock;
a stopped old lease cannot shut down the next generation. Unconfirmed socket
shutdown retains reconciliation state and prevents a successful process Stop
claim. These software rules are independently reviewed before final acceptance.

Failure handling is implemented and remains under independent review: a trustworthy
bound stream emits only the allowed fixed ERROR/CLOSE profile for its stage;
the first two Runtime hops permit ERROR then transport close. Only after
KEY_ATTEST has been completely published may ERROR be followed by CLOSE. Actual publication order
must remain continuous when a frame was constructed but never published. An
uncertain partial write cannot be retried as a fresh complete frame. Diagnostics
contain fixed codes and fresh correlation IDs, never exception payloads.

## Evidence and remaining qualification

The worker's initial new/related regression run passed 190 tests, including 42
new Runtime stream/server cases; scoped lint, format and Linux-target type checks
passed. The failure-profile repair passed 54 targeted tests; an additional six complete
four-leg traces exposed and corrected the early ERROR-only phase rule, yielding
60 stream/server cases. Independent review has since identified an expired-health
input permission gap and non-exit probe states incorrectly emitted as EXIT. These
have been repaired, along with preserving INPUT_UNCERTAIN and other workspace
faults after positive attachment cleanup. Subsequent actual UDS tests reproduced
and repaired sending an already-built OUTPUT after detach or exact Stop. The
latest worker regression command was:

```sh
.venv/bin/python -m pytest -q tests/unit/test_waw_encrypted_server.py tests/unit/test_waw_encrypted_stream.py tests/unit/test_waw_supervisor.py tests/unit/test_waw_runtime_executor.py
```

It exited 0 with 160 passed, including pending Stop, partial output interrupted
by a cross-thread Stop, old-lease/new-generation isolation and unconfirmed
shutdown. All ten R7 files passed scoped lint, format and Linux-target type
checks. Final review of the first draft head found a map/supervisor lock-order
inversion and a 2001-line retention error. The repaired Start transaction now
uses `supervisor → map`, holds the stopped old-generation state through final
map replacement and rechecks exact objects/binding/reservation/inflight/
generation. The ring counts LF-delimited lines plus one unterminated stream tail.

The worker's repaired complete R7 matrix passed 170 cases; 16 focused lock/state/
cancellation cases passed. The PTY suite passed 17 cases. All ten R7 files passed
scoped lint, format and Linux-target type checks. Independent re-review passed
10 deadlock/state tests plus all 17 PTY tests and reproduced both former failures
as closed. This is software evidence; exact-head CI/merge and host qualification
remain separate.

Local tests perform actual temporary Unix socket reads/writes. PTY, capture,
static-key and peer-provenance ports are explicitly synthetic. macOS does not
provide the target Linux listening-socket/provenance proof; the local listen
probe is a test substitution, and production fails closed without that proof.

R10/R12 still supply and qualify the actual fixed interactive PTY/capture
adapter, sole-API pidfd/unit provenance, inherited descriptors and Runtime key
custody. R8 connects the API relay, R9 the independent trust consumer and browser
terminal. No real CLI login, Runtime HOME access, key enrollment, host activation
or production support claim follows from this increment.
