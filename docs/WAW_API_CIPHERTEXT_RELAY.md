# API ciphertext relay

R8 composes the actual [staged coordinator](WAW_STAGED_ADMISSION.md), native
WebSocket transport and Runtime Unix stream adapter. Status: **implemented and
independently reviewed PASS locally; exact-head CI/merge remain pending**. It is not production activation;
the [remaining plan](project/REMAINING_PLAN.md) retains R9–R12 qualification.

## Native transport and deployment inputs

`WAWWebSocketProtocol` is an explicit Uvicorn protocol implementation using the
existing bounded RFC 6455 parser. The ASGI route requires its qualified scope
marker and an explicitly configured `WAWStreamHandler`/Runtime factory. The
default absent handler remains unavailable. No new WebSocket dependency,
arbitrary target URL or generic shell/filesystem endpoint is introduced.

Masking, RSV bits, binary messages, control-frame size, fragmented-message
assembly and native PING/PONG budgets are enforced before ASGI delivery. Upgrade
headers and the first application message retain their fixed ceilings; the
protocol is exactly `agentbox-waw-v1`. Authentication uses the original native
peer/TLS observations, not an ASGI scope rewritten by proxy middleware.

Under delegated software authority, an extension **offer** is distinguished
from negotiated use: standard Chromium offers `permessage-deflate` without a
JavaScript switch to suppress that offer. The server declines negotiation,
returns no extension response and rejects RSV/compressed frames. It does not
claim that the browser omitted its offer or enable an extension implementation.

The Runtime adapter uses the fixed authenticated control/stream paths, exact
connection and tuple identity, bounded raw reads and a cancellation-safe single
reader handoff. A partially consumed header remains with the same connection;
it cannot disappear when admission hands ownership to the active relay.

## Authority, queues and terminal delivery

API handles only validated metadata and opaque key/ciphertext payloads. It does
not obtain Noise state, Runtime static keys, plaintext INPUT/OUTPUT, Runtime
HOME or Provider Secrets. It relays original key JSON bytes and immutable AWCE
payloads while translating outer hops and the bounded input ACK references.

Every live permission is separate from the R6 slot TTL: current cookie/DB scope
and epochs, thirty-second stale/sixty-second grace, fifteen-minute idle,
eight-hour absolute lifetime and Runtime health remain enforced. Exact cleanup
and durable fixed Audit records govern release; timeout/cancellation is not
positive cleanup proof.

The browser output queue has independent 192 KiB data and 64 KiB control lanes.
The input queue is capped at 64 KiB encoded bytes. Dropping any ciphertext
fences the channel; there is no synthetic numeric GAP, ACK or continuation under
the same CipherState. Runtime-generated GAP metadata retains its own provenance.
Terminal queue draining cannot bypass current authorization or expiry checks;
the reviewed publication guard enforces the check at the actual send boundary.

Terminal ACK replay preserves the input/crypto references and terminal result
body, at most once in the original five-second cache, with a fresh outer hop.
An accepted/nonterminal ACK cannot be replayed. Browser input is never resent.

The sole nonfatal wire ERROR is an already-ADMITTED API→browser
`CONTROL_RATE_LIMITED` with `retryable=true`, used for the owning relay's bounded
RESIZE/HEARTBEAT/PING decisions. All pre-admission, Runtime-originated and other
ERROR combinations remain fatal. INPUT/OUTPUT quota loss still fences; the
exception cannot make a dropped ciphertext recoverable.

## Admission failure translation

The integration repair translates only Runtime negative metadata already
accepted by the complete wire observer. Reservation fencing and quarantine
discard happen first. Runtime ERROR result fields are retained but its
correlation ID is replaced by a fresh API-generated browser-leg ID. A separate
browser completed-write frontier determines
which negative profile may be published: before KEY_ATTEST, ERROR and native
close only; afterward, validated negative STATE or ERROR and CLOSE. A rejected
commit yields fixed failure metadata without ever releasing ADMITTED.

Incomplete, cancelled or uncertain prior browser writes allow only native
close; allocated hops are not mistaken for published bytes. Notification is
best effort within 100 ms, the original five-second admission deadline and the
same one-second cleanup deadline. Its failure cannot skip Runtime cleanup or
the mandatory detached Audit. Missing current authorization suppresses it.
The retained negative frame is bounded metadata, not a payload queue.

## Verification boundary

The initial worker matrix passed 482 tests, with a final 62 native/relay subset,
275 Web wire tests, the 50-profile cross-language check and Linux-target mypy
over 222 files. Tests use real temporary TCP, Uvicorn upgrades and Unix streams,
plus explicitly synthetic peer/PTY/key provisioning. These numbers precede the
independent terminal-drain repair and are not final acceptance.

The new coordinator failure tests cover all admission phases, invalid metadata,
revocation, uncertain key writes, notification timeout/cancellation and retained
cleanup fencing. Its final 17 local cases passed. Independent review found and
closed Runtime correlation-ID forwarding and missing revalidation between
ERROR/STATE and CLOSE; the reviewer ran 26 focused coordinator/wire cases and
replayed the original revocation failure successfully. Native shared parser
allocation and immediate first-ciphertext-drop fencing are implemented. The
latest related matrix passed 505 cases; scoped lint/format and Linux-target mypy
over 223 files passed. Global parser accounting reserves retained array capacity,
temporary copies and growth before allocation; mixed active/pending use of all
128 slots, rejection of the 129th and exact release are tested.

One ownership token now carries each encoded INPUT through native-ready,
browser-delivery, relay-pending and Runtime-send-inflight; transitions never
release/reacquire capacity. The exact 65536-byte boundary passes, while 65537
and the former 65872-byte split-queue trace synchronously fence before new copy,
hop, map, ACK or forward. The expanded matrix passed 604 cases; full lint/format
and Linux-target mypy over 224 files passed.

Final independent review found and closed two additional cleanup faults. Relay
and admission cleanup now share one cancellation-resistant task, retain the first
`authority.fence` error, still attempt Runtime cleanup, detached Audit and every
transport/budget/wire close, and release the authority record only after exact
positive proof. A CLOSE-frame encoding failure now passes `close_frame=None` to
the fixed Runtime cleanup instead of skipping it. The final reviewer reran 12
directed cases, 126 admission unit cases and 69 sandbox-compatible relay cases
and reported PASS. Main-agent validation then passed 539 R8 Python cases, 832 Web
cases, the 50-profile Python/Web wire interop check, Ruff, Black over 232 files,
Linux-target mypy over 224 files, the production Web build and all 62 isolated
Chromium E2E cases. Desktop and 390x844 mobile visual read-back showed
`0.3.0rc3` without horizontal overflow or overlap. Exact-head CI and merge
evidence remain pending and belong in CURRENT_STATE only after observation.
Browser trust/terminal interaction, real CLI execution, Linux identity/isolation
and production deployment remain separate requirements.
