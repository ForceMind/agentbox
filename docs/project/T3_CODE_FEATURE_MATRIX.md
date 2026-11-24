# T3 Code 固定版本功能融合矩阵

核查日期：2026-11-23（America/Los_Angeles；固定来源时间另列 UTC）。性质：**固定上游功能审计、现有能力映射和操作级验收输入**。
这是 [全量 70 项清单](FULL_CAPABILITY_INVENTORY.md)、
[S00–S14 交付计划](FULL_CAPABILITY_DELIVERY_PLAN.md) 与
[K0–K8 产品计划](KEBUI_PRODUCT_PLAN.md) 的审计子项；执行顺序由
[T3 融合计划](T3_CODE_INTEGRATION_PLAN.md) 和现有
[K2-D01–D07](KEBUI_DELIVERY_EVIDENCE_AND_GAPS.md) 收口，不另建路线。

## 1. 固定基线与当前交付边界

| 对象 | 精确基线 / 结论 |
| --- | --- |
| T3 Code | `pingdotgg/t3code@d73e41a3fa379b591d9fb59d722d2569ec05994b` |
| 上游 tree / commit 时间 | `8be25ebe4d0f58ec2055d3f6c45470ccc21c3b7f`；`2026-11-24T05:55:58Z` |
| AgentBox 比较基线 | `13b2877823d5338cd4044ead39d658a0c89e96de`；PR177 在本次基线核对时未合并，不计入已有交付 |
| 本批代码范围 | K2-D01 纯只读 adapter capability descriptor 与对应验证；另有 Vite `7.3.7` 修复。具体软件证据见主计划/合同，不由本矩阵推断 |
| 本批未实现 | 本表中真实 provider 执行、队列、handoff、Files、worktree、远程多端、MCP/Workflow 等融合用户闭环；本表不宣称这些能力已接线 |
| 直接源快照 | 46 个完整文件，1,984,837 字节；46/46 Git blob SHA 复算匹配，逐文件 SHA-256 见 [provenance](../../third_party/t3code-sources.json) |
| 上游运行证据 | **NOT RUN**：未安装、运行或端到端测试 T3 Code；main 中有实现不能推定某 stable/nightly 已发行或各平台可用 |
| 审计数量 | 147 个 U 编号。保留 U001–U120，edge 重叠能力合并到原编号，独立缺项扩为 U121–U147；数量不是完成百分比 |

当前我方可复用的是既有正式 Project、Web/U2、WAW typed lifecycle/terminal/exact Stop、
有界 Changes、Project 标签/收藏/搜索，以及限定 inert/synthetic K2/S03 子集。
详细证据与缺口以 [已有交付清单](KEBUI_DELIVERY_EVIDENCE_AND_GAPS.md) 和本轮实时回读为准。
旧 70 项清单中的日期状态不能取代本次 main，D01 descriptor 也不能将 upstream 的
`supported` 自动提升成我方 software/host-qualified 或 `execution_allowed=true`。

## 2. 如何读矩阵

### 2.1 证据等级

| 标记 | 可证明范围 | 不可推定范围 |
| --- | --- | --- |
| **S** | 46 文件固定快照内已阅读的具体内容/关键实现；许可文件也按完整已读内容登记 | 不是全文每函数正式审计，也不是运行成功/安全认证/发行资格 |
| **D** | 固定 ref 的官方用户/架构文档说明；部分 edge 文档由独立只读子审计核对 | 文档不替代代码或 runtime 验收；不能外推所有 provider/platform |
| **P** | 确认的源码/文档路径，或补充抽读线索；**未完成该行对应细节的逐函数审查，不提升为 S** | 不把路径存在、类型或测试文件存在当成可用功能；46 个完整快照也不表示 46 个文件均已逐函数审计 |

每个源锚点前的标记仅对应该路径，不提升同一行其余路径。S、D、P 都不是 PASS。
最终 200 个唯一源锚点均由固定 ref 的已有目录或文件缓存确认存在。无法直接确认的
具体叶路径已降为已确认模块，并在对应行保留“路径待补证”；目录存在不证明功能细节。
表内实现模式是借鉴线索，**“最短验收”是未来我方关闭该项所需的最小用户/失败闭环，
本轮未执行**。每项仍需按 provider、平台、外部服务及安全合同展开实际操作清单；
多动作行不能只跑其中一个动作就全部关闭。

为缩短表格，链接标签使用以下前缀；链接本身均为上面固定 commit 的完整准确路径，
没有浮动 `main`：

| 标签前缀 | 仓库完整前缀 |
| --- | --- |
| `server/` | `apps/server/src/` |
| `web/` | `apps/web/src/` |
| `client-runtime/` | `packages/client-runtime/src/` |
| `contracts/` | `packages/contracts/src/` |
| `provider-core/` | `packages/provider-core/src/` |
| `user/` / `internals/` | `docs/user/` / `docs/internals/` |
| 其他标签 | 已是完整仓库相对路径；目录锚点仅证明该模块域，不能冒充具体函数已读 |

### 2.2 归属与边界

- U001–U147 是本审计的条目 ID，与 UI 路线 U0–U5 不同。多个 U 可归同一现有能力；
  表中 `AG01–03` 等范围表示已有 ID 的展开，不新增能力身份。
- S 阶段使用原路线定义。K2 是显式会话，K3 是 durable Task，K4 是 handoff/review，
  K5 是可解释路由，K6 是持久个人工作区，K7 是协作；`K—` 表示运维/平台能力不强行归入 K 阶段。
- “待实现/缺”指尚未具备该项完整我方闭环或相应证据，不抹去表内明确可复用的基础。
  “当前差距”由现有清单、K2 合同和本轮基线比对，不是逐文件证明仓库完全不存在任何相关代码。
- 上游 server 按 OS 用户执行，不是进程/文件系统租户沙箱。普通 shell、任意文件、repo scripts、
  custom executable/env、Secret store 需按 [ADR 0012](../adr/0012-t3-code-integration.md)
  转成我方受限等价。Control Plane 决策、Runtime 执行、Root Helper 固定特权生命周期边界继续有效。
- Claude 保持 runtime/session-only；Provider Authentication、Codex/Claude Login、环境配对、
  Remote Control 和交互 Workspace 不合并。K2 首版 busy 拒绝不被队列/steer 参考自动改写。
- T3 Connect/1Password/云语音/外部 SCM/移动商店等是独立服务前提。软件参考不等于有账号、
  生产域名、付款、真实 Secret 或外发授权；不将 T3 官方服务端点迁入派生产品。

## 3. 逐项矩阵

### A1. 安装、客户端与服务（U001–U009）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U001 | CLI 安装；stable/nightly/精确版本 | D [user/install.md][t3s-001]；P [server/cli/install.ts][t3s-002] | 平台限定；不覆盖不属于安装器的同名程序 | CL04、OP01；S07；K— | 已有 AgentBox 安装基础；缺跨平台精确版本安装闭环 | 选定版本安装并回读版本；已有异源同名命令时拒绝覆盖。 |
| U002 | 前台 server、自动开 Web、无浏览器启动 | D [user/install.md][t3s-001]；P [server/cli/server.ts][t3s-003] | 默认 CLI 入口；headless 可用性需按平台验收 | CL01、OP01；S01；K2 支撑 | 已有 Web/原生服务；缺统一前台启动与可见连接信息 | 前台启动后浏览器连接同一实例；headless 模式不启动浏览器，退出行为可说明。 |
| U003 | 一步启动远端环境及后台服务 | D [user/background-service.md][t3s-004]；P [server/cli/up.ts][t3s-005] | LAN/Connect 有不同网络与账号前提 | CL06、OP01；S07；K— | 已有原生管理路径；缺自托管远端引导体验 | 完成一次 AgentBox 自有远端引导，重跑复用实例，并能回读服务归属。 |
| U004 | Linux/macOS/Windows 后台服务管理 | D [user/background-service.md][t3s-004]；S [server/serviceLauncher.ts][t3s-006] | systemd user/launchd/Task Scheduler；登录生命周期各异 | CL02、OP01；S07；K— | Linux 软件基础不能外推桌面系统资格 | 每种声明平台分别证明启动、重启、退出登录/重登录与停止；不停止其他实例。 |
| U005 | PATH 集成、桌面 CLI 安装与卸载 | D [user/install.md][t3s-001]；P [server/cli/uninstall.ts][t3s-007] | 包管理器/源码/受管安装各有所有权 | CL02、CL04、OP01；S07；K— | 缺多安装来源的归属与卸载合同 | 卸载只移除所属二进制/PATH 条目；保留用户数据和未知程序并解释残留。 |
| U006 | 桌面三平台与 iOS/Android 客户端 | D [user/install.md][t3s-001]；P [apps/desktop][t3s-008]；P [apps/mobile][t3s-009] | 平台/发行限定；Intel Mac CLI 与桌面支持不能混同 | CL02、CL03；S07；K6 | 现有移动 Web 不等于原生客户端；原生客户端未验收 | 各目标系统安装自有制品、连接同一环境并恢复同一线程；单列签名/分发证据。 |
| U007 | Windows WSL 远端运行环境 | D [user/install.md][t3s-001]；P [apps/desktop][t3s-008] | WSL distro 和 Windows 桌面是不同进程/路径域 | CL02、OP01；S07；K— | 缺 WSL 安装、实例定位和生命周期接线 | 在选定 distro 启动并复用服务；切换 distro 不误用前一实例路径或凭据。 |
| U008 | CLI/文件管理器打开项目、拖入文件夹 | D [user/install.md][t3s-001]；P [server/cli/app.ts][t3s-010] | 桌面可接原生路径；Web 不能从文件夹拖放获得可信主机路径 | WS01、CL02、CL04；S02/S07；K2 | 已有正式 Project；缺客户端打开入口到正式注册的映射 | 桌面/CLI 打开已注册项目；未知路径先登记校验，浏览器拖放不直接授予主机路径权限。 |
| U009 | 服务环境配置文件 | D [user/background-service.md][t3s-004]；P [server/cli/service.ts][t3s-011] | 字面 KEY=VALUE；保留变量受保护，不作 shell 展开 | OP01、AG05；S01/S05；K— | 已有固定 Runtime 配置；不接受上游任意 env 语义照搬 | 仅允许声明字段，拒绝保留名与命令替换；错误配置不启动半配置服务。 |

### A2. 更新、兼容与恢复（U010–U015）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U010 | Provider/server/desktop 联合更新 | D [user/updating.md][t3s-012]；P [server/desktopUpdate/DesktopAppUpdate.ts][t3s-013] | 更新顺序和各环境失败独立；离线/手工管理可跳过 | AG05、OP01、OP02；S05/S07；K— | 已有 rc 制品基础；缺跨组件协调更新与失败显示 | 一组件失败时报告准确版本与已完成步骤；重试不重复破坏已成功组件。 |
| U011 | 不可变版本、迁移试运行与失败回退 | D [internals/07_server-updates.md][t3s-014]；S [server/serviceLauncher.ts][t3s-006] | launcher 拥有版本选择；SQLite 快照不涵盖附件等外部副作用 | OP02、OP05；S07；K— | 需接既有安装/恢复体系；本轮未运行升级 | 试运行失败恢复旧 DB/版本；prepared 与 committed 分开，重连后读回 update ID。 |
| U012 | 协议版本与能力协商 | D [internals/09_connection-runtime.md][t3s-015]；P [client-runtime/connection/compatibility.ts][t3s-016] | 不匹配拒连；不能从客户端版本猜 provider 能力 | CL01、CL05、OP02；S03/S07；K2/D01 | D01 仅纯只读 descriptor 候选；缺真实客户端/服务协商 | 协议不匹配明确拒绝；unknown/stale 能力禁用，不能落到另一 Agent。 |
| U013 | stable/nightly 切换与降级保护 | D [user/updating.md][t3s-012]；P [server/cli/update.ts][t3s-017] | 远端降级和 DB 向后兼容受限 | OP02、OP05；S07；K— | 缺渠道切换与 DB 兼容的操作级验收 | 切换前展示版本/兼容性；无法证明兼容则拒绝，失败可回读原版本。 |
| U014 | 崩溃后续跑、暂停与循环上限 | S [server/orchestration-v2/RestartContinuation.ts][t3s-018]；S [server/orchestration-v2/EffectOutbox.ts][t3s-019] | 最多 3 次连续 crash 续跑；人工等待/停止等阻止自动继续 | AG07、AG08；S03；K2/D04、K3 | 已有 inert journal 的 UNKNOWN 规则；缺真实 provider 接受/恢复证据 | 崩溃注入区分未发送/已接受/未知；未知不重放旧写入，审批等待不被自动跳过。 |
| U015 | Doctor、数据库维护与旧库保留 | D [user/thread-migration.md][t3s-020]；P [server/cli/doctor.ts][t3s-021] | 独占维修；旧库与临时副本不能默默删除 | OP01、OP05；S07；K— | Doctor UI/管理基础已在；缺此 DB 维修链的验收 | 运行中拒绝冲突维修；离线维修先备份，失败保留原库并可恢复。 |

