# AgentBox Execution Plan

## 目标与完成标准

目标用户是管理单台服务器的管理员。最终操作路径是：登录 AgentBox →
选择正式 `READY` Project → 选择 Claude/Codex → Start/Connect →
浏览器 input/output/resize → detach/reconnect → exact Stop；保留 Project
和 Git 修改。Remote Control、Provider Authentication、官方 CLI Login 与
Interactive Workspace 保持独立。

2026-09-03 Owner 要求制定计划、启用多智能体并行开发、持续完成剩余功能，
且每完成一个阶段更新 GitHub 和文档。该指令覆盖日常软件开发与阶段交付；
architecture 变更、真实 host 激活、Secret handling、生产发布及支持承诺仍遵守
`GOVERNANCE.md` 的明确授权与证据边界。历史提案中的未实现描述不替代 live
代码，历史授权记录也不自动升级为生产证据。

最终完成必须同时具有已合并实现、exact-head terminal CI、适用的独立审查、
merge read-back 和与能力相称的运行证据。Synthetic/Fake Runtime、macOS
本地测试和 CI 不证明真实 Linux terminal/host readiness。

## 已核实基线

- `main` / `origin/main`: `24d08414b20e7158e8c84694aac59d0326799bfd`。
- 工作区开始时干净；main exact-head 的 Backend、Frontend、E2E、Deployment、
  Security、Release Candidate 六个 workflow 均为 terminal `success`。
- 已有 WAW lifecycle、ticket/admission、attachment prepare/detach、bounded
  synthetic stream、fail-closed WebSocket boundary 和 Codex lifecycle 契约。
- 尚不能通过真实浏览器终端使用 Claude/Codex；不能把 HTTP 成功视为 connected。
- 历史 Draft PR #42 不在本轮写入范围内。

## 阶段清单

状态使用：未开始、进行中、待验证、审查未通过、已完成。只有完成本阶段
适用验证、审查、CI 和合并回读才标为已完成。

| 阶段 | 状态 | 交付范围 | 验收与依赖 |
| --- | --- | --- | --- |
| A — 计划与基线 | 已完成 | 修正 stale snapshot、统一现行治理引用、建立需求/实现/验证映射 | 对照 live Git/GitHub；随首个实现 PR 交付 |
| B — WAW-3 recovery contracts | 已完成 | 补齐现有纯 recovery/cursor/lease 决策与前端 stale-event fencing | 覆盖 exact generation/binding/host/epoch/attachment、同代 replay、API/Runtime restart 分类、mobile suspension、uncertain input 与 cleanup proof；不接通真实 transport |
| C — WAW-2 Codex integration | 已完成 | 在既有 substrate 上补齐 Project-scoped Codex API attachment 与 Web contracts；复用固定 CLI command contract，真实执行接线列入 F | Codex/Claude 隔离、legacy Remote Control conflict、fixed argv/provenance、正常/冲突/失效路径及 Fake Runtime 集成；依赖 B |
| D — Workspace metadata UX | 已完成 | 页面接通选择、精确查询、Start/exact Stop；Connect/Detach/input 随真实通道 gate 保持不可用，明确恢复/失败/未开放能力 | zh-CN、显式用户操作、Stop 二次确认、无持久 ticket/input/output、desktop/mobile 元数据交互；依赖 B/C |
| E — 软件发布准备 | 已完成 | 完整 CI matrix、独立 Architecture/Security/Test 审查、限制和 release checklist、产物验证 | 所有检查 terminal；精确记录 artifact fingerprints 与未验证范围；依赖 B/C/D，不能标为生产就绪 |
| F1 — Mac 持续实现 | 进行中 | F1.1 双 AgentType supervisor 已合并；F1.2 concrete executor/probe/cleanup 已合并；F1.3 Noise 核心、独立向量和双语言互通已合并；应用加密流三处未定义 wire bytes 待 Owner 决策后继续接线 | 在 Mac 做可运行的软件实现/本地测试；Linux CI 补平台矩阵；不等同真实 host 验收 |
| F2 — Linux 集成与产品验收 | 未开始 | systemd/cgroup/namespace/PTY/真实 CLI/重启恢复等平台行为与生产准备 | 真实 host 激活和新的架构决策仍需授权、非 Secret evidence 和恢复条件；按 `docs/WAW1_HOST_GATE_CHECKLIST.md` 验收 |

Owner 已明确要求在 Mac 持续开发。F2 的缺少证据不阻止 F1 软件实现，但它是整体产品完成的阻断项。
没有真实证据时不能将其标为已完成，也不能开放 plaintext fallback、generic
shell/filesystem gateway 或通过重命名消除 gate。

A/B 已由 PR #58 交付：head `f3bb9035e061fc0babfcace6af891f257eb7fa74`，19/19 exact-head checks `SUCCESS`；实际 merge `d2470601a06da0a4024fa1772b4f32ec2daa7293`（2026-09-03T04:22:05Z）。完整 WAW-3 transport/reboot 验收仍在 F。

