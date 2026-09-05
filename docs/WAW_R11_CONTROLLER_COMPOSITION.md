# WAW R11 production integration contract

Status: accepted software implementation contract for R11/rc6–rc9. This document
does not activate a host, install a managed extension, handle a real credential,
or qualify a vendor CLI.

## Delivery order

R11 is delivered as four serial release-candidate increments:

1. `0.3.0rc6`: compose the production controller after closing process identity,
   authority transfer, durable epoch, redraw and singleton ownership gaps.
2. `0.3.0rc7`: run deterministic composed failure injection across admission,
   active stream, restart, shutdown, Stop and browser lifecycle boundaries.
3. `0.3.0rc8`: run artifact-only composition and upgrade/rollback rehearsals with
   synthetic external harnesses and exact provenance/read-back.
4. `0.3.0rc9`: migrate every user-facing route and state to the fixed document
   locale contract and complete desktop/mobile bilingual E2E and visual QA.

Each increment updates the visible version from one source, documentation and
GitHub; it must complete exact-head CI, normal merge and exact read-back before
the next increment is marked complete.

## rc6 current implementation checkpoint

PR #80 head `b2f0e0b...` is the verified remote baseline with 20/20 exact-head
checks `SUCCESS`. The current controller composition is uncommitted and therefore
is not represented by that baseline: it wires one `WAWPeerAuthority`, typed
control-dispatch peer context, authority-backed encrypted-stream verification,
lifecycle transfer/revocation and Runtime server shutdown ownership.

The final local core matrix completed 216 plus 5 focused cases; the independent
reviewer completed 244 cases with 1 Linux-only skip and 9 deselected, plus 8
encrypted-server non-UDS cases. Twenty-eight real-UDS cases remain unverified
because this execution environment returned `PermissionError` during socket
setup. Ruff, Black, Linux-target mypy (256 sources), documentation links (240),
and `git diff --check` pass. Independent Sol/xhigh review reports PASS with no
remaining P0/P1/P2. This paragraph does not claim a commit, exact-head CI result
or merge for the uncommitted integration.

The remaining rc6 order is commit/push, exact-head Linux CI including real UDS,
then the next controller slice. Normal merge and exact read-back occur only when
the complete rc6 acceptance set is satisfied. rc7–rc9 remain serial successors,
and R12 remains the separate real-host qualification boundary.

## rc6 composition invariants

- One API process owns one `AttachmentAuthority`, API authority epoch/nonce,
  bind coordinator, authorization policy, stream handler and process-lifetime
  singleton lock. Production rejects a worker/replica count other than one.
- Control and stream sockets bind the same live API process to the same live
  Runtime process through retained pidfd-backed identities. UID, GID or numeric
  PID alone is never sufficient.
- Runtime control, encrypted stream, legacy conflict coordinator, executor,
  registry and epoch come from one filesystem-v2 `WAWRuntimeApplication`.
- Browser state becomes `CONNECTED` only after independent trust is current,
  the local ACK canary is verified and exact `ADMITTED` is received. No terminal
  plaintext, renderer or keyboard is enabled earlier.
- Stop and Detach synchronously revoke new INPUT and RESIZE publication before
  awaiting cleanup. A late encrypt/send/resize callback cannot publish after the
  fence or compete with R10's final parser barrier.
- A production-enabled configuration with a missing anchor, key custody, peer
  authority, redraw capture or socket provenance fails startup. It does not fall
  back to an empty capture, fixed test key or synthetic trust provider.

## Runtime peer and API authority state

The first valid `BIND` retains a typed API process lease. A malformed or pre-bind
connection cannot reserve the singleton. Every control dispatch and stream peer
must match that exact live lease. A second live API process is rejected.

On the API side, the first control `BIND` retains one Runtime pidfd-backed peer;
all later control requests and stream sockets borrow that same object. A poisoned,
closed or terminal peer invalidates the cached attestation. Candidate pidfds are
closed on cancellation, protocol failure or failed attestation and are published
atomically with the verified attestation.

Connection borrows use `dup` of the retained pidfd and carry the exact parent
object/generation; they never reconstruct authority from a numeric PID. Client and
coordinator close publish a synchronous fence before awaiting locks, and an
unpublished candidate cannot cross that fence. A retired client may create one
fresh owner only after its close task completed successfully with no pending work.

