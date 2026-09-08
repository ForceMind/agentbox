# AgentBox 生产落地与后续产品计划

计划版本：PRP-2026-09-08-v1。状态：**Owner 已批准执行；R12-A 进行中**。
基线：`1ab28e524d018df3d59e6c48f01646bb1021a978`；源码 `0.3.0rc10`。
本轮文档分支：`codex/production-readiness-plan`。

本计划回应 Owner 的“制定完整的计划”，把上一轮评估转为可执行交付。
Owner 于2026-09-08明确回复“好的，按计划开始进行”。该批准覆盖本计划的软件执行、
阶段记录、并行分工及既有仓库的CI/正常merge/read-back。具体host/client安装、真实key/
login/付费调用/reboot、生产和发行仍按第4/10节的独立目标与授权边界执行。
已有Accepted架构继续有效；Mac Chrome/Edge完整终端、手机管理/Stop作为获批建议范围
推进。具体浏览器分发、目标主机、Origin和部署输入尚未确认，不能由计划批准推定为可用。

## 1. 阅读路径与事实基线

- Owner：先读第 2–4 节，再读第 8–12 节，判断目标、成本、支持范围和授权。
- 开发与审查：读第 5–7 节，按文件所有权、接口和验收矩阵实施。
- 部署与恢复：读第 4、7–9 节，逐项补齐目标记录和真实证据。
- 续跑：先做 live Git/GitHub preflight，再读第 12 节进度表；历史快照不覆盖 live state。

2026-09-08 已重新执行 `git fetch origin --prune`、Git/GitHub 只读检查，exit `0`：

| 项目 | 已核实事实 |
| --- | --- |
| 仓库 | `ForceMind/agentbox` |
| 起始工作区 | 干净；`main = origin/main = HEAD = merge-base = 1ab28e524d018df3d59e6c48f01646bb1021a978` |
| 最新合并 | PR #88 为文档回读；其前的 PR #87 交付 WEV-1 |
| exact-main CI | Backend、Frontend、E2E、Deployment、Security、Release Candidate 六个 workflow 均 success |
| 检查语义 | 当前 main 26 个 check：23 success；2 个历史 rc8 job 与 push 上的 dependency-review 为预期 skipped |
| 自动测试 | Linux Python 3.11/3.12/3.13 各 3920 passed / 44 skipped；Web 1109、extension 6；E2E 96 passed / 28 skipped |
| 本轮前的定向复核 | 同一源码基线的配置/API/Runtime 组合 31 passed，exit `0`；Mac 结果不替代 Linux qualification |
| 远端版本 | 仅 `v0.3.0-rc.1` 预发布；rc10 为源码/CI 候选，没有正式 rc10 Release |
| Open PR | 仅历史 Draft #42；不纳入本计划写入范围 |
| Goal | 规划开始时为`null`；Owner批准后已创建一个active主Goal，阶段记录见第12节 |

基线事实来源：[当前快照](CURRENT_STATE.md)、[既有剩余计划](REMAINING_PLAN.md)、
[能力矩阵](../CAPABILITY_MATRIX.md)、[rc10 交付](../releases/0.3.0rc10.md)。
软件、制品、host、client、真实 CLI 和运营证据分别记录。

## 2. 目标、完成定义与范围

### 2.1 首要目标

让单个管理员在一个明确支持的客户端上，通过 AgentBox 选择服务器上的正式
`READY` Project，使用实际安装的 Claude Code 和 Codex CLI，完成：

`Login → Project → AgentType → Start → Trust → Connect → input ACK/output/resize → Detach/Reconnect → exact Stop`

页面离开、返回、断网、API/Runtime 重启和主机重启都有准确状态、可执行恢复步骤，
Project 和 Git 修改得到保留。只有收到正确准入证据后才显示 `CONNECTED`。
输入 ACK 只表示既有协议定义的接收阶段，不冒充模型已经消费、任务完成或测试通过。

### 2.2 三个交付层次

| 交付层次 | 完成条件 | 可以声明的能力 |
| --- | --- | --- |
| Software/Artifact Ready | 实际 production entrypoints 接线、可安装制品、负向测试、独立审查、exact-head CI 与 merge read-back | 可以进入指定目标的安装与验收 |
| Target Qualified RC | 五项 R12 gate 在指定 host/client/CLI/artifact 组合上全部 PASS，恢复与运维验收完成 | 仅在指定非生产/evaluation Project内受控使用；不能外推其他平台或业务范围 |
| Limited Production | 已资格化 RC 完成受控试用，真实生产范围获批，部署与运维回读完成 | 单机、单管理员、明确版本和平台范围的有限生产使用 |

GitHub Release、扩展商店发布和 stable-support 声明是独立外部操作。
内部 Target Qualified RC 不要求先公开发布，也不能借未公开发布掩盖缺失验收。

协议的`ADMITTED`与产品的production qualification不同。为了取得H/I的真实证据，
G可在明确获准的隔离目标、测试Project和时间/调用窗口内进行**资格化启用**：使用真实
production组合并满足当次全部identity/key/trust/isolation准入校验，再执行受限测试。
它不是测试绕过，也不要求尚未取得的H/I结果作为启动测试的前提；记录中production仍为
`NOT ADMITTED`，不能因此对业务Project开放或作生产承诺。J才作有限生产准入决定。
I完成前后、J明确批准前都限于D08所列evaluation Project；真实CLI及Provider调用只在
D09已批准的测试调用/费用上限内进行。包含真实业务代码、生产数据或日常生产任务的
Project必须在J的具体范围中批准，不能以“内部使用”提前纳入。

### 2.3 保留与后续范围

- 保留 Phase 0–10 管理 MVP、已合并 R0–R11、WEV-1、现有技术栈、语言规则和权限边界。
- 保留 Runtime-owned Project/Git、持久化 Job、recent-auth、CSRF、Origin 和准确 Stop。
- R12 只补真实交互路径、部署、所选客户端和运营闭环。
- Phase 11 完整 Provider Manager、Files/Diff、Discovery/Resume、Approval、Task/Worktree
  在第 11 节单列；它们不会因本计划被误标为已实现或成为 R12 的隐藏依赖。
- 不扩展为多租户、多服务器控制平面、Kubernetes、通用 shell/filesystem gateway。

### 2.4 不可变边界

1. Control Plane 决定；非 root Runtime 仅执行 typed、固定 allowlisted actions。
2. Root Helper 继续只有固定生命周期能力，不参与终端路径，不获得 Secret authority。
3. Web/API/Worker 不读取 Runtime HOME、Provider Secret、WAW private key 或加密 Secret 记录。
4. Remote Control、CLI Login、Provider Authentication、Pairing、WAW 和 Browser Trust 分开。
5. 生产无 synthetic provider、test key、test harness、明文 fallback、任意 argv/path 或宽权限降级。
6. 不确定输入不重发；Detach 不等于 Stop；Reconnect 不等于 Resume；reboot 不复活原进程。
7. 保留失败及 cleanup 证据；未证明 clean 时不能释放所有权、重新发布准入或声称 Stop 成功。

