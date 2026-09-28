# AgentBox 工作台代码迁移与后续开发计划

计划版本：AB-WORKBENCH-2026-09-28-v1。状态：**A0/A1 已合并；原技术基线保留，范围由 [v2 全量计划](FULL_CAPABILITY_DELIVERY_PLAN.md) 扩展**。

Owner 随后明确要求吸收上游全部已有功能。因此本文第 4/6/13 节的“只选部分功能”、排除项及 24–42 批次估算不再代表完整目标；继续使用本文已接受的 AgentBox 权限/来源/数据规则，完整能力与交付顺序以 [70 项清单](FULL_CAPABILITY_INVENTORY.md) 和 v2 为准。

本计划响应 Owner 的要求：下载 Paseo，将适用代码迁移、改造并整合进 AgentBox，最终只保留 AgentBox 产品，然后继续既有开发路线。Owner 已确认保留必要的第三方版权与许可声明，并于 2026-09-28 明确批准按本计划开发。软件实施、文档、必要测试和既有仓库的日常 CI/Git 交付获准；具体现场、Secret、生产及公开发行仍以本文第 13 节的输入和范围为准。

## 1. 目标、交付物与完成定义

最终产品只有 AgentBox：一个网页登录入口、一套管理员认证、一个正式 Project 体系、一套 Runtime 生命周期、一套安装升级流程和一个版本体系。用户不需要安装、启动、配置或登录 Paseo。

分三次形成可验收产品：

1. **整合工作台软件候选**：AgentBox 页面整合项目导航、工作标签、运行状态、Attention、受限 Files/Changes；已有 WAW 控制器继续负责终端。代码和制品可以验收，实际终端开放仍取决于 R12。
2. **首个真实可用版本**：完成 R12 生产入口、制品、客户端信任、双 CLI 操作、断网和重启恢复。用户可在指定主机/客户端上完成 Project → Claude/Codex → 输入输出 → 检查修改 → 重连 → exact Stop。
3. **后续完整开发工作台**：按既有 WEV-4/5、Phase 11、Task/Worktree 路线，增加受控 History/Resume、结构化会话与审批、Provider 管理、独立工作副本。每个能力单独取得实际证据，不把所有后续特性绑成首发条件。

本计划不是功能百分之百复制。上游的普通 shell、任意主机文件访问、动态插件执行、公共 relay/Hub 和多主机管理不符合当前边界；对应能力的处置在第 4 节逐项列出。用户目标由 AgentBox 能力交付实现，不以导入代码数量作为完成标准。

## 2. 已核实基线与保护范围

核验时间：2026-09-28 10:58 UTC。以下均为本次只读核对结果，早期状态文档不能覆盖这些事实。

| 对象 | 已核实状态 |
| --- | --- |
| AgentBox | ForceMind/agentbox；当前分支 codex/r12-runtime-main |
| AgentBox Git | HEAD、main、origin/main、merge-base 均为 a696193fec127595b1beafb1ed1cabf2ae58efa9；HEAD 是 PR #96 的 merge |
| AgentBox CI | 对该 SHA 查询到 Backend、Frontend、E2E、Deployment、Security、Release Candidate 六类 workflow 均 completed/success；本次没有重跑测试 |
| Open PR | 仅历史 #42，codex/agentbox-project-operating-context；不属于本次范围 |
| 当前版本 | Python 0.3.0rc13 / npm 0.3.0-rc.13；本次纯文档不升级版本 |
| 现有缺口 | server.py 的 _main 仍直接构造旧 RuntimeExecutorServer；生产 provider/application 尚未接入；R12 真实目标验收未完成 |
| 上游下载 | /private/tmp/paseo-comparison-20260928；浅克隆已完成；没有安装依赖、运行上游脚本或启动服务 |
| 上游固定版本 | getpaseo/paseo，30178c4f58b67f8472901356e1484022bd835de0，提交时间 2026-09-27T12:01:37Z；package.json 为 0.10.0-beta.1 |
| 上游许可 | 根 LICENSE 为 Apache-2.0，包含 Mohamed Boudra 版权；内部第三方组件仍按各自许可。没有发现根 NOTICE；仍须逐个迁入文件核查 |
| 当前 Goal | 批准前 get_goal 返回 null；批准后已创建一个主 Goal，承接本计划的软件与资格化清单 |

必须保留现有未跟踪工作：.reasonix/、build/、waw_runtime_provider.py、test_waw_runtime_provider.py。后两文件的完整路径及本次 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| packages/agentbox-runtime/src/agentbox_runtime/waw_runtime_provider.py | 45994c1220a23b488fd63218ede1e7f83b1f57fb788eadc2b82454a96495998a |
| tests/unit/test_waw_runtime_provider.py | 8cf3505a49b3ff88761f1c23f7965f2b28b584a709afa0f9b30a7576c01dc357 |