### B1. 多端连接与环境身份（U016–U025）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U016 | Web/desktop/mobile 共享同一环境会话 | D [internals/01_architecture.md][t3s-022]；D [internals/09_connection-runtime.md][t3s-015] | server 拥有进程/文件/状态；client-runtime 共享客户端领域状态 | AG08、CL01–03；S03/S07；K2/K6 | 已有 Web 与 WAW；缺跨原生客户端的结构化会话同步 | 两客户端观察同一会话版本，重连补齐缺口；缓存明确离线，不生成新执行。 |
| U017 | LAN/VPN/Tailscale/HTTPS 直连与配对 | D [internals/05_remote.md][t3s-023]；P [server/auth/EnvironmentAuth.ts][t3s-024] | 网络可达性与授权分开；配对后 session 可撤销 | CL06、CL09；S07/S08；K— | 反向代理/WAW 信任基础不能替代新环境配对 | 配对到指定 host ID，错误目标拒绝；撤销后新请求与持续连接均失效。 |
| U018 | 托管 Connect/relay 穿透访问 | D [internals/06_t3-connect.md][t3s-025]；P [server/cloud][t3s-026] | T3 的 Clerk/Cloudflare/域名为其服务前提 | CL07、OP04；S08；K— | 自有 relay/身份/成本方案未交付 | 使用 AgentBox 自有端点完成跨网连接与撤销；不发送任何数据到上游官方账号服务。 |
| U019 | 无头机器 device OAuth 登录 | D [internals/06_t3-connect.md][t3s-025]；P [server/cli/connect.ts][t3s-027] | 需独立身份服务；不是 provider CLI 登录 | CL07、CL09；S08；K— | 缺远端设备授权合同；需与 Provider Authentication 分域 | 另一设备完成指定 code 授权，过期/重复 code 拒绝；不因此登录 Claude/Codex。 |
| U020 | SSH 启动/复用 server 与 tunnel | D [internals/05_remote.md][t3s-023]；P [packages/ssh][t3s-028] | 只清理本次拥有的资源，不杀既有远端服务；模块内具体文件路径待补证 | CL06、OP01；S07；K— | 缺受控 SSH transport 与远端所有权证明 | 断连后重连复用既有 server；关闭隧道不停止非本次启动的服务。 |
| U021 | 环境 ID 独立于 route | D [internals/09_connection-runtime.md][t3s-015]；P [client-runtime/connection/resolver.ts][t3s-029] | 发凭据前验证身份；不降级 HTTPS | CL06、CL08、CL09；S08；K— | 已有 host/epoch 概念；缺多 route 身份解析 | 同地址更换环境后拒绝旧凭据；route 变化不改变环境身份或偷偷降级协议。 |
| U022 | 多 route 学习、排序与故障切换 | S [client-runtime/connection/supervisor.ts][t3s-030]；P [client-runtime/connection/routes.ts][t3s-031] | 远端失败不能回落本机 loopback | CL06、CL08；S08；K— | 缺多路径目录和切换状态 | 首选 route 失效可切到同一已验证环境；不存在可用路径时准确离线。 |
| U023 | 统一重连、离线状态与恢复同步 | S [client-runtime/connection/supervisor.ts][t3s-030]；D [internals/09_connection-runtime.md][t3s-015] | 单 owner 重试；jitter backoff；认证失败等待明确唤醒 | AG08、CL06；S03/S07；K2/D06、K6 | WAW 浏览器恢复规则可复用；结构化输出未接线 | 断网/前后台/双 tab 后各只有一个重连 owner；读同步不重发消息或审批。 |
| U024 | HTTP token 刷新与 WS 生命周期分离 | D [internals/09_connection-runtime.md][t3s-015]；P [client-runtime/connection/driver.ts][t3s-032] | 连接健康与数据订阅新鲜度分开 | CL06、CL09；S08；K— | 缺同一认证体系下的长期连接更新合同 | 刷新 HTTP 授权不重复订阅健康 WS；撤销仍关闭连接，过期数据标 stale。 |
| U025 | 设备授权、scope、批准与撤销 | S [server/auth/RpcAuthorization.ts][t3s-033]；D [internals/05_remote.md][t3s-023] | 上游 full scope 近似该 OS 用户权限；非租户沙箱 | CL09；S08；K7 支撑 | 现有单管理员域；尚无多设备分级授权闭环 | 设备 A 收窄授权后不能调用设备 B 权限；撤销在执行前重查并终止对应会话。 |

### B2. 多环境与共享（U026–U030）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U026 | 按资源为新线程选择环境 | D [internals/05_remote.md][t3s-023]；P [server/resourceTelemetry][t3s-034] | 新 thread 选择，不迁移已有 thread；移动端可有不同入口 | CL08、AG14；S08/S06；K5 | 当前单 host；缺可解释路由与资源新鲜度 | 显示所选环境/依据；离线或无权环境不参加选择，用户可覆盖。 |
| U027 | Linked environments 与跨机委派 | D [internals/05_remote.md][t3s-023]；P [server/peer/RemoteDelegation.ts][t3s-035] | Labs beta；link 不传递，关闭后不得启动新委派 | CL08、AG14、HB02；S08/S11；K4 | 缺 peer grant、任务归属与跨机取消 | A→B 委派只带收窄能力；不能借 B 到 C 扩权，撤销后不再派新任务。 |
| U028 | 跨环境线程只读查看及主动接管连接 | D [internals/05_remote.md][t3s-023]；P [server/peer/PeerThreadRelay.ts][t3s-036] | Labs beta；附件/文件不随线程 relay 自动复制 | CL08、AG08；S08；K6 | 缺远端只读 projection 与主动切换语义 | 预览明确来源环境；打开操作需连接/授权，不把不可访问附件当本机路径。 |
| U029 | 单 thread Guest 分享与建议 | D [user/guest-links.md][t3s-037]；P [server/orchestration-v2/GuestShareDecider.ts][t3s-038] | Labs beta；Connect 前提；单浏览器 24h；owner 才能发送 | CL09、AG11；S08；K7 | 缺访客域；不能据此宣称已有组织/团队 RBAC | 访客只能看被分享范围和提出草稿；所有执行由 owner 明确发送，撤销立即生效。 |
| U030 | Guest 附件额度、待审与清理 | D [user/guest-links.md][t3s-037]；P [server/guest][t3s-039] | Labs beta；4 件/条、每条 10MB、待审 20MB | CL09、AG11；S08；K7 | 缺访客附件独立生命周期 | 超额拒绝，dismiss/revoke 删除未发送附件；访客上传不能落入任意仓库路径。 |

### C1. Provider、实例与账号（U031–U041）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U031 | Claude Code 原生结构化执行 | S [server/orchestration-v2/Adapters/ClaudeAdapterV2.ts][t3s-040]；D [user/providers-claude.md][t3s-041] | 基于 Claude Agent SDK；不能由 TUI 文本推断结构化事件 | AG01；S03；K2/D01–D07 | WAW/inert 基础；本批 D01 仅能力描述，无真实 adapter 接线 | 固定 SDK/CLI 版本完成一次合法 turn；真实事件/terminal 可归因，unsupported 操作拒绝。 |
| U032 | Codex 原生结构化执行 | S [server/orchestration-v2/Adapters/CodexAdapterV2.ts][t3s-042]；D [user/providers-codex.md][t3s-043] | typed App Server；能力按版本/账号验证 | AG02；S03；K2/D01–D07 | WAW/inert 基础；descriptor 不等于 Codex 已可用 | 固定 App Server 完成 turn、读取事件并验证 interrupt/恢复各自 ACK，不借 Claude 结果外推。 |
| U033 | Cursor/OpenCode/Grok/Antigravity/Kiro/Pi/Muse/fx | D [internals/03_providers.md][t3s-044]；P [server/provider/builtInDrivers.ts][t3s-045] | 每种 provider 的登录、模型和操作矩阵不同 | AG03、AG04；S05；K2 延伸 | 额外 provider 未取得我方验收；不可只加名称进选择器 | 每个宣称支持的 provider 分别通过运行/失败/取消/恢复，未支持操作在 UI 和 Runtime 均拒绝。 |
| U034 | ACP Registry 发现、认证及自定义 ACP | D [user/providers-acp.md][t3s-046]；P [packages/provider-acp-registry][t3s-047]；P [packages/provider-acp][t3s-048] | v2 preview 优先/v1 协商；自带工具/权限，不保证隔离 | AG04、EX03；S05；K2 延伸 | 缺 ACP 协议适配；自定义本地命令需转为受限配置 | 安装一个固定 registry agent 并协商能力；未知协议版本拒绝，自定义 argv 不变成 Web shell。 |
| U035 | ACP 精确版本安装与 checksum | D [user/providers-acp.md][t3s-046]；P [server/provider/acp][t3s-049] | 有校验值才验证 SHA256；不能把无 checksum 下载称作已验证供应链 | AG04、EX01；S05/S09；K— | 缺可审来源、锁版本与回退链 | 固定版本/来源/校验记录；hash 不匹配拒绝，缺校验值明确显示证据不足。 |
| U036 | 多 Provider instance、独立 scope/catalog/credential binding | S [server/provider/ProviderInstanceRegistry.ts][t3s-050]；S [server/orchestration-v2/ProviderAdapterRegistry.ts][t3s-051] | 按 instanceId 路由；替换先关旧 scope，再建新 scope | AG05、AG06；S05；K2 | Phase 11 有受限 Provider 管理；缺实例生命周期和结构化执行对应关系 | 同 provider 两实例不串账号/模型；更改配置后旧回调不能污染新实例。 |
| U037 | executable/args/home/env 的实例定制 | S [provider-core/server/instanceEnvironment.ts][t3s-052]；D [user/providers-claude.md][t3s-041] | 上游参数字面展开不等于我方允许任意可执行文件 | AG05；S05；K— | 保留固定 allowlist/Runtime 所有权；需受限等价配置 | 只允许受控 executable/profile/env 字段；拒绝 shell 语法、未知变量与 Runtime HOME 旁路。 |
| U038 | Claude 多配置/账号实例 | D [user/providers-claude.md][t3s-041]；P [server/provider/ClaudeProvider.ts][t3s-053] | CLAUDE_CONFIG_DIR 不等于 HOME；不同目录不能原生续同 session | AG01、AG05；S03/S05；K2 | Claude 保持 runtime/session-only，不据上游将其纳入 Provider Manager | Runtime 内两合法 session 配置隔离；跨配置续接明确拒绝或进入独立 handoff。 |
| U039 | Codex 多 CLI 账号与 shadow home | D [user/providers-codex.md][t3s-043]；P [server/provider/CodexManagedHome.ts][t3s-054] | 共享 session/config 与独立 auth 区别；完全不同 home 不能原生续接 | AG02、AG05；S03/S05；K2 | 缺由 Runtime 承担的账号/会话边界；Web 不读取 HOME | 切账号后凭据不串用；只在证明 conversation 同源时 native resume，否则显式另开会话。 |
| U040 | Codex managed ChatGPT connection | D [user/providers-codex.md][t3s-043]；P [server/provider/CodexManagedTokenBroker.ts][t3s-055] | 区别于 CLI login；shared connection 无 Fast/Ultrafast | AG02、AG05；S03/S05；K2 | 未实现托管连接；必须保持 Codex Login 与 Remote Control 分域 | 连接范围/账号/过期可见；撤销后 broker 不再发 token，能力受限不能显示为已支持。 |
| U041 | 自定义 API key/endpoint 与预设连接 | D [user/providers-codex.md][t3s-043]；D [user/providers-claude.md][t3s-041]；P [server/provider/ProviderCredentialStore.ts][t3s-056] | 底层 agent 必须支持该连接；Secret 与普通配置分域 | AG05；S05；K— | 已有 Runtime Secret authority；缺按 adapter 约束的 endpoint/profile 合同 | 普通设置只持 secret reference；API/Web/Worker 不读明文，未知 endpoint/profile 拒绝。 |