## 3. 产品与客户端选择

### 3.1 建议方案及选择分支

Owner已批准按本计划执行，采用下列建议范围；具体平台/分发资格仍需R12-A与真实验证。
未把Mac/Edge目标写成已支持，也不把该批准扩大到手机完整终端。

| Profile | 建议范围 | 处理方式 |
| --- | --- | --- |
| Server | 一个授权的 Linux x86_64 host、一个管理员 | 原生 systemd；具体 distro/kernel/systemd/CLI tuple 在 R12-A 冻结 |
| Mac desktop | Mac Chrome 完整终端；Edge 单独完成同阶段资格验证 | 新增平台 adapter、安装与可信分发，状态 Proposed；两浏览器不互相代替验收 |
| Linux desktop | 已有受管 Chrome 方案的参考和可选首发目标 | 仍需真实安装；Mac 分发受阻时不能擅自把它替换成用户最终客户端 |
| Mobile Web | 状态、返回重读、明确支持的管理操作和 exact Stop | 沿用服务端权限与代次校验；不承诺 terminal Connect/input，不把 UA 判断作为安全边界 |
| Windows / mobile terminal | 不进入建议的首批终端支持 | 用户选择后先补 capability/trust 架构与可行性研究，再调整依赖和排期 |

若选择 Linux Chrome 首发，可跳过 R12-E 的 Mac 平台实现，但保留其后续明确未支持状态。
若选择 Mac 和手机完整终端，R12-A 先证明各客户端可用的独立信任机制；移动浏览器具有
某项 extension policy 不足以证明 Native Messaging、本地 trust authority 和后台恢复可用。
不能把桌面路径直接视为手机实现，不能改为由 Web/API 自己提供可信根。

### 3.2 Mac 分发是前置条件

