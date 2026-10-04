# A3 Changes-page staged reader software composition

Status: source candidate, 2026-10-04; base #142 merge
`b7dd51d3288022f12604656515aafe7e11a00d3e`, tree
`2cdfa72e7ca99b57312dadf156af1b74d82db15e`. The contract was approved before
implementation. This connects the existing [admission/lifetime](WORKBENCH_A3_ADMISSION_LIFETIME.md),
[encrypted read](WORKBENCH_A3_ENCRYPTED_SINGLE_READ.md),
[content codecs](WORKBENCH_A3_CONTENT_CODECS.md) and
[staged selection](WORKBENCH_A3_STAGED_READER.md) to a deliberate page-owned view.
It does not reimplement or weaken those layers.

## Honest source boundary

The shipped Changes page has no A3 Runtime adapter or purpose-specific trusted
pin. It explicitly says the reader is unavailable. API source registration is
absent by default; only `Environment.TEST` can inject the typed metadata port.
Neither production nor development configuration can enable it. There is no
new listener, WebSocket/RPC transport, Runtime key loader, pin enrollment,
installer switch, persistent grant, host activation or production content path.
No WAW pin, key port, application frame, CipherState or ciphertext is a fallback.

A fixture-backed usable DOM flow is software evidence, not production usability.
No real host, physical client, real credential/Provider operation, deploy/release
or support qualification follows. Existing metadata v1 behavior is preserved.

## Exact selector/bootstrap route

`POST /api/v1/projects/{formal_project_id}/git/staged-observation` requires the
existing exact Origin/Host policy, authenticated administrator session and CSRF.
It rejects any query, nonempty body (including `{}`) and non-formal Project ID.
It accepts no caller path, revision, command, OID, option or selector. Default
source absence returns fixed `PATCH_UNAVAILABLE_CONFIG`. It never auto-reads a
patch. Responses and failures are noncacheable; success also has `Pragma:
no-cache` and `Vary: Cookie, Origin`. No token/content is logged or audited.

The API reads the existing `A3SessionCurrentness` adapter. It sends its typed
noncredential `A3CurrentAdmission` to the injected metadata port and rechecks the
same entire current tuple after the await. The API neither imports a Runtime
implementation for this boundary nor executes a Runtime process. Isolated tests
compose the port with the existing Runtime owner; no production indirect
in-process Runtime invocation is installed.

Success is the usual v1 envelope with a dedicated data schema:

- `schema_version: a3-staged-observation/v1`
- `snapshot_sha256`: complete sorted Runtime observation digest
- `binding`: exact `project_id`, `project_revision`, `binding_revision`,
  `binding_digest`, `runtime_host_installation_id`,
  `runtime_host_installation_revision`, `runtime_epoch`, `session_scope`,
  `auth_epoch`; revisions and auth epoch are canonical positive decimal strings
- `entries`: at most 10,000 unique entries, each exact `path`, `kind`,
  `side: staged`, `selection_id` or fixed `unavailable_code` (exactly one non-null)

Each selector is the existing 156-character Runtime-minted opaque value. Each
path is display-only, bounded to 4,096 characters; Web additionally enforces
4,096 UTF-8 bytes. Whole API serialization is bounded to 2 MiB, with overflow
failing before publication rather than publishing partial metadata. The binding
excludes internal relative keys, host absolute paths, raw session/user IDs,
cookies, CSRF, credentials and pins. No bootstrap response can establish its own
trusted pin. The current GET metadata v1 schema and strict parser do not change.

## Purpose-specific trust and one-shot ownership

The independently supplied Web trust port requires exact purpose
`agentbox-a3-content/crypto/v2`, a raw public pin32, and current full public
binding including noncredential session scope/auth epoch. It supplies synchronous
currentness and invalidation. It has no production provider in this slice.
The bootstrap binding must equal that independently supplied tuple. Matching
syntax or a synthetic fixture provider does not establish real trust provenance.

