# Kebui Brand Direction

Status: strategic product and brand direction  
Date: 2026-10-07  
Repository: `ForceMind/agentbox`

## 1. Decision

The user-facing product brand is **Kebui**.

Chinese brand name: **科布**.

Kebui is intended to become the conversational product layer above the existing
AgentBox execution/runtime foundation. This document does **not** rename the
repository, packages, services, APIs, database identifiers, runtime authorities,
or release artifacts yet. Those changes require a later migration gate.

Current transition model:

```text
Kebui
└─ user-facing AI workspace and conversation layer
   └─ AgentBox Runtime
      ├─ Claude Code
      ├─ Codex
      ├─ OpenCode / future agents
      ├─ browser/tool integrations
      └─ local and remote execution
```

The immediate engineering roadmap remains valid. Kebui is the strategic product
direction that the existing AgentBox work should grow into.

## 2. Name and pronunciation

### Written name

**Kebui**

Five letters. Capitalization in product prose should be `Kebui`, not
`KEBUI`, except where an all-caps wordmark is intentionally used.

### Official product pronunciation

For the product, use the simplified two-syllable pronunciation:

**KEH-boo**

Suggested IPA for brand guidance: **/ˈkɛ.buː/**.

Chinese: **科布（kē bù）**.

The product pronunciation is a deliberate brand pronunciation. It is **not** a
claim to reconstruct the exact historical pronunciation of an ancient Egyptian
name.

### Name inspiration

Kebui is inspired by **Qebui**, a name used in later literature for the Egyptian
north wind deity. Historical and Egyptological sources associate `qbw` with a
cool or refreshing north wind and with the lexical root `qbb`, "to be cool".

The brand uses this as an **inspiration**, not as a literal religious identity.

The useful metaphor is the wind:

- it is not the destination;
- it is the force that carries movement between places;
- it can be present without becoming the object of attention;
- it connects intention to motion.

That maps naturally to Kebui's product role: the user expresses intent once,
while Kebui coordinates the agents, runtimes and tools that actually do the work.

### Historical-source caution

Do not market the name as an exact ancient-Egyptian transliteration or exact
historical pronunciation. The safe wording is:

> Kebui is inspired by Qebui, the Egyptian north-wind figure, and by the idea of
> a cool wind that carries movement.

References for the underlying historical motif:

- Lewis Spence, *Myths and Legends of Ancient Egypt* (1915), minor-deities
  section describing Qebui as the north wind.
- Oxford research discussing Egyptian `qbw` as a cool wind and its relation
  to `qbb`, "to be cool":
  https://ora.ox.ac.uk/objects/uuid:d0e387f0-084f-4b0e-b539-4ecef7fdac87

## 3. Product meaning

Kebui is **not another model**.

Kebui is the place where the user's existing and future AI agents work together.

The product should let a user say what they want in one conversation while the
system handles:

- Project context;
- durable task state;
- agent selection;
- Claude/Codex/other agent sessions;
- local or remote execution;
- approvals and permissions;
- progress and failures;
- artifacts and results;
- reconnection across devices.

The user should not need to understand Runtime, Provider, Session or Harness
terminology for ordinary work.

Advanced users may still explicitly choose an agent or execution path.

## 4. Core positioning

### Primary English one-liner

> **Kebui is an open-source AI workspace where you talk once and let the right
> agents do the work.**

### Primary Chinese one-liner

> **Kebui（科布）是一个开源 AI 工作空间。你只需要通过对话表达意图，它会调用合适的 Agent 持续替你完成工作。**

### Primary slogan

> **One conversation. Every agent.**

Chinese:

> **一次对话，调动所有 Agent。**

### Supporting lines

> **Talk to Kebui. Work gets done.**

> **Your agents. One workspace.**

> **Open source. Self-hostable. Yours.**

> **Kebui isn't another model. It's where your agents work.**

The first slogan is the default. Do not use several slogans on the same primary
surface.

## 5. Brand promise

Kebui should make four promises:

1. **Conversation first**  
   The user communicates intent in natural language instead of manually
   navigating between agent consoles.

2. **Agent neutral**  
   Kebui must not be defined by one model vendor. Claude, Codex and future
   agents are interchangeable execution capabilities where contracts allow it.

3. **Persistent work**  
   Work continues as tasks and sessions rather than disappearing with a single
   request/response.

4. **User control**  
   Open source, self-hostability, explicit permissions and typed execution
   boundaries are part of the product identity, not implementation trivia.

## 6. Open-source message

Recommended public statement:

> **Your agents shouldn't live inside someone else's black box. Kebui is open
> source and built to run where your work lives.**

Kebui should preserve the existing AgentBox security principles:

- no Browser -> arbitrary shell gateway;
- no generic filesystem/process gateway;
- typed and allowlisted Runtime actions;
- explicit privilege boundaries;
- separated Provider/Runtime/Login/Pairing identities;
- non-root Web/API/Worker;
- no silent expansion of Secret authority;
- visible approvals for consequential operations.

"Open source" must not be used to imply that all third-party models, agent
vendors or remote services are themselves open source.

## 7. Product personality

Kebui should feel:

- calm;
- capable;
- concise;
- reliable;
- action-oriented;
- technically transparent when needed;
- never over-eager or theatrical.

Preferred interaction:

> Got it. Codex is checking it.

> Found the issue. Claude is reviewing the fix.

> Done. Tests passed and PR #142 is open.

Avoid default assistant filler such as excessive congratulations or repeated
"happy to help" language.

Kebui is not primarily a companion chatbot. It is the person in the conversation
who understands the request and gets the work moving.

## 8. Interaction language

The long-term product metaphor is **conversation as the control plane**.

A normal user should be able to write:

> Fix yesterday's CI failure and open a PR.

Kebui should be able to present a visible execution trace such as:

```text
Kebui
├─ identified project: AgentBox
├─ Codex: investigating
├─ Claude: waiting for review
├─ tests: queued
└─ PR: pending
```

Then:

```text
Kebui
├─ Codex: complete
├─ Claude review: complete
├─ tests: passed
└─ PR #142: opened
```

Advanced explicit routing can remain available:

```text
@codex implement this
@claude review it
```

but ordinary users should not need it.

## 9. Brand architecture during migration

Use a two-layer architecture first:

### Kebui

User-facing product identity:

- website;
- chat experience;
- mobile/desktop identity;
- future collaboration layer;
- product marketing;
- public brand voice.

### AgentBox Runtime

Transitional technical identity:

- existing runtime implementation;
- existing repository history;
- service/package compatibility;
- security contracts;
- current release qualification evidence.

Do **not** mass-rename internals in the first branding change. Rename only after
compatibility, packaging, migration and release implications are explicitly
reviewed.

Possible long-term outcomes:

1. keep `AgentBox Runtime` permanently as the open execution engine; or
2. migrate it to `Kebui Runtime` with compatibility aliases and a versioned
   migration.

That decision is intentionally deferred.

## 10. Visual direction

Use the north-wind story as an abstract design source, not as an Egyptian theme.

Preferred visual ideas:

- flow;
- direction;
- air/current;
- motion paths;
- subtle conversation shapes;
- a simple K-derived mark;
- distributed points converging into one route.

Avoid defaulting to:

- pyramids;
- pharaoh imagery;
- scarabs;
- faux hieroglyphics;
- decorative "Egyptian" gold;
- literal four-headed-ram mascots.

The mythology is a brand root, not a UI skin.

No final palette is frozen by this document.

## 11. Domain and naming operations

Primary domain target:

- **kebui.com**

Defensive historical-spelling target:

- **qebui.com**

At the time of planning on 2026-10-07, both were observed as registrable through
the domain availability check. This repository must **not** claim ownership until
the Owner confirms registration.

Recommended domain operations after purchase:

- enable registrar lock;
- enable automatic renewal;
- enable 2FA on the registrar;
- keep registrant/recovery details current;
- redirect `qebui.com` to `kebui.com` if both are acquired;
- do not publish DNS or launch claims before the Owner explicitly approves them.

## 12. Public copy kit

### Website hero

**Kebui**

# One conversation. Every agent.

Talk to Kebui and get work done with Claude, Codex and the agents you already
use.

Kebui keeps projects, tasks and agent sessions together in one persistent,
open-source workspace.

**Open source. Self-hostable. Built to work for you.**

### GitHub description

> Open-source workspace for running Claude, Codex and other AI agents through
> one conversation.

### Short launch copy

> Meet Kebui. One conversation for every AI agent you use. Talk naturally,
> keep work persistent, and let the right agent take it from there. Open source
> and self-hostable.

### Chinese launch copy

> **Kebui（科布）——一次对话，调动所有 Agent。**
>
> 不再分别打开 Claude、Codex 和其他 Agent，也不必手工管理每一个 Session。
> 告诉科布你想完成什么，它会把工作交给合适的 Agent，在你的环境中持续执行，
> 并把过程与结果带回同一条对话。
>
> 开源、可自托管、不绑定单一模型。

## 13. Naming rules

Use:

- Kebui
- Kebui Runtime, if/when approved
- Kebui Workspace
- Kebui Chat
- Kebui Tasks

Chinese:

- 科布
- 科布工作空间
- 科布任务

Avoid:

- Kebui AI as the primary product name;
- Kebui Agent as the primary product name;
- KebuiOS until there is an actual OS-level product contract;
- "Egyptian AI";
- claiming a historically exact pronunciation;
- expanding K-E-B-U-I into a forced technical acronym.

The name should work because it is a name, not because every letter is an
acronym.

## 14. Non-goals of this brand decision

This document does not:

- rename the GitHub repository;
- rename current packages/services/DB tables/API fields;
- change current permissions or security architecture;
- authorize production deployment;
- authorize real host activation;
- change current release version;
- claim `kebui.com` is owned;
- add automatic agent routing before its product and safety contracts exist.

See [KEBUI_PRODUCT_PLAN.md](KEBUI_PRODUCT_PLAN.md) for staged delivery.
