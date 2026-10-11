# Kebui K2 conversation architecture preparation

Revision: `k2-preparation-v1`, 2026-10-10. Status: **reviewable software design;
not a qualified S03 protocol or production enablement**.

## 1. Position and current gate

This is the bounded next preparation item in
[K2 and immediate next actions](project/KEBUI_PRODUCT_PLAN.md#20-immediate-next-actions),
under the existing software-decision delegation in
[governance](project/GOVERNANCE.md).
It prepares the admission package required by
[U3](project/KEBUI_UI_DELIVERY_PLAN.md#7-u3-首个聊天工作台的退出条件) and
[S03](project/FULL_CAPABILITY_DELIVERY_PLAN.md#3-阶段顺序能力归属与退出证据).
It neither declares that package accepted nor starts production U3/K3–K7 work.

The inspected base is main `9f8d20e325b6a17173a223bff7a2d14f0059fdd6`, tree
`06eb70dcb01c1ad65243a693c7207455d0d6455e`. Existing U2 pages, product identity
and bounded U1 prototype work are already delivered. The five public reference
sources have [19 observed images/frames](../design/kebui/PUBLIC_VISUAL_EVIDENCE.md);
older public-image UNKNOWN statements are historical, not a fresh task queue.
The [Cromma reference card PR169](https://github.com/ForceMind/agentbox/pull/169)
is qualified but still unmerged at this snapshot. Preparing this independent
document does not close that merge, U0 as a whole, or the release/host gates.

This change adds no route, migration, protocol enum, adapter, dependency,
production control, deployment setting or version bump. Existing terminal input
and A3 patch transport are not repurposed to implement conversation messages.

## 2. Verified starting point and operation matrix

The following is a **source inventory**, not a new host qualification:

| Operation / source | Claude Code | Codex | K2 treatment |
| --- | --- | --- | --- |
| Formal Project metadata / READY binding | Existing typed Project domain | Same | Select an existing authorized Project; no client cwd/root |
| WAW metadata, lifecycle start/status/stop | Existing fixed WAW actions | Same software action family | Keep original Workspace labels, admission and exact target |
| WAW attach, terminal input/output, resize, detach/reconnect | Existing WAW contract | Same software contract | Terminal bytes remain terminal bytes; not structured turns |
| Structured message acceptance, turn events, completion | No qualified S03 adapter | No qualified S03 adapter | Unavailable until agent-specific protocol evidence exists |
| Structured tool approval / turn interrupt | No qualified S03 adapter | No qualified S03 adapter | Unavailable; no terminal-text parsing or synthetic “yes” |
| Vendor history, Resume, rewind, archive, concurrent conversations | Not established by WAW | Not established by WAW | Separate S03 capability rows; no implicit adoption |
| Changes metadata / qualified bounded patch observation | Existing separate Project-scoped sources | Same | Link to existing surface; do not manufacture a result attachment |
| Generic Files, artifact bodies, automatic routing / handoff | Not admitted by K2 | Not admitted by K2 | Keep unavailable; later contracts/stages |

Source anchors:

- [WAW API](../apps/api/src/agentbox_api/workspaces.py): `WorkspaceMetadata`,
  existing lifecycle requests and attachment/detach handling.
- [WAW records](../packages/agentbox-core/src/agentbox_core/waw_models.py):
  `AgentWorkspaceSessionRecord` is one durable Project/AgentType identity;
  its lifecycle state is not a conversation or AI-task result.
- [Closed control codec](../packages/agentbox-protocol/src/agentbox_protocol/waw_control.py)
  and [WAW wire](../packages/agentbox-protocol/src/agentbox_protocol/waw_wire.py):
  exact lifecycle/terminal schemas; no structured turn or approval grant.
- [Recovery contracts](WAW3_RECOVERY_CONTRACTS.md) and
  [browser reducer](../apps/web/src/features/workspace/workspaceState.ts):
  scope/epoch/attempt fences and uncertain input; reuse principles, not identity.
- [Phase 11 approval schema](../packages/agentbox-core/src/agentbox_core/approval_schema_v1.py):
  `ConfirmationPurpose.PROVIDER_SECRET_PROVISION`, not Agent tool permission.
- [ADR0009](adr/0009-workbench-identity-and-content-boundary.md) and
  [WEV research](WORKSTATION_EVOLUTION.md): distinct identities, Runtime-owned
  content and structured, versioned approval prerequisites.

An Agent name appearing in a picker is not a capability declaration. A future
matrix entry must identify the fixed adapter revision, vendor/executable
evidence, execution kind, supported operation and rejection behavior. Preserve
supported / unsupported / unknown / stale as distinct source observations;
missing, unknown and stale evidence all disable the operation without claiming
the vendor cannot support it. Host tuple qualification remains separate from
the software matrix. No fall-through to another Agent is allowed.

## 3. Decisions and identity ownership

These choices narrow the planned design; exact serialized schemas and migrations
remain the finite follow-on work in section 10.

1. **Explicit Agent only.** First K2 selects `claude` or `codex` explicitly.
   Agent changes create a new explicit execution binding; they do not transfer
   an active turn, history, approval or credential. K5 routing is out of scope.
2. **One active turn per conversation.** No implicit queue, steer, parallel
   branches or “send on reconnect.” Busy submission is rejected visibly.
3. **Single existing administrator domain.** Conversation identity does not
   create collaborators, Hub tenants, cross-host access or a new permission role.
4. **Separate identities.** `conversation_id`, `turn_id`, `operation_id`, the
   administrator authentication Session, WAW Workspace and browser tab are
   distinct. A URL, tab, title or vendor handle grants no authority.
5. **Runtime owns execution.** The Control Plane owns authorized noncontent
   metadata; Runtime owns adapter handles, content and execution admission.
   No second supervisor, Job queue or arbitrary Runtime operation is introduced.
6. **No dual writer.** A structured adapter and a TUI attachment cannot both
   submit input to the same execution. The first profile must choose one owner
   and reject the other before admission. Runtime must atomically hold the writer
   reservation by underlying execution identity across tabs and conversations,
   not merely by conversation ID. Ownership uncertainty prevents admission.
   Read-only discovery of a vendor handle
   does not establish ownership or allow Resume/adoption of an external process.

The design's complete execution scope contains authenticated owner scope and
auth epoch; Project ID/revision and current binding revision/digest; host
installation ID/revision; Runtime epoch; execution kind; AgentType;
conversation identity/revision; execution generation; and current turn identity.
API authority and client attempt additionally fence each observation/operation.
Opaque vendor references remain Runtime-internal. The precise field encoding
must use canonical bounded types, reject extra/duplicate keys, overflow and
unknown enums, and distinguish opaque epochs from ordered counters.

Authorization is rechecked at admission and immediately before each side effect,
including after an await. A matching tuple is necessary but not authentication.
Trusted peer/channel provenance, current authentication, Project readiness and
adapter capability are independently required. Project archive/rebinding,
logout/revocation, host/Runtime change and scope replacement invalidate pending
content, writes and approvals before new events can be published.

Conversation metadata persistence must be additive and exclude prompt, output,
tool arguments, vendor history and credential bytes. A generated title/summary
is content too, not harmless metadata. Restart-safe operation identity may be
required for K2; it is not K3's durable cross-agent Task/Work Item. K3 gets its
own state/retention/migration contract and must not rename an existing Job.

## 4. Content path and limits

The intended path is Browser ↔ separately admitted encrypted S03 content channel
↔ Runtime fixed adapter. API/Worker may carry bounded opaque records only under
an accepted S03 relay contract. This document does not authorize such a relay or
select keys, pins, cipher contexts, routes or production custody. No plaintext
HTTP fallback, Control Plane content storage, prompt-in-URL, analytics payload,
Audit body, log body, exception body or clipboard capture is permitted.

Neither WAW terminal frame types nor A3 patch records acquire a second meaning.
Only reviewed cryptographic primitives may be reused; S03 needs independent
domain/version/context/admission, direction and counter rules, lifetime/cleanup,
backpressure, test vectors and cross-language evidence. Existing A3 evidence
does not qualify this new prompt/streaming content purpose.

The first design profile proposes these **hard maxima to qualify**, not current
settings and not permission to enlarge any existing transport limit:

| Resource | Proposed ceiling | Exhaustion behavior |
| --- | --- | --- |
| One user message | 16 KiB UTF-8 after canonical validation | Reject before admission; no silent truncation/split |
| One decoded content event | 32 KiB including its structured envelope | Reject before publication; never parse an oversized suffix |
| Browser visible content | 1 MiB encoded content and 256 events, whichever first | Explicit bounded/truncated view; no hidden transcript growth |
| Active turn / new-message submission | One per conversation and underlying execution | Reject a second turn; do not queue |
| State-changing control operation | One in flight per underlying execution, separate from active-turn count | Exact approval reply/interrupt remains possible during a turn; concurrent conflicts read the owner result or reject busy |
| Pending approval | One per active turn | Reject conflicting second request until adapter semantics qualify |
| Approval lifetime | At most 60 seconds and never longer than vendor deadline | Expire fail closed; reconnect does not extend it |

Read-only status reconciliation consumes neither a turn nor a writer slot.
The executable profile must reserve bounded capacity for denial/cancellation
and keep the existing exact-Stop path independent of message/output backpressure;
new-message admission cannot starve those controls. An unresolved conflicting
control still requires authoritative resolution, not concurrent blind writes.

The wire slice must separately bound raw/ciphertext length, depth, field counts,
string expansion, parser work, aggregate Runtime/client concurrency and retained
event/operation metadata. Compression and file attachments are absent in v1.
No implementation may begin with only the per-message table and an unbounded
process-wide allocation. Overflow must not discard the only terminal/cancellation
observation and then claim success; a metadata read must report the authoritative
state independently of a truncated display.

Initial content is transient in the admitted Runtime/browser owner. No IndexedDB,
localStorage, Service Worker cache, server transcript, vendor-home scan or backup
inclusion is inferred. Page/scope loss clears local plaintext best-effort and
revokes content authority; this does not promise secure memory erasure. Any
history retention, replay window, vendor logging or export policy must be explicit
before enabling that capability. Content expiry does not fabricate turn failure
or authorize a replacement request.

## 5. State, provenance and event ordering

Render four independent facts rather than one green “done” badge:

- transport: disconnected / connecting / admitted / interrupted;
- operation observation: pending / accepted / rejected / unknown;
- turn observation: idle / running / awaiting approval / awaiting input /
  completed / failed / canceled / unknown, only when the adapter proves it;
- existing Workspace lifecycle, if the execution actually has a WAW binding.

The turn labels are proposed semantic outcomes, not added production enums.
`completed` means the qualified adapter reported completion of that exact turn;
it does not assert the requested work is correct, tests passed, changes exist,
or a K3 Task succeeded. A CLI exit, Job success, idle screen, disconnect,
terminal phrase or synthetic prototype event proves none of these outcomes.

Every visible fact needs its exact source, execution scope, observation revision
and currentness. Untrusted provider text cannot be promoted into an authoritative
status, tool call, approval, file reference or test result. A future event profile
must distinguish typed metadata from encrypted content and fix a Runtime-owned
sequence within one execution generation. Same-sequence/different-payload is a
protocol fault; identical duplicates are no-ops; stale scopes cannot mutate the
new view. Gaps and missing terminal events produce an explicit incomplete state
and read reconciliation, not invented output or automatic write retries.

Terminal observations are final within their turn. Later content cannot revive
it; late cancellation cannot overwrite a positively observed completion. Races
are resolved by the Runtime operation owner, and the browser displays the read
result. A new turn requires a new accepted identity and explicit user action.

## 6. Message acceptance and unknown outcomes

An idempotency key names one exact attempted operation in the authenticated
owner, Project, conversation and execution scope. It is not a content digest or
authorization token. Same-key/same-operation returns the original status;
same-key/different-body or target is rejected. Content equality is checked only
inside Runtime using the accepted content protocol, never by exposing prompt
hashes to the Control Plane. Client attempt IDs do not replace server deduplication.

The planned linearization point is the Runtime owner's committed acceptance of
the operation **before** invoking the vendor. Admission/ledger capacity must be
reserved first. The implementation contract must define atomic persistence and
crash windows: before acceptance, after acceptance/before vendor delivery, after
vendor delivery/before acknowledgment, and after terminal observation. If vendor
delivery cannot be proven, the record is `unknown`, not “safe to send again.”
No exactly-once vendor execution claim follows from a local acceptance ledger.

After a timeout, lost acknowledgment or reconnect, query that operation's state.
Do not replay the message, assign a new key for the same uncertain operation,
or automatically restart the Agent. A definitive rejected-before-dispatch result
may allow an explicit new user attempt; `unknown` blocks dependent writes until
the qualified recovery procedure resolves it. An evicted/expired/missing ledger
entry must never be interpreted as proof that an old write did not happen.
The deduplication retention horizon, tombstones and restart durability are blocking
schema/retention decisions for the first executable contract slice.

## 7. Approval contract

An approval is a Runtime-adapter-issued request for one concrete operation in
one current turn. It binds the complete scope, request ID, monotonic request
revision, immutable operation descriptor and authoritative expiry. Tool name,
arguments, affected target, consequences and changed scope are content carried
only over the qualified channel. Display-safe metadata never substitutes for
reviewing that descriptor. Unsupported or unrenderable requests fail closed.

Approval responses are a closed allow-once / deny choice for the exact request
and revision. No free-form “yes,” remembered choice, policy wildcard, terminal
keystroke or Provider Secret confirmation is accepted. The Runtime atomically
checks current identity, descriptor revision, deadline, pending status and single
consumption immediately before delivering the decision. Two tabs/device races
cannot resolve it twice; duplicate same responses read the first result, while
conflicts report the already-final status.

The lifetime is the minimum of 60 seconds, the actual vendor deadline and the
admitted execution/content lifetime. Unknown vendor expiry is unsupported until
an adapter supplies a safe bounded contract. Runtime-authoritative elapsed time
and fail-closed clock handling are mandatory; browser countdown is informative.
Updated descriptors require a new revision and explicit new review; a timer
cannot refresh merely because the page reconnects. Cancel/Stop, revocation,
binding change, terminal turn or expired authority invalidates the request.

Timeout/deny attempts an explicit vendor denial only where the qualified adapter
supports it. A missing acknowledgment remains an unknown outcome and fences
later decisions; the UI does not claim the tool was prevented. If the vendor
can proceed despite denial/expiry or lacks reliable pending-request ownership,
that operation is unsupported. These semantics require adapter tests and real
vendor evidence before any approval button becomes active.

## 8. Cancellation, Stop and recovery

| User action / event | Required meaning | Must not imply |
| --- | --- | --- |
| Close view / change tab | Drop view-local ownership; no new execution action | Turn canceled or process stopped |
| Disconnect / detach | End that connection according to its contract | Vendor work stopped |
| Interrupt current turn | Separate qualified adapter operation for exact turn | WAW exact Stop or rollback of side effects |
| Exact Stop | Existing precise owned process target and positive cleanup proof | Broad host kill, pending turn cancellation alone |
| Cancel an unaccepted submission | Local cancellation only if not dispatched is proven | Retraction after uncertain send |
| Refresh / return / reconnect | Reauthenticate and read current scope/state | Re-send prompt, approval, Start or Resume |

There is no fallback from unsupported turn interrupt to Ctrl-C, arbitrary signal,
or wider Stop. If a future structured execution does not have an existing WAW
owned process binding, the WAW Stop action cannot be pointed at it by renaming
IDs. Its lifecycle/cleanup contract must first qualify through the same authority
boundary, including failure recovery. A process-stop observation also does not
prove undoing already-completed external side effects.

On loss of visibility, network or authentication, pending controls are fenced and
the observation becomes stale. Return performs read-only reconciliation, then
requires an explicit action to reconnect content. Browser Back/Forward and
Agent/Project switching cannot restore old write authority. Runtime restart or
binding/generation change invalidates old vendor handles, cursors and approvals;
history discovery is not Resume/adoption authority. Unsupported recovery remains
visible `unknown`/reconciliation-required, with no speculative restart.

## 9. Required adversarial acceptance cases

These are planned tests, **not tests run by this documentation change**. Each
requires Python/Web agreement where both consume the contract, focused negative
tests, independent source review and exact-head CI before its implementation is
called qualified. Browser/vendor/host evidence must be labeled separately.

| ID | Case | Required result / observation |
| --- | --- | --- |
| K2-T01 | Swap each owner/auth/Project/binding/host/epoch/Agent/conversation/turn field | Reject before content publication or side effect |
| K2-T02 | Unknown operation, extra/duplicate keys, numeric overflow, malformed UTF-8 | Closed rejection; no fallback to shell/terminal |
| K2-T03 | Two tabs submit same key; same key with changed body/target; different keys/conversations or TUI compete for one execution | One accepted operation and one writer; conflict does not dispatch; a current approval response is not blocked merely by an active turn |
| K2-T04 | Crash at every acceptance/vendor/ACK window; ledger missing after restart | Query authoritative status; uncertain delivery never auto-replays |
| K2-T05 | Duplicate/out-of-order/gapped events, same sequence with different content | No resurrection or invented completion; explicit incomplete state |
| K2-T06 | Delayed old response after Project/Agent switch, logout or host replacement | New scope unchanged; old controls remain fenced |
| K2-T07 | Approval revised/expired/resolved concurrently; conflicting decisions | At most one resolution for exact revision; no renewed TTL |
| K2-T08 | Approval timeout/deny with vendor ACK lost or vendor still running | Unknown/fenced outcome; no false prevention claim |
| K2-T09 | Interrupt races completion; Stop fails cleanup; detach succeeds | Preserve exact authoritative facts; no broad Stop or false canceled |
| K2-T10 | Each byte/event/concurrency budget at limit and limit+1; slow consumer | Bounded allocation and explicit rejection/truncation; state still inspectable |
| K2-T11 | Prompt/tool/output attempts HTML, link, path, forged approval or status injection | Text remains untrusted; no new request/resource load/authority |
| K2-T12 | Hidden/offline/reload/Back/Forward then reconnect | Reads only until explicit action; no repeated message/approval |
| K2-T13 | Inspect API/Worker DB, audit, logs, errors, cache and browser persistence | No prompt/output/tool/credential payload or content-derived title/hash |
| K2-T14 | Fixed Claude and Codex adapter tuples, including unsupported capability | Each advertised operation actually qualified; unsupported stays disabled |

## 10. Finite implementation handoff and stopping conditions

Do not turn this checklist into repeated UI/CI runs on an unchanged baseline.
The preparation outcome is this reviewed architecture and exact remaining gaps.

1. **Metadata and reducer contract:** freeze canonical scope/event/operation
   schemas, complete aggregate budgets, durable deduplication/tombstone retention
   and crash outcomes. Implement only pure validation/reducer/negative fixtures
   first, isolated from production routes and Runtime construction.
2. **Fixed adapter evidence:** inspect the intended installed CLI versions and
   their structured APIs. Freeze each Agent/operation matrix, request/response
   sources, approval deadline ownership, cancellation and crash behavior.
   Source inspection/fixtures and actual authorized CLI qualification are distinct.
3. **S03 content contract:** independent domain-separated authenticated channel,
   ownership/lifetime/retention, vectors, interop and source/secret isolation.
   No production keys or new persistent access as a side effect of development.
4. **Integrated inert candidate:** use typed synthetic adapters and approved U1
   design to exercise T01–T14 without production route imports. Obtain independent
   security/source review and required exact-head software checks.
5. **U3 admission decision:** record accepted revisions, actual implemented matrix,
   true status/content sources and unresolved capabilities. Only then schedule
   bounded production wiring. Complete remaining UI/release gates explicitly;
   unmerged PR169 or real-host/Secret/release limits are never silently waived.

Steps 2 and 3 require their own frozen source/wire profiles before integration;
the complete scope is not declared executable by this preparation document.
An unresolved capability blocks only that capability, not safe independent
schema/design work. K3 durable Tasks, automatic routing, Agent handoff, external
notifications, persistent memory, collaboration, final brand assets, DNS and
release/deploy are outside this batch.
