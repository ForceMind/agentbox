# WAW R11 execution plan

Status: active software implementation plan, 2026-09-05.

This plan refines the accepted R11 controller contract. It governs software
implementation on the current Mac and Linux CI only. It does not activate a
host, provision an API/Runtime identity, install a CRX, handle a credential, or
claim product qualification.

## Verified starting point

- `main` and `origin/main` are R10 merge
  `341a69bf855f48f90cbecfb5c6872c3bf8c28360`.
- Draft PR #80 currently points at
  `e45a456eaaa1a43d5be61711dd6ce02962035c43`; its 20 exact-head checks are
  terminal `SUCCESS`.
- That result does not cover the current uncommitted rc6 continuation. The
  continuation is implementation work until its own commit, review and
  exact-head CI complete.
- R8–R10 delivered crypto, opaque relay, trust/terminal foundations and fixed
  Runtime process composition. The browser page still has no live terminal
  controller. The formal Project-to-first-workspace path is implemented in the
  local rc6-B checkpoint but awaits its own exact-head CI.

## Product outcome

The software outcome is one administrator workflow:

```text
READY Project + Claude/Codex
  -> verified Project binding
  -> typed Start
  -> current independent trust + ADMITTED
  -> input/output/resize
  -> Detach/reconnect
  -> exact generation-bound Stop
```

No step grants a browser a shell, filesystem path, process ID, tmux target,
plaintext terminal content at API, Runtime HOME, provider Secret or root
authority.

## rc6: production controller composition

rc6 is complete only after all three work units below integrate on one exact
controller path.

### A. API process ownership and lifecycle

Production has two explicit modes:

- `DISABLED`: WAW routes remain fail-closed and no WAW authority is created.
- `FILESYSTEM_V2`: one internal, fixed builder creates the entire WAW graph.

`FILESYSTEM_V2` may not accept a caller-supplied factory, socket path, UID/GID,
policy, Runtime callback or fragmented `app.state` component. Test fixtures use
named `test_only` construction exclusively.

The builder owns one process lock, public anchor, control client, bind
coordinator, authority epoch/nonce, `AttachmentAuthority`, authorization policy,
stream handler and work ledger. The ledger owns active HTTP/WS work, relay
cleanup, Audit executor futures, control detached work and exact detach
operations.

The state machine is:

```text
NEW -> STARTING -> RUNNING -> QUIESCING -> DRAINED -> CLOSED
                    \---- any uncertain identity/work/close ----> POISONED
```

Startup obtains the lock, validates fixed public inputs, transfers a provisional
cleanup owner, binds and classifies the Runtime epoch, restores Project bindings,
then publishes `RUNNING` atomically. Shutdown synchronously fences new HTTP/WS
work and INPUT/RESIZE, drains real work and Audit, closes the bound peer/client,
proves authority cleanup, closes the login executor, closes the database and
releases the lock last. A cancelled waiter does not cancel a shared close task.
Any incomplete step retains the lock and database state for process termination;
it never reports clean.

Only direct single-worker Uvicorn is supported. Fork must precede lifecycle
startup. An after-fork child closes inherited owner descriptors, fences its graph
and cannot issue WAW work.

### B. Project binding persistence and first use

A formal `READY` Project must reach first Start without browser-supplied
provenance or a prebuilt workspace row. The implementation adds:

- monotonic Project metadata revision;
- immutable, Project-scoped binding attempts with exact predecessor evidence and
  `PENDING`, `CURRENT`, `RECONCILIATION_REQUIRED` and `SUPERSEDED` state;
- Runtime durable `bindings-v1` validation and exact replay;
- first-use flow: reserve binding attempt -> Runtime attestation -> CAS current
  binding -> durable workspace intent -> typed Start;
- executable evidence state (`UNOBSERVED`, `VERIFIED`, `STALE`) rather than a
  fabricated executable fingerprint.

Only a Runtime typed proof for the current generation, host tuple and Runtime
epoch can mark executable evidence `VERIFIED`. Ticket issuance, Attach and a
confirmed running state require it. API or Runtime restart replays pending and
current bindings in deterministic Project order before the host/binding layer is
ready. A missing durable Runtime binding at revision greater than one fails
closed with `BINDING_BOOTSTRAP_REQUIRED`.

Migrations use expand then activate. Existing rows are never reverse-engineered
into a digest or fingerprint; unprovable nonterminal rows become reconciliation
work. Unsafe downgrade is rejected.

#### rc6-B first-use checkpoint