文件存在不代表 provider 已经通过审查、提交或集成。进入 R12-C3-b 时先核对所有权和最新内容，再利用有效实现；不 reset/stash/clean、不整体提交 build/，不覆盖并发修改。

上游临时 checkout 仅供迁移取证，不进入产品、安装包或服务列表。临时目录不是永久交付；每次取用记录固定 SHA、源路径和文件 digest，即使目录被系统清理也能按同一提交重新取得。迁移完成后只需保留实际采纳代码及来源清单，无须在仓库内保留第二个完整项目。

## 3. 推荐架构

保留 AgentBox 的 Python/FastAPI、SQLAlchemy/Alembic、SQLite、React DOM/Vite、Runtime 与原生 systemd 体系。Paseo 的 Expo/React Native、Node daemon 与 AgentBox 并不具有可直接合并的运行结构。

上游 packages/app 声明了 95 个直接 dependencies，packages/server 声明了 41 个；Claude 主 adapter 约 6419 行、Codex 主 adapter 约 7487 行。这些是当前源码测量，不是迁移比例或工作量承诺。不能把完整 provider、页面或包改个名字就当成独立模块。

拟议调用关系：

    AgentBox React Web
      ├─ 认证、项目、Job、非敏感状态 → AgentBox API / Worker
      └─ 终端及获准的内容数据 → 经 API 不透明转发 → agentbox-runtime
                                                  ├─ 既有 WAW 固定 CLI 执行链
                                                  ├─ Project Files / Git / History 适配
                                                  └─ 后续固定 Agent adapter 子进程

    Root Helper → 仍只有既有固定特权生命周期动作

明确保留以下结构：

- Control Plane 决定，Runtime 执行；浏览器不提交可执行路径、shell、argv、任意 cwd、环境变量映射或原始 provider 配置。
- Project ID 在 Runtime 内解析到 descriptor-bound 工作目录。所有新增内容操作仍是有类型、有范围、有上限的 Project 功能。
- 一套认证、授权、CSRF、Origin、审计、Job 和恢复语义。不会嵌入上游第二套管理员认证、daemon 数据目录和任务队列。
- 保留现有 Noise/AWCE、独立 browser trust、代次、epoch、pidfd/cgroup、exact Stop 契约。不导入另一套 relay 加密协议，不更换已接受的终端 renderer。
- 新 Files/History/结构化事件涉及正文时，新增独立版本化内容 schema 与准入合同，复用经审查的加密基础和 opaque relay 边界；不能把新业务 JSON 塞进现有终端 frame 冒充兼容，也不能经普通 API/log/SQLite 暴露 Runtime HOME 或 Secret。
- 上游的进程启动、fs、插件与网络能力全部从可复用算法中拆开；只有 Runtime 内被批准的固定执行层可以实际调用。

### 3.1 结构化 Agent adapter 的技术选择

推荐在 WEV-4/5 阶段采用 **AgentBox 所有的固定 TypeScript adapter bridge**，以保留可验证的事件转换代码和 Claude SDK 互操作经验；它只是 Runtime 启动和监督的受限子进程，不是 Paseo daemon，也不是独立 HTTP/WS 服务。

这项扩展属于本方案提出的新架构，尚未成为 Accepted。它不阻塞已有 R12 TUI，也不能用来绕开当前原生固定执行链。实施前用一个有限原型证明：