Only clicking an eligible staged add/modify/delete row starts a read. The owner
requests a fresh whole selector observation, matches the display path locally,
generates a fresh CSPRNG nonce32 and builds the unchanged canonical v1 content
context. The opaque adapter receives Project ID, selector and nonce, never a
path/command. Existing Runtime lifecycle/selector authority owns full binding,
original expiry, four shared operation slots and the 128-nonce ledger. No second
Project registry, nonce ledger, lease service or general gateway is introduced.

The page creates fresh `A3Browser` crypto v2, executes INIT/ATTEST/CONFIRM/ACK and
encrypted READ/PAGE/END. The opaque software port preserves one whole <=24 KiB
record/direction and one sender/receiver owner, backpressure and irreversible
cancellation. Final actual publication requires the owner's synchronous guard
after scheduling/backpressure. Source cancellation, uncertain delivery or loss
closes rather than automatically retrying. API/Worker never see patch plaintext.

Only complete END/count/size/digest/UTF-8 validation permits inert React text.
No raw HTML/Markdown/source execution, partial preview, plaintext transport,
logging, database, analytics, service worker or persistent cache is added.
Rendered completion time is explicitly browser completion time, not claimed
Runtime trusted observation time. The staged content is a stable double
observation of mutable Git, not a filesystem transaction or secret scrubber.

## Lifetime and UI closure

A page owns one generation. Cancel, another click, metadata refresh, changed
Project/session/auth epoch, hide/freeze/pagehide/unmount, offline/disconnect,
trust drift, expiry and malformed/lost/late content immediately fence generation,
close pending crypto/transport, and discard the visible result. Every asynchronous
return is checked. No automatic read/replay occurs when visibility returns.

The crypto role exposes only its effective local deadline so the page can retain
the already authenticated tightened deadline after terminal END destroys crypto
state. Displaying content never renews or resets it. The page keeps currentness,
trust invalidation and <=50 ms idle checks through that same deadline. Browser
suspension is handled by lifecycle closure; arbitrary clock skew or suspended
clock progress is not claimed. Clearing references is not memory zeroization.

The UI supplies Chinese actionable empty/loading/unavailable/stale/too-large/
binary/permission/failed/completed states, sensitivity warning, explicit cancel
and clear, native keyboard controls and a bounded wrap-safe desktop/phone view.
Without both A3 port and purpose pin it remains honestly unavailable.

## Evidence contract

`tests/a3_changes_fixture.py` creates isolated native staged Git, a real current
API session/READY database binding and the existing Runtime executor/lifecycle
owner. It invokes the actual new ASGI route in process, then serves unchanged A3
crypto through `A3OpaqueTestRelay`. Public deterministic synthetic key material
is supplied independently from observation. Credentials stay inside the test
process. Stdout exchanges only bounded metadata and opaque hex records.

The CI-only `a3_changes_peer.py` and Node bridge connect that actual pipeline to
the actual Changes page/controller in Chromium desktop and phone-width projects.
The test harness is excluded from the production build, with fixture-marker
checks. No new real network adapter is qualified by an in-process bridge. Cases
include complete inert source, staged/unstaged separation, preflight binary and
too-large, denied path, cancellation/late END, tamper/loss and page lifecycle.
Only explicit synthetic Changes screenshots may be retained; global traces,
video and incidental screenshots remain off. Local browser execution is not run;
existing authorized CI Chromium supplies actual rendering evidence.

Local focused tests, independent review, full exact-head workflows and later
merge/read-back are recorded in [current state](project/CURRENT_STATE.md).
Pending/never-run checks are not PASS. Production adapter/pin/host qualification
remains a separate future contract and gate.

## First CI integration correction

PR #143 initial head `892dbd8` passed five workflows; E2E failed before all 28 new
DOM cases because the fixture child inherited the outer E2E application's
AGENTBOX settings. Product Settings intentionally prioritizes environment over
constructor values, so the child reached the already initialized outer DB.
Only the fixture spawn now strips AGENTBOX_*; production settings are unchanged.
The actual bridge has a poisoned-environment/startup-failure Node regression,
without launching a browser. First failure remains evidence; a new head needs
all workflows and actual desktop/phone screenshots before completion.
