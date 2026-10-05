# A3 native Changes transport and HTTPS bootstrap

Status: accepted bounded software contract, 2026-10-05. Independent contract
review and parent software-design approval precede implementation; implementation
source review, final ec89d73 cross-process/browser CI and actual pixel review
have passed. PR #144 merged as 3e313b3 with the same tree; all six exact-main
workflows passed. Historical pending/failure records below remain historical.
Baseline #143 merge
`61a5efce6ab43754a2acdb313d5e21ee83f64c52`, tree
`ec1ca86988ea4e84e7aa1d818e5d85a4b967cf08`.

## Scope and retained authorities

This single software candidate connects actual separate API and Runtime
processes, the formal App Changes route, the existing staged selector owner and
A3 crypto v2. It supplies native transport consumers and a purpose-specific
HTTPS public-bootstrap consumer. Unconfigured installation remains unavailable.
There is no production key loader, pin enrollment, installer activation, real
host listener deployment, actual account operation, release or support claim.
CI temporary listeners and published synthetic keys are software evidence only.

The sole existing Runtime API-peer/lifecycle, formal Project binding, selector
key, four operation slots and 128 burned-nonce ledger remain authoritative. No
second Project registry, selector owner, nonce ledger or renewable authorization
lease is added. WAW keys, pins, bootstrap schema, ABWS/application frames,
CipherStates and ciphertext are never accepted as A3 fallbacks.

## Fresh bounded native bundles

Every explicit OBSERVE or OPEN obtains a fresh bundle of three already-connected,
close-on-exec AF_UNIX stream descriptors: command, opaque records, currentness.
Trusted composition supplies the connector; browser input cannot select an
address, path, file descriptor or transport. Product consumers never bind/unlink
listeners or spawn Runtime. Loss has no reconnect, retry or resume. A later
explicit user read is a new bundle, fresh nonce and fresh A3 crypto instance.

Every descriptor is checked using SO_PEERCRED plus a retained live pidfd and
matched to the same existing API/Runtime process generation/authority. UID or PID
alone does not confer authority. Distinct numeric descriptors and distinct socket device/inode identities are
required; duplicated aliases are not three streams. All three role handshakes bind the same fresh
128-bit bundle ID and SHA256 of the exact complete admission facts. Mismatched
roles, duplicate roles, bundle mixing, stale peer generation or callback ownership
permanently close the bundle. API credentials/session IDs never cross UDS.

Composition admits at most four bundles, including incomplete handshakes and
metadata-only operations, before allocating a thread/task. There is no waiter
queue. At most 12 connected descriptors, four Runtime command-reader threads and
four API currentness-reader threads are attributable to this owner. Its connector
must count partially assembled descriptors against that same cap. CI acceptors
are bounded and connect only after both processes exist; socketpair created
before fork cannot prove the child's SO_PEERCRED identity.

Native framing is A3-only: 4-byte magic `A3N1`, one-byte fixed kind, uint32be
sequence, uint32be payload length, then exact payload. No flags/extensions or
trailing bytes. Command/currentness JSON is canonical sorted ASCII JSON without
whitespace, duplicate/unknown fields or numeric coercion. Maximum command/reply
payload is 8 KiB; complete metadata response is at most 2 MiB; each opaque crypto
record is 1..24 KiB. Length is rejected before body allocation. Linux socket buffers request32KiB
and reject an observed effective buffer above64KiB in either direction. Sequence starts
at one per direction, increases exactly once, and cannot wrap or be replayed.

Closed message families are bundle role hello/ack; OBSERVE/full facts and its
metadata response; OPEN/full facts/selection ID/nonce and owned-task ACK;
PUBLISH_CHECK/record sequence/SHA256 and one-use OK; PUBLISHED/identical record
sequence/SHA256 and ACK; CURRENT/full-facts digest/challenge and boolean reply;
opaque RECORD; fixed ERROR code; COMPLETE; and CLOSE. Each role has an exact
allowlist. No caller-selected path, revision selector, arbitrary action/command or patch plaintext
can be represented. Metadata entries retain the existing dedicated schema.