### C2. 模型、权限、维护（U042–U050）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U042 | 模型目录、自定义模型和 provider options | D [internals/03_providers.md][t3s-044]；P [server/provider/model-manifest.json][t3s-057] | manifest 与实时能力合并；部分 provider 不支持手工 custom model | AG05、AG06；S05；K2 | 缺动态能力目录；D01 不能由模型名推导权限 | 过期目录标 stale；不支持的 option 被拒绝，用户选择与最终运行模型可回读。 |
| U043 | 同 thread 切 provider/model 与接续策略 | S [server/orchestration-v2/ProviderSwitchService.ts][t3s-058]；D [user/portable-handoffs.md][t3s-059] | in-place/next-turn/restart+resume/handoff/reject 明确区分 | AG07、AG10、AG14；S03/S06；K4 | K2 首版显式执行绑定；跨 agent 接续未实施 | 切换显示 native resume 或新会话 handoff；当前 turn 不被暗中转给另一个 Agent。 |
| U044 | 手动/自动压缩、清空与重启 session | D [user/providers-claude.md][t3s-041]；D [user/portable-handoffs.md][t3s-059]；P [server/orchestration-v2/IdleCompactionService.ts][t3s-060] | 主动 cache 前压缩为 beta；clear 可保留 UI 历史而另开 native session | AG07、AG08；S03；K2/K6 | 缺 provider-specific context 生命周期 | 压缩/clear/restart 各自回读 native identity；不把保留的 UI 历史冒充仍在模型上下文内。 |
| U045 | Plan、Todo、结构化问题与审批 | S [provider-core/server/ProviderAdapter.ts][t3s-061]；P [server/orchestration-v2/RuntimeRequestService.ts][t3s-062] | 能力不同；问题回答/计划确认/工具审批不能合成一种 terminal 输入 | AG11、AG12；S03；K2/D05 | 只有 awaiting_approval 元数据；无真实审批/问题执行 | 显示原始 request/options 与 scope；一次性答复，过期/冲突拒绝；不发 terminal yes。 |
| U046 | Supervised/auto edits/Auto/Full access 模式 | S [provider-core/server/ProviderAdapter.ts][t3s-061]；S [server/orchestration-v2/Adapters/ClaudeAdapterV2.ts][t3s-040] | 上游默认 Full access 不是我方默认；不支持模式不能靠自动同意伪造 | AG06、AG12；S03/S05；K2/D01、D05 | 权限模式需映射现有 Runtime policy；本批无放宽 | 每模式有真实 adapter 证明；模式缺失/过期时拒绝，运行中变更不得扩大已授权 turn。 |
| U047 | Provider/MCP 远端登录与回调接续 | D [user/providers-acp.md][t3s-046]；D [user/providers-codex.md][t3s-043]；P [server/provider/ProviderAuthService.ts][t3s-063] | provider/MCP 与环境登录分开；回调可能需手工粘贴 | AG05、AG15；S05/S06；K— | 缺每种登录的独立 scope/回调归属 | 回调绑定发起 instance/state；错设备/过期回调拒绝，不把服务器登录当 provider 授权。 |
| U048 | 安装检测、受管更新与兼容性阻断 | D [user/updating.md][t3s-012]；P [server/provider/ProviderInstallationGate.ts][t3s-064] | 必须证明安装器拥有目标；pinned/Nix/未知安装手动处理 | AG05、OP01；S05；K— | 缺统一受管 provider 安装证明 | 报告检测版本/来源；未知所有权不更新，版本不兼容不能继续启动。 |
| U049 | 被动健康检查与显式重探测 | D [internals/03_providers.md][t3s-044]；P [server/provider/providerStatusCache.ts][t3s-065] | 后台检查不应偷偷启动 MCP/hooks/login | AG05、OP01；S05；K— | 缺低副作用 probe 与状态缓存合同 | 背景查询不会运行用户 hooks 或弹登录；显式重探测返回来源/时效/失败原因。 |
| U050 | Provider 特有 skills/任务/图片/浏览器功能 | D [user/providers-claude.md][t3s-041]；D [user/providers-codex.md][t3s-043]；P [provider-core/server/ProviderAdapter.ts][t3s-061] | 按账号/版本/平台逐项；不把所有 native 功能承诺为通用 UI | AG01–03、EX05；S05/S06；K2/K4 | 缺单项能力登记；这是待展开操作清单，不是一次验收关闭项 | 选定一个具体 native 功能证明事件/权限/结果；其余维持 unknown 或 unsupported。 |

### D1. 输入、队列与线程管理（U051–U064）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U051 | 项目 thread、scratch thread 与转为项目 | D [user/thread-sidebar.md][t3s-066]；P [server/project/ScratchThreadPromotion.ts][t3s-067] | 非 Git 不显示 branch/diff；删 scratch thread 不等于删文件 | WS01、AG07；S02/S03；K2 | 已有正式 Project；尚无可执行 scratch thread 域 | 新建/转正式项目保持内容归属；删除会话保留或清理文件的结果明确可回读。 |
| U052 | 后台新建、同 prompt 并发多模型 | D [user/composer.md][t3s-068]；P [server/orchestration-v2/ThreadLaunchService.ts][t3s-069] | 并发模型要求 Git/worktree；各 thread 独立 | AG14、WS03；S04/S06；K4 | 缺多执行归属/预算；K2 首版只显式单 Agent | 同 prompt 产生独立 thread/worktree/结果；取消一个不终止另一个或覆盖其文件。 |
| U053 | Queued/steer 发送模式 | D [user/composer.md][t3s-068]；P [server/orchestration-v2/ThreadMessageIntake.ts][t3s-070] | 只有 provider 支持 steer 才开放；slash command 可强制排队 | AG07；S03；K3 扩展 | K2 当前 busy 拒绝；不把队列悄悄加入 D01 | 分别证明 queue 与 steer 的真实 ACK；不支持 steer 明确拒绝，不自动改成 interrupt。 |
| U054 | 持久消息队列、编辑/删除/提前发送 | S [server/orchestration-v2/EventSink.ts][t3s-071]；S [server/orchestration-v2/EffectOutbox.ts][t3s-019]；D [user/composer.md][t3s-068] | server 持久化；停止/重启可 held，需明确恢复 | AG07、AG08；S03；K3 | 现有 inert journal 不是产品队列；未实现持久调度 | 重启队列顺序和编辑 revision 可回读；held 不自动执行，重复 command 不多发 turn。 |
| U055 | 移动离线草稿、附件与待发恢复 | D [user/composer.md][t3s-068]；P [apps/mobile][t3s-009] | 离线草稿不等于已送达；Web 未上传附件刷新后可能需重选 | AG08、AG11、CL03；S03/S07；K6 | 缺原生离线草稿/附件队列；默认不得 reconnect 自动提交 | 离线编辑后恢复草稿与附件状态；只有用户显式发送才提交一次。 |
| U056 | Markdown 富文本 composer | D [user/composer.md][t3s-068]；P [web/components/ComposerPromptEditorTiptap.tsx][t3s-072] | 编辑体验与最终 Markdown 文本分开 | AG11；S03；K2/D06 | U1 为合成设计；正式正文 owner/发送尚缺 | 代码块/列表往返不改变用户文本；伪审批/HTML 只作为内容，不能触发动作。 |
| U057 | 大文本转附件、图片/视频与限额 | D [user/composer.md][t3s-068]；P [server/attachmentStore.ts][t3s-073] | 文档 120k 字符/32KiB 粘贴阈值；provider 另有限额 | AG11、WS07；S03/S04；K2 | 缺内容准入与附件上传闭环 | 超限在发送前显示，附件 ready 前不提交；失败可重试上传且不重复发消息。 |
| U058 | 文件/终端/diff/元素/PR/thread context chips | D [user/composer.md][t3s-068]；P [web/components/ContextChip.tsx][t3s-074] | thread 引用按需读取；引用不授予远端消息/文件权限 | AG11、WS06、WS08；S03；K2/D06 | 缺统一 ContextRef 与来源/快照区别 | chip 保留 Project/environment/版本；跨环境无权时不可读取，不静默换成同名本地文件。 |
| U059 | 回答引用、prompt stash、跨草稿复制 | D [user/composer.md][t3s-068]；P [contracts/orchestrationV2.ts][t3s-075] | 复制 context 可失败；失败 chip 应保留修复提示 | AG11、EX05；S03/S06；K6 | 缺持久模板/引用语义；不代表泛化插件或长期记忆 | 引用能定位原消息；stash 往返文本无损，失效引用不偷偷删去。 |
| U060 | pin/reorder/tag/unread/rename 与标题生成 | S [contracts/orchestrationV2.ts][t3s-075]；D [user/thread-sidebar.md][t3s-066]；P [server/orchestration-v2/ThreadManagementService.ts][t3s-076] | 排序等 server 状态与自动生成字段分开 | AG09、AG17、WS14；S03/S10；K6 | 已有 Project 收藏/标签；没有 thread 级全套生命周期 | 两客户端排序/标签收敛；自动标题不覆盖手改标题，未读状态有明确作用域。 |
| U061 | active/working/settled/archive/snooze | D [user/thread-sidebar.md][t3s-066]；P [server/orchestration-v2/ThreadSettlementService.ts][t3s-077] | 部分 sidebar 布局为 beta；archive 禁止新消息 | AG09；S03；K3/K6 | 缺 thread 终态/暂停/归档区分 | 归档后拒发且能恢复；settled 不伪装已杀进程，snooze 不丢审批。 |
| U062 | 自动 settle、PR 关闭关联和 Undo | D [user/thread-sidebar.md][t3s-066]；P [server/orchestration-v2/ThreadSettlementService.ts][t3s-077] | 工作中/待审批/待问题不能自动 settle | AG09、WS05；S03/S04；K3 | 缺自动生命周期规则与撤销 | PR 结束且线程无待办才 settle；人工 Undo 恢复准确状态，不重跑任务。 |
| U063 | 限额状态、reset 后继续与 snooze | D [user/thread-sidebar.md][t3s-066]；P [server/orchestration-v2/UsageLimitRecoveryWorker.ts][t3s-078] | provider 无 reset 时间时手动；停止/新指令可撤销计划 | AG16、AG07；S03/S10；K3/K5 | 缺 quota 恢复与用户控制；不能据此自动换付费账号 | 展示限额来源/reset；用户停止后 reset 不续跑，未知 reset 不伪造倒计时。 |
| U064 | thread/消息全文搜索 | D [user/thread-sidebar.md][t3s-066]；P [server/orchestration-v2/ThreadSearch.ts][t3s-079]；P [server/orchestration-v2/messageSearchIndex.ts][t3s-080] | 文档 CJK ≥2 字/英文 ≥3 字母；搜索须服从内容权限 | AG08、WS14；S03；K6 | 已有 Project 搜索；不等于会话全文索引 | 搜索仅返回可授权历史；删除/撤销后索引同步清除，旧 cursor 不跨范围混合。 |

