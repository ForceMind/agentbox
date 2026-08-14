# AgentBox Product Definition

Status: MVP Release Candidate product boundary through Phase 10
Audience: maintainers, contributors, security reviewers

## Product Vision

AgentBox turns a user-controlled Linux server into a remotely managed AI development workstation. Its value is not general server administration or browser-based coding; it is a safe, repeatable control plane for AI development runtimes, persistent project sessions, workspaces, diagnostics, and lifecycle operations.

English positioning: **Turn a user-controlled Linux server into a remotely managed AI development workstation.**

Chinese positioning: **把任意 Linux 服务器变成可远程管理的 AI 开发工作站。**

Product category: **AI Developer Infrastructure**.

## User Problem

A developer who buys a fresh Linux cloud server currently has to combine SSH, package managers, shell profiles, Git/GitHub authentication, Codex/Claude installation, tmux, systemd, tunnels, and hand-written recovery steps. The resulting workstation is difficult to reproduce and easy to misconfigure:

- npm and standalone Codex installations can coexist or expose different capabilities.
- Runtime commands and paths change; internal managed paths are not stable contracts.
- Codex Remote Control may support start/stop/pair but no status command.
- Claude Remote Control is an interactive process that must survive SSH disconnects and be trusted per project.
- Credentials and one-time pairing codes can leak through logs, history, job records, or Web responses.
- Running a Web panel as root turns convenience into a remote-root attack surface.
- Git ownership, tmux ownership, runtime HOME, and Workspace Trust easily diverge.

AgentBox standardizes these concerns while leaving explicit control with the server owner.

## Core User

The MVP serves one technically capable developer or administrator who:

- owns or administers one Linux server;
- wants to manage AI development sessions from phone, tablet, or computer;
- accepts an initial SSH bootstrap but wants minimal daily SSH use;
- understands that Codex, Claude, GitHub, tunnels, and cloud firewalls remain third-party or external systems;
- values safe defaults, diagnostics, and recoverability over a general-purpose terminal.

The MVP is explicitly **single-server and single-administrator**. “Single administrator” is an application authorization model, not permission to run everything as root.

## First-Version Problem Statement

The first version must let the administrator safely answer and act on five questions:

1. Is this server ready, and what is broken or unsupported?
2. Which Codex and Claude installations and capabilities are actually available?
3. Can I start, observe, pair, and stop supported remote AI runtime sessions without exposing a shell API?
4. Which project workspaces exist, and what is their minimal Git state?
5. Can AgentBox install, upgrade, recover, and explain failures without corrupting existing services?

## Core Value

- **Less routine SSH:** daily status, pairing, session, project, and diagnostic operations have controlled UI/CLI flows.
- **Capability-aware operation:** decisions are based on detected commands and capabilities, not assumed versions or private files.
- **Persistent AI sessions:** Claude runs in project-scoped tmux sessions owned by a non-root Runtime user.
- **Safe privilege separation:** system changes go through a minimal root Privileged Helper; the Web/API is never root.
- **Recoverable lifecycle:** installation, upgrade, jobs, backups, and errors have explicit state and rollback guidance.
- **Honest diagnostics:** Unsupported, Unavailable, Unauthenticated, and Broken are distinct results.

## Product Surface Priority

The recommended product-surface priority is:

1. shared Application Services and CLI contracts, because bootstrap and recovery must not depend on the browser;
2. the idempotent installer and native systemd packaging needed to deliver those services;
3. the minimal Web/API as the primary daily management experience.

This is not a statement that the Web is optional: a usable Web panel is an MVP release requirement. The CLI is the operational source of truth and recovery surface; the Web is the daily product surface; the installer is the acquisition and repair surface.

This priority does not require the final installer to be coded before all components it packages. `DEVELOPMENT_PLAN.md` builds the API/UI foundations first and completes the deployable installer after the Runtime components exist; its install contract, dry-run model, and systemd boundaries are defined earlier.

## Non-Goals

AgentBox is not:

- a general Linux operations panel;
- a browser IDE or arbitrary Web terminal;
- a multi-tenant hosting SaaS;
- a Kubernetes or container-management platform;
- a cloud-server purchasing platform;
- a replacement for GitHub, Codex, Claude, Tailscale, Cloudflare, SSH, or a reverse proxy;
- a general-purpose third-party credential vault. A narrowly scoped future
  Secret Manager may support Provider references, but raw API keys remain
  outside ordinary Provider metadata and product output.

The MVP does not expose arbitrary shell input, full filesystem browsing, unrestricted Git commands, or a public listener by default.

## Typical User Flows

### New Server Bootstrap