Commit `708acd8aa9dc2af945f5664a7ba983c192affde4` implements the typed first-use
flow and `workspace.workspace.executable_evidence.v1`. Its first exact-head run
failed only because the existing Project verifier released a descriptor before a
Linux inode-reuse check; fix `3ba85cb` retains a bounded descriptor per verified
key. The resulting `bbdd67c` exact head completed 20/20 checks. The exact
contract, failure fences, replay requirements and local validation are recorded
in [R11 rc6 first use](WAW_R11_RC6_FIRST_USE.md). This is not completion of
rc6-B: deterministic startup/restart replay and the remaining rc6 acceptance
evidence are still due.

### C. Browser controller and exact Stop

The existing browser crypto, wire, trust and bounded-terminal modules become one
controller. It obtains a fresh ticket and trust lease, opens the exact same-origin
binary WebSocket, and only exposes `CONNECTED` after local canary verification
and `ADMITTED`. It serializes output rendering before advancing the reconnect
cursor; lost ciphertext closes the attachment. INPUT has one owner and uncertain
input is never replayed. Resize is bounded and coalesced.

Stop fences browser INPUT/RESIZE synchronously, requests positive Detach cleanup,
then sends the generation-bound Stop. `pagehide`, freeze, unmount, selection/auth
change, provider loss and controller epoch change immediately fence publication.

### rc6 exit evidence

- lifecycle, singleton inode, fork, cancellation, pidfd, delayed Audit, detached
  task, database-close and lock-close tests;
- first Project Start, concurrent Start, response loss, API restart, Runtime
  restart, binding drift and migration tests;
- browser success and exact Stop controller tests with no early connection;
- Linux real-UDS/native evidence, full Backend matrix, Web type/lint/build and
  relevant E2E;
- independent architecture, security and test review; then exact-head CI, normal
  merge and read-back.

## rc7: deterministic composed failure injection

After rc6 merge/read-back, add test-only named checkpoints, manual promises,
fake clocks and partial-write sockets. No production environment, query or global
fault switch is allowed.

The matrix covers ticket, preparation, key/canary, commit/admission, input ACK,
output/render/GAP/redraw, resize, heartbeat, revoke, provider loss, API/Runtime
restart, shutdown, page lifecycle and Stop. Each case proves: no early
`CONNECTED`, one ticket burn, no uncertain input retry, no key continuation after
ciphertext loss, no post-fence publication, positive cleanup before writer
release, and no payload/key/ticket canary in persistent or diagnostic output.

## rc8: artifact and operations rehearsal

After rc7 merge/read-back, the release artifact builds native helpers from its
unpacked source and imports only from an artifact wheelhouse environment. A
synthetic key/peer/trust/PTY harness drives the artifact API, Runtime, RFC6455
and Unix sockets through attach, input, output, resize, detach and Stop.

An exact predecessor/candidate upgrade then rollback verifies the final
predecessor version, database, Project, Runtime-home and epoch non-secret
canaries, receipts and journal integrity. Artifact/log/report scans reject
payload, key and ticket canaries. This does not enable systemd WAW sockets or
reuse R12 host evidence.

## rc9: complete browser-selected bilingual UI

Only `navigator.languages[0]` is read once per browser document. A primary `zh`
selects `zh-CN`; all other, absent or malformed values select English. Later
preferences and `navigator.language` are ignored until reload.

One typed catalog covers common, auth, Dashboard, Codex, Claude, Workspace,
Projects, Doctor, Logs, Settings, errors and closed enums. English/Chinese key
sets match at build time. Known API codes map to local copy; server prose is not
rendered directly. Protocol values, IDs, error codes, AgentType, repositories,
branches, tmux, Claude and Codex remain technical English.

Each route/state combination is tracked in the rc9 locale manifest and tested at
1280x800 and 390x844 for language, overflow, focus and 44px controls. Terminal
tests use non-sensitive data and disable trace, video and screenshots.

## R12 boundary

R12 starts only with a concrete, authorized Linux target. Its evidence covers
systemd/tmpfiles identities and sockets, key custody, signed CRX/trustd install,
vendor CLI/login, PTY/devpts/cgroup/namespace/seccomp/LSM, reboot/recovery,
publication and support scope. CI or synthetic harnesses do not satisfy this
boundary.

## Ownership and delivery

Complex security, recovery and architecture work uses Sol. Defined local UI,
catalog, fixture and documentation work uses Terra. No agents concurrently write
the same modules. Each independently verifiable work unit updates the relevant
contract, current state, remaining plan and GitHub branch. A release candidate
only advances after terminal exact-head CI, normal merge and exact read-back.
