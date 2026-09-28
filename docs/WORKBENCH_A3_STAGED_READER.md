# A3 Runtime-only staged patch reader

Status: security-sensitive software candidate, 2026-09-29. This extends the
[A3 patch contract](WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md), the rc17 held
Project/Git root, rc19 Linux descriptor-bound child cwd, and the merged
staged-selection policy. It adds no Runtime RPC, API endpoint, browser
admission, JSON patch response, plaintext relay, or file preview. A future
content action must first bind formal Project, administrator session,
selector, Runtime epoch and encrypted delivery authority.

`GitStagedPatchReader` takes the fixed Runtime `ProjectRegistry` and
`GitAdapter`. The caller supplies one registered relative Project key and
one selected path; it cannot supply cwd, Git options, environment, revision,
object ID or executable. The reader resolves the Project under the fixed
root and holds descriptors for the Project, `.git`, index, config, HEAD and
local object directories. It inventories at most 20,000 object-store nodes,
rejects symlinks/shared writable files and external alternates, and checks
the inventory before and after each child. An oversized or changing local
store fails closed. This is a bounded best-effort observation of a mutable
repository, not a filesystem transaction or a defense against a privileged
actor who can change the Runtime process itself.

The child uses the pinned Git executable, sanitized Runtime environment and
Linux `run_with_cwd_fd`; it receives the held Project directory rather than
an untrusted path lookup. The fixed status command produces porcelain v2;
the merged policy accepts only tracked regular staged add/modify/delete and
records exact HEAD/index OIDs and modes. Git config is read without includes
and rejects executable helpers, partial-clone/promisor settings and unsafe
extensions before content extraction. The reader does not use
`--no-lazy-fetch`, because the older Linux Git versions in scope do not
document that flag; it rejects partial-clone configuration instead. This
must be confirmed against the actual target Git version before host use.

Two bounded `git diff --cached` observations use `--literal-pathspecs`, a
final `--`, `--no-ext-diff`, `--no-textconv`, `--no-color`, `--no-renames`,
`--full-index`, fixed context and prefixes. The patch must have one diff
header and one full index header whose two OIDs match the selected status
record. The complete UTF-8 output is capped at 256 KiB and 4,096 lines;
binary, invalid encoding, unsafe config, timeout, changed root/index/status,
second-patch mismatch and cancellation never return partial plaintext.
The [Git diff manual](https://git-scm.com/docs/git-diff) defines the staged
comparison and disabling flags; the [Git command manual](https://git-scm.com/docs/git)
defines literal pathspecs, optional locks and replace-object suppression.

Local tests use real Git repositories with a test-only child shim to cover
staged modification alongside unstaged content, add/delete, option-like
path, packed objects, unborn branch, rename/symlink/untracked, binary,
invalid UTF-8, size/line caps, external helper canary, partial-clone config,
index/object drift, second-patch/OID mismatch and cancellation FD closure.
The positive production runner case is Linux-only and must pass exact-head
CI. The shim is not descriptor-cwd or host evidence. Security-critical
Architecture, Security and Test review, target Linux Git/host checks,
selector, encrypted channel and browser rendering remain separate gates.
Do not merge this reader as a qualified content action or expose its patch
result without those gates.