官方文档说明：Chrome 的 Mac 自托管扩展强制安装要求相应管理资格，列出 MDM、MCX
或 Chrome Enterprise Core；Edge 对商店外扩展列出 MDM/MCX 条件。
Native Messaging 有 macOS 接口不代表本项目的 Linux trustd 已可运行。
资料核对日期：2026-09-08。
[Chrome policy](https://chromeenterprise.google/policies/extension-install-forcelist/)、
[Edge policy](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/extensioninstallforcelist)、
[Chrome Native Messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)、
[Edge Native Messaging](https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/native-messaging)。

R12-A 只比较可行的发行路径：已有管理环境的自托管 CRX，或经过批准的商店分发与
管理策略。新建 MDM、商店账号、付款、签名身份及公开发布均不是规划请求的隐含授权。
开发者模式、unpacked extension 和本地改 plist 不能作为生产分发验收的替代证据。
若 Chrome/Edge 分发产生不同 extension ID，先冻结各自 Web/client build profile 与
精确 ID 的交叉绑定；不让页面或普通 API 动态指定可信 extension ID。
Server和client保持两个物理制品，由主智能体在F拥有配对生成责任：独立的不可变
deployment compatibility manifest绑定`profile_id`、`source_sha`、server artifact/Web
digest、client artifact digest、Origin、browser family、extension ID、Native Host protocol
及明确兼容范围。它在两个制品生成后签发/固定，不递归嵌入自身digest，也不替代独立信任根。
D的最终Web构建依赖E已经冻结的公开identity/build-profile；F必须同时校验配对结果，
不能把仍含`null`的Web或另一浏览器ID的包标为可部署配对候选。

## 4. 前置输入与决策记录

未知输入不阻止有独立价值的软件工作，但阻止依赖该输入的实现决策和外部操作。
目标记录只保存非敏感信息；SSH 密钥、账号令牌、CLI 登录正文不写入文档或聊天。

| ID | 必须明确的内容 | 推荐处理与完成证据 |
| --- | --- | --- |
| D01 | 服务器身份、distro/version/arch/kernel/systemd/cgroup、CPU/RAM/disk、现有服务及权限范围 | 优先隔离测试机；先读回环境，形成安装差异和恢复清单；现有连接不等于允许部署或 reboot |
| D02 | 最终 HTTPS Origin、DNS、TLS/反向代理、出网与私网策略 | 选与现有信任网络策略兼容的入口；私网需求另定 typed policy，不能全局放开 |
| D03 | 首批 desktop/mobile 范围及具体浏览器版本 | 按第 3 节选择；若要求双浏览器，两者都必须 PASS 才算完成该范围 |
| D04 | CRX/store 身份、更新 URL、浏览器管理能力、客户端安装权限 | 先证明可安装与可回读的官方分发路径；public key/ID 可记录，私钥不进入仓库 |
| D05 | Runtime UID/GID、正式 Project、CLI exact binary/version/profile、登录安排 | 分别记录 Claude/Codex public capability 与 artifact digest；不从系统其他 HOME 迁移凭据 |
| D06 | WAW channel key、trustd installation key、离线 root signer 的责任与恢复 | 各 authority 分离；本地创建/使用只输出状态和允许公开的 digest；Provider Manager 不成为依赖 |
| D07 | 威胁模型是否要求抵抗管理员整盘一致回滚、是否要求硬件不可导出 | 现有软件 store 无该保证；要求更强保证时单列硬件/外部单调锚决策及成本，不虚称已支持 |
| D08 | exact predecessor、备份、测试 Project 数据保留、可执行失败注入及 reboot 窗口 | 核实 release/DB/schema 兼容；定义谁恢复、恢复到哪里、允许丢失多少测试状态 |
| D09 | 真实 Prompt/模型/调用数/费用上限，资源及可用窗口 | 未确定前只做不触发付费调用的检查；预算为用户提供值，不按估算写入工具预算 |
| D10 | 内部试用、生产激活、tag/Release、客户端签名/分发的范围 | 分开记录；批准软件计划不自动批准这些外部动作 |
| D11 | native预编译制品或受控目标构建，以及server/client完整兼容tuple | A必须选定；冻结编译器/工具链/ABI/离线依赖/SBOM/回退，版本覆盖server、Web、extension、trustd、Native Host、client installer与policy schema |

当前 [trust store](../../packages/agentbox-browser-trust/src/agentbox_browser_trust/store.py)
的 `verify_origin_network` 只接收 `production` 或 `loopback-development`，production
拒绝 private、loopback、link-local、reserved 等解析结果。不能承诺 Tailscale IP、
内网 DNS 或任意 VPN Origin 开箱可用。采用公网解析的受限 HTTPS 入口也不意味着
API 可直接监听公网；API 的 loopback 与精确代理/Origin 校验保持。
若确需私网，R12-A 必须冻结精确 host/address class、DNS 重绑定、混合解析、变更/
撤销与回读行为，再进入实现；不能用 development 模式承载生产。

## 5. 阶段、依赖与文件所有权

R12-A 至 R12-K 是既有 **R12 的子阶段**，不另建竞争性的 Roadmap。
阶段实际状态见第12节；R12-A已开始，后续仅在依赖满足时启动，不提前标记完成。

| 阶段 | 依赖 | 主要交付 | 完成后允许进入 |
| --- | --- | --- | --- |
| R12-A 目标与契约冻结 | 本计划确认；稳定输入可先完成 | target record、client/network/key 决策、五门映射和证据格式 | 平台无关实现；特定分支等其输入齐备 |
| R12-B Production API | A 的 API 契约 | 实际入口、显式 mode、singleton/readiness/lifespan 接线 | 软件组合验证 |
| R12-C Production Runtime | A 的 Runtime 契约；可与 B 并行 | 固定 executor、Runtime-only key port、filesystem-v2 主入口 | 软件组合验证 |
| R12-D 安装与制品 | A；B/C接口冻结；最终Web制品依赖E的公开identity/profile | 固定 units/sockets、manifest-v2、native 制品、安装/回退 | artifact-only 验收 |
| R12-E Client trust | A 中客户端/分发决策；可与 B/C 并行 | Linux 或 Mac 平台 adapter、浏览器策略、独立 client package | 客户端软件验收 |
| R12-F 集成候选 | B/C/D/E 的所选范围完成 | 真实 production graph 的合成外部依赖测试、版本、CI、独立审查 | Software/Artifact Ready |
| R12-G 目标安装与隔离 | F；host/key/client 安装等具体操作获批 | 只读预检、dry-run、安装、identity/socket/isolation/key gate | 目标基础资格 |
| R12-H CLI 与用户流程 | G；client 安装、CLI Login 与测试调用范围齐备 | 各 AgentType/浏览器/手机支持范围的真实流程证据 | 功能资格 |
| R12-I 故障、升级与资源 | H；可逆注入、reboot 与预算齐备 | 断网/重启/回退、备份、资源测量、可执行恢复说明 | Target Qualified RC |
| R12-J 有限生产 | I；明确生产部署与支持范围获批 | 受控试用、生产回读、runbook、维护责任 | Limited Production |
| R12-K 发布与交接 | I/J 的已获准发行范围 | immutable artifacts、签名/来源、tag/Release 或内部交付、完整记录 | 仅声明实际交付和已验证支持 |

关键依赖为 `A → (B ∥ C ∥ E) → D/F → G → H → I → J`。
D 的模板/fixture 可提前，F 必须等全部所选接口；公开发布 K 不阻断明确批准的内部试用。
没有 host 时继续 B–F 中依赖已满足的工作；不能把 G–J 的缺失证据填成 PASS。

### R12-A：目标与验收契约

- 所有权：主智能体维护 `docs/project/`、相关 WAW 文档和新的 target/evidence 模板；
  Architecture/Security/Test 只读复核。模板以当前 schema 和已批准协议为准。
- 将 [旧 host checklist](../WAW1_HOST_GATE_CHECKLIST.md) 的 v1 字段、仅 Claude 的
  readiness 和旧“crypto 待决定”文字映射到已接受的 v2、双 AgentType 和 R11 契约。
  保留历史，不重开已解决的 crypto 决策，不让 v1 清单覆盖 v2 的部署要求。
- 每项交付列出 claim、依赖、实现点、测试点、真实观察和恢复；所选 Origin/client
  分发的不可行分支须先解决，不能拖到安装后。
- D11的native构建路径必须在D实施前唯一化；受控目标构建若被选中，工具链和完整
  输入也属于受验证制品，不能临时从网络安装编译器。server与client各组件的exact
  version/digest、协议/schema兼容及可回退组合同时冻结。
- 验收：稳定软件契约无未决冲突；外部输入逐项有值或明确等待状态；测试和责任可追溯。

### R12-B：API production composition

- 所有权：`apps/api/src/agentbox_api/main.py`、`waw_application.py`、必要 typed Settings/
  readiness 与对应 tests。共享 core configuration 由主智能体协调，避免并行写入。
- 实际 `app/run` 使用显式、可审计的安装 profile；默认管理模式仍可关闭 WAW。
  选择 WAW 后缺依赖即失败，不能静默降为管理 ready 后声称终端 ready。
- mode 来自固定、installer 管理且普通服务不可修改的部署配置；只接收已有
  `DISABLED` / `FILESYSTEM_V2` 语义。A 冻结其读取与环境变量优先级，普通请求/query/
  未验证环境输入不能切换；未知值或配置owner/mode漂移拒绝。首次安装/迁移先保持关闭，
  由具体获准的资格化启用或生产激活事务在对应前置条件齐备后切换。
- 只读取固定 public anchor；保持单 API process、锁、当前 Runtime peer、Project binding
  replay、inventory finalization、stream/control 同一 owner 和 shutdown 顺序。
- readiness/Doctor 区分管理服务健康、WAW dependency readiness 与 host qualification；
  只返回有界 code，不能把 readyz 200 当成真实终端已验收。
- 验收：默认关闭、显式启用、缺项、第二进程、peer/epoch 漂移、取消、部分启动和
  cleanup failure；重放不制造重复生命周期动作，原管理流程回归通过。

### R12-C：Runtime production composition

- 所有权：`packages/agentbox-runtime/src/agentbox_runtime/server.py`、
  `waw_runtime_application.py`、新的受限 executor/key adapter 与 Runtime tests。
- `_main` 接入现有 filesystem-v2 builder。loader、epoch、executor、control、stream、
  legacy conflict 和 provider 由同一 application owner 组合，禁止启动第二套 authority。
- concrete executor 使用已验证的固定 binary/profile/held descriptor；版本、inode、digest
  和 project authority 不匹配时拒绝。生产 key port 由 Runtime 独占、固定本地入口提供。
- key 初始化和轮换定义 prepare→public pin/manifest核验→激活→旧key退休的完整事务；
  私钥不离开Runtime。失配、响应丢失或中断进入不可准入状态，旧key不会因失败被提前销毁；
  已撤销/过期的旧pin也不能为程序回退重新生效。A记录各步骤authority、持久点与恢复状态。
- 普通程序升级默认不轮换channel key。独立轮换先生成candidate，准备并验证public
  fingerprint/Runtime manifest/API anchor/Browser pin，持久化提交记录后切换active
  generation，再按恢复窗口退休旧key。提交前失败仅在证明未发布/未登记且无引用时销毁
  candidate；public trust水位已前进时保留必要key与公开记录并向前修复或关闭WAW，不能
  倒退水位。提交后失败采用向前修复，或关闭WAW并重新登记，不回滚epoch/floor。
  程序/DB rollback永不降低Runtime epoch、root/pin floor或trusted-time high-water。
- 保持单次 `take()`、启动顺序、部分构造的可达 cleanup owner、关闭期限和 poisoned 状态。
  不用进程名 kill、数值 PID 重建权限或测试 executor 补空缺。
- 验收：成功与每个失败窗口均有行为/泄露 canary 测试；legacy 与 WAW 互斥、重启分类、
  Stop/Detach/输入 race、FD/peer/provider 关闭顺序均保持。

### R12-D：Installer、systemd 与制品

- 所有权：`installer/src/agentbox_installer/`、固定 systemd/tmpfiles 资源、
  `native/waw/` 打包接口与相关脚本/tests。native 行为变更单独审查，不能伪装成打包修改。
- installer plan 精确列出将新增/替换的资源和 owner/mode；只安装固定资源。接入 WAW
  control/stream socket activation、peer 参数、manifest-v2/public anchor、Project binding
  store、epoch store、cgroup delegation 与固定 native binary 的可追溯构建。
- 当前loader要求`LISTEN_PID`匹配、`LISTEN_FDS=2`、control/stream名称顺序及FD 3/4精确对应。
  unit方案必须在真实PID 1下证明该交付顺序，不能从两个socket unit的声明顺序推断。
  无法保证时先完成固定名称映射的契约审查和拒绝重复/未知FD的测试，再改loader。
- 冻结 unit hardening 与实际 kernel/CLI 需求；CI 曾改变的 userns/AppArmor 设置不得照搬
  到主机。若确需系统策略变更，先提供最窄变更及恢复证据。
- Server release 与 client trust release 分开。前者不夹带客户端密钥/策略私有状态；
  后者不安装服务器 Runtime。公开 manifest 记录兼容 tuple 和互相需要的版本/identity。
- 当前包只含 inert native source 的范围须明确改为“目标上可验证使用的固定制品”或
  可复现、受控的目标构建流程；不通过运行时 PATH 搜索掩盖未交付 binary。
- 验收：离线核心安装、幂等重装、权限、缺包、部分写入、upgrade/rollback/uninstall、
  artifact-only imports 与真实入口组合。安装不自动启用；G中的资格化启用与J中的生产
  激活分别按第2.2节执行。

安装资源按现有v2契约明确分域，新增实际key路径由A冻结，不在本计划猜测：

| 固定资源 | 写入/读取authority | 升级与删除边界 |
| --- | --- | --- |
| `/usr/share/agentbox/waw/` public bundle及`api-host-anchor.v2.json` | installer/root写，API/Runtime按权限只读 | 与exact release/cross-pins绑定，不放Secret |
| `/var/lib/agentbox-waw/runtime-host-installation.v2.json` | installer创建固定非Secret manifest，Runtime读 | API不能读取Runtime-private bundle；host revision变化重新核验 |
| Runtime epoch/bindings/attestation | Runtime独占相关持久状态 | 程序升级不重置，卸载默认保留 |
| `/run/agentbox-waw/workspace-control.sock` / `workspace-stream.sock` | systemd创建，Runtime接收固定FD，API受限peer | 绑定当前进程身份与模式，确认cleanup再删除 |
| `/run/agentbox-waw-api/waw-api.v1.lock` | installer/tmpfiles创建固定安全资源，API持有锁 | 不因数字PID变化自动夺锁；目录/文件权限按现有loader核验 |
| native binaries与固定vendor policy | root-owned不可写制品，Runtime只读执行 | exact digest/profile验证；碰到外部既有policy冲突即停止 |
| Runtime HOME / Project / private keys | 各既有非root authority | 不随程序rollback/uninstall销毁；purge另需明确授权 |

精确资源规范复用`waw_manifest_codecs.py`、`waw_host_manifest.py`、`waw_activation.py`
和各store/lock loader；表中用途不覆盖其更严格的owner/mode/link/type校验。

### R12-E：浏览器独立信任与平台适配

- 所有权：`clients/browser-trust/`、`packages/agentbox-browser-trust/`，以及 Web 中
  `wawTrustChromium*` 的精确 build-profile 接线；普通 Workspace 状态由 Web owner 集成。
- Linux 沿用独立 systemd trustd；Mac 新增经过评审的本地服务/安装方案。当前 Linux
  `SO_PEERCRED`、`/run`、`/var/lib` 不能直接套用到 Mac；重新证明 peer identity、
  UID/PID 语义、service ownership、socket 与持久 store 权限、原子性和掉电恢复。
- 复用已接受的 public-record/protocol/crypto 核心，不新增 Web 可写信任根、localhost
  HTTP 信任代理、localStorage pin、任意 Native Messaging command 或客户端 shell。
- 每个浏览器独立回读强制安装状态、extension ID、Origin/update policy、Native Host
  manifest/path 和 trustd fingerprint；安装/撤销不由普通网页或服务器 API 触发。
- macOS 代码签名、公证、installer receipt、服务启动及回退方案在发行契约中明确；
  所需身份/账号/费用缺失时只交付未激活源码/测试包，不能宣称 production installed。
- 验收：tamper、错误 UID/ID/Origin、native shadowing、trustd loss、revoke、time rollback、
  stale floors、browser restart、sleep/wake 与 upgrade；Chrome/Edge 分开给结论。

### R12-F：组合、版本与独立审查

- 所有权：主智能体串行维护统一 version、CI/release gate、共享协议和文档；各 owner
  提供组件证据。合成外部依赖驱动真实 production composition，不复制一套 test-only app。
- 主智能体依第3.2节生成配对compatibility manifest，验证server Web和对应client的
  digest/Origin/extension ID/protocol；Chrome/Edge使用不同ID时分profile构建和验收。
  F交付可安装binary、固定公开identity及经过测试的enrollment/profile生成流程。
  trustd installation fingerprint等目标创建后才产生的公开值不由fixture冒充：G使用同一
  受控生成流程形成独立target deployment revision及最终public bundle，并重新核验
  exact配对digest后才进入H。若发生源码修改，则回到新RC的F验证。
- 运行入口、fixture installer、Linux native/sanitizer、双语言协议与 Web/native browser、
  artifact import/组合、安全 canary 和升级/回退测试；生产 build 不含 test bypass。
- Architecture/Security/Test 独立只读复核身份、Secret、持久状态和失败恢复；范围内问题
  修复并回归后再进入 CI → normal merge → exact read-back。
- 验收：所有当前必需检查终态满足版本契约；当前 required job 不得随意 skipped。
  仅记录 `Software/Artifact Ready`，G–J 仍单列未验证。

### R12-G：目标安装、key 与系统隔离

- 负责人：主智能体承担Host/Client Deployment Owner和恢复协调；Runtime与Client
  owner分别准备/执行其获准的安装步骤，现场写入串行。客户端真实安装归G：安装独立
  client package、回读强制策略/extension ID/native/trustd、验证卸载/恢复；向H交接
  exact client tuple、public enrollment/profile digest与安装receipt，未就绪不得进入H。
- 前置：具体 host、现有服务边界、安装资源、系统策略、真实 key 操作及回退范围均已获准。
  先只读预检和 dry-run，交付 exact artifact、unit/目录差异、备份验证和恢复步骤。
- 固定 artifact/source/CLI digest；本地主机创建 identity/key 的操作不回传原始 key。
  回读真实 PID 1/systemd、socket inode/owner/mode、重新 listen 后 peer identity、pidfd
  路径、cgroup controller/limit/cleanup、namespace/devpts/seccomp/LSM 与模板一致性。
- 主机与客户端当次准入前提就绪后，在第2.2节限定的测试目标进行资格化启用；H/I使用
  真实production入口收集证据，不开放未批准的业务Project或省略任何安全前提。
- 无特定 kernel primitive、owner/mode 漂移或策略冲突时保持 `NOT ADMITTED`。
  不能通过关掉隔离、扩大 socket 权限或让 Web/API 以 root 运行完成安装。
- 验收：完成G2/G3的主机安装与隔离子项，client安装单独留证；完整gate仍须等待H/I
  的CLI与恢复证据。恢复到已知管理服务或WAW disabled状态可以复验，不能只写“有快照即可回退”。

### R12-H：真实 CLI 与最终用户流程

- 负责人：主智能体统筹Test/Web owner执行实际流程并记录矩阵；CLI Operator为获得
  授权的Runtime-user操作者，Owner完成需要账号交互的官方登录，仅提供readiness。
  所需检查和工具操作由当前Codex环境直接执行，不要求Owner转交给另一个AI。
- 每个 AgentType 单独核实公开 help/version/auth/profile，实际 binary 和证据绑定。
  Runtime user 通过官方本地流程完成登录/Workspace Trust；代理只接收非敏感 readiness。
- 在批准的测试 Project 和调用预算内执行完整流程；看到真实输出且输入 ACK 身份正确，
  再验 resize、Detach、Reconnect、显式 Stop、重复 Stop 和 legacy conflict。
- desktop 使用实际浏览器交互，不用 curl、源码阅读或合成 Playwright 代替。
  测 IME、短输入、现有多行粘贴拒绝、返回、关页、窗口切换、信任失效与前后台恢复。
- 手机只验批准的管理/Stop 范围：fresh status、recent-auth、CSRF、精确 generation、
  旧确认撤销、取消、失败和晚响应。按钮可见性不替代服务端授权。
- 验收：所选每个 CLI/浏览器组合都有 PASS；局部成功可单列，但不能自动缩小批准目标
  并将双 CLI/双浏览器目标标为完成。

### R12-I：恢复、升级与容量

- 负责人：主智能体承担Recovery Owner，独立Test reviewer定义并复核故障案例；
  获准的Host/Client Deployment Owner执行注入与恢复。交接产物为完整恢复矩阵、
  exact predecessor/receipt、资源基线、未解决风险和Target Qualified RC记录。
- 对实际组合验证 API restart、Runtime restart、host reboot、browser suspension、
  网络中断、trust/CLI auth 失效、输出背压、Stop race 和失效后的明确下一动作。
- 测试数据卷/限定配额内注入磁盘不足和持久化失败，不填满共享服务器系统盘。
  付费模型调用、资源限制、reboot 和故障窗口按 D08/D09 执行。
- 对真实部署 predecessor → candidate 完成 upgrade/rollback；rc7→rc8 的历史演练
  不自动覆盖 rc1→新候选或 client trust 新 schema。不能随机选择老版本作 rollback target。
- 分别测 API/Runtime/native/trustd/browser 的 idle/active CPU、RSS、FD、磁盘、启动/
  连接/回连/Stop 时间和 cleanup 残留；记录 exact scenario、样本数与版本。
- 资源、延迟、并发和连续试用时长在 G 的实测基线后冻结；无测量时不填虚假阈值。
  协议已有 deadline、frame/input/parser budget 保持原值，不能为通过验收放宽。
- 验收：约定 failure matrix、恢复与数据保留全 PASS；允许的数据损失、恢复步骤及
  实测恢复时间都有记录，无持续资源增长或未清理进程/FD等未解释问题。

### R12-J/K：有限生产、发行与交接

- 负责人：主智能体承担Operations/Release Owner并交付可审阅的具体操作；Owner
  决定业务范围、发行身份和支持承诺。这些是责任角色，不增加并发代理或隐含新的操作者。
- J 先交付具体试用方案：一个批准 host、指定管理员、测试/业务 Project 范围、
  经 H 验收的客户端/CLI tuple、观测窗口、成功条件和停止/恢复负责人。
- 通过 I 后才允许有限生产激活。上线后回读版本、服务、权限、identity、readiness、
  实际流程和备份。试用发现变化时修复、产生新候选并重验受影响的 gate。
- K 交付 exact artifacts、checksums、SBOM、manifest、来源/签名验证方式、完整兼容矩阵、
  安装/升级/回退/诊断/登录/撤销/卸载 runbook，以及未支持项。
- 固定公开签名验证根和分发渠道；checksum 不是发布者认证。签名私钥由独立发行
  authority 保管，不进 PR/普通 CI。内部固定制品验收和公开发布可分开安排。
- tag、GitHub Release、扩展商店提交、MDM enrollment 和 production-support 文案在
  具体内容与目标可审阅后分别执行既有或新授权；没有授权时交付内部 RC，不自行发布。

## 6. 关键接口与数据契约

| 契约 | 必须成立的条件 | 失败与恢复 |
| --- | --- | --- |
| Mode / readiness | typed 管理/WAW profile；实际入口与安装配置一致；single API owner | 选 WAW 缺项不准入；管理健康与终端资格分开报告 |
| Runtime application | 一组 epoch/registry/executor/control/stream/legacy owner；held identity | 构造失败保留 cleanup owner；不产生第二个空壳 ready 服务 |
| Project / Stop | 正式 Project、current binding、host/epoch/generation、当前观察与权限匹配 | 同代/跨代并发、响应丢失与 uncertain side effect 不自动重放 |
| Protocol / terminal | 复用固定 Noise/AWCE/wire/renderer；准入前无输入；INPUT 单 ledger | 失密文或失信任新建 channel；不续旧 key，不缓存原始终端数据 |
| Installed identities | manifest-v2/public anchor/cgroup/executable/template 交叉绑定 | 不从可写 path、普通 UID/PID 或数据库旧记录重新创造 authority |
| WAW channel key | Runtime-only 固定 provider；生成/持久/使用/轮换/关闭可审计 | 缺 key、权限不符、错误 pin、关闭不确定即失败；不自动生成替代 key |
| Browser trust keys | offline root signer、trustd installation key、CRX signer 各自分离 | server/API 不能登记或降 floor；恢复需要保持单调或明确重新登记 |
| CLI credentials | Runtime user 与官方 CLI 持有；仅回传 readiness | 登录失败不复制 root auth、不扫描其他 HOME、不绕过 Workspace Trust |
| Client profile | 精确 browser/extension ID/native path/Origin/fingerprint；每平台证据 | 错 profile 或更新身份变化拒绝；不靠多个宽泛 ID/Origin fallback |
| Release / migration | exact source、schema compatibility、receipt、artifact digest、版本一致 | 应用与DB恢复分别验证兼容性；Runtime epoch、Browser root/pin floor和trusted-time high-water永不回退；不执行破坏性down migration |

Root Helper 可以执行已批准的固定服务生命周期，但不读、生成、传输、保存或恢复以上
Secret/private-key 材料。installer 的特权文件布局与 Runtime/trust authority 的本地
初始化分开实现，不能用“安装需要 root”把 Secret authority 转给 Helper。
完整 Provider Secret Manager 仍是独立 Phase 11；CLI Login 和 WAW channel key 不依赖它上线。

## 7. 五项 R12 准入与测试矩阵

沿用 [五项 R12 gate](../WORKSTATION_EVOLUTION.md#r12-production-bootstrap-and-host-gates)，
不另建一个可以绕过旧 gate 的“生产就绪”开关。

| Gate | 关闭缺口的阶段 | 最终必须包含的证据 |
| --- | --- | --- |
| G1 Production API | B/F/G/H | 实际 entrypoint/mode、public anchor、singleton/peer/readiness 和真实连接 |
| G2 Runtime provider | C/F/G/H | concrete executor/channel-key provider、one-owner graph、真实 CLI/profile |
| G3 Installed socket/isolation | D/F/G/I | systemd、socket peer、pidfd、cgroup/namespace/LSM/seccomp、Stop/重启 cleanup |
| G4 Managed browser trust | A/E/F/G/H/I | 所选真实客户端的签名/分发/强制策略/native/trustd/revoke/恢复 |
| G5 User workflow/operations | H/I；J只追加生产回读 | 双 CLI、所选浏览器、输入输出/返回/Stop、重启、upgrade/rollback 与 runbook；I结束即可判定资格化结果，不依赖尚未开始的J |

| 验证层 | 最低场景 | 明确失败条件 |
| --- | --- | --- |
| 单元/组件 | 缺依赖、非法字段、identity drift、取消/异常/超时、partial construction/close | 默认成功、遗漏 cleanup、生产测试入口或敏感正文泄露 |
| 集成/状态 | BIND→inventory→ticket→ADMITTED→stream→Detach/Stop；epoch/replay/并发 | 过早 CONNECTED、旧 generation 可写、uncertain input 重试 |
| Artifact | 独立解包/import/实际入口、版本、native inventory、安装/升级/回退 | 偷用 workspace/PATH/global runtime、来源或schema不匹配 |
| Host | 原策略下 systemd/socket/peer/cgroup/devpts/namespace/seccomp/LSM | 必需隔离缺失、广域系统策略降级、无可信 Stop/cleanup |
| Browser/client | 真签名和安装、Chrome/Edge分别、foreground/background/sleep/restart | 仅开发者模式、伪 native provider、错误 ID/Origin、撤销后仍准入 |
| Real CLI | Claude/Codex分别；正式 Project、固定argv/profile/login、真实输入输出与退出 | fixture替代vendor、登录未知算成功、错误 Project/进程被停止 |
| Recovery | API/Runtime/host restart、断网、升级中断、磁盘失败、信任损失 | 重复副作用、epoch/floor倒退、数据损失未声明、无法恢复管理面 |
| Privacy | 合成 canary 覆盖 DB/WAL/SHM、Audit/Job/log/diagnostics、DOM/storage/artifacts | 任何不允许持久化的 key/ticket/input/output/ciphertext 进入声明表面 |
| UX | zh-CN/English、桌面/手机、加载/空/失败/未授权/过期/冲突/处理中/成功 | 操作与权限不一致、假成功、遮挡/横向溢出、旧确认复活 |
| Operations | idle/active/cleanup资源、备份校验、恢复耗时、值守和限额 | 超已批准资源、持续增长、遗漏 Project/credential恢复边界 |

执行阶段状态：未开始、进行中、待验证、审查未通过、已完成。验收证据状态：
`PASS / FAIL / BLOCKED / UNKNOWN / NOT RUN / N/A`；`FAIL` 表示实际失败，不能混为没运行。
若沿用旧 checklist 只接收四种状态，则将失败记为 BLOCKED 并保留原始失败字段/exit code，
不能丢弃失败记录；映射在 A 冻结。N/A 必须有当前版本契约支持，不得用于规避必需项。

每条证据保存：case ID、对应 gate/requirement、evidence type、exact SHA/artifact digest、
OS/kernel/systemd/CLI/browser tuple、执行时间、命令与 exit code、期望/观察、恢复及审查结果。
只记录允许公开的 identity/digest/code；不保存凭据、auth 输出、私钥、真实终端正文或 cookie。
真实画面检查使用专门的非敏感 Project；敏感流程的 trace/video/screenshot 默认关闭。

## 8. 恢复、备份与回退

| 对象 | 正常保留/备份范围 | 回退要求 |
| --- | --- | --- |
| Application artifact / current link | exact predecessor 与安装 receipt | 可回到兼容候选；先关新准入、排空并核实 cleanup，再切换 |
| Control-plane DB/config | 既有 SQLite 在线备份、一致性校验、schema/版本和digest | 验证 WAL一致性；schema不兼容时使用已审核恢复路线，不直接 down migration |
| Project/Git 工作树 | 独立测试数据/代码备份，保留未提交修改与正式Project身份 | 既有安装备份不包含代码；不能用git reset/stash/clean制造“恢复成功” |
| Runtime epoch/generation | Runtime 独有持久状态及其不可回退约束 | 程序回退不倒退epoch、不复活旧ticket/session；必要时进入reconciliation |
| Browser root/pin/floor/journal/time | 独立trust authority管理；保留撤销/历史/单调水位 | 不随应用备份整体回滚；无法证明新鲜时拒绝准入并按批准方案重新登记 |
| CLI/Provider credentials / WAW keys | 不进普通安装备份或证据包 | 由各authority按明确恢复方案处理；缺失时重新登录/登记，不能复制其他用户凭据 |
| Native/systemd/client政策 | 原资源digest、owner/mode、启用状态与变更receipt | 只恢复本计划变更，不覆盖既有管理员策略或其他服务 |

优先恢复路径是“停止新 Connect/Input → 核实并清理已有 attachment/workload → 保留异常
证据 → 恢复兼容的管理服务或 WAW disabled profile → 明确重新登记/重连条件”。
若 Stop 或 cleanup 无法证明，禁止声称自动回退完成；保留隔离与所有权，由已授权运维
路径处理。不能用全盘快照还原同时重置 trust floor 和 epoch 而继续宣称原信任有效。

## 9. 风险、资源、进度与停止条件

| 风险/未知 | 影响 | 处置 |
| --- | --- | --- |
| Mac CRX分发资格缺失 | 客户端写好仍无法正式安装 | A先证实官方安装路径；不擅自部署MDM/商店发布 |
| 所选Origin解析私网 | trust拒绝准入 | A明确兼容入口或typed private策略，独立审查并测DNS变化 |
| Linux内核/LSM/userns与CLI不兼容 | 启动或隔离失败 | 原策略预检、固定受支持tuple；需要变更时给最窄恢复方案 |
| 同机运行其他服务/重要数据 | 安装与故障测试影响生产 | 隔离目标、receipt差异、限定资源；无安全窗口不做依赖动作 |
| CLI版本/官方能力漂移 | 登录/启动/恢复行为改变 | 每vendor固定公开证据与digest；未知只降级该能力 |
| Store完整回滚威胁超现有能力 | 软件签名状态可能自洽但旧 | D07明确威胁模型；强要求加单独external/hardware anchor |
| 旧rc1与新schema/状态不兼容 | 回退损坏数据或身份 | 测真实predecessor；状态分域；无兼容目标即停止升级 |
| 自定义crypto/native/trust链维护成本 | 修改影响多层协议与恢复 | 复用既有契约、集中接口、独立review；不新增通用抽象或替换框架 |
| 只追求CI绿或界面齐全 | 产品流程仍不可用 | 必须独立通过G/H/I真实运行；按gate报告，不按测试数量计算完成度 |

资源策略：最多使用环境提供的 4 个 agent 槽位，含主智能体；不递归派工。
Mac 先检查内存/负载；重型 Web/Chromium/build 串行，定向验证优先；Linux 全矩阵和
native/sanitizer优先使用 CI，不在 Mac 反复执行完整 Linux 套件，不删除共享缓存。
主机按 D09 的 CPU/RAM/disk/cgroup 和调用预算执行；同一主机/client 安装与故障注入串行。

本次未获得时间、token、费用或目标机资源预算，因此不承诺固定日期、不填写虚构完成率。
A 完成后，按已冻结目标给出每阶段区间排期、负责人可用窗口、验收/恢复时长与关键路径；
MDM/商店审核、账号、证书与主机窗口等外部等待单独列出。每批交付后依实际CI/故障数据修正。
进度以“阶段产物完成 + 相关gate证据完成”双状态表示；完成R0–R11不等于产品已完成。

下列情况停止对应依赖路径：用户要求暂停；目标/身份/必要权限不明；真实Secret可能越界；
协议或架构冲突未解决；必需CI失败/未终态；签名/Origin/peer/epoch不符；隔离缺失；
input uncertain却需要重试；Stop/cleanup不确定；预算超限；数据回退无可验证方案。
保存成果和恢复条件，继续其他独立且已批准工作，不把一个host阻断扩展为全项目停工。

## 10. Goal、模型、协作与Git交付

计划批准后主智能体先 `get_goal`：存在一致有效Goal则沿用；无Goal则创建一个主目标。
执行前查到无Goal，Owner批准后已创建active主Goal。阶段清单留在本文第12节，同任务不为每个阶段重复建Goal。
若已有不一致的未完成Goal，保留并报告冲突；不得覆盖或伪造完成。

建议主目标文本：完成获批R12范围的production API/Runtime接线、服务器与客户端制品，
在批准的host/CLI/browser组合上通过五项gate、真实交互与恢复验收，交付可验证的运维/
回退说明和已授权GitHub同步；生产激活与发布按独立明确范围执行。保留现有功能、权限、
Project/Git修改、Secret隔离、准入和准确Stop约束。未指定token budget则不设置该参数。

| 角色 | 模型/强度 | 责任与边界 |
| --- | --- | --- |
| 主智能体 | 沿用当前会话实际主模型 | 范围/接口/版本/共享文档/Git/集成/交付；配置文件或计划不代表运行模型已切换 |
| 总体规划 | `gpt-5.6-sol / ultra` | 依赖、契约、失败恢复，只读规划；本轮已使用 |
| API/常规Web/模板 | `gpt-5.6-terra / high`；简单文件可medium | 获分配目录内实现与定向测试，不动共享version/workflow |
| Runtime/key/native/client trust | `gpt-5.6-sol / high`，疑难可xhigh/ultra | 高风险身份/生命周期/平台契约与实现 |
| 独立审查 | `gpt-5.6-sol / high`或Astra high/xhigh | Architecture/Security/Test只读审查，与其实现者分离 |

每次派工明确目标、plan版本、输入、依赖、允许操作、文件所有权、接口、产物、测试及返回格式。
所有代理知晓共享工作区，不能回退他人修改；同一文件写入串行。可采用“主智能体 + API +
Runtime + Client”一批，再回收槽位做Installer/独立review；不同时堆积超过四槽的角色。

软件计划批准后的建议Git范围：已有仓库`ForceMind/agentbox`，使用`codex/r12-*`
feature branches，按独立可验收批次提交本次文件、push、CI、normal merge、exact read-back。
沿用已有机械merge政策，不增加逐PR Owner gate；禁止force push、`--admin`、改写历史。
每批开始fetch/revalidate，提交只选本次文件，保留并发WIP；权限/网络失败时保留本地并如实记录未同步。
真实host/client安装、key操作、CLI login/付费调用、reboot、生产激活、tag/Release/
商店发布及支持承诺，仅在具体授权范围内执行；不重复索要仍有效的同一授权。

版本策略：文档-only保持`0.3.0rc10`。首个行为变更批次建议`0.3.0rc11`/
`0.3.0-rc.11`/`0.3.0.11`，后续按实际独立交付递增并显式更新release gate。
独立client release还必须记录trustd、Native Host、client installer/receipt和policy
schema版本；由D11的exact兼容tuple与第3.2节配对manifest约束，不能只比较MV3版本。
初期优先沿用同一产品RC标识并附独立artifact/profile revision；任何独立升版或回退
都重新核验tuple，不假设server升级会自动升级客户端。
R12是计划阶段，不与rc编号绑定。host/client证据绑定exact artifact；仅做测试不升版，
实现变更产生新候选并复验受影响gate。不预写未来merge SHA，不提前创建`0.3.0`正式版。

每批更新：CURRENT_STATE、NEXT_ACTION、REMAINING_PLAN/ROADMAP当前入口、能力矩阵、
相关契约/说明/变更记录、可见版本与验收记录；历史移动或标记后仍可追溯。
缺现场证据写“待验证”，独立review与主智能体自查分开。Goal complete只在获批目标真完成时标记；
blocked遵守工具规定，不用其表示普通等待或困难。后台定时运行/用户可见新任务不由本计划自动创建。

## 11. R12之后的完整产品路线

以下是后续独立产品范围的完整入口，保持Proposed；R12不因它们尚未完成而无限扩张。

| 顺序 | 交付与接口范围 | 关键前提和验收 |
| --- | --- | --- |
| WEV-2 Active Work/Attention | 基于已有Job/Runtime/Project的有界只读投影，显示来源/观察时间/Unknown | 不建第二队列；状态过期/权限/去重/空失败；不从终端文字推断任务或测试成功 |
| WEV-3 Files/Changes | 新Project-scoped typed只读RPC，摘要/文件树/受限文本/patch | descriptor-bound路径、symlink/traversal、敏感内容、binary/encoding/size/取消；不附带写删/Stage/Commit |
| WEV-4 Discovery/History/Resume | 每vendor已公开能力与允许Project/Runtime user内的历史/可恢复会话 | 发现、Attach、Resume、Adopt分开；live ownership独立；跨版本/已退出/外部会话需各自证据 |
| WEV-5 Structured Approval | 先站内Attention，再接可信Runtime adapter的结构化请求 | Session/generation/requestId/TTL/撤销/一次消费；不解析终端prompt注入yes，不复用Provider approval |
| Phase 11 Provider Manager | 沿用既有Accepted ADR推进config transaction→validation→Codex adapter→activation/rollback→API/UI | 非Secret基础复用；不与WAW/login合并；失败/SSRF/配置保留/Secret custody逐阶段闭合，真实Secret另行授权 |
| Later Task/Worktree | 有实际工作流证据后再建任务与工作副本生命周期 | .git共享锁/磁盘/并发/残留/迁移/删除恢复，禁止默认每Task强制新Worktree |
| Later notifications/mobile terminal | 外部通知、PWA/push或完整手机输入另列能力合同 | 通知渠道/权限/费用/后台限制；真实移动trust/native能力先证实；不承诺必达或自动外发 |

上述各项开始前各有有限计划、数据/API/权限/验证与同步边界；不能用R12的一次确认笼统
授权全部未来业务域。优先级以真实使用反馈调整，先补主流程阻断，再补可观察的体验问题。

## 12. 执行与交接记录

| 工作 | 当前状态 | 成果/剩余条件 |
| --- | --- | --- |
| 本轮完整计划 | 已完成 | 内容/链接检查及两项独立复核通过；Owner已明确批准执行 |
| R12-A | 进行中 | host checklist已更新；API软件契约已收敛；[target record](R12_TARGET_RECORD.md)区分稳定决定与外部输入，Runtime契约继续收敛 |
| R12-B | 待验证 | rc11实现与82定向tests、51发布检查、2版本checks、Ruff/Black/Linuxmypy通过；Architecture/Security/Test发现已修复并最终PASS，等待exact-head CI/merge回读 |
| R12-C | 进行中 | [C1 key port](../WAW_R12_RUNTIME_KEY_PORT.md)实现与65定向tests通过，Architecture/Security最终PASS；独立交付/CI待完成，C2 auth-isolation/executor、C3 main待推进 |
| R12-D/E/F | 未开始 | 对应稳定契约/输入齐备后开始；不使用测试provider接通main |
| R12-G/H/I | 未开始 | 需要所选目标和具体外部操作范围，以及真实证据 |
| R12-J/K | 未开始 | 需要先前gate通过及对应生产/发行授权 |
| 后续产品路线 | Proposed | 按第11节逐项建立有限执行范围 |
| Git同步 | 进行中 | PR #89 final head `f58a41a...`完成26检查并合并`6db8d62...`，精确parents回读完成；六个post-main流程成功（Frontend同SHA重跑后成功）；API/C1源码分别待交付 |

规划交付验证记录（2026-09-08，执行前历史）：

- 主智能体完成目标/依赖/边界/复用的结构化自查；源码版本保持`0.3.0rc10`。
- `gpt-5.6-sol / ultra`完成计划完整性与依赖审查，所提三项P2修正并回审通过。
- `gpt-5.6-sol / high`完成部署/Secret/回退/制品配对审查，所提重要问题及契约歧义
  修正并回审通过。两项审查在各自文档范围内均无残留问题，不是生产安全认证。
- `python3 scripts/check-doc-links.py`：exit `0`，378个relative links通过。
- `git diff --check`及新增计划的直接空白/结尾换行检查：exit `0`。
- 本轮只有三份文档改动，没有运行新的代码测试或重新触发CI；第1节软件CI来自同一
  已核实基线，不能当成本草案的远端交付。commit/push/PR/merge均未执行。

未来阶段交接包含source/merge SHA、artifact digest、版本、修改所有权、验证/review、
gate状态、未解决风险、恢复条件和下一可执行阶段。

## 13. 术语与依据

| 术语 | 含义 |
| --- | --- |
| WAW | Web Agent Workspace，本项目受限且经过准入的网页交互工作区 |
| Runtime | 独立非root执行进程，执行固定typed动作并独占相应Secret authority |
| trustd | 客户端独立信任服务，维护public root/pin及单调状态；不是服务器API |
| epoch / generation | 区分authority重启和具体workspace运行实例的身份代次 |
| exact Stop | 绑定当前目标身份与代次，并验证实际停止/cleanup的动作 |
| Qualified tuple | exact artifact + host/CLI/client版本及配置的已验收组合 |
| fail-closed | 前提缺失、矛盾或不可验证时拒绝继续准入/执行 |

当前事实优先级：live Git/GitHub → 对应exact源码/测试/制品 → 当前Accepted契约 →
当前能力矩阵/计划 → 标记历史的报告。外部技术行为以执行前官方资料与实际目标证据共同核实。

- [项目治理](GOVERNANCE.md)、[现有执行计划](EXECUTION_PLAN.md)、[现有下一步](NEXT_ACTION.md)。
- [R11组合](../WAW_R11_CONTROLLER_COMPOSITION.md)、[R11执行](../WAW_R11_EXECUTION_PLAN.md)。
- [Workstation evolution](../WORKSTATION_EVOLUTION.md)、[能力矩阵](../CAPABILITY_MATRIX.md)。
- [Browser trust provider](../WAW_BROWSER_TRUST_PROVIDER.md)、[Browser decision](WAW_BROWSER_IMPLEMENTATION_DECISION.md)。
- [固定process](../WAW_FIXED_INTERACTIVE_PROCESS.md)、[artifact operations](../WAW_R11_RC8_ARTIFACT_OPERATIONS.md)。
- [平台支持](../PLATFORM_SUPPORT.md)、[已知限制](../KNOWN_LIMITATIONS.md)、[备份设计](../BACKUP_AND_MIGRATION.md)。
- [Phase 11 canonical ADR](../adr/README.md)、[Release checklist](../RELEASE_CHECKLIST.md)。
- [基线commit](https://github.com/ForceMind/agentbox/commit/1ab28e524d018df3d59e6c48f01646bb1021a978)、
  [Backend CI](https://github.com/ForceMind/agentbox/actions/runs/34185571106)、
  [Frontend CI](https://github.com/ForceMind/agentbox/actions/runs/34185571120)、
  [E2E CI](https://github.com/ForceMind/agentbox/actions/runs/34185571160)。
