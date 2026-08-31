# AgentBox Project Context Index

本目录是 Codex 的项目上下文入口。先读取本页，再按任务读取下表。

| 文件 | 用途 |
|---|---|
| `CHARTER.md` | 长期产品与架构边界 |
| `GOVERNANCE.md` | Branch、CI、Review、Owner gate |
| `CURRENT_STATE.md` | 最近一次 live verified snapshot（非事实源） |
| `NEXT_ACTION.md` | 唯一最近授权动作 |
| `ROADMAP.md` | 已完成与后续路线图 |
| `DECISION_INDEX.md` | ADR/architecture/PR 索引 |
| `OPERATING_PROTOCOL.md` | Codex task lifecycle 与失败处理 |
| `OWNER_COMMANDS.md` | Owner 自然语言命令 |
| `HISTORY.md` | 压缩里程碑与历史状态 |
| `REPORT_TEMPLATE.md` | 统一最终报告结构 |

## Authority Order

1. Git objects and GitHub live state（local HEAD、`origin/main`、remote branch、PR、exact-head CI、merge read-back）
2. Accepted/merged architecture 与 ADRs on authoritative main
3. Current feature branch documents（只代表 proposed work）
4. `CURRENT_STATE.md`（verified snapshot）
5. `NEXT_ACTION.md`（最近授权判断）
6. Codex conversation summaries
7. Historical handoff/chat text

冲突时上层覆盖下层；合同冲突必须 BLOCKED，不静默调和。

## Current Architecture Documents

- [Phase 11 provider domain model](../../PHASE11_1_PROVIDER_DOMAIN_MODEL_ADR.md)
- [Phase 11 runtime capability contract](../../PHASE11_2_RUNTIME_CAPABILITY_CONTRACT_ADR.md)
- [Phase 11 secret boundary](../../PHASE11_3_SECRET_BOUNDARY_ADR.md)
- [Phase 11 ownership/approval foundation](../../PHASE11_3_2A_CONTROL_PLANE_OWNERSHIP_APPROVAL_AUTHORIZATION_REVIEW.md)
- [Proposed Web Agent Workspace architecture](https://github.com/ForceMind/agentbox/blob/codex/web-agent-workspace-architecture/WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md)（PR #41 branch only）

## ADR and Active PR Entry Points

详见 [`DECISION_INDEX.md`](DECISION_INDEX.md)。当前 active product PR 是 [PR #41](https://github.com/ForceMind/agentbox/pull/41)，其 live state 必须每次通过 GitHub 查询。

## Per-task Read Set

读取本目录全部核心文件、当前 Slice/phase document、branch diff、open PR metadata 与 exact-head checks。旧 handoff 只作历史背景，不能当作 live state。
