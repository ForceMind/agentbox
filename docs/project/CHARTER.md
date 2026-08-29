# AgentBox Charter

## Vision

AgentBox turns any Linux server into a remotely managed AI development workstation: a secure control plane coordinates managed runtime sessions without becoming a shell gateway.

## Stable Architecture

- **Control Plane** decides intent, authorization, project scope and lifecycle state.
- **`agentbox-runtime`** executes fixed, typed, allowlisted Runtime actions and owns Runtime operation authority.
- **Root Helper** performs only fixed privileged lifecycle actions; it has no Secret authority, arbitrary shell, arbitrary `systemctl`, generic filesystem or sudo gateway.

永久禁止 Browser → arbitrary command → Linux。Web/API/Worker 均 non-root，不读取 Runtime HOME、plaintext/ciphertext Secret、root key/KEK/DEK/nonce/tag/AAD，不直接执行 Runtime process。

## Identity and Secret Boundaries

Remote Control != Provider Authentication != Codex Login != Claude Login != Pairing != Interactive Agent Workspace。

Phase 11 v1 中 `agentbox-runtime` 是唯一 Provider Secret authority。Claude 保持 runtime/session-only，不进入 Provider Manager。Provider plaintext 永不经 Web/API/Worker 传输；真实 Provider API Key 在未授权时 PROHIBITED。

## Web Agent Workspace Goal

长期目标是登录 AgentBox 网页、选择正式 Project、选择 Claude 或 Codex、Start/Connect，在网页 terminal 中输入并实时查看 CLI output，支持 Detach、刷新/断网后 reconnect 与 exact Stop。当前架构是 Proposed，implementation 需单独 Owner authorization。

## Language Rule

普通用户 UI 使用 zh-CN；identifiers、source names、protocol fields、enums、DB tables/columns、error codes、Audit actions、Git branches/commits/PR titles/filenames 使用 English。

## Explicit Non-goals

本 Charter 不授权任何产品 Slice、真实 Secret provisioning、Provider API key、自动 merge/Ready、自动 next Slice、generic shell/filesystem gateway 或 Root Helper terminal path。
