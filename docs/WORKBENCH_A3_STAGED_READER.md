# A3 Runtime-only staged patch reader

Status: reconciled software candidate, 2026-10-04; parent source review completed,
new exact-head CI pending. This reuses Draft [#117](https://github.com/ForceMind/agentbox/pull/117)
without rewriting its history. It extends the [A3 patch contract](WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md),
held Project/Git root and Linux descriptor-cwd process runner. It adds no Runtime
RPC, API endpoint, selector, browser admission, encrypted content channel, file
preview or patch UI. These remain independent subsequent slices.

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
is claimed. New exact-head CI, selector, encrypted delivery, client rendering and
real-host acceptance remain distinct.
