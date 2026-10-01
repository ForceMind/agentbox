# AgentBox 逐版本交付计划

## 2026-09-30 交付纠偏：以完整用户流程关闭首版

Owner 指出执行可能偏离逐版本计划。Coding Agent 确认：后续功能范围没有
扩到 70 项，但执行过度拆分基础批次，用 CI/源码进展替代可体验版本，偏离
了交付节奏。下文旧 Mac/MV3 目标由最新 PC/手机浏览器选择和已批准的
ADR 0010 HTTPS Web、ADR 0011 A 受限子树方案承接，不再作为首版唯一入口。

当前仅关闭一个部署版本，沿用 Draft #125 和同一版本号；内部提交不单独
称版本完成。首版验收清单只有以下完整路径及其必要恢复条件：

- [ ] 用户在服务器执行固定发布的一条命令，安装/首次配置成功；同版本
  重试、错误提示和数据保留可操作，得到实际 HTTPS 入口。
- [ ] PC 与手机浏览器登录，创建/选择正式 READY Project；通过已批准的
  Web 信任启动，明确确认服务器身份，不能靠测试信任或模拟数据。
- [ ] Claude Code 与 Codex CLI 均能 Start/Connect、真实 input/output、resize、
  detach/reconnect、exact Stop；账号登录和 Runtime Secret custody 保持分域。
- [ ] 关键网络/服务中断、重启和升级回退有可执行恢复；浏览器后台返回、
  键盘/触摸在真实代表性客户端验收。上述条件通过后才固定版本和制品交付。

每项只保留当前可执行阻断、负责文件和直接证据；必要底层改动必须对应
这四项之一。禁止把额外抽象、独立基础迭代、更多测试数量或后续功能当作
首版进展。当前直接阻断依次是完整 manifest/Runtime _main、Web 信任启动和
双 CLI 核心流程。安装恢复已实施的部分保留，不在接线完成前继续扩大到
新的恢复体系。新的外围优化进入后续版本；安全边界不因纠偏而放宽。

细节与实际未完成项沿用 [首版部署记录](DEPLOYABLE_RELEASE_PLAN.md)。现有
probe 只关闭 systemd 255 受限子树的实际可行性问题，通过后直接接启动链，
不再为 probe、codec、provider 等各自新建产品版本或重复独立交付计划。

计划版本：AB-RELEASE-ITERATION-2026-09-29-v1。Owner 已明确要求一个版本一个版本迭代；本文件只调整执行顺序和验收方式，不缩减 [70 项长期清单](FULL_CAPABILITY_INVENTORY.md)，也不授权真实主机、Secret、付费调用或发布操作。

## 当前事实与唯一目标

2026-09-29 的执行基线是 `origin/main = 3a23f350582287de6b00499b8d4daa5d69c52011`，Web 源码版本 `0.3.0-rc.29`。该 SHA 的 Backend、Frontend、E2E、Deployment、Security、Release Candidate 六类 post-main workflow 均为 completed/success。这是软件/CI 证据，不是可用版本、真实主机验收或 GitHub Release。安全关键 Draft #122（固定 Runtime vendor enrollment）和 #117（Runtime-only staged Git patch reader）仍未合并；原 `codex/r12-runtime-production` 工作区有未提交的 C3-b WIP，必须保全。

**当前唯一产品目标：首个可用单机 RC。** 在指定 Linux 主机与已资格化的 Mac Chrome/Edge 客户端，管理员登录 AgentBox，选择正式 READY Project，分别使用 Claude Code 和 Codex CLI，完成 Start/Connect、真实 input/output、resize、detach/reconnect、exact Stop，并验证服务/主机重启和升级回退后的恢复。既有计划中的手机管理/exact Stop 同样单独验收；未通过时不能宣称该客户端受支持。完成范围以 [R12 计划](PRODUCTION_READINESS_PLAN.md)的 R12-A–I 和实际目标记录为准。具体主机、客户端安装、key/Login、测试调用、重启与生产/发行操作仍需各自的目标输入和授权。

## 版本序列与退出条件

