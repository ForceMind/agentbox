# A3 Runtime-only staged patch reader

Current continuation (2026-10-04): the [independent encrypted single-read slice](WORKBENCH_A3_ENCRYPTED_SINGLE_READ.md)
now composes these primitives in a synthetic in-memory Git→Noise→Web pipeline.
The codec/reader-only descriptions below remain the scope of their original
slices; production resolver/key/relay/UI and host qualification remain unopened.


Status: reader merged in [#138](https://github.com/ForceMind/agentbox/pull/138)
on 2026-10-04 as `35d25bdccbb9311a57fc06a0683f4f60bf50dd9c`; original #117
history is retained and indirectly merged. The short-lived selector below merged in [#139](https://github.com/ForceMind/agentbox/pull/139)
as `587fe8eabf7e5d5e4d3a561091ec00c3e9f40881`; it is not a production content action.
It extends the [A3 patch contract](WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md).
No Runtime RPC, API endpoint, encrypted content channel, file preview or patch
UI is added. These remain independent subsequent slices.

## Fixed inputs and private staged view

`GitStagedPatchReader` accepts only the fixed Runtime `ProjectRegistry` and
`GitAdapter`, one registered relative Project key and an eligible selected path.
It does not accept caller argv, cwd, environment, revisions or executable paths.
The existing path sensitivity policy remains enforced before any Git process.

The original candidate checked repository config, then ran `git status` against
the working tree. Real-Git canaries confirmed that concurrent `core.fsmonitor`
or `filter.*.clean` changes could execute a helper before the final `PATCH_STALE`
rejection. The old 48 related A3 tests did not detect this. A post-read failure
is not an execution boundary, so this reconciliation removes that working-tree
process path rather than merely adding another config check.

The reader now constructs a private Runtime-owned Git view:

- Index and original config are bounded copies in Linux sealed memfds. Original
  config is inspected with fixed `git config --no-includes --file` inside the
  private view; it is never the child repository configuration.
- The private directory contains only fixed canonical bare config, validated
  HEAD/ref/packed-ref metadata and descriptor links. Those regular metadata
  files are not sealed memfds. No source object body or patch is copied to disk.
- Loose objects and pack companion files are opened `O_NOFOLLOW`, validated as
  same-owner, nonshared regular files, and held read-only. The generated object
  paths point to these held `/proc/self/fd` inputs, never source pathnames.
- The child receives the private directory's held cwd, fixed `--git-dir=.`,
  `--no-replace-objects`, no optional locks and a fixed sanitized environment.
  All Git transport protocols are denied; HOME/XDG locations are `/dev/null`.
  Original working files, worktree config, info attributes, external config,
  hooks and alternate object paths are not used by the child.
- Fixed `git diff --cached --raw -z --no-abbrev --find-renames` observes staged
  metadata only. Its bounded rows are translated into the existing internal
  staged-selection policy. The v1 Changes metadata API is unchanged. An absent
  staged selection, including an untracked path, yields `PATCH_STALE`; it is
  never shown as an empty complete patch. Pure mode-only changes are explicitly
  unsupported. Working-tree and private info attributes do not determine this
  staged-only view; tracked index attributes remain untrusted Git data, with
  external diff/textconv disabled and no driver configuration.

This v1 explicitly supports ordinary SHA-1 loose and packed Git storage, including
packed refs and unborn branches. It rejects unsafe refs/symlinks, incomplete
pack/idx pairs, alternates, promisor files, shallow boundaries, grafts, split
index files, worktree config, reftable and nonzero/extended repository formats.
SHA-256 storage is not silently interpreted as SHA-1. Unsupported forms return
fixed unavailable errors and need a later reviewed compatibility slice.

## Resource, currentness and cleanup contract

The original root inventory is bounded to 20,000 nodes and depth four. The
private view additionally limits object files to 256 and their combined stored
size to 64 MiB, index to 8 MiB, original config plus HEAD/refs/packed-refs metadata
to 128 KiB, ref nodes to 128 and ref depth to eight. It owns at most 512 total
file/directory descriptors; the root separately owns nine, and the process
runner's cwd duplicate and standard subprocess pipes are separately scoped.
Only the two sealed inputs and at most 256 object-file descriptors are lent to
Git. Reaching any limit fails closed and cleans up; this is not an arbitrary FD
API. The process runner accepts only the exact internal snapshot owner and its
matching private cwd for this input path.

**Held object FDs are not immutable content.** They prevent reopening a replaced
source pathname, but another writer can modify the same inode. Root/index/config,
ref/pack metadata, directory inventories and held/named object identities
(including size, mtime and ctime) are rechecked before/after each child, and two
bounded patch observations must agree. Any detected drift discards the result.
This is best-effort stable observation, not a filesystem transaction or defense
against an actor controlling the Runtime process. No stronger content-isolation
or real-host qualification claim follows from these software tests.

The complete UTF-8 patch is limited to 256 KiB and 4,096 lines, with one full
index header matching the selected old/new OIDs. Binary, invalid text, oversize,
unsafe config, timeout and drift have fixed failure codes. Each child has a
five-second timeout and bounded stdout/stderr; this is not a separate hard RSS
limit on Git. Cancellation waits for the existing runner's exact-child cleanup,
then removes the private metadata directory and closes all owned FDs. Constructor,
limit and ordinary-error paths also clean up. No partial patch is returned.

## Evidence and remaining gates

Local Linux Git 2.52.0 tests cover staged add/modify/delete alongside unstaged
content, packed objects/refs, unborn branch, fixed argv/environment, forbidden
kinds, binary/encoding/size/line failures, helper races, ref/object in-place
mutation, metadata/FD budgets, sealing and cleanup. The two helper races run
through both the real-Git test shim and production `ControlledProcessRunner`.
Shim results are not native runner evidence; native cases are recorded separately.

The [Git diff manual](https://git-scm.com/docs/git-diff) defines staged raw/patch
modes and disabling options; the [Git command manual](https://git-scm.com/docs/git)
defines literal pathspecs, optional locks and replace-object suppression.
The new `fcntl`/memfd implementation is Linux-only; it provides no Windows
import or execution qualification. Actual target Git/host qualification remains
NOT RUN. Software self-review is not an independent review. Parent source review
of snapshot/reader/process completed before commit; no GitHub review submission
is claimed. The merged reader exact-head CI is recorded in [current state](project/CURRENT_STATE.md).
The selector exact-head/post-main CI is also recorded there after #139. Encrypted
delivery, client rendering and real-host acceptance remain distinct.

## Internal staged selector candidate

`GitStagedSelectors` owns the fixed reader and one trusted synchronous context
resolver. Its input is a formal `prj_` ID and a 32-byte noncredential API session
scope; `read` additionally accepts only the opaque `selection_id`, never a path,
OID, revision, side, argv or signer payload. The resolver must return the CURRENT
READY Project's complete `WAWProjectBinding`, Runtime epoch and active session
scope, or None for missing/revoked/ambiguous/invalid mappings. This trusted port
is intentionally **uncomposed**: no production READY/session check, endpoint or
content authorization is claimed from the fixture implementations. Raw cookies
and CSRF values must never reach this port.

The internal `runtime-staged-observation-v2` returns sorted metadata entries,
fixed unavailable reasons and a selector only for eligible regular staged
add/modify/delete. The digest is SHA-256 over a domain and length-framed complete
sorted raw rows, including denied/unselected rows, all paths (including rename
source), HEAD/index OIDs, modes, kind and side. Input remains bounded to 1 MiB and
10,000 entries. The v1 metadata-only API/parser/digest/strict clients are unchanged;
its display-only digest is not sufficient to bind content.

Each owner creates a fresh 32-byte CSPRNG key with no caller-supplied key or
persistence. Fixed binary payload `>BQQI32s32s` contains version 1, monotonic
issuance/expiry nanoseconds, entry index, full snapshot digest and a keyed opaque
context commitment. A distinct fixed-domain HMAC-SHA256 authenticates that
85-byte payload; the complete 117 bytes encode to exactly 156 base64url characters
with no padding. The context includes every formal binding field, relative key,
Runtime epoch and session scope. The HMAC domain binds `staged`; no other side or
generic sign/verify API exists. Tokens contain no host path or raw scope, are not
bearer authorization, and are neither persisted nor logged. Metadata repr omits
tokens; errors carry fixed prose only. A new owner/process invalidates prior
selectors, forked instances fail closed, and close drops the ephemeral key without
claiming Python memory zeroization.

Validity is exactly `issued <= monotonic_now < issued + 30 seconds`. Regressing or
invalid monotonic time permanently fences the owner. Issuance checks currentness
again before publication. Read opens a fresh held view, observes its complete
staged metadata and validates the token against **that same view**. It resolves
the selected path only from that current sorted entry index. There is no
validate-then-reopen path. The reader's synchronous currentness/expiry check is
immediately before each patch call and before returning its complete result;
all original pre/post child revalidation and dual-patch checks remain. Changes
during reading, including expiry/revocation/epoch/close, discard the result.
This closes the application-level observation swap, not the documented mutable
object/filesystem transaction limitation.

At most four operations per selector owner can hold views concurrently; excess
work fails with `PATCH_UNAVAILABLE_BUSY` rather than queueing beyond token TTL.
Per-operation reader FD/byte/time limits remain unchanged. Cancellation and every
error close the view/root before releasing operation capacity. The module adds
no process, file-storage, network, API, Worker, WAW frame or logging surface.
Necessary selector tests and review are software evidence only; target-host and
physical-client acceptance remain NOT RUN.

## Following independent codec slice

The [A3 content schema/codecs](WORKBENCH_A3_CONTENT_CODECS.md) candidate consumes
no reader or selector directly. It defines dedicated context/AAD bytes, bounded
plaintext messages, all-or-nothing pagination and a pure transcript model with
cross-language tests. The selector's production READY/current-binding/session
resolver is still uncomposed. No Noise profile, Runtime/API content transport,
patch UI or real-host qualification follows from that candidate.
