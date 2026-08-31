# AgentBox Roadmap

## Completed

- Phase 0 through Phase 10
- `v0.3.0-rc.1`
- Phase 11 Slice 1
- Phase 11 Slice 2
- Phase 11 Slice 3 Architecture
- Phase 11 Slice 3.1
- Phase 11 Slice 3.2a Architecture
- Phase 11 Slice 3.2a implementation / PR #40 merged

## Current Product Priority

Web Agent Workspace

## Remaining Web Agent Workspace

1. PR #41 final Owner Architecture/Security Review and merge
2. WAW-1 Claude first user-visible vertical Slice
3. WAW-2 Codex on the same substrate
4. WAW-3 continuity/mobile/recovery/release hardening

## Deferred Provider Manager

- Slice 3.2b Secret provisioning
- Config Transaction Framework
- Provider Validation
- Codex Provider Adapter
- Binding/Activation/Continuity/Rollback
- API/CLI
- Provider Web UI
- final release gate

Provider Manager 不再是当前 Web Agent Workspace 的前置依赖。不得写未经 Owner 授权的硬发布日期。WAW-1 与 Slice 3.2b 均需独立 authorization。