A phase has one absolute monotonic deadline, never reset per partial read/write:
connection/role handshake <=1 s; OBSERVE <=5 s; OPEN task-ownership ACK <=1 s;
currentness and publication-check RPC <=250 ms; each opaque partial record/write
or browser-consumption ACK <=1 s. All are additionally capped by the original
selector deadline once admitted. Original <=30 s Runtime expiry and <=5 s crypto
handshake deadline are unchanged. Partial I/O failure, cancellation, timeout,
ambiguous delivery, extra input or broken sequence closes without retry.

## Currentness and actual publication

Each bundle is bound to one freshly authenticated API A3SessionCurrentness and
its complete original A3CurrentAdmission. A dedicated checker thread answers
only that bundle's exact challenge and facts digest, freshly reading the existing
DB session, active user, READY Project, unique current binding, host/Runtime epoch
and auth epoch on EVERY request. No positive reply is cached as authorization.
The API checker never calls the API event loop or Runtime owner loop.

One shared Runtime selector owner resolves currentness through a ContextVar whose
default is unavailable. Every operation installs its exact bundle callback and
resets the context in finally; its serve task inherits that context. Every remote
publication guard dispatch explicitly reinstalls the same context. No global
"most recently current" facts or adapter lookup substitutes another operation.
Runtime still independently compares existing binding/lifecycle/peer state.

The Runtime command-reader thread dispatches at most one command to the Runtime
owner event loop. Only that event loop touches selector/admitted handles and
crypto state. OPEN acknowledges an owned serve task before doing long Git/crypto
work, leaving the command channel available for publication checks. No lifecycle
lock is held over remote I/O and there is no nested checker lock cycle.

For each outgoing record, Runtime retains its admitted handle and original slot,
record sequence/hash and synchronous guard while writing UDS and awaiting API
publication acknowledgment. Runtime calls fresh currentness and peer/lifecycle/
expiry checks after every writable wait and immediately before every local write.
Complete UDS delivery is NOT browser publication and cannot release the handle.

At the API's native WebSocket publication frontier, AFTER backpressure, a
synchronous guard obtains a fresh <=250 ms Runtime PUBLISH_CHECK for that exact
outstanding record. Runtime checks the held handle, original expiry, existing
peer/lifecycle and full API currentness. API rechecks peer generation and freshly
re-reads the DB tuple after the reply, then writes with no intervening await.
The one-use check is not permission for another record or a later retry.
For the API, publication means acceptance of one whole bounded frame by the
existing asyncio.Transport.write frontier. Automatic residual kernel writes are
already accepted/in-flight bytes; no per-kernel-write revalidation or physical
retraction is claimed. Revocation/EOF watchers abort owned residual buffers.
Runtime's directly owned UDS partial writes remain guarded before every syscall.
This distinction is deliberate and parent-approved; no new direct-socket writer
or distributed atomicity claim is introduced.

A browser consumption ACK may race ahead of native drain. Both the native
publication/drain completion AND the exact browser ACK are required before API
sends PUBLISHED; neither alone releases the pending record/slot or permits the
next Runtime record. This applies to END too.

The guarantee is fresh bounded remote observation followed by immediate local
check-to-write ordering, not global linearizability: another process may revoke
after the completed read, and already accepted/in-flight bytes cannot be
retracted. No renewable authorization window is introduced. API idle DB checks
and Runtime held-handle checks run at <=50 ms while progressing; failed/paused
RPC closes within its absolute bound. Process suspension is not a trusted clock
or instantaneous revocation claim.

The API native UDS reader remains active while browser publication is blocked,
so Runtime EOF/currentness failure aborts the WebSocket's owned partial buffers.
An API exit/pause or missing publication ACK closes Runtime's pending read and
preserves nonce burns. Bundle close synchronously shuts down its sockets, fences
callbacks and cancels owned work; cleanup is observed rather than assumed.

Final END keeps the same handle/slot through actual API publication, browser
consumption ACK and a terminal COMPLETE wait. Runtime does not close the browser
before END decrypt/hash/UTF-8 validation can finish. The native completed display
retains its channel, close subscription, held handle and slot through the ORIGINAL
expiry; clear/cancel/lifecycle/expiry closes it. The historical synthetic adapter
may retain its separate close-on-END behavior. No plaintext is returned to API or logged, traced, cached or stored.