1. The administrator invokes a reviewed installer over SSH.
2. The installer detects distribution, architecture, systemd, dependencies, existing services, and conflicts.
3. A dry-run plan is shown before privileged changes.
4. AgentBox installs versioned files, creates narrowly scoped users/directories, and starts loopback-only services.
5. The administrator initializes the single local admin account and runs `agentbox doctor`.
6. Remote access is added separately through Tailscale, an existing Cloudflare Tunnel, VPN, or HTTPS reverse proxy.

### Codex Pairing

1. The administrator signs in and opens the Codex page.
2. AgentBox refreshes capabilities and confirms that pairing is supported.
3. After recent-authentication and CSRF checks, AgentBox generates a one-time Pair Code through the Runtime Adapter.
4. The code is returned once through a no-store response and held only ephemerally in memory.
5. Audit data records the action and result but never the code.

### Claude Session

1. The administrator selects a registered Project Workspace.
2. AgentBox verifies ownership, path containment, installation, authentication status, and Workspace Trust state where detectable.
3. If trust cannot be determined safely, AgentBox provides a manual project-scoped instruction and does not trust `/root`.
4. The non-root Runtime Executor creates a namespaced tmux session and starts Claude Remote Control in the project directory.
5. The Web shows state and bounded recent output; CLI prints a safe attach command. The MVP does not embed a terminal.

### Project Setup

1. The administrator creates an empty workspace or submits a credential-free Git URL to clone.
2. A Job validates the destination beneath the configured project root and performs the operation as the Runtime user.
3. AgentBox reports branch, dirty count, sanitized remote URL, and Runtime launch actions.

### Diagnosis and Recovery

1. Dashboard and `agentbox status` show component health.
2. `agentbox doctor` creates a bounded Diagnostic Run with findings and safe remediation plans.
3. Destructive or privileged remediation is never automatic; it becomes a separately confirmed Job.

## Product Principles

1. Default to `127.0.0.1`; remote access is an explicit integration.
2. Prefer capability detection over version assumptions.
3. Treat public CLI behavior as a contract and private files as best-effort diagnostics only.
4. Never expose arbitrary shell execution.
5. Separate Web/API, Worker, Runtime, and root privileges.
6. Preserve existing services and unmanaged sessions unless the administrator explicitly adopts them.
7. Never persist Pair Codes, tokens, passwords, cookies, OAuth codes, SSH keys, or full auth configuration.
8. Make long operations Jobs with idempotency, timeouts, bounded output, and recovery states.
9. Fail closed on unknown paths, capabilities, ownership, versions, or confirmation state.
10. Optimize for a small single server without blocking future multi-user evolution.

## MVP Success Definition

MVP acceptance requires a single administrator to bootstrap through an isolated
fixture and exercise the designated OpenCloudOS upgrade/rollback host, sign in,
run Doctor, register or clone a project, inspect and safely update Git state,
manage a supported Codex Remote daemon and one-time pairing flow, and
create/observe/stop a project-scoped Claude tmux session—without Web/API root,
a default public listener, or sensitive values in persistence/output. Platform
evidence is stated at its actual Real-host/CI/Fixture/Unsupported level.

## Long-Term Directions

Possible post-MVP directions include multiple servers, multiple workspace users, optional Docker development/deployment modes, richer GitHub and PR workflows, bidirectional terminal experiences, hardware/resource scheduling, pluggable Runtime Adapters, enterprise identity, and native mobile clients. These are not commitments and must not distort the MVP architecture.

One explicitly planned post-MVP direction is Phase 11 — Provider, Secret &
Runtime Continuity Management. It lets administrators select a model/API
Provider independently of Remote Control while separating a concrete
`ProviderDefinitionID` from stable AgentBox `RuntimeBindingID` intent. It must
support Official OpenAI, OpenAI-compatible, local, and Runtime-native Providers
through typed adapters; use platform Secret backends and verified atomic config
transactions; protect active writers; and report Provider, Runtime, Remote,
Thread Resume, Context Continuity, and Thread Discovery independently.

Phase 11 does not promise seamless cross-provider history, mutate private
session DB/JSONL/rollout data, or automatically fail over Providers. It is
tracked by Issue #23; it is not part of the current MVP or authorization to read
keys, modify Runtime configuration, restart Runtime, or affect Remote Control.

## Branding and Third Parties

AgentBox is an independent project. Codex, Claude, GitHub, Linux distribution names, and other third-party names are used only for factual compatibility descriptions. AgentBox must not imply affiliation or endorsement, copy third-party logos without permission, bundle credentials, or redistribute third-party software contrary to its license. All third-party marks remain with their respective owners.
## Phase 7 delivered capability

AgentBox now treats Projects as formal managed workspaces and offers bounded create/clone, structured Git state, ordinary branch management, fast-forward-only Pull, no-force Push, Draft PR creation, and Project-bound Claude sessions. It remains a control plane rather than a browser IDE and intentionally omits staging, commit, destructive Git, filesystem deletion, and arbitrary commands.