An inherited systemd AF_UNIX listener carries the credentials of the process that
called `listen`. Before readiness, the Runtime process must explicitly call
`listen(fixed_backlog)` again on both inherited control and stream listeners so
client `SO_PEERCRED` identifies Runtime rather than systemd. API prefers
`SO_PEERPIDFD` when the kernel exposes it; the fallback closes the
`SO_PEERCRED → pidfd_open → response → still-current` window as far as supported
without inventing stronger responder proof. R12 records the real kernel path.

Listener startup and shutdown share one operation per phase. Control socket
ownership advances only through `RAW`, `IN_FLIGHT`, and `TRANSFERRED`; close may
directly close only a confirmed `RAW` descriptor, while an in-flight transfer is
poisoned and left to the eventual `AbstractServer` owner. Stream accept failure
poisons immediately, and a cancelled/failed close is sticky rather than later
reported as successful.

When the old API pidfd is terminal, Runtime may accept one new authority epoch
and nonce. It first revokes old capability, Session and INPUT publication,
preserves any incomplete cleanup fence, and only then publishes the new authority.
Delayed old frames, PID reuse and a new process presenting the old epoch fail.

Runtime represents an observed connection as a candidate or exact generation
lease and a bind as a single-use transfer plan. A terminal-authority transfer
invalidates the old generation before external revocation work. Failure after that
point permanently poisons the authority; it never restores old publication or
retries a detached FD number. Foreign-authority leases are rejected before locks,
and authority-scoped `RuntimePeer` views retain no connection borrow FD.

Runtime connection shutdown observes every cancelled worker. An unfinished
worker leaves a poisoned/incomplete result; it cannot be reported as clean.

## Durable Runtime epoch classification

`RuntimeHostInstallation.last_runtime_epoch` is canonical decimal `TEXT`, bounded
to unsigned 64-bit and updated inside `BEGIN IMMEDIATE`:

- same host/revision and same epoch: API restart; durable Workspace state remains;
- same host/revision and strictly greater epoch: Runtime restart; all nonterminal
  Workspace records become `UNKNOWN` with `reconciliation_required` and pending
  Stop operations become `RECONCILIATION_REQUIRED` atomically;
- lower, reused, malformed or host/revision-mismatched epoch: reject without
  changing state.

Bind-response loss, database commit failure and process-identity drift keep the
application unavailable. Readiness exposes only a bounded WAW availability code,
never an anchor path, nonce or PID.

API loads only the fixed public `api-host-anchor.v2.json`: root-to-parent traversal
uses held `O_DIRECTORY|O_NOFOLLOW` descriptors, every directory is root-owned and
not group/world writable, the final public directory is mode `0755`, and the leaf
is a single-link root-owned regular `0444` file. File and directory identities are
revalidated after the bounded read. The API never opens the Runtime-private
manifest, Runtime HOME or a Secret.

## Bounded redraw

Runtime captures from the exact marked tmux pane through the held tmux executable
and derived socket/session identity. The capture returns at most 24 rows and
60 KiB plus a one-bit `has_more` result obtained from row 25 and byte 60,001
sentinels. Sentinels are discarded and never enter output rings or Audit. The
operation uses one monotonic second and validates socket identity before and after.

Fresh redraw selection, output cursor allocation and the live-output baseline are
published under one supervisor owner. Timeout, wrong pane, socket replacement,
row overflow and byte overflow return explicit failure or `has_more`; no PATH
lookup or unbounded `capture-pane` is allowed.

## Browser controller

- Connect uses an exact same-origin WebSocket URL, subprotocol
  `agentbox-waw-v1`, `binaryType = "arraybuffer"`, no query and binary frames only.
- Ticket acquisition is followed by an independent trust lease and one shared
  five-second admission deadline for `WS_HELLO`, key exchange, confirmation and
  `ADMITTED`.
- Provider invalidation, selection/auth/controller epoch changes and unmount are
  rechecked after every await. Any ambiguity fences the channel.
- Incoming complete frames and browser outbound buffering have independent
  256 KiB limits. Ciphertext loss requires a fresh channel; no key continuation.
- OUTPUT decryption is serial. Reconnect cursor advances only after scheduler and
  renderer finish. Render failure closes the channel without advancing the cursor.