## Browser transport and independently sourced trust

The formal route is `/projects/:projectId/changes`. The factory uses the current
AuthProvider identity and CSRF value locally, never a page-level fixture adapter.
Observation is the existing exact POST with no query/body. Content socket path
is `/api/v1/projects/{project_id}/git/staged-stream`, same-origin WSS only, with
subprotocol `agentbox-a3-content-v2`. The only opening message is <=8 KiB closed
JSON `{schema_version: "a3-open/v1", selection_id, request_nonce, csrf_token}`.
API validates exact Origin/Host/session/CSRF and full current tuple before OPEN.
Cookie and CSRF never enter native metadata or Runtime.

A3 crypto records remain exact binary bytes. To retain one pending record rather
than silently expanding queues, browser consumption ACK is exactly 41 bytes:
`A3CA || 0x01 || uint32be(sequence starting at 0) || SHA256(record)`. It is an
A3 transport control, not a crypto record or proof of decryption. API accepts it
only for its one outstanding record. Duplicate/wrong/unsolicited ACK closes.
Browser receive owns its slot through digest/ACK; one sending/receiving owner,
bounded bufferedAmount and synchronous currentness immediately before send are
required. WebSocket.close cannot retract bytes already queued by the user agent;
crypto/UI are fenced immediately and accepted bytes are uncertain/in flight.

Independent static path: `/.well-known/agentbox/a3-bootstrap.v1.json`.
Unique meta names are `agentbox-a3-trust-profile` = `a3-https-web-v1` and
`agentbox-a3-build-identity` = lowercase hex64. Missing markers result in no A3
bootstrap/observation/socket calls. No WAW fallback exists.

Bootstrap is <=8192 bytes canonical sorted ASCII JSON plus newline, exactly 13
string fields: schema_version=`agentbox-a3-https-bootstrap.v1`, trust_profile=
`a3-https-web-v1`, purpose=`agentbox-a3-content/crypto/v2`, repository,
origin, runtime_host_installation_id, runtime_host_installation_revision,
runtime_attestation_x25519_public_key (exactly 64 lowercase hex characters
encoding 32 raw public-key bytes), host_manifest_digest,
build_identity, version, valid_from, valid_until. Repository is ForceMind/agentbox;
Origin/build/host/revision and exact UTC validity (positive, <=31 days) are checked.

Two fresh, matching, bounded, credential-omitted/no-redirect HTTPS reads are
required, each <=5 s. The lease polls every 5 s, is stale at 10 s without a fresh
successful read, and synchronously rejects change/expiry/clock rollback/Origin/
meta drift. <=50 ms local checks and hide/freeze/pagehide/offline/route/auth change
invalidate it. ADR0010's trusted HTTPS code/Origin assumptions apply; no native
rollback or compromised-Web protection is claimed.

Static bootstrap establishes only A3 host/key trust. A fresh authenticated
observation separately supplies the dynamic Project/session/auth/binding tuple.
The controller explicitly distinguishes those sources, verifies their host match
and keeps the dynamic admission generation/local auth scope unchanged at every
yield/send. Server currentness remains authoritative; a static trust lease is
never a content authorization lease. Existing synthetic full-binding trust tests
remain separately typed and cannot become the production fallback.

## Bounded displayed-content currentness (explicit contract change)

The approved native profile replaces the old same-realm synchronous full-binding
invalidation assumption with bounded remote observation for already delivered
content. It is NOT an equivalent guarantee or a renewable content authorization.
The browser sends exactly 25 bytes `A3CQ || 0x01 || uint32be(sequence starting at 0)
|| CSPRNG challenge16`; API responds only after fresh Runtime held-handle and API
DB checks with exactly `A3CR || 0x01 || same sequence || same challenge16`.

One challenge may be outstanding. Capture progressing local issue time before
scheduling its send; issuance/pending work NEVER renews freshness. Only the exact
same-channel/generation reply before its issue-time +1,000 ms deadline renews
observed currentness to that same deadline, capped by original authenticated
selector expiry. Old, unknown, duplicate, out-of-order or late replies permanently
fence the channel; no response may revive a fenced owner. Issue the next challenge
after 250 ms only once the prior challenge has settled. Initial successful fresh
observation is required before plaintext publication. Final render and every
post-await crypto/UI action require both observed freshness and original expiry.

