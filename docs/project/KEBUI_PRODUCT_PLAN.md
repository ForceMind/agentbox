# Kebui Product Evolution Plan

Status: approved strategic direction; staged implementation required  
Date: 2026-10-07  
Repository: `ForceMind/agentbox`

## 1. Goal

Evolve the existing AgentBox project into **Kebui**, a conversation-first,
open-source AI workspace where a user can ask for work once and let Claude,
Codex and future agents execute it through durable, typed and auditable runtime
boundaries.

This is a product evolution, not a rewrite.

The existing AgentBox work remains valuable because it already addresses the
hard layer behind a conversational product:

- runtime discovery;
- project ownership;
- session lifecycle;
- detach/reconnect;
- exact Stop;
- remote execution;
- provider/login separation;
- typed API boundaries;
- secrets and privilege separation;
- deployment and recovery.

Kebui should place a simpler product model above that foundation.

## 2. Product model

Long-term user model:

```text
User
  |
  | natural-language intent
  v
Kebui Conversation
  |
  +-- context / project
  +-- task state
  +-- approvals
  +-- artifacts
  +-- memory
  |
  v
Orchestration
  |
  +-- Claude Code
  +-- Codex
  +-- OpenCode
  +-- browser/tool agents
  +-- future providers
  |
  v
AgentBox Runtime / future Kebui Runtime
  |
  +-- local machine
  +-- remote Linux host
  +-- project workspace
  +-- controlled tool actions
  +-- durable session lifecycle
```

The user sees conversation, task progress and results.

The system may expose Runtime/Provider/Session detail for advanced use, but those
concepts should not be mandatory navigation for ordinary work.

## 3. Product principles

### 3.1 Conversation is the control plane

Conversation is not a cosmetic wrapper around terminals. A message should map
to a durable, inspectable work item.

### 3.2 Agents are execution capabilities

Claude, Codex and future agents are not the product's primary navigation model.
They are capabilities Kebui can invoke.

### 3.3 Explicit control remains available

Advanced users can still choose or mention an agent explicitly. Automatic
routing must never remove the ability to inspect or override a choice.

### 3.4 Persistence is first class

Tasks should survive:

- page refresh;
- device change;
- disconnect/reconnect;
- long-running agent sessions;
- agent handoff where supported.

### 3.5 Open execution boundaries remain non-negotiable

Kebui must not turn conversation into an arbitrary remote shell.

All new conversational actions must terminate in existing or newly reviewed
typed actions with explicit authority.

## 4. Delivery strategy

Do not stop the current release/UI work to perform a brand rewrite.

Deliver Kebui as a sequence of bounded product slices.

Each slice should follow the repository's existing:

`feature branch -> CI -> merge -> exact read-back`

process.

No phase below authorizes real production deployment, paid third-party calls,
new Secret authority or destructive host actions by itself.

### 4.1 Reference-led UI design is a required delivery stream

The Owner additionally requested better UI design using the previously supplied
projects. The concrete design requirements are now in
[KEBUI_UI_DESIGN.md](KEBUI_UI_DESIGN.md); the phase mapping and acceptance work
are in [KEBUI_UI_DELIVERY_PLAN.md](KEBUI_UI_DELIVERY_PLAN.md).

Cromma supplies the conversation/contact metaphor; Cindy supplies a unified
user-facing identity and continuous workspace reference. The existing Paseo,
HAPI, CloudCLI and Yep Anywhere reference set and AgentBox prototype are retained.
Reference claims, screenshots, design proposals and implemented capabilities must
remain distinct. The UI stream is not a second roadmap or a product rewrite.

The target is a conversational front door with a serious workbench behind it:
project-bound work, visible actual agents, explicit approvals, inspectable
results, and understandable failure/recovery states on desktop and mobile.

Before a new product surface is implemented, deliver visible design artifacts
and a usable synthetic prototype, not only documentation. Current rc31 page
closure continues independently; future Chat/Task capabilities do not appear as
working production controls until their contracts and implementation exist.