- One INPUT writer owns bounded plaintext staging. It records accepted,
  written/uncertain and terminal ACK states without retaining plaintext; it never
  automatically retries an uncertain input.
- Keyboard, IME and mobile input use a controlled nonpersistent surface. Multiline
  paste is visibly rejected. Resize is user-viewport-only, 8–240 by 1–200,
  five/second with burst five, one outstanding and latest-one coalescing.
- Rendering uses `textContent` and fixed classes only. URLs, links, title changes,
  clipboard, notifications and terminal device responses remain disabled.
- Clean reconnect may retain only fully rendered model/cursor state. Crypto,
  tokenizer carry and pending raw frames never cross attachments; an identity or
  safety failure clears the model.

## Shutdown and exact Stop

API lifespan shutdown stops new streams, fences and awaits active cleanup,
invalidates all authority, closes retained pidfds and the singleton lock, then
closes the database. Runtime shutdown stops admission, closes encrypted streams
and control, finishes the legacy owner last, and reports incomplete work.

Exact Stop first quiesces browser INPUT/RESIZE, attempts typed Detach and positive
cleanup, then sends generation-bound HTTP Stop. An input already accepted by the
kernel may be `written` or `uncertain`; the UI never claims vendor consumption.
`pagehide`, freeze, hidden and unmount fence publication immediately; foreground
recovery requires an explicit fresh reconnect.

## rc7 failure matrix

Tests use named checkpoints, manual promises, fake monotonic clocks and controlled
partial-write sockets. No production environment/query/global fault switch is
allowed. Coverage includes every ticket, PREPARED, key, ACK canary, COMMIT,
ADMITTED, INPUT/ACK, OUTPUT/render, GAP/redraw, resize, heartbeat, revoke,
provider-loss, API/Runtime restart, shutdown, page lifecycle and Stop boundary.

Every case proves: no early `CONNECTED`; no input retry; no continued key after
ciphertext loss; no post-EXIT ACK; one ticket burn; positive cleanup before writer
release; and no payload, key or ticket canary in SQLite sidecars, Audit/Jobs,
logs, browser storage, reports, artifacts or retained DOM/tasks.

## rc8 artifact and operations rehearsal

The release workflow compiles native helpers from the unpacked artifact source,
installs only its wheelhouse into a temporary environment and proves imported
modules come from that environment. A separate synthetic harness supplies test
key/peer/trust/PTY while the artifact's API/Runtime code, TCP RFC6455 and Unix
sockets execute attach, input, output, resize, detach and Stop.

Upgrade/rollback uses exact predecessor and candidate source SHAs, preserves
non-sensitive database/Project/Runtime-HOME/epoch canaries, and ends at the exact
predecessor version with database and receipt/journal integrity verified. This
does not modify installer `UNIT_NAMES`, enable WAW sockets or inherit earlier
real-host evidence.

## rc9 locale and UI contract

Only `navigator.languages[0]` is read once per document. A valid primary language
`zh` selects `zh-CN`; every other, missing or malformed value selects English.
Later list entries and `navigator.language` are ignored. Changing browser language
within the document does not hot-switch; reload creates the new document locale.

Typed catalogs cover common, auth, Dashboard, Codex, Claude, Workspace, Projects,
Doctor, Logs, Settings, errors and closed enums. English and Chinese key sets must
match at build time. Server prose and `ApiError.message` are not rendered directly;
known codes receive localized copy and exact code/request ID remain technical.

Protocol identifiers, AgentType, Audit actions, filenames, branches, repositories,
Git/GitHub, tmux, Claude and Codex remain English. User names and Project names are
untranslated Unicode data rather than ASCII-only technical values.

E2E covers every route, loading/empty/error/success/dialog state, 1280×800 and
390×844, no horizontal overflow and controls at least 44 px. Terminal tests keep
trace, video and screenshots disabled; visual QA uses explicit non-sensitive data.

## R12 boundary

R11 cannot qualify real systemd identities/sockets, Runtime key custody, canonical
manifest enrollment, signed CRX/trustd installation, vendor builds/accounts,
PTY/devpts/cgroup/namespace/seccomp/LSM, reboot, publication or support promises.
Those require the separately authorized R12 target and real evidence.