C 已由 PR #59 交付：head `3e0e7a921e008d9c6b5198d37b8254fbee174068`，19/19 exact-head checks `SUCCESS`；实际 merge `7c1c755854077d2e0989ff1d3ab3d54f77e9e707`（2026-09-03T04:45:48Z）。

D 已由 PR #60 交付：head `9be95b10e57a3daa3690205d6c2ffad8da74424d`，19/19 exact-head checks `SUCCESS`；实际 merge `6972f0dba907afd9741c2dc3584f431ee32765ed`（2026-09-03T05:27:15Z）。

E 已由 PR #61 交付：head `0c894ff52f49793f599eb33c4b92b8223e6109b3`，19/19 exact-head checks `SUCCESS`；实际 merge `35191eeaf858041cf5c0767dc1579b67690444ec`（2026-09-03T05:47:57Z）。候选包独立扫描及4份WAW文档包含性检查已通过。随后 Owner 澄清在 Mac 持续开发，F1 已开始；F2 真实平台验收单独跟踪。

## 多智能体职责与写入边界

- 主智能体：计划、文档、接口协调、最终集成、GitHub/CI/merge/read-back。
- Backend worker：core/runtime recovery 与对应 Python 测试；不改 Web。
- Frontend worker：Workspace reducer/hook/page 与对应 Web 测试；不改 Python。
- 独立 reviewer：只读 Architecture/Security/Test 审查，报告证据与缺陷；
  不参与实现，不把 synthetic evidence 写成 host PASS。

先确认依赖和文件所有权，再并行独立模块；禁止覆盖其他贡献者修改。
每阶段中按实际需要复用角色，不为形式重复审查。

## 每阶段交付流程

1. `git fetch origin --prune`，核对工作区、HEAD/main/merge-base、open PR、
   exact-head CI 和上阶段 read-back。
2. 在 `codex/` feature branch 实施已授权范围，保存有意义的测试与非敏感证据。
3. 同步 `CURRENT_STATE.md`、`NEXT_ACTION.md`、`ROADMAP.md`、相关契约文档，
   明确实现、合并、真实运行验证之间的差别。
4. 创建 PR，完成独立审查与 exact-head 所有 CI；pending 不是 PASS。
5. CI 通过后普通 merge；禁止 force push、`--admin` 或 history rewrite。
6. 读取 PR 的实际 `mergeCommit` 并核对 `origin/main`。下一阶段 snapshot
   记录已观察 SHA；绝不预测包含自身文档更新的未来 merge SHA。

每次报告记录实际命令、exit code、exact SHA、审查方式、剩余阻碍与下一步。

## 参考与权威顺序

最新 Owner 指令与 `AGENTS.md` / `GOVERNANCE.md` 决定执行权限；live Git/GitHub
决定仓库事实；代码和实际测试决定实现状态；`CURRENT_STATE.md` 是快照。
`WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md` 保留历史提案与
安全契约，不改写其历史批准状态。现行阶段入口为 `NEXT_ACTION.md`。

## Development-platform clarification

此前将整个剩余 F 阶段等待 Linux 主机的表述过宽。Mac 是当前开发平台，
Linux 是目标部署/验收平台。可在 Mac 编写与验证的 Runtime、协议、浏览器及
恢复逻辑继续实现；真实 host 激活与平台能力声明仍逐项取证。A–E 的已交付
范围与历史证据保留，但不代表所有剩余软件都已完成。

F1.1 已由 PR #63 交付：head `c78cb92a5afe8056ab44a1cc4e8a6bea3074e184`，19/19 exact-head checks `SUCCESS`；实际 merge `90df8b9adfe3c03fc089634c18214a4fb6fcfe9e`（2026-09-03T06:43:01Z）。F1.2 继续开发 concrete Runtime composition，不能将其等同真实 CLI/PTY 产品验收。

F1.2 已由 PR #64 交付：head `ef8641bd409bbb6d17db707370de66f552bf4640`，19/19 exact-head checks `SUCCESS`；实际 merge `624b34b656dbf239dbc56fa79d216db7d17a349b`（2026-09-03T07:09:03Z）。F1.3 实现固定 Noise 核心；应用层三处未冻结的 wire bytes 已形成明确补充提案，单独请求 Owner 决策，不影响核心算法软件开发。

F1.3 已由 PR #65 交付：head `6d0c0f8ff8b452fd0288d6ac98b1f3fe79352ed7`，19/19 exact-head checks `SUCCESS`；实际 merge `f95d1a4b0f0bdbdda45bd8da6cc10f3f8ac10269`（2026-09-03T07:40:44Z）。固定核心独立安全审查通过；Python目标矩阵54通过、Web129通过、双角色Python/Node完整独立向量与篡改拒绝互通通过。下一 application profile 保持未开始，待明确协议补充方案确认。
