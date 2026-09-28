# AgentBox 全量功能整合与原路线续建计划

计划版本：AB-FULL-PARITY-2026-09-28-v2。状态：**Owner 已要求吸收所有现有功能；能力与权限边界正在冻结**。

本计划按 Owner 最新要求扩展 [v1 工作台整合计划](WORKBENCH_INTEGRATION_PLAN.md)。v1 的固定来源、WIP 保护、单一 AgentBox 产品、Apache-2.0 归属、Control Plane/Runtime 分权、R12 主流程及已合并 A0/A1 仍有效；其中“只选部分功能”“移动端/语音/插件/Hub 仅评估”等范围限制由本计划替代。70 个冻结能力 ID 及三份上游源码提交见 [全量清单](FULL_CAPABILITY_INVENTORY.md)。两份文档组成同一个主 Goal 和一条交付路线，不建立第二套互相冲突的 Roadmap。

## 1. 产品完成定义

最终用户只看到 AgentBox 品牌、账户、项目、客户端、CLI/SDK、远程连接、自动化和文档。可由多个 AgentBox 自有组件提供服务（Web/API/Runtime、桌面/手机、relay、Hub），但不需要部署或操作名为 Paseo 的产品或保留其 daemon。源码出处、版权、许可和必要归属记录继续准确保留。

“全部功能”指固定提交所对应清单的所有 70 项具有可执行的 AgentBox 用户路径、权限、失败和恢复行为及对应验收证据。只把模块拷贝进仓库、CLI 帮助中出现命令、模拟 E2E 通过或保留上游服务，均不算完成。各平台、provider、外部集成分别验收；不能用一项成功外推其他项。

**双层里程碑**：先交付现有 R12 的单机真实主流程（首个可用 RC），随后沿同一产品逐阶段扩展到全部清单。R12 不以 Hub、Stripe 或手机商店作为隐藏依赖；全量完成也不能因 R12 先可用而提前声明。

## 2. 架构取舍与待决策点

原 AgentBox 的控制面、Runtime、Root Helper、正式 Project、Secret authority、代次/exact Stop、独立浏览器信任和原生安装器仍是单一权威。上游 TypeScript、React Native、Elixir 与 Hub 的算法、组件和边界实现可按文件迁入改造；不会让第二套 daemon、用户库、Project 身份或 Job 队列与 AgentBox 并行处理同一动作。

宽权限功能的定义需要 Owner 明确选择：上游普通 shell、任意 daemon 可读文件、repo setup/scripts、插件 server RPC、多主体 Hub 授权，可能改变 AgentBox 不可变边界。具体问题已发给 Owner。答复前：S01、S02、S03 的无冲突部分继续，冲突能力不实施；答复后把选定语义写入后继 ADR、权限表、威胁模型、数据/API 合同和验收计划。即使选择放宽，也先完成可审查的软件架构和负向测试，再处理真实 host/Secret/外部服务。

| 情况 | 实施合同 |
| --- | --- |
| 在现有边界内实现对应体验 | 受限 Project 终端/脚本/文件/插件等分别拥有固定动作与资源；记录与上游原语义的差别，不能声称任意 shell/filesystem 原样兼容 |
| 明确批准修改权限架构 | 先形成新的 Owner 批准 ADR，修改 AGENTS/CHARTER/安全模型和隔离协议，再单独迁移宽权限能力；旧 Runtime 不能被普通 Web 请求直接调用任意命令 |

## 3. 阶段顺序、能力归属与退出证据

下表每阶段是若干可独立审查的交付批次，不是单个大 PR。每个阶段的具体 API、schema、文件所有权、测试与制品在第一批提交前冻结；结束时把所列 ID 展开成操作级验收表，记录 PASS/FAIL/BLOCKED/UNKNOWN/NOT RUN/N/A。