| 版本阶段 | 本阶段只解决的问题 | 退出条件 |
| --- | --- | --- |
| 软件/制品候选 | 完成 R12-C3-b `_main` 生产组合、固定 enrollment、R12-D/E 安装与客户端信任、R12-F 制品配对；按当前 AGENTS.md 安排风险检查 | 固定生产图正负例、相关安装/回退与客户端构建、准确标注的自查/适用审查、exact-head CI 和 merge read-back；标记 **Software/Artifact Ready**，不称可用 |
| 首个可用 RC | 对上述固定 host/client/CLI tuple 完成 R12-G/H/I | G1–G5 实测、双 CLI 真输入输出/重连/exact Stop、故障/重启/升级回退、恢复记录全部通过；标记 **Target Qualified RC**。缺任何关键证据则列明失败或 NOT RUN |
| 后续功能版本 | 每次从 70 项清单选一个可实际操作的能力组，优先完成 Files/Changes，再按依赖交付结构化会话、开发环境、Provider、客户端、relay、插件、自动化与 Hub | 每版有用户路径、权限/失败/恢复行为、实际客户端或目标服务证据、版本/制品与明确未支持范围；逐项关闭清单，不用源码导入量计进度 |

软件候选可能需要多个内部 PR/rc 编号；**源码 rc 数字与 CI 绿色不等于产品版本可用**。首个可用 RC 的确切版本号在其包含的最后提交与制品固定后记录，不预先占号。R12-J 有限生产和 R12-K 发行/交接分别需要相应授权与证据，不能从 Target Qualified RC 自动推定。

## 当前范围冻结与下一步

1. 停止新增 WS14 标签、导航、命令中心及 S02–S14 的功能批次。它们的已合并成果保留；#117 维持 Draft，等待其自身审查，不把 patch reader 当成首个可用 RC 的隐藏前提。
2. 先完成 #122 的风险检查、相关回归与 exact-head CI，按当前 AGENTS.md 的 `feature branch → CI → merge → exact read-back` 交付；主智能体自查不称独立审查。随后核对原工作区 C3-b WIP 的归属、diff 和依赖，在独立干净分支接续 R12-C3-b、D/E/F，不 reset、stash、clean 或广泛提交原工作区。
3. 软件/制品证据齐备后，依据 [目标记录](R12_TARGET_RECORD.md)补齐 D01–D11 中实际依赖的 host、Origin、分发、CLI、费用与恢复输入，再执行已获具体授权的 G/H/I。现场输入缺失时报告阻断及最小所需输入，保持该版本未完成；不以新功能开发掩盖阻断。
4. 首个可用 RC 的目标现场验收完成后，再为下一版选择 Files/Changes 的一个完整用户路径，处理 #117 审查和内容通道依赖。70 项清单是长期 backlog，不是当前并行施工清单。

## 成本与变更控制

- 同时只设一个当前产品版本目标；每个 PR 必须写清它消除的本版阻断、可观察行为和必要验证。安全审查等待不触发无关功能替代开发。
- 每版开工前冻结包含/不包含的能力 ID、目标平台、文件归属、外部输入和验收表。超出范围的新能力进入后续版本；影响当前目标的实质变更先更新本计划并说明成本与风险。
- 每完成一批只运行受影响的必要本地验证与该 PR 的 exact-head CI。失败修复后补跑相关项；不因例行文档更新重复全量测试。按现有版本体系为应用行为批次更新 rc，纯文档不升版本。
- 范围清楚的实现、文档和常规检查优先使用 GPT-6 Luna；Runtime 权限、Secret/host 边界和独立安全审查采用足够的模型能力。默认单智能体；本计划不授权启动子智能体。
- 每次报告只列当前版本目标、已证明的状态、剩余阻断、下一项和实际耗费。不能用 PR 数、测试数或百分比代替用户可用性。

本文件是当前执行顺序入口；[全量计划](FULL_CAPABILITY_DELIVERY_PLAN.md)继续定义长期能力与依赖，[R12 计划](PRODUCTION_READINESS_PLAN.md)继续定义主机与生产门禁。历史阶段记录保留为证据，不再作为自动推进旁支的指令。