## 5. Phase K0 — Brand freeze and asset reservation

### Purpose

Make the brand durable without touching runtime behavior.

### Deliverables

- brand document;
- product evolution plan;
- Chinese name `科布`;
- official product pronunciation `KEH-boo`;
- primary slogan `One conversation. Every agent.`;
- primary domain target `kebui.com`;
- defensive `qebui.com` recommendation;
- preliminary software/AI trademark and naming-conflict review before launch;
- reserve relevant repository/social/package names where practical.

### Acceptance

- Owner confirms domain registration;
- no repository claims ownership before confirmation;
- no mass rename;
- no user-visible production launch.

## 6. Phase K1 — Product identity layer

### Purpose

Introduce Kebui as the strategic user-facing product name while keeping
AgentBox internals stable.

### Deliverables

- README brand section;
- website/product shell wording;
- application title/metadata plan;
- `Kebui` product icon/logo direction;
- reference board, visual tokens and desktop/mobile design artifacts as defined
  by the U0/U1 design stream;
- migration glossary:
  - Kebui = product;
  - AgentBox Runtime = execution engine during transition;
  - Claude/Codex = agent capabilities;
- compatibility policy for old links, service names and documentation.

### Constraints

Do not rename package/service/database/API identifiers merely for aesthetics.

### Acceptance

Existing tests, deployment names and compatibility contracts remain unchanged
unless the slice explicitly covers them.

## 7. Phase K2 — Conversation shell

### Purpose

Make conversation a first-class product surface without automatic orchestration
yet.

### Initial scope

A user can open a Project and talk through one conversation surface.

The user may explicitly choose an existing supported agent:

- Claude Code;
- Codex.

The conversation presents:

- user message;
- selected agent;
- task/session state;
- streaming or bounded output already permitted by current contracts;
- completion/failure;
- reconnect state;
- links to existing Project/Changes/artifact surfaces.

### Important boundary

K2 is **not** "browser sends arbitrary commands".

Messages must map to explicit supported agent/session operations.
Structured conversation, turn, content and approval contracts must be qualified
through the existing S03/WEV route before production wiring. Do not parse TUI
strings into fabricated tool events, or equate Job/process completion with AI
task success. Prototype future surfaces remain visibly synthetic.

### Evidence required to exit K2

Record the accepted S03/WEV contract revision, supported Agent/operation matrix,
Project/session/turn ownership and source of each visible status. Qualify message
idempotency, stale/duplicate events, interruption, reconnect without replay,
content admission and approval expiry. Link the exact implementation head,
regressions and actual browser paths; synthetic U1 output alone cannot pass K2.
Links to artifacts or Files remain unavailable until their own contracts qualify.

### Illustrative acceptance example (future behavior, not implementation evidence)

```text
User: @codex investigate the failing test.

Kebui:
Codex started in AgentBox.
Working...

Kebui:
Codex finished.
2 files changed.
Review changes?
```

## 8. Phase K3 — Durable chat-to-task bridge

### Purpose

Separate a user's conversational intent from an individual terminal/session.

### New first-class object

Introduce a versioned, typed **Task/Work Item** contract if one does not already
satisfy the requirement.

A task should have at minimum:

- owner;
- Project;
- originating conversation/message;
- requested action;
- chosen agent;
- state;
- timestamps;
- permission/approval state;
- execution/session references;
- result summary;
- artifact references;
- failure reason;
- cancellation semantics.

### Required states

Avoid a single ambiguous "running" state. Model at least:

- pending;
- awaiting approval;
- queued;
- running;
- waiting on agent/user where needed;
- succeeded;
- failed;
- canceled.

### Acceptance

A page refresh or reconnect does not lose the task's identity or final state.
Prove request-to-task deduplication, authorized durable-state recovery and explicit
unknown/interrupted outcomes. Retried reads must not replay a write or approval.
K3 consumes qualified K2/S03 events; an existing Job or exited CLI is not a Task
success signal. Record content-retention, cancellation and result-source evidence
before enabling each surface in production.