| 阶段 | 能力 ID | 依赖与交付 | 退出证据 |
| --- | --- | --- | --- |
| S00 固定基线与全量盘点 | 所有 ID 的来源清单 | 主仓、生产 relay、Hub 三个提交/许可证、功能矩阵、已合并 A0/A1、WIP 保护；差异/缺项可追溯 | 完整 ID、来源文件和目标模块映射；清单链接/许可证检查 |
| S01 R12 首个真实主流程 | AG01–02 的 TUI 子集、AG07、WS01、WS09 的 WAW 子集、CL01、OP01 | 接续 C3-b，完成 _main、installer/systemd/socket、客户端信任及 R12 A–I；Host/key/真实 CLI 仍按具体授权 | Software/Artifact Ready 后，在指定 host/client/CLI tuple 完成 G1–G5；J/K 按授权独立完成 |
| S02 整合工作台与只读变化 | AG16、WS01–02、WS05–06、WS08、WS14–15、CL11–12 | 延续已合并 Diff 树，统一项目导航/工作标签/Attention/Files/Changes/面板；内容权限先验收 | 实际数据、权限、截断/过期/空错态、桌面/手机视觉与交互；不依赖假数据 |
| S03 结构化 Agent 与历史 | AG01–02、AG07–12、CL05 的基础事件契约 | 固定 adapter、conversation/turn、timeline/composer/工具/审批、历史/Resume/rewind/archive；不混用原 WAW exact Stop | 双 CLI 真会话，取消/断线/重启/旧 handle/重复事件/权限冲突 |
| S04 开发环境与全工作副本 | WS03–04、WS07、WS09–13 | Git worktree/PR、文件写入/上传、终端命令感知、脚本/服务/端口、内置浏览器；依权限决定推进宽权限子项 | 数据保全、路径/脚本来源、服务代理/浏览器隔离、并发/回退及实际操作 |
| S05 Provider 生态 | AG03–06、EX03 的 provider 子集 | OpenCode/Pi/Copilot/ACP、目录、一键安装/custom adapter/alias/profile；依赖 S03 会话契约 | 每种声明支持的 provider 运行、权限、历史与失效矩阵；不支持者明确阻断 |
| S06 Agent 编排与开放接口 | AG13–15、EX05、EX08、CL04–05 | managed/native 子 Agent、技能、MCP/AgentBox CLI/SDK、跨工作区协调 | 并发文件归属、父子清理、能力收窄、可取消/可恢复、真实客户端调用 |
| S07 全平台客户端与语音 | CL02–03、CL06、CL10–12、OP02–03、OP05 的客户端部分 | Electron Mac/Linux/Windows、iOS/Android、语音、直连/VPN/SSH、Docker/更新/备份 | 各平台真实安装、签名/分发、升级/回退、离线/通知、麦克风/费用/隐私与可访问性 |
| S08 relay、多主机与主体 | CL07–09、OP04、OP05 的跨主机部分 | 迁入并改造 Elixir relay 或实现协议等价 AgentBox relay；配对、多设备、主机同步、主体/权限 | 跨主机 E2E、钥匙/撤销/重放、节点失败、负载、备份/恢复及成本观测 |
| S09 插件与扩展 | EX01–04 | 客户端/服务端插件、主题/面板/命令/附件、自定义 provider、Git/npm/local 来源与目录 | 签名/来源、权限、沙箱、版本兼容、安装/禁用/升级/回退与安全审查 |
| S10 计划任务与元数据 | AG17、EX06–07 | cron/heartbeat、聊天/CLI 管理、自动标题与候选模型；复用 AgentBox Job 和审计 | 时区/DST、幂等、取消、费用、通知、重复触发与恢复 |
| S11 Hub 基座与 API | HB01–02、HB09–10 | 自有 Hub/组织、成员、daemon 授权、Embedded/PostgreSQL、API key/CLI/OpenAPI | 多主体/跨 daemon 边界、部署迁移、备份、撤销与审计 |
| S12 Hub 集成和工作流 | HB03–08、HB11 | GitHub/Slack/Discord/Linear、触发器、YAML 工作流、分类器、活动、附件、邮件 | 各供应商真实授权与 webhook 验证、事件去重、配置版本回滚、回复范围 |
| S13 可选商业面 | HB12 | 将上游已有试用、计划、Stripe 软件能力纳入 AgentBox Hub；真实开通另行授权 | 金额/配额/幂等/对账/取消/争议与失败恢复；无真实账户不称可用 |
| S14 文档、来源与全量回归 | OP06 及所有 ID | AgentBox 品牌与一致版本、帮助、SDK/CLI 示例、SBOM/NOTICE、三仓来源追溯 | 70 项逐条验收、平台/host/生产事实分列；仅在全部适用项有证据后判定全量完成 |

S02/S03 的无冲突软件可与 S01 的现场输入等待交错推进；单智能体仍串行写共享文件。S11–S13 需要独立服务和多主体数据域，不能偷偷塞进单管理员控制面。S09 的插件执行与 S04 的普通终端依权限选择分流；其余能力在明确接口后继续实施。