### D2. 分支会话、恢复与上下文（U065–U072）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U065 | Side chat 与主线程并行 | D [user/portable-handoffs.md][t3s-059]；P [server/orchestration-v2/ThreadForkService.ts][t3s-081] | 可能共享 checkout；权限独立快照，影响恢复隔离 | AG10、AG14；S03/S06；K4 | 缺 side chat 的内容/文件所有权合同 | side chat 不打断主 turn；共享目录可见且文件恢复被冲突保护。 |
| U066 | Fork 到指定回合与 merge-back | S [contracts/orchestrationV2.ts][t3s-075]；P [server/orchestration-v2/ThreadForkService.ts][t3s-081] | native fork/portable handoff 按 provider 分支；不能承诺等效内部状态 | AG10；S03；K4 | 缺真实 fork/回传适配；D01 只描述能力 | 在指定边界分支，结果回传有父子身份；不支持 native fork 时明确改用有限上下文。 |
| U067 | 原生/应用子 Agent 进度与审批汇总 | S [provider-core/server/ProviderAdapter.ts][t3s-061]；P [server/orchestration-v2/DelegatedTaskQuestionReactor.ts][t3s-082] | provider-native 与 app-owned 两种归属不可混淆 | AG13、AG12；S06；K4 | 缺真实子任务关系、事件/问题转交 | 主线程看到每个子任务来源；回答只作用于对应 request，父任务退出不误标子任务完成。 |
| U068 | Stop/interrupt 与子任务终止防串线 | S [server/orchestration-v2/Adapters/CodexAdapterV2.ts][t3s-042]；S [contracts/orchestrationV2.ts][t3s-075] | run/attempt/ordinal 拦截迟到事件；turn interrupt 不等于 exact process Stop | AG07、AG13；S03/S06；K2/D05、K4 | WAW exact Stop 已有有限软件证据；structured interrupt 尚缺 | 旧 run 的 completion 不结束新 run；interrupt ACK 未知时 fence，不用 Ctrl-C fallback。 |
| U069 | 跨 provider portable handoff | S [server/orchestration-v2/ProviderSwitchService.ts][t3s-058]；D [user/portable-handoffs.md][t3s-059]；P [server/orchestration-v2/ContextHandoffService.ts][t3s-083] | 完整消息/角色/顺序；默认 16k 预算；不复制 reasoning/tool 状态/附件 | AG14、AG08；S06；K4 | 缺有界上下文选择与跨 Agent provenance | 保留当前请求与完整历史片段，省略项可追溯；UI 明示新 native session。 |
| U070 | Native resume 失败与有限历史恢复 | D [user/portable-handoffs.md][t3s-059]；P [server/orchestration-v2/ProviderContinuationService.ts][t3s-084] | 未知副作用不能盲重播；新会话与旧会话身份分开 | AG07、AG08；S03；K2/D04、D06 | 已有 UNKNOWN 原则；缺 vendor resume 失败分类 | 失效 handle 不继续写；提供明确恢复选择，新 session 不能冒称接续旧进程。 |
| U071 | 旧历史迁移与原库保留 | D [user/thread-migration.md][t3s-020]；P [server/orchestration-v2/legacy][t3s-085] | 只复制一次；tool/approval/checkpoint/native session 不完全迁移 | AG08、OP05；S03/S07；K6 | 未定义通用会话历史迁移 schema | 重复迁移不重复导入；显示不可迁移字段，旧库保留且无权限内容不外泄。 |
| U072 | 持续 goal 与暂停/停止 | D [user/providers-codex.md][t3s-043]；D [user/providers-claude.md][t3s-041]；P [provider-core/server/ProviderAdapter.ts][t3s-061] | provider-specific；goal completion 不等于 CLI exit | AG07、AG14；S06；K3 | 尚无 durable Task/goal；不能给现有 Job 改名完成 | 目标/轮次/停止原因可回读；用户暂停后不继续，完成必须有定义的结果证据。 |

### E1. 项目、仓库与 worktree（U073–U080）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U073 | 创建/导入/clone/publish 项目 | D [user/project-settings.md][t3s-086]；P [server/project/ProjectService.ts][t3s-087]；P [server/project/ProjectCloneTracker.ts][t3s-088] | clone 异步，draft 与可执行 workspace 区分 | WS01；S02；K2 | 正式 Project 已有；缺一体化 clone/publish 及 clone 中状态 | clone 完成且绑定 READY 后才允许执行；失败保留原因，重复打开不重复克隆。 |
| U074 | SSH clone 失败后的 HTTPS fallback | D [user/source-control.md][t3s-089]；P [server/project/ProjectCloneTracker.ts][t3s-088] | 认证失败不能伪报成功；fallback 与 remote 变化须可见 | WS01、WS05；S02/S04；K— | 缺传输 fallback 的受控凭据/状态规则 | SSH 失败后只在已允许 HTTPS 目标重试；最终 remote/认证方式可回读。 |
| U075 | 多 repo 项目、外部目录、忽略 repo/submodule | D [user/multi-repo-projects.md][t3s-090]；P [server/project/T3ProjectFileLoader.ts][t3s-091] | 项目配置来自 project-root t3.json；外部目录有独立范围 | WS01、WS03；S04；K6 | 现有单正式 Project 边界不能隐式扩到外部目录 | 列出每个 repo 身份和授权；未知目录拒绝，submodule 状态不混入父 repo。 |
| U076 | 隔离 worktree 与 branch 命名 | S [server/vcs/GitVcsDriver.ts][t3s-092]；D [user/multi-repo-projects.md][t3s-090] | 无 commit 仓库不能创建 worktree；worktree 不是 OS 沙箱 | WS03；S04；K— | 缺 managed worktree 用户闭环 | 从明确 base 建独立 branch/worktree；失败清理只影响本次资源，原 checkout 内容不丢失。 |
| U077 | 多 repo worktree、自定义 layout | D [user/multi-repo-projects.md][t3s-090]；P [server/vcs/VcsProvisioningService.ts][t3s-093] | 自定义脚本需幂等；逐项目串行/超时/补偿 | WS03、WS11；S04；K— | 任意 repo 脚本与现有边界冲突；需固定 Runtime 动作等价设计 | 一个 repo 失败时报告并补偿已创建资源；不接受浏览器任意脚本/argv。 |
| U078 | worktree 之外的共享文件显式标识 | D [user/multi-repo-projects.md][t3s-090]；P [server/project/worktreeContainer.ts][t3s-094] | shared link 会影响其他 thread；不随快照自动隔离 | WS03、WS07；S04；K— | 缺共享/隔离文件分类及冲突 UI | 编辑前显示共享范围；恢复不会静默覆盖其他 thread 的共享文件。 |
| U079 | 项目 setup/actions/settle scripts | D [user/project-settings.md][t3s-086]；P [server/project/ProjectSetupScriptRunner.ts][t3s-095] | 原 checkout 与 managed worktree 清理语义不同 | WS11、WS09；S04；K— | 缺仓库脚本来源/固定动作合同；不直接开放 shell | 经允许的命名动作在正确 workspace 执行一次；停止/settle 不误杀共享服务。 |
| U080 | 默认分支 pull 与 worktree 清理 | D [user/project-settings.md][t3s-086]；P [server/serverRuntimeStartup.ts][t3s-096]；P [server/vcs/worktreeRemoval.ts][t3s-097] | 不能清理唯一未保存副本；自动 pull 应避免 dirty checkout | WS04、WS05；S04；K— | 缺清理引用计数/数据保全及自动 pull 策略 | dirty/WIP/仍引用 worktree 拒删；清理后正常 checkout 和未跟踪用户文件保留。 |

### E2. Diff、Git 与 checkpoint（U081–U086）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U081 | turn/branch/commit diff 与多 repo 筛选 | S [server/vcs/GitVcsDriver.ts][t3s-092]；D [user/source-control.md][t3s-089]；P [server/checkpointing/CheckpointDiffQuery.ts][t3s-098] | pull/rebase 引入内容不能自动归因于本 turn | WS08；S02/S04；K2 | 已有路径与有界 staged diff 基础；缺 turn/branch/commit 全模型 | 同一 turn 的修改归因准确；截断/二进制/旧 base 显式显示，切 repo 不混 snapshot。 |
| U082 | Git status/branch/switch/commit/push | S [server/git/GitWorkflowService.ts][t3s-099]；S [server/git/sharedCheckoutGuard.ts][t3s-100] | 共享 checkout 活跃会话需围栏；上游部分查询 fail-open 不照抄 | WS05；S02/S04；K— | 已有元数据；尚无全套固定 Git 写动作闭环 | 共享活跃 checkout 拒绝危险切分支；无法证明状态时拒写，commit/push 回读确切 SHA。 |
| U083 | 隐藏 checkpoint 与独立 index/object staging | S [server/vcs/GitVcsDriver.ts][t3s-092]；S [server/checkpointing/CheckpointStore.ts][t3s-101] | commit-tree/隐藏 ref；先发布对象再 ref；不是用户分支提交 | AG10、WS08；S03/S04；K2/K6 | 缺 checkpoint 存储与 retention 合同 | 抓取快照不改用户 branch/index；断在对象/ref 之间可恢复，不生成悬空有效 checkpoint。 |
| U084 | 对话 rewind 与文件 restore 协调 | S [server/orchestration-v2/CheckpointRestoreSafety.ts][t3s-102]；P [server/orchestration-v2/CheckpointRollbackService.ts][t3s-103] | 先核验 provider rollback；admission/执行双重检查隔离 | AG10、WS07；S03/S04；K2 | 缺双资源回退事务/补偿与真实 provider 证明 | provider 不支持时不改文件；共享目录/代次改变时拒绝，部分失败有准确恢复状态。 |
| U085 | 多 repo rewind 的不可恢复范围 | D [user/multi-repo-projects.md][t3s-090]；P [server/orchestration-v2/CheckpointRollbackService.ts][t3s-103] | 无历史 snapshot 的 repo、repo 外文件不能自动倒回 | AG10、WS03；S03/S04；K6 | 缺逐 repo 恢复结果与缺口呈现 | 回退报告逐 repo 成功/未覆盖/失败；绝不显示整任务已恢复而遗漏共享文件。 |
| U086 | worktree 位置与 clone 加速 | D [user/project-settings.md][t3s-086]；P [server/vcs/CheckoutCloner.ts][t3s-104]；P [server/vcs/worktreeCheckoutCache.ts][t3s-105] | macOS APFS 等平台优化；不保证其他文件系统效果 | WS03、OP01；S04/S07；K— | 缺可配置存储位置与缓存失效策略 | 缓存命中/失效都产生相同正确 checkout；不支持平台安全退化并记录实际耗时。 |