A <=50 ms browser owner check clears expired displayed content. Thus 1,050 ms is
only a conditional observed bound when the browser event loop and compatible
elapsed clock progress normally. Arbitrary process/device suspension, network
scheduling or browser clock failure is not a hard real-time SLA. Hide/freeze/
pagehide/offline/route/auth and detected clock regression immediately fence local
owners. Resume never reads/replays or resurrects content automatically.

This reply is outer HTTPS/native transport metadata. An actively malicious API
could forge it: it is not a Runtime-signed revocation proof and does not promise
strong displayed-content revocation against a compromised API. Independent A3
Noise/pin, Runtime checks at each new content publication and original authenticated
expiry retain their roles. Cached displayed freshness never authorizes Runtime
content or substitutes for native publication checks. Clearing UI/references is
not memory zeroization.

Only one crypto record, one 41-byte consumption ACK and one 25-byte challenge
mailbox can be owned by the Web writer; there is no growing promise/command queue.
One record pending plus fixed control fields is the complete transport budget.
Every control actual send is guarded after its bounded backpressure wait. API
currentness replies have the same post-backpressure native publication guard.
Unexpected controls, control flooding or concurrent external send/receive closes.

Before first crypto INIT, Runtime completes admission/Git/preflight and sends one
READY (`A3RD || 0x01`, exactly five bytes), with the admitted guard installed.
Web open waits <=5 s for READY and the first freshness exchange, then resolves.
Preflight errors use `A3ER || 0x01 || fixed ASCII ContentError code`, <=100 bytes;
only existing ERROR_CODES are accepted, never arbitrary exception text.
Malformed/internal protocol failures simply close; they do not invent error codes. No crypto record is accepted before READY. No extra final-decrypt ACK is
invented to claim distributed atomicity.

## Native exact codec inventory

Header kinds are fixed numbers: 1 HELLO, 2 HELLO_ACK, 3 OBSERVE, 4 METADATA,
5 OPEN, 6 OWNED, 7 PUBLISH_CHECK, 8 CHECKED, 9 PUBLISHED, 10 ACK, 11 CURRENT,
12 CURRENT_REPLY, 13 RECORD, 14 ERROR, 15 COMPLETE, 16 CLOSE, 17 LIVE,
18 LIVE_REPLY, 19 READY. Unknown values are rejected before body allocation.
Each role's receiver accepts only its expected state/kind/sequence.

Exact canonical JSON payload fields (no optional/extra fields):

- HELLO/HELLO_ACK: `bundle_id` (hex32), `role` (command/opaque/currentness),
  `facts_digest` (hex64). The complete three-role binding is checked before work
- OBSERVE: `facts`; OPEN: `facts`, `selection_id`, `request_nonce`
- `facts` is the complete exact A3CurrentAdmission schema; session_scope is hex64,
  auth_epoch and revisions are canonical positive uint64 strings. Its exact digest
  is SHA256 of its canonical bytes. relative_key remains internal UDS metadata
- METADATA: existing `snapshot_sha256`, `entries` only, bounded by the existing
  schema and whole-response size. No pin/credential/patch field exists
- PUBLISH_CHECK/CHECKED/PUBLISHED/ACK: `record_sequence` (positive uint32 JSON
  integer, no bool coercion), `record_sha256` (hex64). Exact pending record only
- CURRENT: `facts_digest`, `challenge` (fresh hex32); CURRENT_REPLY adds `current`
  (exact boolean). Sequence, challenge, bundle, facts digest and peer must match
- LIVE/LIVE_REPLY: `observation_sequence` (uint32 JSON integer), `challenge`
  (hex32). One pending outer challenge. Runtime handles LIVE on the owner loop
  with that bundle context and live held admission; API rechecks after RPC
- ERROR: `code`, restricted to the existing ContentError allowlist
- OWNED/COMPLETE/CLOSE/READY: empty exact object; RECORD is opaque binary

