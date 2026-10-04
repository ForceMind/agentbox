# A3 Project Git patch content contract

Current continuation (2026-10-04): the [independent encrypted single-read slice](WORKBENCH_A3_ENCRYPTED_SINGLE_READ.md)
now composes these primitives in a synthetic in-memory Git→Noise→Web pipeline.
The codec/reader-only descriptions below remain the scope of their original
slices; production resolver/key/relay/UI and host qualification remain unopened.


Status: software contract candidate, 2026-09-29. This document follows
[ADR 0009](adr/0009-workbench-identity-and-content-boundary.md), the
[rc15 path metadata contract](WORKBENCH_A3_GIT_CHANGES.md), and the Owner-approved
[full capability plan](project/FULL_CAPABILITY_DELIVERY_PLAN.md). It freezes the
scope and negative cases for the next A3 implementation slices. No content
endpoint, Runtime patch action, encrypted content channel, or patch UI is
implemented by this document. rc16's Changed Paths page remains metadata-only.
The rc17 source candidate implements only internal descriptor custody for the
fixed Project/Git nodes. It does not close child-cwd or full object-store
provenance and cannot release content.
The rc19 source candidate adds an internal Linux-only held-descriptor child
cwd seam, still without a patch action or object-file provenance proof. See
[A3 cwd proof](WORKBENCH_A3_GIT_CWD.md).