## 9. Phase K4 — Agent handoff and review

### Purpose

Allow one work item to involve more than one agent while preserving ownership
and auditability.

Example:

```text
User:
Fix this bug and have another agent review it.

Kebui:
Codex is implementing.
Claude will review after tests pass.
```

### Requirements

- each handoff is explicit in the task timeline;
- the user can inspect which agent performed which step;
- no hidden authority escalation;
- each agent gets only the Project/context it is allowed to receive;
- cancellation semantics cover the whole task and individual stages;
- no agent may inherit another agent's secret authority by implication.

## 10. Phase K5 — Policy-based agent routing

### Purpose

Let the user state intent without choosing Claude or Codex manually.

Example:

```text
User:
Review this PR and fix any straightforward test failures.
```

Kebui may choose agents according to a visible policy.

### Routing inputs

Potential inputs:

- task type;
- Project policy;
- agent availability;
- required capabilities;
- owner preference;
- cost policy, when explicitly configured;
- privacy/data-location constraints;
- current session state.

### Requirements

- routing policy is deterministic or explainable enough to audit;
- user can override agent selection;
- no silent paid call or unsupported vendor action;
- failures do not trigger unbounded automatic retries;
- agent selection does not redefine authorization.

### Acceptance

The timeline records:

- selected agent;
- reason/policy identifier;
- override if any;
- fallback if any.

## 11. Phase K6 — Persistent personal workspace

### Purpose

Make Kebui useful across many conversations and devices without forcing the user
to recreate context.

### Capabilities

- Project-linked conversation history;
- durable task timeline;
- user-selected durable preferences;
- explicit memory/context boundaries;
- artifact/result history;
- resume from desktop/mobile;
- notification of completed long-running work.

### Privacy requirement

Memory is not an excuse for indiscriminate retention.

Define separately:

- transient conversation context;
- Project state;
- durable user preference;
- secrets/credentials;
- agent session material;
- artifacts.

Each needs its own retention and visibility contract.

## 12. Phase K7 — Human + agent collaboration

### Purpose

Support the product direction where humans and agents can coexist in the same
work conversation.

Possible model:

```text
Project room
├─ Owner
├─ teammate
├─ Kebui
├─ Codex
└─ Claude
```

Example:

```text
Owner:
@Kebui turn our decision into an issue, let Codex implement it,
then ask Claude to review.

Kebui:
Issue #231 created.
Codex is implementing.

Codex:
PR #232 opened.

Claude:
Review complete. Two changes requested.

Kebui:
Both changes are fixed. CI is green. Merge?
```

### Important

This is a later collaboration layer, not a requirement for the first Kebui
conversation release.

Do not build a social network before the single-owner workflow is excellent.

## 13. Phase K8 — Runtime naming decision

Only after the user-facing Kebui product is stable should the project decide
whether to rename AgentBox internals.

Options:

### Option A — permanent split

- Kebui = product;
- AgentBox Runtime = open execution engine.

Advantages:

- preserves repository/release history;
- makes runtime identity explicit;
- reduces migration risk.

### Option B — full Kebui migration

- AgentBox Runtime -> Kebui Runtime;
- repo/package/service naming migrates through compatibility aliases;
- old install/upgrade paths remain supported for a defined period.

A separate ADR is required before Option B.

## 14. UI implications

The concrete reference matrix, desktop/mobile layouts, component behavior,
full-page inventory and design acceptance requirements are maintained in
[KEBUI_UI_DESIGN.md](KEBUI_UI_DESIGN.md). See
[KEBUI_UI_DELIVERY_PLAN.md](KEBUI_UI_DELIVERY_PLAN.md) for staged visual artifacts,
interactive prototypes and implementation mapped to K0–K8 and S00–S14.

The long-term navigation should increasingly prioritize user work over
infrastructure nouns.

Likely primary surfaces:

- Chats / Work;
- Projects;
- Tasks;
- Artifacts / Changes;
- Settings.

Advanced/system surfaces can include:

- Agents;
- Runtimes;
- Providers;
- Diagnostics.

Do not hide operational truth. Reduce the need to understand it.
Do not claim a rebrand or a token/palette change alone completes the UI redesign.

## 15. Mobile direction

Kebui should work naturally as a mobile control surface.

Mobile does not need to replicate a full terminal IDE.

High-value mobile actions include:

- send a work request;
- inspect agent/task progress;
- answer an approval;
- review a concise change/result summary;
- reconnect to an existing task;
- receive completion/failure notifications;
- explicitly stop/cancel a task.

Physical mobile qualification remains separate from responsive screenshots.

## 16. API and architecture implications

Future conversation APIs should remain versioned and typed.

Do not introduce endpoints equivalent to:

```text
POST /shell
POST /run-arbitrary-command
POST /filesystem
```

Prefer contracts such as:

```text
POST /conversations/{id}/messages
POST /tasks/{id}/approve
POST /tasks/{id}/cancel
POST /tasks/{id}/agent-selection
GET  /tasks/{id}
GET  /tasks/{id}/timeline
```

Exact APIs require architecture review; these names are illustrative, not frozen.

The control plane decides; the runtime executes allowlisted capabilities.

## 17. Security requirements for conversational control

Conversation increases usability and therefore increases the need for precise
authority boundaries.

Every consequential operation must preserve:

- authenticated owner;
- Project ownership;
- current session/task ownership;
- CSRF/origin protection where applicable;
- explicit approval when required;
- replay protection;
- stale-response isolation;
- bounded output and retention;
- cancellation semantics;
- audit record.

Natural language must never itself become an authorization token.

## 18. Product metrics

Do not optimize first for message count.

Useful product metrics later may include:

- time from user intent to first meaningful action;
- work items completed without manual agent switching;
- reconnect/resume success rate;
- task failure recovery;
- approval response latency;
- percent of tasks with clear final state;
- agent routing override rate;
- user-visible retries;
- Project/context re-selection frequency.

A good Kebui experience should reduce manual orchestration.

## 19. Rollout order

Recommended order after the current bounded UI/release work:

1. confirm brand/domain assets;
2. add product identity copy without runtime rename;
3. design and freeze K2 conversation contract;
4. implement explicit-agent conversation shell;
5. make chat intents durable tasks;
6. add agent handoff/review;
7. add policy-based routing;
8. add durable personal workspace features;
9. add collaborative human+agent rooms;
10. decide final runtime/repository rename.

Current production UI closure is U2, not a claim that the U1 Kebui redesign is
already implemented. U4 covers K4 handoff, K5 routing and K6 persistent work in
that dependency order; U5 covers K7 collaboration. Each capability keeps its
existing S-stage prerequisites and separately qualified data/permission contract.

The U0/U1 design stream may prepare reference boards and synthetic desktop/mobile
prototypes before this rollout, without displacing current rc31 closure. It does
not authorize production wiring or early release of later capabilities.

Do not jump directly to automatic multi-agent routing.

## 20. Immediate next actions

Brand/product planning actions:

1. Owner confirms whether `kebui.com` and optionally `qebui.com` were
   registered.
2. Run a dedicated naming/trademark conflict review before public launch.
3. Keep the current repository and runtime names unchanged for now.
4. Complete the existing bounded UI/release plan already in progress.
5. After that work reaches its planned gate, create a dedicated Kebui
   conversation architecture document for K2.
6. Prototype the chat control surface against synthetic/typed existing
   Project/agent contracts before changing runtime authority.
7. Only then schedule implementation slices.

The UI planning deliverable is now documented. Its next visible deliverables are
reference-backed desktop/mobile designs and the synthetic interactive prototype
specified in U1; they are not yet implemented by this documentation change.

## 21. Success criterion

Kebui succeeds when the ordinary user can think:

> "I tell Kebui what I want."

instead of:

> "I need to decide which agent, find its session, open its console, manage its
> runtime, remember the context, and move the result back myself."

The implementation may remain sophisticated.

The interaction should become simple.