### F1. Source control 与 Pull Request（U087–U097）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U087 | 多 source-control host 认证与适配 | D [user/source-control.md][t3s-089]；P [packages/source-control-definitions][t3s-106] | GitHub/GitLab/Forgejo/Gitea/Bitbucket/Azure/GitCafe/TanStack/Cursor Origin 按能力区分 | WS05、HB03；S04/S12；K4 支撑 | GitHub 管理基础不等于所有 host adapter | 每个声明 host 分别证明读/写/认证范围；无能力的操作明确 unavailable。 |
| U088 | commit/push/PR 串联与生成文案 | S [server/git/GitWorkflowService.ts][t3s-099]；D [user/source-control.md][t3s-089] | 元信息可独立文本模型生成；外部写入必须有明确动作范围 | WS05、AG17、EX07；S04/S10；K4 | 缺可审串联结果/副作用收据；不授权自动发 PR | 用户审核文案后执行一次；某步失败保留已成功 SHA/PR，重试不重复建 PR。 |
| U089 | PR 列表/过滤/保存视图/详情/评论/review/merge | D [user/source-control.md][t3s-089]；P [server/pullRequest/PullRequestService.ts][t3s-107] | 保存视图可为客户端本地；各 host 权限不同 | WS05、WS08、HB03；S04/S12；K4/K7 | 缺 PR 工作台；需将并列动作分别验收 | 列表到确定 PR 的评论/review/merge 逐动作回读；无权动作拒绝，保存视图不冒充跨端同步。 |
| U090 | 确定 head 的 review/merge 与 stale 拒绝 | D [user/source-control.md][t3s-089]；P [server/pullRequest/PullRequestService.ts][t3s-107] | 查看后有新 push 则需重新确认目标 | WS05、WS08；S04；K4 | 缺 expected-head 绑定的外部修改合同 | 确认后注入新 head，merge/review 拒绝或要求重审；不静默作用于未审变更。 |
| U091 | thread 多 PR/stack 关联与 CLI PR 发现 | D [user/source-control.md][t3s-089]；P [server/orchestration-v2/ThreadPullRequestService.ts][t3s-108] | 关联不直接授予修改权限；PR 状态驱动 settle 仍有条件 | WS05、AG09；S04；K3 | 缺可靠关联来源与生命周期联动 | 识别关联的 repo/head；PR 关闭不误 settle 正在工作或待审批的 thread。 |
| U092 | Watch PR：CI/评论/冲突唤醒 Agent | D [user/source-control.md][t3s-089]；P [server/pullRequest/PullRequestWatchService.ts][t3s-109] | 定期共享读取与有限唤醒；文档检查/失败上限不可当 SLA | HB05、HB07、AG16；S10/S12；K3/K4 | 缺事件去重、有限自动执行及 owner 可见控制 | 同一 CI/评论事件只唤醒一次；取消 watch 后不再派发，失败上限可见。 |
| U093 | auto-merge、workflow 批准、revert PR | D [user/source-control.md][t3s-089]；P [packages/source-control-core][t3s-110] | host-specific；批准 workflow 属外部有后果动作 | WS05、HB03；S04/S12；K4 | 缺每动作权限与结果未知处理 | 逐动作绑定 repo/PR/head；权限不足或 ACK 未知时回读，不自动重复外部修改。 |
| U094 | GitHub stack 导航/merge/rebase | D [user/source-control.md][t3s-089]；P [packages/source-control-github][t3s-111] | 多 PR rebase 可部分成功，非原子 | WS05；S04；K4 | 缺 stack 依赖和部分完成状态 | 中间 PR 失败时列出已完成/剩余，保留真实 heads；重试只处理合法剩余部分。 |
| U095 | PR Review guide 与变更引用 | D [user/source-control.md][t3s-089]；P [server/pullRequest/PullRequestReviewGuideService.ts][t3s-112] | Labs beta；临时 checkout 只读；Claude/Codex 限定 | WS08、AG14；S06；K4 | 缺受限审查任务与引用 provenance | 对固定 head 生成导读，引用定位到真实 diff；审查进程不得写原 checkout。 |
| U096 | 文件 viewed 标记与新变化失效 | D [user/source-control.md][t3s-089]；P [server/pullRequest/pullRequestViewedFiles.ts][t3s-113] | GitHub 原生同步与其他 host server 记录有差别 | WS08；S02/S04；K6 | 缺文件审阅进度与 head 绑定 | 文件变化后旧 viewed 标记 stale；跨客户端读回范围一致且不掩盖新变更。 |
| U097 | 跨环境 PR 凭据路由 | D [internals/05_remote.md][t3s-023]；P [client-runtime/connection/pullRequestRoutingPermissions.ts][t3s-114] | 默认关闭；读/写分级；未知 mutation 不自动重试 | CL08、CL09、WS05；S08/S12；K7 | 尚无跨 host 凭据代理；Secret 不能进控制面 | 只在显式 grant 下代执行固定动作；撤销/未知结果时停止，凭据不泄给请求方。 |

### F2. Issue、关联与链接（U098–U100）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U098 | Issue 检索/评论/状态/标签/assignee/reaction | D [user/source-control.md][t3s-089]；P [server/issue][t3s-115]；P [packages/issue-tracker-linear][t3s-116] | GitHub/GitLab/Azure/Forgejo/Linear 各自能力；不是全部外部集成都已证明 | HB03–05；S12；K7 | 缺统一 issue 工作台及逐 tracker 资格 | 每种声明 tracker 完成读取和一种已授权修改；外部消息类动作保持明确发送范围。 |
| U099 | Issue↔thread↔PR 关联与 Agent 工具 | D [user/source-control.md][t3s-089]；P [server/orchestration-v2/ThreadIssueService.ts][t3s-117]；P [server/mcp/toolkits/issues][t3s-118] | 读关联与远程写 scope 分开 | WS05、HB05、AG14；S06/S12；K4 | 缺同一 Task 的三方关联来源 | 从 issue 启动合法任务并关联确切 PR；无写 scope 时只能读，不能自动改 issue 状态。 |
| U100 | PR/thread 链接、prompt links 与 deep links | P [user/prompt-links.md][t3s-119]；P [server/cli/app.ts][t3s-010] | 品牌 scheme/domain 自有；链接参数是不可信输入 | CL02、CL03、WS14；S07；K6 | 缺跨端深链；文档路径已确认，未逐函数审查 | 自有链接打开正确环境/项目草稿；外部链接不能直接发消息、选任意 cwd 或绕过登录。 |

### G1. MCP、CLI 与 Agent 编排（U101–U106）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U101 | Agent 调用项目/thread/worktree/PR/preview 等产品能力 | D [internals/02_effect-services.md][t3s-120]；P [server/mcp/toolkits][t3s-121] | transport 复用领域服务；工具出现不代表当前 caller 获权 | AG15、EX08、CL04、CL05；S06；K4 | 缺对外工具能力合同；不复制 generic RPC | 同一受限动作经 UI/CLI/MCP 获得一致权限/结果，缺 scope 均拒绝。 |
| U102 | 外部 Claude/Codex/ChatGPT 通过 MCP 接入 | D [user/outside-agents.md][t3s-122]；P [server/mcp/McpHttpServer.ts][t3s-123]；P [server/auth/McpOAuth.ts][t3s-124] | OAuth/PKCE、独立 audience 与 mode ceiling | AG15、CL09；S06/S08；K4 | 缺第三方 agent 身份和可收窄授权 | 外部 MCP client 只能访问所授 Project/tool；token audience 错误或撤销后拒绝。 |
| U103 | MCP thread 读/启动/发送/等待/停止 | D [user/outside-agents.md][t3s-122]；P [server/mcp/OrchestratorMcpService.ts][t3s-125] | 外部 caller 必须显式 thread/Project；内部专用工具不外露 | AG15、EX08、CL04；S06；K4 | 缺 tool 与既有 Runtime action 的精确映射 | 一次启动/等待/停止能回读 operation；重复请求幂等，外部不能调用内部提权工具。 |
| U104 | 跨模型子任务委派、问题转交和结果回流 | D [user/outside-agents.md][t3s-122]；P [server/orchestration-v2/DelegatedTaskQuestionReactor.ts][t3s-082]；P [server/peer/RemoteDelegation.ts][t3s-035] | 子权限收窄；native 与应用子任务归属分开 | AG13、AG14、EX08；S06；K4 | 缺 managed delegation 状态/预算/取消链 | 任务创建绑定父 scope；问题回答定向且一次性，取消后不再回写新执行。 |
| U105 | MCP 事件 poll/stream/webhook 通知 | D [user/outside-agents.md][t3s-122]；P [server/mcp/McpWebhookTransport.ts][t3s-126]；P [server/milestones][t3s-127] | 1000 milestones 内存窗口/最长 1h 订阅；重启可能有 gap | AG16、AG15；S06；K3 | 缺有界事件订阅与 gap 回补合同 | 断线超过窗口明确 gap；通知投递不自动重跑任务，订阅到期/撤销停止。 |
| U106 | 本机 CLI 控制 thread、JSON 和 wait exit code | D [user/outside-agents.md][t3s-122]；P [server/cli/thread.ts][t3s-128] | busy send 排队不自动 interrupt；exit 2 可表示等用户 | CL04、AG07；S06；K2/K3 | 已有管理 CLI；缺会话 CLI 等价操作 | 机器输出 schema 稳定；等待用户与失败分开 exit code，重复发送有明确去重规则。 |

### G2. 定时、Webhook 与 Workflows（U107–U110、U121）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U107 | 一次/间隔/定点/星期任务；编辑/启停/立即运行/删除；三种线程目标 | D [user/project-settings.md][t3s-086]；P [server/scheduledTasks/ScheduledTaskService.ts][t3s-129]；P [server/scheduledTasks/Schedule.ts][t3s-130] | 新 thread/沿用 session/同 thread 新 session 分开；离线 missed-run 规则明确 | EX06、HB07；S10；K3 | Job 基础不是定时产品；缺 definition/occurrence 与幂等派发 | 重启后 occurrence 不重复；一次逾期/固定时刻错过/DST 各按明示政策运行，归档目标失败可见。 |
| U108 | Durable Workflow 定义、版本、step/agent/ask | D [user/workflows.md][t3s-131]；P [server/workflows][t3s-132] | Labs beta 默认关闭；TS/Effect，非原路线 YAML 的原样兼容；具体实现路径待补证 | HB06；S12；K3/K4 | 缺 durable Workflow 模块；不能并入一个 cron 开关 | start key 幂等；成功 step 不重复执行，人工 ask 可恢复，未完成 run 保留所需版本。 |
| U109 | Workflow triggers、重试、signal、resume 与子运行取消 | D [user/workflows.md][t3s-131]；P [server/workflows][t3s-132] | Labs beta；代码重试与 agent 失败暂停不同；外部副作用需自身幂等；具体实现路径待补证 | HB05–07；S12；K3/K4 | 缺持久 wait/signal 与安全取消；K3 Task 需先定合同 | 中途崩溃恢复等待点；cancel 先持久终态并清理子任务，副作用未知时不盲重播。 |
| U110 | Webhook 离线托管 holding | D [user/project-settings.md][t3s-086]；P [server/relay][t3s-135] | 可选 Connect；原始 payload 可在云端暂存；仅确认 relay 模块入口，托管实现路径待补证 | HB05、HB07、OP04；S08/S12；K3 | 缺自有 holding 服务及保留/隐私策略；本机 webhook 不自动含此功能 | 显式 opt-in 后限时缓存；过期/撤销删除，恢复派发去重，失败不误报已执行。 |
| U121 | Webhook 签名/过滤/模板/去重/coalesce/日志/URL 轮换 | D [user/project-settings.md][t3s-086]；P [server/scheduledTasks/webhookVerification.ts][t3s-136]；P [server/scheduledTasks/webhookDedupe.ts][t3s-137] | 未逐函数审查；补充抽读提示 7d 去重、60/min/task、队列 20 等预算 | EX06、HB05、HB07；S10/S12；K3 | 缺请求认证、持久 claim 与任务调度；不将 payload 视为用户指令 | 坏签名/重放拒绝；同事件重复仅派一次，合并窗口重启不丢 payload，轮换后旧 URL 失效。 |

### H1. 权限、受管策略与设置（U111–U116）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U111 | 每 RPC 与 payload 字段所需 scope | S [server/auth/RpcAuthorization.ts][t3s-033]；P [contracts/clientRpcPermissions.ts][t3s-138] | 未知 method 缺 scope 直接拒绝；UI 不是授权边界 | CL09、AG12；S03/S08；K2/K7 | 已有 typed action 边界；新产品动作需逐一列 scope | 新增未知 method 默认拒绝；混合 payload 增加权限时重新核验，不能只藏按钮。 |
| U112 | 单次 pairing、DPoP、WS ticket 与撤销 | D [internals/05_remote.md][t3s-023]；P [server/auth/PairingGrantStore.ts][t3s-139]；P [server/auth/dpop.ts][t3s-140] | token 不置 URL；短期 ticket 与长期设备授权分开 | CL07、CL09；S08；K— | 已有独立信任链；此设计不能替换受限 S03 来源决定 | 错 audience/nonce/replay/过期 ticket 拒绝；撤销最终动作前重查且闭合存量连接。 |
| U113 | 跨平台 managed policy 文件与部署模板 | D [user/managed-policy.md][t3s-141]；P [server/policy/ManagedPolicy.ts][t3s-142] | 启动读取；无效/不可执行 policy 拒绝启动 | CL09、OP01；S08/S11；K— | 缺管理员策略制品及部署资格；不是既有生产 profile 替代品 | 错误策略 fail closed；普通客户端不能修改 ceiling，各平台证明策略来源所有权。 |
| U114 | Provider/mode/client/Connect/telemetry/webhook policy ceiling | D [user/managed-policy.md][t3s-141]；P [server/policy/managedProviders.ts][t3s-143]；P [server/policy/managedLimits.ts][t3s-144] | 组织策略不是 OS 进程/文件系统租户隔离 | CL09、AG06；S08/S11；K5/K7 | 缺策略继承与冲突呈现；不据此宣称已有多租户 | 项目/设备只能收窄 ceiling；被禁 provider 和遥测无后门恢复，UI 显示限制来源。 |
| U115 | 默认/environment/project/client 设置层次 | D [user/project-settings.md][t3s-086]；P [server/serverSettings.ts][t3s-145] | All environments 是在线批量写；Mixed 不等于 durable 全局同步 | AG06、WS14、CL08；S05/S08；K6 | 现有 Settings 页面不代表此层次模型 | 显示有效值/来源；多个环境部分失败逐项报告，设备偏好不会误写全局。 |
| U116 | 项目 provider 启停、默认模型与 options | D [user/project-settings.md][t3s-086]；P [server/provider/ProjectSettingsOverrideSweep.ts][t3s-146] | 禁用可允许当前 turn 完成；后继 queue/new turn 拒绝 | AG05、AG06；S05；K2 | 缺项目到 provider instance 的可审约束 | 禁用后新 turn/队列不得使用该实例；已运行任务处理符合明示策略并可回读。 |

