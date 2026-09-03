# WAW staged admission

R6 composes ticket authority, the accepted wire protocol, fixed asynchronous
ports, durable metadata ordering and bounded publication. It does not decrypt
frames, open sockets, launch a CLI or by itself enable the WebSocket route.
See [the accepted contract](project/WAW_ENCRYPTED_STREAM_DECISION.md) and
[remaining plan](project/REMAINING_PLAN.md) for the complete product scope.

## Authority and publication

`AttachmentAuthority` retains the existing lock/capacity domains and adds explicit
staged reservation, ordered advancement, publication, fencing and exact cleanup
acknowledgement. Its old `consume` path remains for synthetic compatibility;
the real coordinator uses the staged path.

A syntax-valid WS_HELLO first reaches the authority's atomic bearer lookup/burn.
The authority then compares the complete presented tuple/epoch and current
API-only authorization context to the stored ticket and expected claims. A known
bearer with a validly shaped mismatch is consumed and rejected as
`ATTACHMENT_STALE`/4403; it cannot survive for a second guess. Malformed frames
retain their syntax-failure result. No Runtime prepare occurs after rejection.

`WAWAdmissionCoordinator.run()` executes the full sequence through fixed ports:

1. Reserve/burn the ticket and receive the exact key initiation.
2. Prepare the exact Runtime attachment and relay the unchanged key frames.
3. After positive Runtime confirmation metadata, persist PREPARED Audit, then
   exchange STREAM_READY/ACK on the same bound Runtime connection.
4. Build a quarantined ADMITTED frame; exchange COMMIT/ACK with the one permitted
   byte-identical same-connection retry inside the original admission deadline.
5. Persist ADMITTED Audit, stop and await admission readers, recheck the current
   authorization/failure/deadline conditions, then atomically publish ACTIVE and
   release the quarantined queue.

Runtime confirmation metadata is not browser canary verification. The API owns
no channel key; the browser must independently verify its ACK and admission gate.
All awaits share the original five-second monotonic admission deadline. Current
Session, scope, workspace and epoch checks are supplied by a synchronous trusted
revalidator, not a cached comparison of the initial parameters.

## Closed ports and queues

The Runtime port supports only prepare, send/receive fixed wire frames, exact
close-and-cleanup and abort. Prepared/cleanup records bind the exact claims,
Runtime epoch and private connection identity; capability-bearing records are
redacted. A port is a trusted adapter, not a caller-selectable command/path API.
The browser port supplies bounded complete ABWS messages and key-frame delivery;
native WebSocket policy is enforced below it by R8.

The shared pending-handshake budget is at most 128 with at most eight per trusted
source. Core record/writer/admin caps remain 64/32/4. Production composition must
share the pending budget across its authority, not construct one per request.

The quarantine is at most 64 KiB including the complete ADMITTED frame, every
header, OUTPUT and GAP. Readers cannot observe data before publication; ADMITTED
precedes output. Each read verifies the exact active authority binding. Overflow,
revocation and failed publication discard the quarantine. Reader cancellation is
acknowledged before successful handoff, so the next owner can call receive
immediately without racing a previous reader or requiring an extra event-loop tick.

## Failure and cleanup

Fencing stops publication immediately. A late or cancellation-resistant port
operation cannot produce a later successful admission. Unfinished work or missing
cleanup proof retains the exact fenced reservation; elapsed time alone does not
free the writer slot. A cleanup proof from a different connection, epoch or tuple
is rejected.

The cleanup operation and required DETACHED failure Audit are handled independently
within the original one-second cleanup bound. A Runtime exception/cancellation/
timeout cannot silently skip a healthy Audit sink. Missing proof or unsuccessful
required Audit keeps the workspace fenced. Both staged and legacy known-cleanup
fences reject new ticket issuance for that workspace; exact cleanup can restore
issuance, while unrelated workspaces remain available.

PREPARED/ADMITTED/DETACHED events contain only their fixed identifiers, generation,
epochs and normalized reason. Tickets, capabilities, admission fences, context
hashes, terminal data and raw adapter errors are excluded.

## Verification and remaining active lifecycle

Independent sol review reproduced and verified all four fixes: burn-before-bound
comparison, awaited reader handoff, issue-time cleanup fencing and failure Audit
after Runtime cleanup exceptions. The frozen new suites passed 135 cases; the
worker's relevant API/ticket regressions passed, and the combined R6/wire gate
passed 496 cases after the independent R5 parser-performance correction. Additional
reviewer reproduction, async Audit and exact-capacity negatives passed.

These tests use actual authority/coordinator/wire code with explicitly synthetic
ports and metadata. They do not prove Runtime cryptography, host cleanup, native
WebSocket behavior or a real durable Audit backend. R7/R8 supply those adapters.

Configured authority expiry is not the complete active lease policy. R7/R8 must
integrate the existing 30-second browser-heartbeat stale input/control fence,
60-second grace with positive cleanup, 15-minute idle and eight-hour absolute
limits, plus ten-second Runtime health and current-auth watchers. Neither
`ActiveAttachment` nor `queue.read()` alone is an INPUT/control permit. Actual
network queues, ACK/PING lifecycle and failed-attempt rate limits also remain
required integration work.