The current [staged reader candidate](WORKBENCH_A3_STAGED_READER.md) is reconciled
against main on 2026-10-04. Configuration/helper race evidence requires a private
staged-only Git view: sealed index/config inputs, held object-file descriptors,
validated ref metadata, fixed cached raw/patch commands and dual observations.
It does not run working-tree status for content extraction. Held objects remain
mutable and are revalidated; metadata/FD/storage limits are explicit in that
contract. It returns text only to Runtime-internal code and adds no RPC, API,
encrypted channel or UI. The reader has merged in #138 with exact-head and
post-main CI; see [current state](project/CURRENT_STATE.md), including the retained
first post-main Frontend failure. The Runtime-only selector has merged in #139,
with its trusted current-context resolver still uncomposed. Its full sorted
snapshot digest and same-view validation/read contract are specified in
[the reader/selector contract](WORKBENCH_A3_STAGED_READER.md#internal-staged-selector-candidate).
No v1 API migration or production admission is implied. Real host/device acceptance
is deferred, not passed. The implementation
contract supersedes the older direct-worktree status approach below for this
first reader only; unstaged extraction and future content delivery remain gated.

The rc23 internal staged-selection slice adds a Runtime-only path policy and
porcelain-v2 index eligibility check. It accepts only tracked regular staged
add/modify/delete rows and records the exact HEAD/index modes and OIDs. It
rejects ambiguous paths, credential path classes, rename/copy, conflicts,
untracked, submodule, symlink, invalid OIDs and missing selections with fixed
reasons. A normal source file named `config.json` remains eligible, while
`.env*` components, Runtime/credential directories, credential filenames and
private-key extensions are denied case-insensitively. This is metadata-only:
no Git child, object read, patch bytes, Runtime action or browser route exists.
Object-store provenance, snapshot/re-read and encrypted delivery gates below
remain open.

The next [independent schema/codecs candidate](WORKBENCH_A3_CONTENT_CODECS.md)
freezes canonical context/AAD bytes, four strict plaintext record schemas and
pure Python/Web transcript/vector behavior. It does not implement or open an
encrypted channel. Its 16 KiB page ceiling includes ALL JSON metadata and
base64 payload; the 256 KiB reader ceiling is not a promise that every reader
result fits 16 pages. An all-or-nothing planner rejects transport-oversize
results with PATCH_TOO_LARGE before any PAGE can escape.

## Authority and delivery order

The only entry point is a READY formal Project. The Runtime resolves its
registered relative key under the fixed Project root. A browser-visible path
is display data; it is never a filesystem grant, process argument, working
directory, or generic Git selector. The administrator Web Session authorizes
the Project observation but does not own Git execution or file content. Root
Helper, Worker, API and provider adapters receive no file body, patch text,
Runtime HOME, key, or Provider Secret.

The current `ProjectRegistry.resolve` and `GitAdapter._run` use path and cwd
checks. They are sufficient for the delivered metadata observation but do
not prove a descriptor-held content root. Content extraction is blocked
until a Linux descriptor-bound Project/repository resolver, Git store/index
provenance checks (including symlink and alternate-object-store rejection),
and a child-cwd ownership proof are implemented and tested. Rechecking a
pathname before/after `git diff` alone does not close a path-swap race.

Implement this contract in separable order:

1. Runtime-only bounded Git patch extraction and failure taxonomy, with no
   network route or browser control.
2. A versioned change observation that adds a Runtime-minted, short-lived
   `selection_id` to each eligible entry. The existing v1 metadata schema and
   strict clients remain valid until an explicit v2 migration. A selector is
   bound to Project, Runtime process epoch, sorted metadata snapshot and entry
   index; it is not a bearer authorization. The Runtime re-observes all of
   these before extraction. The selector carries no host path to the caller.
3. A separately admitted encrypted content channel, then the Web diff view.
   Content never uses the JSON metadata API or the WAW terminal frame types.
   The channel is closed by default until its software and host inputs pass.

The selector may use a per-process CSPRNG key and HMAC over those typed fields
plus a trusted API-provided session scope; no raw cookie or CSRF token enters
the Runtime.
This key lives only in `agentbox-runtime`; restart invalidates old selectors.
No selector is persisted, logged, accepted as an arbitrary file ID, or used to
extend an administrator's Project access. Validity is at most 30 seconds and
is checked again when a content read starts. A selection from a different
Project/session, Runtime epoch, or changed Git observation fails closed.

## Runtime extraction v1

The first extraction slice admits only staged, tracked, regular,
non-conflicted `modified`, `added`, or `deleted` entries from a verified
Git index/object store. An unstaged slice follows only after descriptor-bound
working-file acquisition and a stable content observation are proven. A
caller chooses `staged` or `unstaged` only when that side is supported and
present. The two sides are never silently combined. Untracked,
renamed/copied, conflicted, typechanged, submodule, symlink, binary, and
non-UTF-8 cases return a fixed `PATCH_UNAVAILABLE_*` reason in v1. These are
explicit gaps for later A3/Files slices, not clean or empty diffs.

The first reader hard-denies Runtime/configuration locations and obvious
credential path classes inside a Project (`.env*`, `.ssh`, private-key and
credential-store extensions/names) before Git extraction. The exact
case-folded path policy and its false-positive handling are frozen in code
tests before admission. This policy does not promise to discover every
secret in otherwise ordinary source files; the UI must say content may be
sensitive, never prefetch patch text, and require a separate deliberate
read action on a trusted client. No server-side secret scrubber is claimed.

For an eligible entry, the Runtime obtains the path only from its current
validated Git status record and revalidates repository ownership/configuration.
It uses its pinned Git executable, sanitized environment, no optional locks,
no shell, and fixed argv. The tracked-file staged/unstaged commands use
`git --literal-pathspecs diff` with `--no-ext-diff`, `--no-textconv`,
`--no-color`, `--no-renames`, fixed context, and a final `--` before the
Runtime-selected path. Binary patch generation is not enabled, and binary
results are rejected. No browser-supplied Git option, pathspec magic,
revision, filter, hook, pager, cwd or environment reaches the process. Git
config and attributes that could execute an external helper remain rejected
or explicitly disabled. The exact argv must be checked against the installed
Linux Git versions before code admission. The semantics of the disabling
options follow [Git's diff documentation](https://git-scm.com/docs/git-diff).

The complete captured patch is bounded to 256 KiB and 4,096 UTF-8 lines.
Oversize, binary, invalid encoding, process timeout, unsafe repository state,
unsupported mode and changed snapshot have distinct fixed codes. They return
no partial patch as a successful complete result. A bounded preview may later
add pagination with `complete=false` and an explicit truncation reason; this
v1 reader cannot represent missing content as an empty patch. The output is
treated as untrusted source text, never HTML, SVG, Markdown execution, a
command, a secret scrubber result, or Audit detail.

To avoid publishing a torn read, extraction checks the descriptor-held
Project/repository binding, metadata snapshot, selected side and file mode
before and after Git, and compares two bounded patch observations before
releasing bytes. Any drift,
cancelled read or uncertain process cleanup returns `PATCH_STALE` or
`PATCH_UNAVAILABLE` and discards plaintext. This is a best-effort stable
observation of a mutable worktree, not a filesystem transaction; the UI must
label the observation time and offer an explicit refresh. The extraction
runner has a hard timeout and terminates/reaps its exact child on cancellation.

## Encrypted content channel

The content channel has its own protocol version, admission tuple, typed
`PATCH_READ`/`PATCH_PAGE`/`PATCH_END`/`PATCH_ERROR` messages and a distinct
Noise prologue/application context. It may reuse reviewed Noise and AEAD
primitives after domain separation, but cannot reuse WAW terminal INPUT,
OUTPUT, RESIZE, ACK, cursor, frame meaning, or CipherState. Runtime owns the
static private key and plaintext. The browser verifies the independently
trusted Runtime pin; the API verifies current session/Project, Origin,
browser trust, revocation and admission lifetime, and relays only opaque key
and ciphertext frames. No plaintext fallback, JSON debug route, HTTP cache,
server log, database, Audit payload, analytics, or Service Worker cache exists.

One read belongs to one Project, browser session, Runtime epoch, selector,
side and request nonce. Pages are at most 16 KiB plaintext, at most 16 pages,
and carry sequence, total bytes, patch digest, observation time and an exact
`complete` marker inside authenticated ciphertext. A lost page, sequence gap,
replay, wrong project/selector, changed pin, hidden document, disconnect,
revocation or uncertain ACK fences the read and clears the in-memory patch.
The browser never auto-replays a read with an old selector. Patch bytes stay
in volatile view state only and are cleared on Project/session change,
visibility loss, tab close and unmount. Real host/client trust and the R12
Runtime profile are independent deployment gates.

## Required evidence before a patch UI claim

- Real Git fixtures for tracked staged/unstaged changes, both sides together,
  add/delete/typechange, initial commit, large patch, binary, untracked,
  rename/copy, conflict, symlink and submodule; no unsupported case appears
  as an empty complete patch.
- Negative fixtures for traversal, option-like filenames, pathspec magic,
  NUL/control names, unsafe config, external diff/textconv helper, repo swap,
  symlink/alternate object store, unsafe index, stale selector, concurrent
  file/index mutation, cancellation and child
  cleanup. A canary helper must not execute.
- Protocol tests prove API/Worker observe only ciphertext, strict versioned
  schemas and page budgets, no plaintext logging/persistence, and browser
  scope/visibility fences. Cross-language crypto vectors and Linux native
  tests must precede a qualified content transport.
- Desktop/mobile actual rendering must show staged versus unstaged, loading,
  unavailable, too large, stale, binary and failed states, with no execution
  of source text and no horizontal overflow. Local browser evidence is not
  real-host or production acceptance.

The contract will be revised against implementation evidence. The current
`GET /api/v1/projects/{id}/git/changes` remains metadata-only and grants no
patch read while this work is pending.