### H2. Secret、内容安全、隐私与归属（U117–U120）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U117 | Secret 引用、独立 store 与 1Password 连接 | P [user/secrets.md][t3s-147]；P [server/auth/ServerSecretStore.ts][t3s-148]；P [packages/secret-provider-onepassword][t3s-149] | 未逐函数审查；上游 server authority 与我方 Runtime-only 不同 | AG05、EX03；S05/S09；K— | 需 Runtime-owned 受限等价；Web/API/Worker 不接触 Secret | 普通设置只回引用/状态；解析/撤销留在 Runtime，日志/错误不含值，外部库不可扩大权限。 |
| U118 | 不可信正文/工具/预览与桌面 IPC 隔离 | D [internals/01_architecture.md][t3s-022]；P [server/mcpApps][t3s-150]；P [server/htmlRender][t3s-151] | CSP/sandbox/IPC 各有边界；与开发服务浏览器不同权限域 | AG11、WS13、EX02；S03/S04/S09；K2 | 未接正式正文/交互预览；U2 样式不算内容安全资格 | 恶意消息/预览不能生成审批或读取凭据；跨 frame/IPC 越权与资源请求有拒绝证据。 |
| U119 | 产品 telemetry、日志/trace 与隐私开关 | P [user/telemetry.md][t3s-152]；P [server/telemetry][t3s-153]；P [server/observability][t3s-154] | 未逐函数审查；产品 analytics、故障日志、用户反馈分开 | OP01、CL09；S14；K6 支撑 | 缺自有数据字典/默认开关/retention；不复制上游接收地址 | 关闭后无 analytics 请求；prompt/code/Secret 不进入声明外的数据通道，保留策略可核对。 |
| U120 | MIT 来源、品牌分离与第三方许可 | S [LICENSE][t3s-155]；S [TRADEMARK.md][t3s-156]；P [user/open-source-licenses.md][t3s-157] | MIT 版权/许可保留；名称/logo/domain 不随代码授权；Office 有额外许可 | OP06；S00/S14；K0/K1 | 本批只读参考；实际代码迁移需逐文件 provenance/NOTICE/SBOM | 任何 code-port 对应固定源/path/digest/license/修改记录；制品无上游商标资产或官方端点误用。 |

### I1. 文件、搜索与附件（U122–U124）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U122 | 文件树、读取、受控编辑与外部只读展示 | P [server/workspace/WorkspaceFileSystem.ts][t3s-158]；P [web/components/files][t3s-159] | 补充抽读，未逐函数审查；realpath/最近存在祖先/悬空 symlink/.git 是重点；具体实现路径待补证 | WS06、WS07；S02/S04；K2 支撑 | 缺通用 Files；上游 OS 可读范围不能移为我方范围 | 正式 Project 内合法文件可读；路径逃逸/符号链接替换/.git 写入拒绝，外部预览单独准入。 |
| U123 | 文件名/内容搜索、ignore 与索引退化 | P [server/workspace/WorkspaceSearchIndex.ts][t3s-160]；P [web/components/search][t3s-161] | 未逐函数审查；fff native index/git grep fallback，有扫描/输出预算；具体实现路径待补证 | WS06；S02；K6 | 缺受限内容搜索；Project 元数据搜索不能代替 | 索引未准备好仍给有界结果；symlink 不逃逸，超时/截断/取消明确，删除内容不会继续返回。 |
| U124 | 附件两阶段上传/claim、问题草稿与清理 | D [user/question-attachments.md][t3s-162]；P [server/attachmentStore.ts][t3s-073]；P [server/attachmentPaths.ts][t3s-163] | 未逐函数审查；pending→thread claim，稳定 key/TTL；问题附件独立于普通草稿 | AG11、WS07；S03/S04；K2 | 缺附件储存/内容准入；不能用写仓库规避边界 | 断网上传可重试且只 claim 一次；过期 pending 清理，回答撤回不留下越权附件引用。 |

### I2. 格式预览与保存（U125–U128）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U125 | 代码/Markdown/HTML/PDF/媒体/CSV/TSV 预览 | P [web/components/files][t3s-159] | 格式 renderer 逐项准入；可预览不等于可执行 HTML 或编辑文件；具体实现路径待补证 | WS06；S02；K2 支撑 | 缺正式 Files renderer；现有 diff 不覆盖文件预览 | 各声明格式显示正确或明确 unsupported；表格/大文件有边界，内容不能触发任意网络请求。 |
| U126 | Office/ODF/EPUB/RTF/notebook 预览 | P [web/components/files/extendedDocumentPreview.ts][t3s-166]；P [web/components/files][t3s-159] | 未逐函数审查；XML/转义/资源限制；Office 附 LICENSE.opencode，非完整编辑兼容；具体实现路径待补证 | WS06；S02；K2 支撑 | 缺格式组件及其依赖许可；不能只拷 renderer | 每声明格式覆盖合法/损坏/恶意样本；不执行嵌入脚本，许可证随实际迁移文件进入归属表。 |
| U127 | ZIP、超大文本、font/binary 视图 | P [web/components/files][t3s-159]；P [server/zipArchive.ts][t3s-170] | 未逐函数审查；ZIP/表格/解码设大小与资源预算；具体实现路径待补证 | WS06；S02；K2 支撑 | 缺有界解析/worker 与 zip 安全读取 | zip traversal/bomb 拒绝；超大文本可截断/分页，取消后不继续占用解析资源。 |
| U128 | 编辑 revision、自动保存、flush 与失败保留 | P [web/components/files/fileSaveCoordinator.ts][t3s-171]；P [web/components/files][t3s-159] | 未逐函数审查；前端序列化不能替代后端 CAS；具体实现路径待补证 | WS07；S04；K2 支撑 | 缺正式编辑 API 与并发保存合同 | 旧保存晚到不标新内容已保存；双编辑器冲突可见，失败保留草稿，离开页面有准确未保存状态。 |

### I3. HTML、MCP Apps 与浏览器（U129–U134）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U129 | HTML visual reply、截图和持久 artifact | D [user/html-renders.md][t3s-173]；P [server/htmlRender/HtmlRender.ts][t3s-174] | 生成/preview/publish 分开；单图/page/并发浏览器限额 | AG11、WS06、WS13；S03/S04；K2 | 缺 artifact 内容/生命周期；不把 publish 与预览绑定 | 生成有界 artifact 并预览；未经发布动作不外传，线程删除/权限撤销后引用失效。 |
| U130 | 交互 MCP Apps | D [user/html-renders.md][t3s-173]；P [server/mcpApps][t3s-150] | 文档支持 Claude/Codex；其他 provider 可退化普通 tool；有后果工具需审批 | AG15、EX02、WS13；S06/S09；K4 | 缺 app sandbox 与 capability bridge；不是普通 HTML 内嵌 | 只读 app 能交互；写动作经 scope/审批，unsupported provider 显示普通工具结果。 |
| U131 | HTML 公网资源代理与 SSRF 防护 | P [server/htmlRender/publicProxy.ts][t3s-175] | 未逐函数审查；DNS/IP 校验与连接地址绑定，拒私网/自身/特殊 IPv6 | WS13、WS12；S04；K— | 缺不可信渲染专用网络策略；不可复用本机开发 browser 的网络权限 | 私网/自身端口/DNS rebinding/IPv4-in-IPv6 均拒；DNS 异常不自动降级无限网络。 |
| U132 | Host browser、独立 context/profile、远端画面 | D [user/remote-access.md][t3s-176]；P [server/preview/ServerBrowserContexts.ts][t3s-177]；P [server/preview][t3s-178] | 临时 context 与持久 profile 分开；失败不能自动关 sandbox；具体实现路径待补证 | WS13、EX08；S04/S06；K4 | 缺独立浏览器主体/输入授权/资源生命周期 | 两个项目 context 不串 cookie；画面和输入归属于确切环境，撤销立即停止控制。 |
| U133 | 导入浏览器登录态 | D [user/browser-import.md][t3s-179]；P [server/preview][t3s-178] | 一次性 cookie copy；Windows app-bound/partitioned cookie 有限制 | WS13、CL09；S04/S08；K— | 缺授权导入和凭据保存域；不能读取任意用户浏览器库 | 只复制明确允许 profile 的受支持数据；不支持项明示，导入不形成持续后台同步。 |
| U134 | 服务端口发现、localhost 预览与 tunnel | P [server/preview/PortScanner.ts][t3s-181]；P [server/preview/PreviewTunnel.ts][t3s-182] | 未逐函数审查；terminal:operate、loopback-only、禁自身端口、撤销/背压 | WS12、CL06；S04/S07；K— | 缺固定服务代理动作；普通预览不授权任意端口 | 授权服务可访问；自身 API 端口/不允许目标拒绝，撤销断开现有流，慢客户端不无限缓冲。 |

### I4. 终端、外观与活动（U135–U138）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U135 | 多持久终端、history/attach/resync/resize/kill | D [user/terminal.md][t3s-183]；P [server/terminal/Manager.ts][t3s-184]；P [server/terminal][t3s-185] | 上游普通 shell 与我方 WAW 不同；有界历史/sequence，server 拥有 shell；具体实现路径待补证 | WS09、WS10；S04；K— | 已有 WAW 终端子集；未开放独立通用终端 | 只在独立获准终端合同内实现 attach/resync；旧 sequence 不混输出，kill 核对进程归属。 |
| U136 | 主题、外观、自定义 CSS 与设备偏好 | D [user/appearance.md][t3s-186]；P [web/components/settings][t3s-187] | CSS 外部 url/import 受限；主题不能改变授权语义；具体实现路径待补证 | EX02、CL12；S02/S09；K1 | 已有 Kebui UI/品牌；缺可扩展主题和受限自定义 CSS | 切主题可恢复且不遮审批/错误；恶意 CSS 不加载远端资源或突破应用布局限制。 |
| U137 | 快捷键、焦点、键盘与移动布局 | D [user/keybindings.md][t3s-188]；D [user/keyboard-focus.md][t3s-189]；P [web/components/settings][t3s-187] | 平台快捷键不同；输入法/编辑器焦点不得误触发送；具体实现路径待补证 | CL12；S02/S07；K2/D06 | 既有 U2 焦点/缩放证据可复用；新聊天控件未验收 | 键盘能到达/退出主要面板；IME Enter 不误发，手机触摸与 screen reader 对新操作可用。 |
| U138 | Activity log、工具显隐与细节展开 | D [user/activity-log.md][t3s-191]；P [web/components/settings][t3s-187] | 隐藏工具不能隐藏待审批/问题/错误；具体实现路径待补证 | AG11、AG16；S03；K2/D05–D06 | Attention 只读基础已有；正式 tool timeline 未接线 | 关闭细节后仍看到需处理事件；展开只取所需正文，伪造工具文本不变成状态。 |