## 4. 首批交付与现有工作接续

- A0/A1 已由 [PR #97](https://github.com/ForceMind/agentbox/pull/97) 交付：最终 head `ffe08c456d0870c1804644cdf662c7c862be2e4d` 完成 26 个终态检查（24 success、2 个既定历史 skip），正常合并为 `135eb8cdb22a6b88a825eb214bde86f3f11e8442`；本地 Git 回读确认父提交 `a696193fec127595b1beafb1ed1cabf2ae58efa9` 和最终 head。该 merge SHA 上 Backend、Frontend、E2E、Deployment、Security、Release Candidate 六类 post-main workflow 均 completed/success。证据只覆盖来源/Changes 纯逻辑，不覆盖 Files/Runtime/页面。
- 原 checkout `codex/r12-runtime-production` 保有 C3-b 未提交 provider/test、.reasonix/、build/ 和先前计划文档。C3-b 的 owner/native path/cleanup 修正在进行中，尚未构成可合并候选；不得重置或把这些文件与文档一并广泛提交。
- 本范围修订先落清单/计划/状态；Owner 的宽权限答复确定后冻结 S04/S09/S11 权限合同。依赖满足后继续 S01 C3-b 与 S02 可独立 UI/只读工作。
- 所有原计划 A2–A10 已映射到 S01–S14；没有将其“取消后重做”。已通过的测试按输入版本复用，后续新变化只补相应验证。

## 5. 技术栈、来源和品牌

AgentBox 的 FastAPI/SQLite/Runtime/React Web 保留为已有基础。Native 客户端、relay 和 Hub 是新增 AgentBox 组件，可有独立进程与数据存储，但身份、权限、Project/Agent 映射和版本协商只有一套公开 AgentBox 契约。跨服务的密钥/Secret、审计、故障、备份和升级职责在 S07–S12 各自冻结，不让一个服务以自己“可信”绕过 Runtime 权限。

每个实际复制/改造的文件依 [v1 来源规则](WORKBENCH_INTEGRATION_PLAN.md#9-品牌版权依赖与供应链)记录原仓库/提交/路径/digest/许可/改动，并让制品 NOTICE/SBOM 回读覆盖它。法律出处允许出现 Paseo 名称；用户界面、可执行名、服务、配置、SDK 和新产品文案使用 AgentBox。上游商标、logo 与托管域名不会作为 AgentBox 产品资产继承。

## 6. 资源、依赖与门禁

v1 的 **24–42 批次估算不适用于全量范围**。冻结的 70 项包括多个跨端/跨服务领域；一项往往需要多批代码、契约和现场验收。基于三仓和现有栈差异，初估软件交付至少 90 个、可能超过 160 个可审查批次；这是排序与资源预估，不是工期承诺。S02、S03、S11 的第一个真实批次之后，用依赖、测量和平台成本重估。未经实际平台/供应商/付款输入，不给出完成日期或费用上限。

当前按项目约定由主智能体单独执行，不启动子智能体、额外用户聊天或后台自动化。每批 feature branch → 必需 CI → normal merge → exact read-back；高风险实现按适用治理取得独立审查，不能把主智能体自查标为独立。受阻时记录阶段/文件/测试/恢复条件，继续依赖已满足的获准项。一个主 Goal 持续保留；不因阶段合并、预算估算或现场等待而标 complete。

Host、浏览器和手机分发、真实 Provider Secret/登录、付费调用、GitHub/Slack/Discord/Linear App、邮件/Stripe 账户、DNS/HTTPS、生产和公开发布仍需具体目标与对应授权。工具返回成功不等于这些外部系统已安装或运营合格；软件/CI、制品、浏览器、真实服务、生产分别给证据。

## 7. 当前决策与下一项

已完成：主仓 A0/A1、三仓源码下载与固定 SHA、70 项初版盘点、PR #97 合并和六类 post-main workflow 成功回读。进行中：C3-b provider 修复、S01/S02 软件。待定：Owner 对宽权限能力的语义选择；S04/S09/S11 的冲突项在答复前保持未实施。

下一可执行批次：完成源清单的代码路径交叉检查、将本计划/清单纳入 AgentBox 文档入口并验证；同时在 C3-b 分支核对 Runtime 原生端口、动态 Project binding、资源 cleanup 和 _main 生产接线。在宽权限答复到达后将选择结果和差异验收写入本计划，继续 S02 用户页面的真数据整合。