1. Runtime 固定 bridge 路径、解释器、依赖、vendor executable、digest、cwd、HOME 和环境；SDK 不自行下载/升级或选取未经固定的 CLI。
2. bridge 和所有 vendor/tool 子进程进入相应批准的隔离、资源及 cleanup 范围。API/Worker 不启动 bridge、不读取其文件或凭据。
3. 私有 inherited FD/受保护 IPC 只允许定义好的 session/create、turn/send、turn/interrupt、history/read、permission/respond 等动作；这些是待定内部动作名称，不直接复用上游宽权限 RPC。
4. 一条客户端交互对应明确的 session、generation、turn、operation；遇到取消、超时、进程退出、重复事件和断线不能产生额外调用。
5. 能够执行并证明整个所有权范围的 exact Stop。单独调用 turn/interrupt 不能被映射成 Stop 成功。
6. pinned Node/依赖可以进入 AgentBox 制品、SBOM、离线校验及回滚体系；构建输出不依赖 @getpaseo/* 包。

原型未通过时，该 bridge 不进入产品。Codex 可改用 Runtime 所有的固定 app-server 协议实现；Claude 的 SDK 执行隔离若仍无法满足边界，则保持既有 TUI 可用并将结构化 Claude 能力标为 BLOCKED。任何替代实现仍须同样的验收，不会通过放宽权限获得通过。

## 4. 逐模块迁移清单

分类：直接迁移是抽离依赖后的 TypeScript 代码复用；改造迁移保留适用算法或协议转换但重接 AgentBox；实现迁移按已确认行为在本仓技术栈实现。三类都记录来源和验证，不把翻译实现自动当作无来源的新代码。

下表目标路径均是拟建或拟修改位置；不是声称这些模块已经存在。

| 能力与上游来源 | 处理 | AgentBox 目标及约束 | 阶段 |
| --- | --- | --- | --- |
| workspace-tabs/model.ts；screens/workspace/workspace-tab-model.ts、workspace-pane-state.ts | 改造迁移纯状态逻辑 | apps/web/src/features/workbench/；使用 Project/WAW identity，不持有任意 cwd；React DOM 重做容器 | A2 |
| screens/workspace/ 的侧栏、标签、面板与手机布局 | UI 改造 | WorkspacePage 与 workbench/；保留本仓认证、路由、zh-CN/English catalogs、键盘行为；不引入 Expo 壳 | A2 |
| runtime/directory-sync/、replica-cache、状态投影 | 迁移适用机制与回归案例 | 复用 useWorkspaceStatus/useWorkspaceController；刷新水位、去重和过期提示；不复制全局 SessionStore | A2 |
| git/diff-tree.ts、diff-order.ts及对应 tests | 首批直接迁移候选 | apps/web/src/features/changes/；改用 AgentBox ParsedDiff 类型，保持文件树与正文排序一致 | A3 |
| git/diff-document/、utils/diff-layout.ts | 逐函数改造 | 先迁入必要的 diff 模型/虚拟化；DOM 渲染适配 CSP/字体/可访问性；不整体复制 Skia/native renderer | A3 |
| session/files/、workspace-git-observer/、file observation | 行为与测试迁移到 Python | Runtime 的 project_files.py / project_changes.py（拟建）及 typed protocol；权限不是上游 daemon-wide 权限 | A3 |
| types/stream.ts、timeline/、composer/ | 改造迁移 | apps/web/src/features/agentSessions/；只消费可信结构化事件；TUI 字符串不生成伪结构化工具事件 | A6/A7 |
| Claude/Codex tool-call-mapper、parser、partial-json 和 app-server transport | 小模块抽离，固定 adapter 原型 | packages/agentbox-agent-adapters/（拟建）；路径/进程/fs 权限归 Runtime，拆除插件/Hub/MCP 注入 | A6 |
| agent-storage.ts、agent persistence、provider history | 契约和恢复案例迁移 | 控制面只存 non-secret identity/状态；vendor handle/历史内容由 Runtime 保管；不复制上游 JSON 目录为第二数据库 | A6 |
| permission requests、pending-turn 与 interrupt regressions | 改造迁移 | Session/generation/requestId/TTL 绑定；与现有 Provider approval 分域 | A7 |
| worktree-core.ts、workspace archive/reconciliation | 行为和测试迁移 | 复用 GitAdapter/Job/Project 锁；新增工作副本身份；默认归档不删 WIP，不运行 repo setup hooks | A9 |
| packages/protocol、packages/client | 仅抽取必要类型/纯函数/测试案例 | Python protocol + Web contracts 为本仓权威；不完整导入上游 wire、client、认证或配置体系 | A1–A7 |
| terminal.ts、terminal-manager、node-pty/xterm 路径 | 不迁入执行链 | 保留 AgentBox WAW fixed CLI/renderer；普通 shell 与任意 command 路径不进入产品 | 全程 |
| daemon bootstrap、supervisor、relay、Hub、daemon credentials | 不迁入 | 继续 AgentBox systemd、Runtime authority、登录和独立 trust；无 Paseo 后台或外部连接 | 全程 |
| 任意插件、MCP server 配置、repo setup/scripts、自动 worktree 删除 | 不直接迁入 | 后续若需要只能建立有限 allowlist/授权/恢复合同；不因品牌迁移一并开放 | 后续另列 |
| Electron、iOS/Android native、语音、浏览器自动化、schedules | 本轮不交付 | AgentBox Web 和手机管理优先；这些不是既有路线的首发依赖，需求成立后另立有限阶段 | 后续评估 |

## 5. 数据、状态与权限合同

### 5.1 身份映射

| 上游概念 | AgentBox 处理 |
| --- | --- |
| Project/cwd | 使用既有正式 READY Project ID；cwd 由 Runtime 解析，不作为浏览器可写权限 |
| Workspace | A2 先作为 UI 工作上下文；不替换既有 Project+AgentType 唯一 WAW record。多 checkout 在 A9 引入独立 WorkContext/Checkout identity |
| Agent session | 新 AgentConversation metadata；绑定 Project、AgentType、RuntimeBinding、execution kind 和 vendor handle 引用。不是管理员登录 Session |
| Turn | 独立 turn ID、client operation ID、状态和结果引用；ACK 不等于 provider 已消费或任务成功 |
| Provider | Paseo 的 claude/codex 在本仓对应 AgentType；不能直接写成 Phase 11 ProviderDefinition 或 Secret credential |
| Approval | Agent 执行批准与 Provider 配置事务批准分域；只消费绑定当前 generation 的一次性 request |
| Archive/Detach/Interrupt/Stop | 归档隐藏、断开观察、中断当前 turn、终止确定进程范围分别定义；不互相代替 |

控制面 SQLite 仅新增必需的 non-secret metadata、索引和状态字段，沿用 Alembic；不改写原 WAW 身份、generation 或历史数据。现有用户不是 Paseo 用户，不需要自动导入 ~/.paseo、其他 HOME 或既有凭据。

会话 title、prompt、工具参数、文件正文、完整 diff、CLI 原始输出和 vendor persistence handle 默认按内容处理，不放进公共 metadata、Audit 或 API 日志。需要持久化的内容保持 Runtime-only 管理；具体 retention、容量和 browser cache 规则在 A1/A6 的 schema 中冻结。

### 5.2 恢复与一致性

- 返回页面必须重新观察 Runtime；缓存明确标记时间和 stale，不自动 Start/Resume/Connect。
- 流式内容采用单一事件标识、cursor、epoch/generation 和有界补拉；重复去重，缺口显式补拉或提示丢失。绝不承诺跨 provider 的 exactly-once。
- 输入超时或 ACK 不确定时不自动重发。UI 展示 write_uncertain，并提供查询当前状态的操作。
- Resume 必须有 vendor 的明确支持与准确 handle；发现记录不自动取得接管、输入或 Stop 权限。
- 用户中断 turn 后可以留存会话；exact Stop 必须停止已归属范围并验证 cleanup，残留未知则显示未完成并阻止同身份重新准入。
- DB migration 采用 expand-first；回退前检查旧程序 schema 兼容。不能以清空 DB、会话或 Project 作为回退办法。

### 5.3 Files/Changes

- 只允许正式 Project 内的相对路径/Runtime opaque file ID；Runtime 使用持有的根目录与文件 descriptor，拒绝 traversal、symlink escape、magic link、设备、socket、FIFO、Runtime 配置和凭据位置。
- 项目内秘密文件同样需要保护：只读不代表内容可公开。批准的敏感目录/文件策略、binary/encoding/size 边界先写入合同；路径匹配不被描述为万能 Secret 检测。
- 文件树与 patch 有分页、字节/行数上限、取消、完整性标记和更新时间；达到上限明确截断，不把未返回内容当作空文件。
- Git diff 禁止 external diff/textconv、hooks 和交互 pager，不接受自由 Git 参数。大仓库与 rename/binary/untracked 流程单独验证。
- 第一版 Files/Changes 只读，不顺带开放文件编辑/删除、stage/commit、shell 或自动测试执行。现有安全 Git 管理能力继续保留。
- 默认源代码/文本展示，不直接执行 HTML、SVG 脚本、Mermaid 外链或项目提供的前端代码。

## 6. 阶段、顺序与验收

以下是一个整合计划中的阶段，不另建相互竞争的路线。R12 仍负责真实执行闭环；原 WEV-2/3 的软件部分提前与工作台整合，WEV-4/5、Phase 11、Task/Worktree 保持后续依赖关系。这项顺序调整随本方案审批，不声称已经生效。

| 阶段 | 具体交付 | 前提 | 完成证据 |
| --- | --- | --- | --- |
| A0 基线与来源 | 源码固定、WIP 保全、许可清单、上游到目标映射、候选模块依赖图 | 方案批准后进入实施；下载/初步核对已完成 | 每个候选可追溯到 commit/path/digest；代码未跨边界执行 |
| A1 契约与薄切片 | Accepted ADR、身份/权限/内容 schema；迁入 diff-tree 或等价纯函数及原回归案例；验证最小 Web 集成 | A0 | AgentBox 自己构建测试成功；不依赖完整上游包；明确可迁入和需重做项 |
| A2 工作台与 WEV-2 | 项目导航、工作标签、状态/Attention、返回重读、旧 Workspace controller 接入；桌面与手机管理布局 | A1 | 实际 API/状态驱动；无伪造聊天/测试结果；关闭标签不隐式 Stop；交互/截图矩阵通过 |
| A3 WEV-3 Files/Changes | Project-scoped 内容合同、Runtime 文件/Git 只读实现、加密内容通道、Web 文件树和 Diff | A1；先 A2 的交付形态 | traversal/敏感路径/权限/资源上限/取消/断线测试；实际受控文件变更可正确显示 |
| A4 R12 软件闭环 | 复用现有 C3-b WIP，完成 _main、provider/application、activated sockets、key/epoch 所有权；D/E/F 制品及客户端适配 | 已合并 C3-a；可在 A2/A3 前优先修复阻断 | fixed production 组合正负向测试、安装制品/升级回退、客户端 build/契约、exact-head CI；仅 Software/Artifact Ready |
| A5 R12 真实验收 | 指定 host/client/Origin 安装；Claude/Codex 登录、输入输出、Files/Diff、重连、exact Stop、服务/主机重启、升级恢复 | A4；各新增通道软件验收；具体现场授权与输入 | G1–G5、R12-H/I 证据；随后按授权完成 J 有限生产、K 发行/交接。未满足时不宣称可用 |
| A6 WEV-4 会话与历史 | 固定 adapter 原型；Codex/Claude 分别落地 structured session/timeline/composer、限定 History/Discovery/Resume | A1；产品开放依赖 A5 和新增 adapter 自身资格 | 一条真实 turn、持久化/重启恢复、重复事件/缺口/跨版本/未知 handle、TUI 与 structured 执行互斥/并发策略均验证 |
| A7 WEV-5 结构化审批 | 一次性 permission 请求、Attention 联动、明确 Allow/Deny、超时与撤销、turn interrupt | 对应 provider 的 A6 能力成立 | 旧 generation、重复/过期/重放响应拒绝；不会注入终端 yes；Stop 与审批竞态验证 |
| A8 Phase 11 | 复用既有模型与 Secret Store 基础；config transaction→validation→Codex adapter→activation/rollback→API/UI | A5；沿用现有 Provider/Secret authority 合同 | 失败回滚、SSRF、配置保留、Secret custody 与审计；真实 Secret 操作单列授权。Claude 仍遵循现阶段 session-only 边界 |
| A9 Task/Worktree | 实际需求驱动的任务、受管 checkout、分支/工作副本生命周期，复用 Job/锁 | A5；涉及结构化会话的功能依赖 A6/A7 | dirty/untracked/unpushed 内容保护、shared .git 锁、并发 checkout、残留恢复、容量和归档验证 |
| A10 收尾与延伸 | 移除迁移适配残留、更新帮助/SBOM/来源、运维交接；评估通知和完整手机输入 | 对应已交付批次稳定 | 产品只依赖 AgentBox；剩余 Proposed/Blocked 明确；不会自动启用外部通知、语音或后台自动化 |

执行规则：主智能体按依赖串行推进。外部 host 或 client 分发缺失时，继续 A2/A3/A6/A7 中不依赖该输入的软件与 fixture 工作；所有相关生产入口保持不准入，并记录待补实际验收。不能把“现场受阻”转成“停止所有软件”，也不能用 mock 替代现场。

首次可用版本不必等 A6–A10。A4 的生产入口修复是当前最高优先级的运行阻断；工作台迁移不会成为延后该修复的理由。

## 7. 第一轮有限实施清单

批准后先完成下面四个可审查批次，之后据实际依赖成本更新估算，保持同一主计划：

1. **来源/契约批次**：落实 A0/A1，写明 upstream-origin manifest、许可文本位置、迁入文件头与 import allowlist，确认正文通道和 identity 模型。
2. **实际代码迁入批次**：从 diff-tree.ts / diff-order.ts 抽离必要算法及相应测试，接到 AgentBox 类型；展示一份受控 patch 的文件树与排序，不新增主机权限。
3. **工作台批次**：保留既有 WAW controller，迁入标签/侧栏纯状态行为，实现真正可操作的 Project/Workspace 页面和 Attention 只读投影；已有管理入口保持可达。
4. **生产入口批次**：核对并接续 C3-b WIP，把 production provider/application 与 _main 连通，关闭资源所有权、异常 cleanup、socket/key/epoch 的单元和集成缺口。

这些批次让代码迁移与最紧迫的原路线同时前进；不先复制整个上游、不先建设所有新业务域。

## 8. 文件归属与代码组织

默认由当前主智能体承担全部实现、集成和自查。本计划不请求或启动子智能体。若之后需要独立审查，按用户授权与适用治理要求列清审查来源；主智能体自查不会标为独立 PASS。

| 责任 | 主要写入位置 |
| --- | --- |
| 主计划、决策、验收与来源 | docs/project/、docs/adr/、docs/LICENSING.md、拟建 third_party/upstream-sources.json 和 notices 目录 |
| Web 工作台/变化/会话 | apps/web/src/features/workbench/、changes/、agentSessions/（拟建）；现有 pages、lib/contracts、i18n catalogs |
| 数据与 API | packages/agentbox-core/、packages/agentbox-protocol/、apps/api/、必要的 Alembic migrations |
| Runtime 内容和会话 | packages/agentbox-runtime/；复用 ProjectRegistry、GitAdapter、WAW ownership，不建立第二进程主管 |
| 后续固定 TS adapter | packages/agentbox-agent-adapters/（拟建）；只有 A6 原型通过后进入制品 |
| 安装、信任与升级 | installer/、clients/browser-trust/、现有 systemd/native 资源、release scripts |
| 验证 | 对应 unit/integration/native tests、Web tests/E2E、artifact 与 host evidence records |

共享 schema、版本、DB migration 和公共 controller 由主智能体串行修改。迁入功能按本仓领域放置，不建立 vendor/paseo 全仓副本或一个与现有应用并列运行的 paseo 包。

## 9. 品牌、版权、依赖与供应链

- 所有产品名称、标题、导航、应用标识、服务、包名、配置命名和帮助入口使用 AgentBox；新代码使用 @agentbox/*，不连接 paseo.sh、其 relay/Hub 或遥测/更新端点。
- 法律声明与迁移来源保留准确的 Paseo 名称、版权主体、原路径与 commit；这不构成保留第二个产品。品牌验收对 notices/来源记录作明确例外，不能执行全仓无差别替换。
- 修改过的来源文件带修改说明，包含原来源、原 SHA 和 AgentBox 改造范围；保留适用版权/专利/归属声明及许可证副本。若具体组件有 NOTICE 或额外许可，按实际材料纳入。
- 根 Apache-2.0 不覆盖所有 bundled 组件。只核查真正采纳的文件、字体、图标、highlight、编辑器和运行依赖；不把上游整个 dependency tree 带入。
- 不复制上游 logo、营销素材、商店标识或示例个人信息。沿用 AgentBox 自有视觉与可用素材。
- 锁定直接和传递依赖，核查 lifecycle scripts，再执行安装；不运行上游 root postinstall/prepare、自动下载模型/CLI、发布或安装 hook 的脚本。
- 来源清单逐文件记录 source URL、commit、source path、SHA-256、license、目标路径、copy/adapt/port 分类、修改说明及对应测试。SBOM/第三方许可库存与实际制品一致。
- 后续更新按 pinned commit 比较和审查补丁；不自动 git merge 上游 main，不直接依赖 @getpaseo/server/client/protocol 的运行时发布包。

依据：[上游 LICENSE](https://github.com/getpaseo/paseo/blob/30178c4f58b67f8472901356e1484022bd835de0/LICENSE)、[Apache-2.0 第 4/6 节](https://www.apache.org/licenses/LICENSE-2.0)、[AgentBox Licensing](../LICENSING.md)。

## 10. 验证矩阵与交付门槛

| 层级 | 必须证明的内容 |
| --- | --- |
| 来源/构建 | 迁入文件与锁定来源相符；import graph 不带入 daemon/Expo/relay；AgentBox 独立 build；品牌与许可清单分别检查 |
| 纯逻辑 | 复用适用的上游测试与边界输入；新增本仓契约测试，覆盖排序、标签 identity、diff 截断、事件重复/乱序/缺口 |
| 权限/内容 | 认证/CSRF/Origin、Project 边界、descriptor replacement、symlink、敏感文件、内容不进入 API logs/DB、超大/恶意数据和 XSS/CSP |
| 生命周期 | input uncertain、detach/reconnect、turn interrupt、exact/repeated Stop、关闭标签、取消/超时/失去权限、cleanup 残留和 epoch/generation 冲突 |
| 数据 | 现有 DB 升级、重复 migration 防护、失败恢复、旧版本兼容判断、非敏感 metadata、Runtime 历史 retention；不破坏既有 Project 和 WAW 状态 |
| UI/交互 | 1440/1024 桌面与 390/768 代表宽度，zh-CN/English、键盘/焦点、加载/空/错/未授权/过期/冲突；真实浏览器渲染与截图，不以 build 代替 |
| 性能 | 对同一提交/环境/样本测量列表、流更新、大 diff、断线补拉的耗时与资源；A1 冻结样本和有依据的预算，不在计划中编造性能提升 |
| Linux/制品 | 既有 CI contract、native/sanitizer 与受影响安装、systemd/socket、SBOM、升级回滚。新 adapter 单独纳入 provenance 与隔离验收 |
| 目标现场 | 指定 CLI/host/browser/artifact 完成 G1–G5 和真实开发流程；必须分开报告 Software Ready、Target Qualified RC、Limited Production |

每批只运行与变更有关的必要检查；当前 head 的全部必需 CI 按既有规则完成。新增变更、失败或未关闭风险才扩大/重复验证。上游测试文件存在不算运行通过，本轮源码阅读也不构成上游安全或可用性认证。

验收表至少记录 command、exit code、exact SHA、环境、case、结果、未验证边界。状态使用 PASS/FAIL/BLOCKED/UNKNOWN/NOT RUN/N/A，不能将 pending/skipped 当成功。

## 11. 发布、回退与 WIP 保护

1. 实施开始重新 fetch 并核对 branch/HEAD/WIP；使用 codex/ 前缀的适当 feature branch。需要隔离时优先复用合适 worktree，遵循 managed worktree 工具流程；不改变当前 WIP 归属。
2. 每批仅提交负责文件，按 feature branch → exact-head CI → normal merge → read-back 交付；本次方案文档尚未 commit/push。方案批准时明确其软件与仓库同步范围，不扩展到新建远端项目或外部发布。
3. 纯文档不改版本。功能批次按既有 Python/npm/MV3 版本来源同步递增，以实施时 live 版本确定下一个号；不提前承诺某个 rc 号或合并 SHA。
4. 新 UI 可以按既有 capability 暴露；没有 backend/host 证据的功能显示准确未就绪原因，不放入可执行假入口。迁移期间保留旧的可用管理入口作为可恢复路径。
5. 产品回退用验证过的 installer rollback/兼容版本，必要时回到 WAW disabled；保留 DB、Project、历史和来源清单。代码撤回用新的正常提交，不重写历史。
6. 新 DB schema 先扩展，删除旧列/旧兼容层放在经过稳定验收的后续批次。worktree 初版归档是 metadata 操作，物理删除始终是独立的已授权动作。
7. CI workflow、lockfile、安装器和 Native Messaging/client distribution 的改变都进入相应审查与回归；不把源码重命名等同于部署身份已改变。

## 12. 依赖、风险和停止条件

| 条件/风险 | 处理及继续方式 |
| --- | --- |
| React Native/Expo UI 隐含依赖 | 迁入算法与状态，DOM/CSS 重建；A1 薄切片验证实际依赖成本，不整包复制 |
| 上游宽权限与本仓严格 authority 冲突 | 拆分执行与展示；保持 Runtime-only 权限。无法拆分的部分停留在参考材料 |
| 新内容通道与既有加密 frame 不兼容 | 新 schema/version 与互通测试先行；不擅自扩展旧 frame 或增加 plaintext fallback |
| SDK 自行 spawn/读取配置绕开 fixed profile | A6 有限原型先证明；不能固定或清理时关闭该 provider 的结构化能力，保留已验收 TUI |
| 两套 Session/Provider/Workspace 语义混淆 | 先 identity 映射、单一权威状态和事件协议；不直接替换现有表或持久化路径 |
| 目标 host/Origin/浏览器分发缺失 | 复用 R12_TARGET_RECORD 的 D01–D11，继续独立软件；暂停相关现场步骤，不宣称产品准入 |
| 上游新版本变化、许可证或依赖问题 | 固定已核对 SHA；缺许可/来源证据的文件不进入制品；每次升级按小补丁重新验证 |
| WIP/并发修改 | 重新核对文件 digest 和 diff，保护 .reasonix/build 与未提交 provider/test；不覆盖、丢弃或广泛提交 |
| 范围膨胀为第二套 IDE/平台 | 第一版只做本文 A2/A3+A4/A5；后续功能按原路线有限交付，新增原生 App/多主机/云端服务另列需求 |

P0/P1、安全边界失效、数据损坏、无法证明进程 cleanup 或客户端信任时停止相应交付；保留现场证据和已完成工作，继续无依赖的获准事项。Host、真实 key/Secret/login、付费调用、reboot、生产与发行仍按具体目标和授权范围执行。

## 13. 资源、估算与执行授权

以单主智能体、小批次实现、已有测试/代码有效、无需重写全部基础设施为估算前提。一个批次表示一个可独立审查和回退的逻辑交付，不等于固定天数或固定一次对话。

| 范围 | 初步批次数估计 |
| --- | --- |
| A0/A1 基线、合同、薄切片 | 2–3 |
| A2 工作台与 Attention | 2–4 |
| A3 Files/Changes 及内容通道 | 3–5 |
| A4 剩余 R12 软件/制品/客户端 | 4–7 |
| A5 目标验收与恢复 | 按真实 host/client case 安排；外部等待不折算软件批次 |
| A6/A7 结构化会话、历史与审批 | 6–10 |
| A8 Provider Manager | 3–6 |
| A9 Task/Worktree 与 A10 收尾 | 4–7 |

首个整合软件候选并达到 R12 Software/Artifact Ready，初估 11–19 个批次；本文完整软件范围初估 24–42 个批次，另加现场验收。估算依据是跨前端平台、Runtime/协议边界、现有 C3-b 和新 adapter 的实际依赖；A1 后、A6 原型后各重估一次。不承诺未验证的复用比例、token 成本或“几天全部完成”。

未指定 token/时间/费用预算，工具预算沿用默认；真实 CLI 调用前采用 Owner 明确给出的费用窗口。默认单智能体，不启动后台自动化或新聊天，不把历史多智能体授权搬到本任务。

Owner 已批准本方案。软件实施范围为 A0–A4、A6–A10 中列明的软件、文档、必要测试和既有仓库的日常 CI/Git 交付；依赖未满足的阶段只做独立可验证部分。架构新增项以本方案和 A1 ADR 明确的边界落实，实质变更重新说明。A5 的真实目标、key/Secret/client 安装、付费调用、reboot、生产与公开发行需要具体输入和对应授权，不能由笼统方案批准推定。

批准后已先 get_goal，并在无冲突目标时建立一个主 Goal。目标清单包括本计划的软件与资格化交付，主 Goal 的具体终点与批准范围一致；不得因外部验收缺失而把整个产品目标标 complete。

## 14. 当前进度与下一步

- [x] 下载固定上游源码，确认源 checkout 干净且 SHA 一致。
- [x] 复核 AgentBox live Git、open PR、exact-head workflow、版本与现有 WIP。
- [x] 核对上游许可、前后端依赖和代表性源码，形成模块映射。
- [x] Owner 确认 AgentBox-only 产品与必要版权/许可声明共存。
- [x] 形成完整方案、阶段、权限、验收、回退与资源估算。
- [x] Owner 批准本技术方案与软件实施范围。
- [x] A0 来源清单、版权声明及独立 worktree 建立。
- [x] A1 首个实际迁入薄切片：Changes 文件树/排序；23 个回归/适配用例、TypeScript、ESLint、Prettier 通过。
- [x] A1 [Workbench identity/内容 ADR](../adr/0009-workbench-identity-and-content-boundary.md) 已接受；A3 具体内容通道另行审查。
- [ ] A1 feature branch 的 CI、normal merge 与 exact read-back。
- [ ] A2–A10 按依赖执行，保留 R12 外部输入与真实证据边界。

**批准后的第一项可执行工作**：保护现有 C3-b WIP，准备适当 feature branch，建立来源清单和最小 diff-tree/diff-order 迁入；同步冻结 Workbench identity/内容通道合同，随后接续工作台和 Runtime 生产入口。

## 15. 依据与证据索引

本仓：[产品入口与当前状态](../../README.md)、[既有生产计划](PRODUCTION_READINESS_PLAN.md)、[目标记录](R12_TARGET_RECORD.md)、[能力矩阵](../CAPABILITY_MATRIX.md)、[Runtime 入口](../../packages/agentbox-runtime/src/agentbox_runtime/server.py)、[WAW 数据边界](../../packages/agentbox-core/src/agentbox_core/waw_models.py)、[WAW R11 合同](../WAW_R11_CONTROLLER_COMPOSITION.md)、[Host Gate](../WAW1_HOST_GATE_CHECKLIST.md)。

上游固定版本：[架构](https://github.com/getpaseo/paseo/blob/30178c4f58b67f8472901356e1484022bd835de0/docs/architecture.md)、[安全边界](https://github.com/getpaseo/paseo/blob/30178c4f58b67f8472901356e1484022bd835de0/SECURITY.md)、[diff-tree](https://github.com/getpaseo/paseo/blob/30178c4f58b67f8472901356e1484022bd835de0/packages/app/src/git/diff-tree.ts)、[workspace tabs](https://github.com/getpaseo/paseo/blob/30178c4f58b67f8472901356e1484022bd835de0/packages/app/src/workspace-tabs/model.ts)、[Claude adapter](https://github.com/getpaseo/paseo/blob/30178c4f58b67f8472901356e1484022bd835de0/packages/server/src/server/agent/providers/claude/agent.ts)、[Codex adapter](https://github.com/getpaseo/paseo/blob/30178c4f58b67f8472901356e1484022bd835de0/packages/server/src/server/agent/providers/codex-app-server-agent.ts)。

本次命令证据：git fetch origin --prune、git status/branch/rev-parse/merge-base/diff、gh pr list、gh run list 均最终 exit 0；上游浅克隆与源码读取 exit 0。python3 scripts/check-doc-links.py 通过 418 个相对链接；git diff --check 通过；新文档尾随空白检查与两个既有 WIP 文件 SHA-256 回读通过，均 exit 0。此次未运行产品测试、未安装上游 dependencies、未发真实 Agent 调用、未部署或迁移数据。
