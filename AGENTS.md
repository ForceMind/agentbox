# AgentBox Project Instructions

## Repository Identity

`ForceMind/agentbox`

## Product Goal

在 AgentBox 网页中选择正式 Project，直接使用服务器上的 Claude Code 和 Codex CLI，支持 input/output/resize/detach/reconnect/exact Stop。

## Non-Negotiable Boundaries

- Control Plane decides; `agentbox-runtime` executes typed, fixed, allowlisted Runtime actions; Root Helper only performs fixed privileged lifecycle actions.
- 永久禁止 Browser → arbitrary command → Linux；Web/API/Worker 不得成为 generic shell/filesystem gateway，也不得直接执行 Runtime process。
- Remote Control、Provider Authentication、Codex Login、Claude Login、Pairing、Interactive Agent Workspace 必须分开。
- Web/API/Worker non-root，不读取 Runtime HOME、任何 plaintext/ciphertext Secret、root key/KEK/DEK/nonce/tag/AAD；不得把 plaintext Secret 发送给 Provider。
- `agentbox-runtime` 是 Phase 11 v1 唯一 Provider Secret authority；Claude 在 Phase 11 v1 保持 runtime/session-only，不进入 Provider Manager；Root Helper 无 Secret authority，且不参与 Web Agent Workspace terminal path。
- 普通用户 UI 使用 zh-CN；identifiers、source names、protocol fields、enums、DB names、error codes、Audit actions、branches、commits、PR titles、filenames 保持 English。

## Instruction Loading Protocol

每个任务先读取：

1. `docs/project/INDEX.md`
2. `docs/project/CHARTER.md`
3. `docs/project/GOVERNANCE.md`
4. `docs/project/CURRENT_STATE.md`
5. `docs/project/NEXT_ACTION.md`
6. `docs/project/ROADMAP.md`
7. `docs/project/DECISION_INDEX.md`
8. 当前 feature/phase architecture document
9. 当前 branch diff、PR 和 exact-head CI

## Live State Preflight

每次执行前 `git fetch origin --prune`，检查 working tree、current branch/HEAD、main/origin/main、merge-base、open PR、exact-head CI，并与 `CURRENT_STATE` 比较。Snapshot 永远不能覆盖 live Git/GitHub。

## Continue Semantics

Owner 说“继续项目”时，完成 live revalidation 后可继续执行当前计划，不再停在额外的 Owner gate：

`feature branch -> CI -> merge -> exact read-back`

日常机械操作可由当前 Coding Agent 直接执行；不再要求独立 governance-bot 或逐 PR approval record。

Host-gated capability（含 real host/systemd/tmux/socket/cgroup/namespace/LSM/seccomp）仍需独立 host evidence 与恢复条件。

## Review Protocol

复杂或安全关键 PR 可按需进行 Architecture/Security/Test review；review 是质量证据，不再作为额外的机械合并门槛。

## Git Governance

`feature branch -> CI -> merge -> exact read-back`

禁止 force push、`--admin`、history rewrite。允许在 CI 通过后由 Coding Agent 执行 Ready/merge/next Slice。
Host-gated 能力仍需 host evidence 和单独恢复记录。

## Reporting

报告使用中文，technical identifiers 保持 English；记录实际命令与 exit code、exact SHAs，并分开 facts/inference/assumptions；不伪造未运行测试或 pending CI。

## State Maintenance

`CURRENT_STATE` 是 verified snapshot，不是 trust root；每次 task 结束在当前 branch 更新。  
merge SHA 只能通过 merge read-back 得到；发现 stale state 先报告再在适当 branch 更新。

## Owner Gate

日常代码和文档变更不再需要单独的 Owner Merge Authorization。架构、真实 host 激活、Secret 处理和生产支持承诺仍必须有明确授权与证据。

## No Prompt Relay

不得让 Owner 把结果转交给另一个 AI；直接在当前 Codex 环境执行或报告 blocker。