Role handshake precedes the directional sequence spaces. HELLO/ACK use sequence
one; subsequent command/currentness/opaque frames continue at two independently
per direction. A response must match its one outstanding request and expected
kind as well as its own directional sequence. Runtime outgoing record_sequence
is independent, starts at one; browser consumption sequence is that value minus
one. Fixed metadata controls never advance the crypto transcript or original TTL.

## Required evidence and deferred claims

Actual separate processes/UDS/Git/A3 crypto v2/END and formal App factory are
required. CI-only independent static assets/bootstrap must prove the API process
cannot author their served bytes. Native tests cover partial reads/writes,
oversize/truncation, exact role/peer/bundle mixing, timeout/backpressure, session
revoke, Project/epoch drift, API exit/pause, Runtime lifecycle loss, cancellation,
late END and original expiry. Tests must assert no publication after a queued
revocation check and no plaintext in API/socket diagnostics. Old fixture/codec/
crypto evidence remains; no test result is renamed real-host qualification.

All normal affected Python/Web gates, independent crypto/interop, exact-head six
workflows, actual CI Chromium Chinese desktop/phone pixels, then ordinary merge
and exact-main six terminal workflows are needed. Prior failed CI history stays.
This document is not evidence that these new checks have run.

References: [previous reader](WORKBENCH_A3_CHANGES_READER.md),
[ADR0010](adr/0010-cross-platform-web-bootstrap.md),
[Linux Unix socket credentials](https://man7.org/linux/man-pages/man7/unix.7.html),
[WebSocket close semantics](https://websockets.spec.whatwg.org/#dom-websocket-close).

## Candidate local verification — 2026-10-05

Independent source review found and closed the fd-watcher reuse, late decode/DB
deadline, cleanup-inclusive capacity and Web expired-freshness revival defects,
with regressions. Affected Python matrix:294 passed. Web:1480 tests plus6
extension tests; lint/format/typecheck/build passed; the final two recovery-copy
changes passed20 focused tests. Dedicated A3 crypto/codec/Changes interop and
bridge isolation passed. Existing synthetic tests are retained.

The full local pytest attempt did not pass: native UDS/host restrictions were
encountered and a shared /tmp ENOSPC caused an internal-error termination near40%.
After workspace-TMPDIR recovery the affected matrix passed. Fourteen new native
process tests are explicitly skipped locally because AF_UNIX creation remains
denied even after authorized escalation; that condition fails in CI. Fifty-two
new formal-route browser cases were collected, not executed locally. Exact-head
CI, real isolated native/static permissions and browser pixels remain pending.

## First exact-head CI, retained failure — 2026-10-05

PR #144 head `d05068d7c067e8a1a08eb64edcd413e6e2f315c7` passed Security,
Frontend, Deployment and Release Candidate. Backend 3.11/3.12/3.13 each reported
5193 passed,88 skipped,11 failed. Its test-only client omitted SELECTOR_DOMAIN
when computing the commitment; Runtime correctly refused the mismatched INIT.
The fix uses the unchanged protocol helper and adds positive/negative regression.

E2E reported144 passed,30 prescribed skipped,52 failed. All new formal-route
errors were masked by a numeric-UID/root-owned fixture-directory cleanup EACCES;
this does not establish that preceding browser work passed. Screenshot upload
was skipped. The test harness fixes exact-owner/retained-dirfd cleanup after
observed child termination, preserves primary errors, and emits only fixed
stage/role/type diagnostics. Partial setup ownership must survive setup failure.
No production behavior, trust/crypto/expiry rule or assertion is relaxed. New
exact-head CI and real screenshot read-back remain required.

## Second exact-head CI, retained failure — 2026-10-05

Head `2dd83b45be8cf18e76046c128b588ebe734352fe` again passed Security,
Frontend, Deployment and Release Candidate. Backend 3.11/3.12/3.13 each reported
5223 passed,88 skipped,2 failed. Twelve of14 new native tests passed, including
actual separate-process Git-to-END reading. Two test-tool defects remained: a
naive revoke timestamp instead of the database UTC6 transaction clock, and a
client that did not answer the normal20-second RFC6455 PING. Corrections keep
the production protocol, original expiry and absolute receive deadline unchanged.

E2E reported152 passed,30 prescribed skipped,52 failed. The eight additional
passes are pure Node cleanup tests, not formal-route browser qualification.
Cleanup now succeeds and exposes the common primary process-start RuntimeError;
its numeric-UID startup cause is still to be established by a bounded probe.
Only fixed role/phase/type/exit diagnostics are permitted. If the original source
is unreadable, a fixture-owned read-only copy is limited to explicit public
tracked Python files in fixed package roots with exact byte digests; no checkout
or system permissions are relaxed. Only the test start-control wait becomes
45 seconds to contain at most four5-second source probes; production timeouts
are unchanged. Existing setup primary-error preservation remains in place.
Screenshots remain unavailable; new exact-head CI and pixel review are required.

## Third exact-head CI, native passed; browser setup still failing — 2026-10-05

Head `33d34817f60931af8ad6ab637faac60864ded1a5` passed five workflows including
Backend. Python3.11/3.12/3.13 each reported5259 passed,88 skipped, with all14 new
real native separate-process cases passing. E2E remained152 passed,30 skipped,
52 failed. The bounded diagnostic now identifies API child initialization
PermissionError, before browser qualification. The fixture imports the API main
module before its explicit TEST configuration; that module constructs a default
app at import and can touch checkout development data. The narrow fix configures
the existing child-owned TEST paths before that import, preserving UID isolation
and product behavior. No actual browser or screenshot success is inferred.

## Fourth exact-head CI, actual browser runs; complete read still failing — 2026-10-05

Head `5cc923d97334dcb6702d3e6020d18c39fa610a47` passed five non-E2E workflows.
All three Python versions reported5261 passed,88 skipped; all14 native cases
passed. Numeric-UID/HTTPS/formal App browser startup now succeeds. E2E reported
174 passed,30 skipped,30 failed:22 of52 new cases pass bootstrap rejection and
unavailable-content states, while normal complete reads do not reach END/DOM.
Their dependent completed-display tests therefore cannot qualify.

Real WebCrypto/controller with a single-writer network stub and interleaved
Runtime socketpair LIVE/publication both pass; neither establishes the actual
browser transport frontier. A test-only passive observer adds fixed bounded
frame/owner counts on failure, without wire bytes, identifiers, secret fields or
exception values. No timeout or assertion is relaxed, and this is diagnostic
evidence only. Actual complete read and Chinese screenshot review remain pending.

## Fifth exact-head CI, complete primary flows pass but failures remain — 2026-10-05

Diagnostic head `e9bee683da60ebaceb5b2ee7a35e03b3bc315af3` passed five workflows;
Backend remains5261 passed,88 skipped per Python version, including all14 native
cases. E2E reported205 passed,30 skipped,2 failed,5 flaky. Both desktop/phone
primary flows reached actual Git-to-END/DOM, but a diagnostics-only change is not
a demonstrated repair. Rotation's desktop read prerequisite and mobile tampered
END status still fail; five other cases passed only on retry. Screenshot upload
was skipped. The new8 counter checks are pure Node logic, not browser evidence.

The primary-flow-only observer emitted nothing because those cases succeeded.
Its unchanged fixed numeric schema now runs in best-effort afterEach for each
unexpected attempt before fixture teardown. Existing bundle-lock double-thread
DB tests exclude the bare-adapter overlap hypothesis on this native path; product
code remains unchanged. Failure/flaky history is retained and qualification is
still pending.

## Sixth exact-head CI and ordering-preserving guard de-duplication — 2026-10-05

Head `07bc1b673992024d3d08f831c56903f3a897f036` passed five non-E2E workflows;
Backend remains5261 passed,88 skipped per version with all14 native cases. E2E
reported185 passed,30 skipped,27 failed. Fixed observations place most failures
after READY, INIT/CONFIRM/READ and3–6 consumed opaque records, rather than before
bootstrap or metadata. They do not disclose ciphertext, plaintext or identifiers.

A two-owner-loop socketpair probe reproduces command-queue expiry with healthy
currentness replies delayed only8–10ms. About500 CURRENT RPCs are involved in a
24KiB read; earlier same-loop tests masked command dispatch/completion queueing.
The narrow reviewed correction removes only earlier redundant checks:

- Private I/O waits keep their full pre-wait/idle check and <=50ms interval;
  readiness returns to the operation's existing final full pre-syscall guard.
  Each partial retry repeats that process. Public readable-only operations add
  their own final full return guard. After-decode checks remain unchanged
- The serve wrapper retains profile.check, whose before/after current callbacks
  both call admitted.context and its fresh admission check, plus the final
  handshake nanosecond deadline; its extra leading admission check is removed
- RPC replies are not cached. Final peer/closed/deadline checks after remote I/O,
  crypto checks,250ms command budgets,1s record budgets and original expiry remain

The identical8/10ms two-loop probe now reaches complete END. This is a local
regression result, not yet new exact-head browser qualification or pixel review.
Final local A3 matrix:428 passed; Ruff, Black403, mypy390, independent crypto/
interop and source review pass. The committed latency regression uses8ms for
CI scheduling margin (old logic failed three times);10ms pressure evidence is
retained separately, with three repeated8/10ms runs passing and no retries.

## Seventh exact-head CI passed; screenshot finishing — 2026-10-05

Head `f67b93dfa0678ee0f04ea187a91d9a8cddb35c07`, tree
`dc5a7665ab2e97c8ac5126bc9941a5922be27af0`, passed all six workflows on their
first runs. Backend3.11/3.12/3.13 each reported5276 passed,88 skipped, including
all14 actual native tests. E2E37315024259 reported212 passed,30 prescribed
skipped,0 failed,0 flaky; all52 formal App native desktop/phone cases passed.
Sixteen of212 passes are pure Node cleanup/counter tests, not browser cases.
This confirms the real chain after the narrow ordering correction; the earlier
failures and same-condition old-red/new-green latency evidence remain above.

Artifact11347219368 ZIP SHA256 is
`15b68f796cd93320a0459a218179a9a3709b47b215cc0fb221d9f6bf90a93fac`.
All four original PNGs were opened. Chinese glyphs and complete inert patch text
are readable without page-level horizontal overflow, but focused content left
fixed navigation midway through full-page captures, and the preexisting mobile
refresh button wraps. The final visual-only correction prevents button wrapping
and explicitly restores/asserts top scroll before capture. Its own exact-head CI
and actual PNG review are still required before normal merge/main read-back.
No security contract, timeout, fixture isolation or content assertion is relaxed.

## Final head, pixels and main closure — 2026-10-05

Final head `ec89d73c64ed6b5b87371d9a72209e79ccc36760` passed all six first-attempt
workflows (24 successful jobs, two historical rc8 skips), independent source/doc
review and actual review of all four desktop/phone PNGs. Fixed navigation starts
at the top and mobile refresh stays on one line. Chinese glyphs, verified status,
inert HTML literal and keyboard focus are readable without obvious overlap or
page overflow. Full24KiB completeness/non-execution comes from E2E assertions,
not from the screenshot's scrollable patch viewport.

PR #144 merged normally as `3e313b36b7cfc7c1de1c54cc20164ae223fcd122`, parents
`61a5efce6ab43754a2acdb313d5e21ee83f64c52` and the final head. Main tree
`d2fa9213b40db3a5f2b9236646da7fdc50c39645` equals the reviewed head. All six
first-attempt main workflows passed (23 successful jobs, three skips: push-only
dependency-review and two historical rc8). Backend reports5276 passed,88 skipped
per version and all14 native cases passing. E2E reports212 passed,30 prescribed
skipped,0 failed,0 flaky;52 new formal native cases pass, and16 of212 are pure
Node checks. Earlier failure history remains intact.

Final-head artifact11349880911 ZIP SHA256 is
`f41b7b4346bf32acf763153e1269cbfc2b33adb861560deb157370af99c8e723`.
Same-tree main artifact11350222710 digest was also verified as
`0cd6b83f513096b1dd3826a6c068f09d2ebed401acdb246051203bdc88f263db`,
without claiming another main-image pixel review. Production trust enrollment,
installer/listener activation and real-host/client/account/release evidence remain
outside this completed software scope.