### I5. Usage、语音和文本生成（U139–U142）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U139 | Usage/限额/历史聚合与多账号去重 | D [user/usage.md][t3s-193]；P [server/usage][t3s-194]；P [server/usage/usageScanCache.ts][t3s-195] | 扫描/API 来源各异；size/mtime/guardHash 增量缓存，未知 tokens 保持未知；具体实现路径待补证 | AG16；S03/S10；K5/K6 | 缺可归因计量；Job Attention 不是 usage/billing | 重复历史或同账号不双计；文件截断后缓存失效，missing tokens 不从文本猜算。 |
| U140 | 模型价格/映射与 API 等价成本 | D [user/usage.md][t3s-193]；P [server/usage][t3s-194] | 估算值不等于订阅账单；未知价格标 unpriced；具体实现路径待补证 | AG16、AG06；S05/S10；K5 | 缺价格版本、币种和估算标签 | 修改价格只影响可解释估算；未知模型不显示零成本，绝不声称反映真实账单。 |
| U141 | 设备/环境/云端语音输入与 streaming/VAD | D [user/voice-input.md][t3s-197]；P [server/speech/SpeechService.ts][t3s-198]；P [server/speech/CloudSpeech.ts][t3s-199] | 最长 5min；目标离线不改发其他环境；本地 GPU 失败仅同环境 CPU 退化 | CL10；S07；K2 | 缺语音权限、模型制品与真机证据 | 录音 opt-in，准确展示处理地点；转写只进草稿，目标离线不悄悄上传云端或发送消息。 |
| U142 | 语音字典/去口头词/cleanup 与轻量标题/commit/PR 文本模型 | D [user/text-generation.md][t3s-200]；P [server/speech/postProcessing.ts][t3s-201]；P [server/textGeneration][t3s-202] | cleanup 临时 cwd，不读 checkout；OpenAI-compatible 文本模型不等于本地 coding agent；具体实现路径待补证 | AG17、EX07；S10；K2/K6 | 缺元信息生成服务/费用/隐私契约 | 生成只接允许文本；不继承仓库工具权限；保留原稿可撤销，自动标题不覆盖用户编辑。 |

### I6. 诊断、反馈、性能与通知（U143–U147）

| ID | 用户能力 | 固定源码 / 证据 | 上游可用性与限制 | 现有能力 / S、K 阶段 | 我方当前差距 | 最短验收（待执行） |
| --- | --- | --- | --- | --- | --- | --- |
| U143 | 进程树/CPU/RSS/trace/event-loop/heap 诊断 | D [user/triage.md][t3s-203]；P [server/diagnostics/ProcessDiagnostics.ts][t3s-204]；P [server/observability/EventLoopMonitor.ts][t3s-205] | 未逐函数审查；pid+startTime 防复用；日志/trace 有界 | OP01、OP05；S01/S07；K— | Doctor 基础已有；缺会话归因资源/trace 界面 | 诊断只读先可用；任何 signal 都核对进程身份，PID 复用拒绝，导出无 Secret/正文外泄。 |
| U144 | 同版本源码/日志辅助 self-triage | D [user/triage.md][t3s-203]；P [server/triage][t3s-206] | 诊断、修改、外发帖子是不同操作；源码版本须匹配运行版；具体实现路径待补证 | OP01、OP06；S07/S14；K4 支撑 | 缺受限故障助手；不允许 agent 借诊断任意读主机 | 诊断标注 artifact/源码版本；修复/外发由明确动作触发，默认报告不含用户代码或密钥。 |
| U145 | 可选 Agent feedback 与产品反馈 | D [user/telemetry.md][t3s-152]；P [server/feedback][t3s-207]；P [server/mcp/toolkits/feedback][t3s-208] | Agent feedback 的 Labs 开关默认关闭；普通反馈、telemetry、运维日志分别处理；Automatic mode 不等于逐次 Send 确认 | OP06、CL09；S14；K6 支撑 | 缺反馈数据范围、模式与自有接收端 | 关闭 Agent feedback 后不发送该类反馈；启用模式与 payload 可审，撤销停止未来上传。 |
| U146 | 长会话/多线程/弱网的传输与渲染预算 | P [server/orchestration-v2/CommandOutputHub.ts][t3s-209]；P [apps/server][t3s-210]；P [web/hooks][t3s-211] | 未逐函数审查且本次无性能实测；history/live/lazy body/worker/closure 各有机制；具体实现路径待补证 | AG08、AG11、WS15；S03/S07；K2/K6 | 缺结构化会话长期负载预算；不能引用上游数字冒称性能 | 固定负载测首屏/恢复字节、渲染/内存坡度；只展开项拉正文，超预算可观测且不丢正确状态。 |
| U147 | 移动通知与长任务提醒 | P [user/mobile-notifications.md][t3s-212]；P [apps/mobile][t3s-009] | 仅路径确认，未逐函数审查；系统权限/后台推送/分发条件待补证 | CL03、AG16；S07；K6 | 缺原生 push/许可/撤销；此项保持证据待补 | 先锁定平台和推送内容范围；只向授权设备送可归因通知，撤销后停止，通知不直接执行操作。 |

## 4. 八组实现借鉴怎样进入现有路线

下列是已读核心文件的结构性结论，按契约/状态机移植即可；不要求将 AgentBox
FastAPI/Runtime 整体改写成 Effect，也不建立第二套 daemon、用户库、Project 或队列权威。

| 借鉴点 | 固定实现锚点与意义 | 既有接线位置 / 不可省略的验证 |
| --- | --- | --- |
| 原子 intent、receipt、projection、outbox | [apps/server/src/orchestration-v2/EventSink.ts][t3s-071] 将命令 receipt、事件、投影和 effect enqueue 放入同一事务后 publish；重复命令读已有 receipt | S03/K2-D04、K3；复用既有 owner/journal，验证 accept/effect/ACK 崩溃窗口和迟到事件，禁止另造并行执行权威 |
| 能力/实例描述与执行权分开 | [packages/provider-core/src/server/ProviderAdapter.ts][t3s-061] 和 [apps/server/src/provider/ProviderInstanceRegistry.ts][t3s-050] 分别定义能力与 instance scope；替换先关闭旧 scope | S03/K2-D01、S05；本批只交纯描述器。source-supported、software-qualified、host-qualified 三者分栏，missing/stale 不执行 |
| Crash 恢复区分可重放与进程绑定 effect | [apps/server/src/orchestration-v2/EffectOutbox.ts][t3s-019] 与 [apps/server/src/orchestration-v2/RestartContinuation.ts][t3s-018] 区分 continuation/cleanup 与 start/steer/respond 等旧 process effect；人工等待阻止自动继续 | S03/K2-D04、K3；UNKNOWN 不由 history/resume 解除，不重放旧 prompt/approval，先证明旧副作用状态 |
| Provider switch 与有限 handoff | [apps/server/src/orchestration-v2/ProviderSwitchService.ts][t3s-058] 按 continuation identity 选择 in-place/native resume/fresh+handoff/reject；[docs/user/portable-handoffs.md][t3s-059] 明示有限上下文 | S06/K4；保完整消息/当前请求、角色顺序与来源；不宣称复制内部 reasoning/tool 状态或自动转移 Secret |
| 代码和对话共同回退 | [apps/server/src/vcs/GitVcsDriver.ts][t3s-092] 使用独立 index/private objects/隐藏 ref；[apps/server/src/orchestration-v2/CheckpointRestoreSafety.ts][t3s-102] 重查共享 checkout 和隔离 | S04 与 AG10；先验 provider rollback，再改文件，持久记录部分失败；上游 shared-checkout 查询的 fail-open 妥协不自动继承 |
| 单连接 owner、环境身份和 RPC scope | [packages/client-runtime/src/connection/supervisor.ts][t3s-030] 统一重连；[apps/server/src/auth/RpcAuthorization.ts][t3s-033] 逐动作拒绝缺失 scope | S07/S08、K2-D06；route 不等于身份，缓存不等于 fresh；撤销/重连/读取不得重发有副作用操作 |
| 安全更新以 durable commit 为界 | [apps/server/src/serviceLauncher.ts][t3s-006] 管版本选择、trial/prepared/committed 与 DB 回退；接受 update RPC 不代表升级完成 | S07/OP02、OP05；接现有安装器，核验 update ID、旧 DB/版本恢复和外部文件边界，不能用软件 fixture 代替真实升级 |
| 领域服务共享与多入口一致 | [docs/internals/02_effect-services.md][t3s-120] 将业务逻辑放领域服务，WS/HTTP/MCP/CLI/定时层仅适配 | S06/S10/S12；相同固定动作在各入口共享授权/幂等/取消/审计，generic tool 不能绕过 Runtime allowlist |

## 5. Edge 审计去重索引

独立边缘审计的 20 个主题均有落点。表中的 source 路径补充读取未扩大 46 文件原文
provenance 范围；P 路径的具体函数与测试仍需在对应实现卡补证。

| 原边缘主题 | 合并后的 U 项 | 保留的独立边界 |
| --- | --- | --- |
| 01 定时类型与管理 | U107 | schedule definition 与 occurrence 分开 |
| 02 三种任务目标 | U107 | 新 thread / 同 session / 同 thread 新 session |
| 03 Webhook | U121、U110 | 本机签名/去重与云端 holding 分开 |
| 04 Workflows | U108–U109 | durable step/ask 与简单定时分开 |
| 05 文件系统 | U122 | 工作区内可编辑与外部只读分开 |
| 06 内容搜索 | U123 | 路径权限、索引预算和 fallback |
| 07 Context chips | U058–U059 | 引用与内容快照分开 |
| 08 附件 | U057、U124 | 上传、claim、问题草稿与过期清理 |
| 09 多格式预览 | U125–U127 | common/Office/archive renderer 与额外许可 |
| 10 保存协调 | U128 | 前端 revision 与后端 CAS 都要验证 |
| 11 HTML/MCP Apps | U129–U130 | artifact 与交互 app 分开 |
| 12 公网资源安全 | U131 | 不可信 HTML 与本机开发 browser 网络域分开 |
| 13 Browser | U132–U133 | context/profile 与导入登录态分开 |
| 14 端口/tunnel | U134 | 独立权限、撤销和背压 |
| 15 持久终端 | U135 | 普通 shell 与 WAW typed terminal 分开 |
| 16 设置/外观/活动 | U115、U136–U138 | 有效值来源、设备偏好和关键事件可见性 |
| 17 Usage/price/quota | U063、U139–U140 | 配额恢复、token 计量和估算账单分开 |
| 18 Voice/text generation | U141–U142 | 录音、转写、清理和用户发送分开 |
| 19 Diagnostics/triage/telemetry | U119、U143–U145 | 运维日志、产品 analytics 与主动反馈分开 |
| 20 性能 | U146 | 机制存在与本轮实测数字分开 |

U147 来自固定用户文档/移动应用路径登记，保持 P，不宣称已完成通知实现审查。

## 6. 原 70 项中不能被 T3 参考替代的范围

T3 条目映射到原 ID 只建立借鉴关系，不宣称某个 ID 的全部操作已被 T3 覆盖。
以下差异继续留在原路线；不能因本表没有对等项或仅覆盖部分而删除它们。

| 原能力 | 本次 T3 证据的局限 | 在原路线的处理 |
| --- | --- | --- |
| WS02、WS15 | 多 thread/预览/性能机制不证明全部可调整面板、并列标签和布局恢复 | S02 继续按原 Workspace 与面板清单独立验收 |
| WS10 | U135 的终端输出/序列不证明完整 shell command integration/hooks | S04 保留命令来源、后台活动与权限合同 |
| CL05 | 内部 client-runtime 不是已承诺兼容的对外 SDK | S06 仍需版本化 AgentBox SDK、真实外部样例与取消 |
| CL11 | 本轮未逐项核查 T3 全量语言目录/翻译；不推定多语言 parity | S02/S07 保留 zh-CN/English 及原路线语言验收 |
| EX01–04 | ACP 安装、MCP Apps、主题不等于一般插件安装/任意 hooks/目录/发布全套 | S09 单独保留插件供应链、权限、隔离与开发者 SDK |
| HB01 | Guest link/managed policy 不能证明组织、成员和邀请完整模型 | S11 与 K7 保留多主体数据域，不将 OS 用户环境宣称多租户 |
| HB02、HB09 | Peer/Connect/MCP OAuth 只覆盖部分 host/grant；不证明完整 Hub API key/OpenAPI | S11 按原 Hub 登记/撤销/组织 API 合同推进 |
| HB04 | Linear issue adapter 不证明 Slack/Discord 连接和自动回复 | S12 分供应商保留授权、外发、去重与回复范围 |
| HB06、HB08 | T3 TypeScript workflows 与版本保留不等于原 YAML 工作流/GitHub 配置部署语义 | S12 明确受限等价与格式迁移，不能暗中删去旧目标 |
| HB10 | T3 SQLite 实现不能证明 Embedded/PostgreSQL、多实例迁移 | S11 保留数据库部署/备份/恢复要求 |
| HB11、HB12 | 本轮没有邮件邀请/通知或 Stripe 计费对等证据；U140 不是财务账单 | S12/S13 保留原可选商业与外部账号范围 |
| OP03、OP04 | 本轮未核查 Docker 产品路径；Cloudflare tunnel 不证明原分布式 relay 的部署/负载资格 | S07/S08 保留各自制品、协议、节点失效与容量验收 |
| OP06 | 147 行功能索引不等于用户帮助/CLI/SDK/许可证交付完成 | S14 仍需自有文案、实例、来源/SBOM 与每项适用证据 |

