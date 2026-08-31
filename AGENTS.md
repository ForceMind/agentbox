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

Owner 说“继续项目”时，必须按以下固定流程进行 live revalidation 后执行唯一授权动作，并停在下一个 Owner gate（不得自动继续）：

`feature branch -> Draft PR -> exact-head CI -> Architecture/Security/Test reviews -> protected Environment approval -> governance-bot mechanical action -> exact read-back`

Coding Agent ≠ governance-bot。Coding Agent 不能创建 approval（包括 PR 准备 / merge 记录）；任何更改 host、secret、架构或 Slice 的动作都受 Owner gate 约束。  
Head/base 变化会使 approval 无效。

Host-gated capability（含 real host/systemd/tmux/socket/cgroup/namespace/LSM/seccomp）仍需独立 host evidence 与恢复条件。

## Review Protocol

复杂或安全关键 PR 至少并行调用 `Architecture Reviewer`、`Security Reviewer`、`Test Reviewer`，等待全部结果后由主 Agent 汇总。Subagent PASS 只是 evidence，不是 Owner approval；结论冲突时列出冲突并重新检查，无法闭合则 BLOCKED。  
不自动发起 Owner 代签或自动 merge；只汇报未决证据和阻塞项。

## Git Governance

`feature branch -> Draft PR -> exact-head CI -> Architecture/Security/Test Review -> Owner approval in protected Environment -> governance-bot mechanical action -> exact read-back`

禁止 force push、`--admin`、自动 Ready/merge/next Slice。只在授权 branch 上写入，不直接写 main。  
Coding Agent ≠ governance-bot，Coding Agent 不能创建/修改自己的 approval record。  
Head/base 变化会使 approval 无效。  
Host-gated 能力仍需 host evidence 和单独恢复记录。

## Reporting

报告使用中文，technical identifiers 保持 English；记录实际命令与 exit code、exact SHAs，并分开 facts/inference/assumptions；不伪造未运行测试或 pending CI。

## State Maintenance

`CURRENT_STATE` 是 verified snapshot，不是 trust root；每次 task 结束在当前 branch 更新。  
merge SHA 只能通过 merge read-back 得到；发现 stale state 先报告再在适当 branch 更新。

## Owner Gate

只有人类 Owner 可以发送 `Owner Merge Authorization: GRANTED`，且必须绑定 exact PR number、exact head SHA、exact base SHA、执行范围（机械步骤/治理步骤）；head/base 变化即失效。  
未收到该声明不得 Ready、机械 Merge、开启下一个 Slice。

## No Prompt Relay

不得让 Owner 把结果转交给另一个 AI；直接在当前 Codex 环境执行或报告 blocker。