## 7. 状态维护和关闭规则

后续每项实现记录应至少链接：U ID、原能力 ID、适用 S/K 卡、实现 commit/PR、
source pin、复用方式（设计参考/改造代码/依赖）、明确的 operation/provider/platform、
输入/ACK/终态来源、失败/恢复行为、软件/制品/浏览器/真实 host 各自证据。
代码迁移须补原路径/digest/license/修改摘要，不能用本表链接代替实际 provenance。

只有相应操作闭环及失败路径通过，才能将该行的指定范围记为 PASS；其余维持
NOT RUN、UNKNOWN、UNSUPPORTED、BLOCKED 或 N/A 并说明原因。
一行在一种 provider 或平台成功，不自动关闭同一行其他平台，更不关闭整个 70-ID 能力。

本矩阵本轮的检查对象是 ID 唯一性、147 行完整性、原能力/阶段映射、固定引用、
S 来源与 46 文件清单一致、文档链接及 diff 范围。它不新增测试生产路由，不触发
上游运行或真实账号调用，也不恢复排除在本任务之外的旧 S03 候选。

## 固定来源链接定义

以下引用全部固定到同一个上游 commit。目录使用 tree，文件使用 blob；
路径标签缩写只影响显示，不影响可回读的 URL。

[t3s-001]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/install.md
[t3s-002]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/cli/install.ts
[t3s-003]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/cli/server.ts
[t3s-004]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/background-service.md
[t3s-005]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/cli/up.ts
[t3s-006]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/serviceLauncher.ts
[t3s-007]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/cli/uninstall.ts
[t3s-008]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/desktop
[t3s-009]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/mobile
[t3s-010]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/cli/app.ts
[t3s-011]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/cli/service.ts
[t3s-012]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/updating.md
[t3s-013]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/desktopUpdate/DesktopAppUpdate.ts
[t3s-014]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/internals/07_server-updates.md
[t3s-015]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/internals/09_connection-runtime.md
[t3s-016]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/client-runtime/src/connection/compatibility.ts
[t3s-017]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/cli/update.ts
[t3s-018]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/RestartContinuation.ts
[t3s-019]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/EffectOutbox.ts
[t3s-020]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/thread-migration.md
[t3s-021]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/cli/doctor.ts
[t3s-022]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/internals/01_architecture.md
[t3s-023]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/internals/05_remote.md
[t3s-024]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/auth/EnvironmentAuth.ts
[t3s-025]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/internals/06_t3-connect.md
[t3s-026]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/cloud
[t3s-027]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/cli/connect.ts
[t3s-028]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/ssh
[t3s-029]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/client-runtime/src/connection/resolver.ts
[t3s-030]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/client-runtime/src/connection/supervisor.ts
[t3s-031]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/client-runtime/src/connection/routes.ts
[t3s-032]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/client-runtime/src/connection/driver.ts
[t3s-033]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/auth/RpcAuthorization.ts
[t3s-034]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/resourceTelemetry
[t3s-035]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/peer/RemoteDelegation.ts
[t3s-036]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/peer/PeerThreadRelay.ts
[t3s-037]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/guest-links.md
[t3s-038]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/GuestShareDecider.ts
[t3s-039]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/guest
[t3s-040]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts
[t3s-041]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/providers-claude.md
[t3s-042]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/Adapters/CodexAdapterV2.ts
[t3s-043]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/providers-codex.md
[t3s-044]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/internals/03_providers.md
[t3s-045]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/builtInDrivers.ts
[t3s-046]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/providers-acp.md
[t3s-047]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/provider-acp-registry
[t3s-048]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/provider-acp
[t3s-049]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/acp
[t3s-050]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/ProviderInstanceRegistry.ts
[t3s-051]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ProviderAdapterRegistry.ts
[t3s-052]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/provider-core/src/server/instanceEnvironment.ts
[t3s-053]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/ClaudeProvider.ts
[t3s-054]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/CodexManagedHome.ts
[t3s-055]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/CodexManagedTokenBroker.ts
[t3s-056]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/ProviderCredentialStore.ts
[t3s-057]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/model-manifest.json
[t3s-058]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ProviderSwitchService.ts
[t3s-059]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/portable-handoffs.md
[t3s-060]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/IdleCompactionService.ts
[t3s-061]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/provider-core/src/server/ProviderAdapter.ts
[t3s-062]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/RuntimeRequestService.ts
[t3s-063]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/ProviderAuthService.ts
[t3s-064]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/ProviderInstallationGate.ts
[t3s-065]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/providerStatusCache.ts
[t3s-066]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/thread-sidebar.md
[t3s-067]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/project/ScratchThreadPromotion.ts
[t3s-068]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/composer.md
[t3s-069]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ThreadLaunchService.ts
[t3s-070]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ThreadMessageIntake.ts
[t3s-071]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/EventSink.ts
[t3s-072]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/web/src/components/ComposerPromptEditorTiptap.tsx
[t3s-073]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/attachmentStore.ts
[t3s-074]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/web/src/components/ContextChip.tsx
[t3s-075]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/contracts/src/orchestrationV2.ts
[t3s-076]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ThreadManagementService.ts
[t3s-077]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ThreadSettlementService.ts
[t3s-078]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/UsageLimitRecoveryWorker.ts
[t3s-079]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ThreadSearch.ts
[t3s-080]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/messageSearchIndex.ts
[t3s-081]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ThreadForkService.ts
[t3s-082]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/DelegatedTaskQuestionReactor.ts
[t3s-083]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ContextHandoffService.ts
[t3s-084]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ProviderContinuationService.ts
[t3s-085]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/legacy
[t3s-086]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/project-settings.md
[t3s-087]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/project/ProjectService.ts
[t3s-088]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/project/ProjectCloneTracker.ts
[t3s-089]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/source-control.md
[t3s-090]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/multi-repo-projects.md
[t3s-091]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/project/T3ProjectFileLoader.ts
[t3s-092]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/vcs/GitVcsDriver.ts
[t3s-093]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/vcs/VcsProvisioningService.ts
[t3s-094]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/project/worktreeContainer.ts
[t3s-095]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/project/ProjectSetupScriptRunner.ts
[t3s-096]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/serverRuntimeStartup.ts
[t3s-097]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/vcs/worktreeRemoval.ts
[t3s-098]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/checkpointing/CheckpointDiffQuery.ts
[t3s-099]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/git/GitWorkflowService.ts
[t3s-100]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/git/sharedCheckoutGuard.ts
[t3s-101]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/checkpointing/CheckpointStore.ts
[t3s-102]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/CheckpointRestoreSafety.ts
[t3s-103]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/CheckpointRollbackService.ts
[t3s-104]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/vcs/CheckoutCloner.ts
[t3s-105]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/vcs/worktreeCheckoutCache.ts
[t3s-106]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/source-control-definitions
[t3s-107]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/pullRequest/PullRequestService.ts
[t3s-108]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ThreadPullRequestService.ts
[t3s-109]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/pullRequest/PullRequestWatchService.ts
[t3s-110]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/source-control-core
[t3s-111]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/source-control-github
[t3s-112]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/pullRequest/PullRequestReviewGuideService.ts
[t3s-113]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/pullRequest/pullRequestViewedFiles.ts
[t3s-114]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/client-runtime/src/connection/pullRequestRoutingPermissions.ts
[t3s-115]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/issue
[t3s-116]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/issue-tracker-linear
[t3s-117]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/ThreadIssueService.ts
[t3s-118]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/mcp/toolkits/issues
[t3s-119]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/prompt-links.md
[t3s-120]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/internals/02_effect-services.md
[t3s-121]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/mcp/toolkits
[t3s-122]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/outside-agents.md
[t3s-123]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/mcp/McpHttpServer.ts
[t3s-124]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/auth/McpOAuth.ts
[t3s-125]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/mcp/OrchestratorMcpService.ts
[t3s-126]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/mcp/McpWebhookTransport.ts
[t3s-127]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/milestones
[t3s-128]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/cli/thread.ts
[t3s-129]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/scheduledTasks/ScheduledTaskService.ts
[t3s-130]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/scheduledTasks/Schedule.ts
[t3s-131]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/workflows.md
[t3s-132]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/workflows
[t3s-135]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/relay
[t3s-136]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/scheduledTasks/webhookVerification.ts
[t3s-137]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/scheduledTasks/webhookDedupe.ts
[t3s-138]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/contracts/src/clientRpcPermissions.ts
[t3s-139]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/auth/PairingGrantStore.ts
[t3s-140]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/auth/dpop.ts
[t3s-141]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/managed-policy.md
[t3s-142]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/policy/ManagedPolicy.ts
[t3s-143]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/policy/managedProviders.ts
[t3s-144]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/policy/managedLimits.ts
[t3s-145]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/serverSettings.ts
[t3s-146]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/provider/ProjectSettingsOverrideSweep.ts
[t3s-147]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/secrets.md
[t3s-148]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/auth/ServerSecretStore.ts
[t3s-149]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/secret-provider-onepassword
[t3s-150]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/mcpApps
[t3s-151]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/htmlRender
[t3s-152]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/telemetry.md
[t3s-153]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/telemetry
[t3s-154]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/observability
[t3s-155]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/LICENSE
[t3s-156]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/TRADEMARK.md
[t3s-157]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/open-source-licenses.md
[t3s-158]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/workspace/WorkspaceFileSystem.ts
[t3s-159]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/web/src/components/files
[t3s-160]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/workspace/WorkspaceSearchIndex.ts
[t3s-161]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/web/src/components/search
[t3s-162]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/question-attachments.md
[t3s-163]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/attachmentPaths.ts
[t3s-166]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/web/src/components/files/extendedDocumentPreview.ts
[t3s-170]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/zipArchive.ts
[t3s-171]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/web/src/components/files/fileSaveCoordinator.ts
[t3s-173]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/html-renders.md
[t3s-174]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/htmlRender/HtmlRender.ts
[t3s-175]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/htmlRender/publicProxy.ts
[t3s-176]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/remote-access.md
[t3s-177]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/preview/ServerBrowserContexts.ts
[t3s-178]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/preview
[t3s-179]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/browser-import.md
[t3s-181]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/preview/PortScanner.ts
[t3s-182]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/preview/PreviewTunnel.ts
[t3s-183]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/terminal.md
[t3s-184]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/terminal/Manager.ts
[t3s-185]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/terminal
[t3s-186]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/appearance.md
[t3s-187]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/web/src/components/settings
[t3s-188]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/keybindings.md
[t3s-189]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/keyboard-focus.md
[t3s-191]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/activity-log.md
[t3s-193]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/usage.md
[t3s-194]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/usage
[t3s-195]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/usage/usageScanCache.ts
[t3s-197]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/voice-input.md
[t3s-198]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/speech/SpeechService.ts
[t3s-199]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/speech/CloudSpeech.ts
[t3s-200]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/text-generation.md
[t3s-201]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/speech/postProcessing.ts
[t3s-202]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/textGeneration
[t3s-203]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/triage.md
[t3s-204]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/diagnostics/ProcessDiagnostics.ts
[t3s-205]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/observability/EventLoopMonitor.ts
[t3s-206]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/triage
[t3s-207]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/feedback
[t3s-208]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/mcp/toolkits/feedback
[t3s-209]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server/src/orchestration-v2/CommandOutputHub.ts
[t3s-210]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/server
[t3s-211]: https://github.com/pingdotgg/t3code/tree/d73e41a3fa379b591d9fb59d722d2569ec05994b/apps/web/src/hooks
[t3s-212]: https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/user/mobile-notifications.md
