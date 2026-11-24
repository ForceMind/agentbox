# T3 Code 全功能借鉴与 Kebui 融合实施计划

## 1. 决定、范围与实际交付

Owner 本次要求把 T3 Code 的实现思路和每项功能借鉴融合进现有项目。
本计划把这一要求落实到 **Kebui 产品、AgentBox Runtime、既有 70 项能力和
S00–S14 / K0–K8 路线**；它扩充来源与验收细节，不建立另一套产品或重复路线。
具体决策见 [ADR 0012](../adr/0012-t3-code-integration.md)，逐项登记见
[功能融合矩阵](T3_CODE_FEATURE_MATRIX.md)。

矩阵共 **147 个审计子项（U001–U147）与 22 组功能表**，逐项记录固定来源、
平台/provider/Labs 限制、我方能力与阶段、现有差距和最短验收；147 是审计范围，
既有 70 项能力仍是正式交付归属。

本批实际软件交付是 [K2-D01 操作能力契约](../KEBUI_K2_ADAPTER_CAPABILITY_CONTRACT.md)
及 Runtime 内无 I/O 的描述与证据评估模块：分开固定版本研究结论、软件实现和
目标环境资格，防止因供应商名称或上游界面存在按钮就启用操作。它不是生产
adapter、认证入口、会话 API 或完整聊天功能。另将 Vite 锁定依赖升级到 7.3.7，
修复基线依赖审计的高危项；未降低审计阈值。

其余矩阵条目本批完成的是来源、目标模块、实现选择、依赖与验收的融合设计。
状态只能按各条真实代码/测试更新；不能把清单覆盖率称为产品完成率。

## 2. 固定基线与研究方式

| 对象 | 固定证据 | 用途与限制 |
| --- | --- | --- |
| AgentBox 主干 | `13b2877823d5338cd4044ead39d658a0c89e96de` | 本批起点；已有 rc31、WAW、A3/U2 与 K2 inert/synthetic 基础 |
| T3 Code | `pingdotgg/t3code@d73e41a3fa379b591d9fb59d722d2569ec05994b` | 2026-11-24 05:55:58 UTC 的 main 快照，不能等同于某个稳定发行 |
| T3 tree | `8be25ebe4d0f58ec2055d3f6c45470ccc21c3b7f` | 文档、目录与关键实现的固定定位 |
| 精选源码取证 | [t3code-sources.json](../../third_party/t3code-sources.json) | 46 个文件的 Git blob SHA、SHA-256、字节数；逐一复算匹配；未执行上游程序 |
| Codex D01 研究 | `0.159.3` / `01fc69f4026735edfdf6789820549727a4867b11` | 延续既有 K2 固定 vendor 研究，不由 T3 当前 adapter 推断旧版本能力 |
| Claude D01 研究 | Python SDK `v0.2.163` / `1ef6d8c71bb0e44a6b33fe61497864f21e17fdb7`，内含 CLI `2.1.286` | 源码支持结论不等于已安装或目标主机资格 |
| 其他在途工作 | [PR177](https://github.com/ForceMind/agentbox/pull/177)，Orca path-token Changes filter | 本批开始时未合并；不覆盖、不算主干已交付，也不重复实现 |

T3 全部源码锚点均使用固定提交。46 文件是可复算的精选证据集；矩阵还引用固定
版本的其他目录、文档和已检查实现，按证据等级逐项区分，不能称全仓逐函数审计。
源码存在、官方文档说明、本地模拟测试、真实 CLI/主机/客户端验收是不同证据。
主线中 Labs/beta、平台限制、商业服务前提和供应商差异必须随功能保留。

## 3. 如何吸收：保留现有所有权，改进能力服务

### 3.1 一个操作契约，供所有入口复用

T3 将 Web、CLI、MCP、自动化入口接入共享 domain service，而非在页面 handler
里各写一套业务。Kebui 采用这一结构，保留 FastAPI、Python Runtime、SQLite 和
React/TypeScript。无需为使用其状态机思想全仓改成 Effect/TypeScript。

| 层 | AgentBox 所有权与落点 | 融合后的职责 |
| --- | --- | --- |
| 产品交互 | `apps/web/src`，未来桌面/手机客户端 | 同一 Project/Conversation/Operation 引用、能力解释、草稿、时间线和恢复呈现 |
| 非内容控制面 | `apps/api/src/agentbox_api`、`packages/agentbox-core` | 授权、项目/设备/操作 metadata、请求状态查询；不读取提示词、工具正文或 Runtime HOME |
| 版本化协议 | `packages/agentbox-protocol` | 固定动作、资源、generation/revision/epoch、预算、错误与能力版本；不接受任意 shell/cwd/env |
| 执行与内容 | `packages/agentbox-runtime` | 已登记 Project、vendor adapter、原 owner/single-writer、内容保留、附件和固定工具能力 |
| 作业与特权 | 原 Worker/Job、Root Helper | 继续只执行各自既有固定职责；不新增竞争的 supervisor、Stop owner 或后台启动器 |

新服务先写 typed domain contract，再提供 Web/CLI/MCP 映射。可以新增满足明确
需求的模块，不能把 T3 server 作为第二后台嵌入，或把其数据库当成 AgentBox
身份/运行状态的另一个权威。

### 3.2 Provider 按操作声明能力，实例和凭据分开

借鉴 `packages/provider-core/src/server/ProviderAdapter.ts`、
`ProviderInstanceRegistry.ts` 与 `ProviderSwitchService.ts`：将 open/resume、
start、steer、interrupt、respond、snapshot、fork、rollback 分开描述，并记录
版本、可接受输入、ACK 含义、终态来源和恢复限制。

本批 D01 实现固定版本目录和无副作用评估；生产路由仍未连接。后继 adapter
通过逐操作证据进入现有 Runtime，不扩旧 Phase 11 capability set 来假装兼容。
Claude 仍保持 Runtime/session scoped；账号/配置目录/profile/provider instance
不混为一项。凭据由 Runtime 的既有 Secret 边界管理，不复制上游共享 HOME、
shadow home 或系统 keychain 的默认方式。

界面能力使用 `supported / unsupported / unknown / stale` 等明确状态及理由；
缺失、版本不符、过期或其他环境的证据都不能启用操作。研究结果可以支持产品
设计，但不能授予执行权限。Codex busy `turn/start` 可能变成 steer；Claude
写入 transport、interrupt 回包和 ResultMessage 都有不同语义，不能当作统一
“已完成”。会话 turn 结束、后台子任务结束、exact Stop 是三个不同事实。

### 3.3 意图、结果、投影与恢复分层

T3 的 `EventSink.ts` 在事务中写命令 receipt、事件、projection 和 effect outbox，
然后发布；`EffectOutbox.ts` 区分可恢复 effect 和依赖原进程的 effect。这些模式
用来完善现有 admission/journal/Job，而不是再加一套 queue 或迁入其数据库。

后继持久化必须先确定现有 owner 下的原子提交边界：

1. 校验身份、当前 generation/binding/epoch、固定 operation 和预算。
2. 在副作用之前记录不可冒用的 operation receipt；ACK 只表示该阶段已接收。
3. 原执行 owner 处理固定动作；结果通过对应 operation/run identity 回写。
4. 投影和 cursor 一起提交，再发布可观察状态；迟到事件不覆盖更新一代执行。
5. 断线/重启先查询 receipt 与实际 owner；未知副作用保持 UNKNOWN，不重发。

控制面仅持有允许的非内容 metadata；消息、工具输出、文件正文与历史不能因
“统一事件流”而进入控制面数据库/审计。现有永久防重放标识及 255 ID 预算不能
用 TTL 清空换取重试空间；改变容量或保留必须有独立迁移/恢复合同。

T3 的重启续跑上限和 outbox replay-safe 名单只是其实现证据，不直接授权我们
自动重跑。聊天完成、检查点生成、PR 后处理可独立失败，界面分别显示。

### 3.4 上下文移交、队列与多 Agent

借鉴 portable handoff：新 agent 获得有边界的任务目标、用户可见历史、已验证
结果和产物引用；保留角色、顺序、原请求及最近进展。native resume 与“新会话
附带上下文”在界面和审计中明确区分，不声称迁移隐藏推理、工具现场或全部附件。
本地引用不能自动变成跨机器可用文件；每个引用标所属环境、权限和可用性。

K2 仍先完成单 active turn，busy 明确拒绝；steer、持久队列、多模型同时启动、
side chat 和自动 handoff 作为后续明确能力，不由 D01 自动开启。K3 Task 需要
自己的持久 schema、迁移、取消/恢复/retention 契约；K4 才扩父子关系、委派、
问题转交、审查和结果归并。Agent 自建子进程与产品管理的子 Agent 分别跟踪。

### 3.5 工作树、Git 和检查点

沿用现有 Project/Workspace/Changes 身份与只读 A3 renderer；T3 的多 repo、
worktree setup/cleanup、PR workspace、每回合 diff 与 checkpoint 增补 S04。
每个工作树有明确 owner、base、branch、共享路径和生命周期；工作树隔离代码
目录，不等于隔离进程、端口、数据库或凭据。

`GitVcsDriver.ts` 的临时 index、独立对象和隐藏 ref 模式可避免把检查点提交放进
用户分支。恢复必须先验证 provider 能否回退、当前执行是否停止、所有相关 repo
是否有快照、是否存在共享写者，再更改文件。检查失败按我方要求拒绝，不能继承
上游某些查询失败放行的实现。外部/shared 文件、未快照 repo 和多 repo 部分失败
必须可见，不把对话回退误报为整个文件系统回滚。

Git mutation 按固定动作逐项接入 Runtime；保护脏文件和未保存草稿、禁止旧 head
执行 review/merge、显式处理 rebase 部分成功。自定义脚本是有来源和权限的执行
能力，不允许浏览器传任意命令直接启动。

### 3.6 文件、上下文与预览是不同能力

T3 的搜索预算、增量索引/退化路径、编辑 revision、pending→claimed 附件和按需
预览值得吸收。S02 先做真实来源支持的只读浏览/Changes；S04 再做文件写入、
附件、保存冲突和服务预览。相对路径和 realpath、符号链接/缺失祖先、非普通文件、
大小/编码/分页/取消在 Runtime 校验，UI 路径不是授权。

前端保存状态绑定被确认的内容 revision；旧请求成功不能覆盖更新草稿。
ContextRef 区分引用和不可变内容快照，文件/终端摘录/diff 评论/PR/thread/浏览器
元素共用可解释的呈现，但不同内容域仍分别授权。附件两阶段接收、claim、失败重试
和清理不把临时文件放进用户仓库。

三类预览分别实现：文件阅读器按格式/大小惰性加载；不可信 HTML artifact 在
隔离 sandbox 和网络策略内渲染；Agent browser/端口透传单独授权指定环境。
不能为 HTML 加载图片而放开私网，也不能将远程预览失败自动转成本机 localhost。
Office 等嵌套 renderer 的额外许可独立核查，本批未引入其代码或依赖。

### 3.7 多端、多环境与权限

借鉴 client-runtime 中每 environment 一个连接 owner、退避+jitter、路由与主机
身份分离、数据 freshness 与传输连通性分离的机制。缓存只显示最近观察，不授权
写操作；认证失败等待明确恢复，不无限换 route；未知 mutation 不跨 route 重发。

S07/S08 依现有部署、身份和加密边界实现 LAN/VPN/SSH、桌面/手机、多 host、
设备配对与撤销。SSH 只回收自己创建的资源。跨环境委派、guest 单会话分享和
外部 MCP audience 都是独立主体，权限只能收窄；撤销与过期覆盖内容/附件访问。

T3 Connect 的 Clerk/Cloudflare/托管账户、域名和离线队列不能随源码获得。
产品目标映射为自有 relay/接入能力，沿 S08/S11 实施。上游默认 Full access、
同 OS 用户 shell、任意外部路径读取、跨环境凭据路由不作为我方默认行为。

### 3.8 定时任务与持久工作流分开交付

S10 的简单任务定义与每次运行记录分离，明确 once/interval/fixed-time、时区/DST、
错过运行、持有/排队、是否新建会话、取消、去重及通知。Webhook 先做来源签名、
稳定事件 ID、持久去重、队列上限和投递记录；托管离线 payload 保存单独设计。

T3 Workflows 是默认关闭的 Labs 能力，不能当成已稳定的简单 cron。其持久
run/step/wait/signal、版本、人工 ask、子运行和外部幂等模式纳入 S12/HB06–08，
对应 Kebui K3/K4/K7。AgentBox 先定义版本化流程/步骤契约；代码步骤通过 Runtime
中明确允许的执行器运行，不能在 API/Worker 引入任意 TypeScript 执行。
不要求复制 T3 的整个 Effect workflow/cluster 服务。

成功步骤结果可恢复，外部副作用仍需自己的幂等；code retry 与已开始 agent 的
失败接续分开，cancel 先持久化意图再回收子执行。旧流程版本有活跃运行时不移除。
原 Job 是固定控制作业，不通过改名获得这些 durable Task/Workflow 语义。

### 3.9 计量、诊断、设置与更新

Usage 记录来源、账号/历史去重、缺失 token、未知价格和统计窗口；API 等价值
估算不冒充订阅实际账单。语音转写先进入草稿，设备/目标环境/本地或云端选择
明确，离线不自动改发别处。标题、摘要、commit 文案等轻任务可用隔离上下文的
文本模型，不能为生成一个标题授予整个仓库访问。

设置分默认/环境/项目/设备，并显示继承来源；“全部在线环境修改”显示每个目标
成功/失败，不虚构持久全局同步。运维日志与产品 telemetry 分开，不连接上游
遥测服务。诊断采用有界脱敏 metadata、进程所有权和 startTime/PID 防复用。

升级借鉴不可变版本、预检、数据库快照、trial prepared/committed gate 和失败回退，
在现有 installer/release 流程中实现，不安装第二 launcher。SQLite 快照不能当成
附件/工作树/Secret 全量备份；升级成功以重连后版本/operation 证据确认。

## 4. 唯一实施路线与交付顺序

所有细项的正式归属在 [功能矩阵](T3_CODE_FEATURE_MATRIX.md) 与
[原全量路线](FULL_CAPABILITY_DELIVERY_PLAN.md)。本表说明如何接入原路线，
不是重新计时或重新排一个与现有阶段冲突的工程。

| 既有阶段 | 本次扩充重点 | 依赖与阶段最短闭环 |
| --- | --- | --- |
| S00 / S14 | 固定来源、逐项矩阵、许可、文档和证据层级 | 本批交付；未来源码迁入逐文件补 provenance 与制品 notice |
| S01 / R12 | 原真实 Project→CLI 主流程 | 保留具体 host/client/vendor 资格；不因研究推进重新开启已完成卡 |
| S02 | 导航、命令中心、面板、只读文件/Changes、真实空错态 | 复用已交付 U2/A3；PR177 单独合并资格；不重复建命令中心 |
| S03 / K2 | 真实对话、流式事件、审批、取消、历史、恢复 | 先 D01→D02，再满足 D03–D05，最后 D06/D07；UI 先按既有设计交付流程 |
| S04 / K6 | worktree、多 repo、checkpoint、Git/PR、文件编辑/附件、脚本/浏览器 | 各固定动作与内容边界；dirty/shared 文件、部分失败、撤销与回滚验收 |
| S05 | 多 provider/实例/模型、ACP、安装/认证/健康探测 | 逐版本/逐操作能力；不支持明确显示；账户变化不串原生 session |
| S06 / K4–K5 | MCP、CLI/SDK、子 Agent、portable handoff、路由 | K2 事件与权限完成；父子取消/问题转交/资源归属/委派收窄 |
| S07 | 桌面/手机、离线草稿、语音、快捷键/无障碍、平台服务 | 单一协议；各平台安装/签名/离线/麦克风及升级恢复分别验收 |
| S08 / K7 | 多环境、relay、SSH、配对/撤销、guest、跨环境查看/委派 | 稳定环境身份；无 localhost/HTTP 降级；每 RPC 与附件权限 |
| S09 | 扩展、主题、MCP Apps、可配置 provider/工具 | 供应链、权限、renderer sandbox、兼容/禁用与恢复；品牌保持 Kebui |
| S10 / K3 | 定时任务、Webhook 运行、元数据生成 | 任务定义/运行持久化；时区/去重/未知副作用/人工恢复与费用约束 |
| S11 | 自有 Hub、组织、设备/主体与接入 API | 既有单管理员服务不悄然变多租户；独立数据/迁移/撤销契约 |
| S12 / K4/K7 | PR/Issue 自动化、外部 MCP、持久 Workflows | provider/webhook 真实授权；版本/step receipts/人工 ask/子运行恢复 |
| S13 | 既有可选商业功能 | 保持原计划；T3 商业接入不构成可复制账号/套餐或支付集成 |

## 5. 下一批的具体输入、接口和验收

延续 [交付证据与缺口清单](KEBUI_DELIVERY_EVIDENCE_AND_GAPS.md) 的 D01–D07，
不是将前轮已完成卡再做一次。

| 卡 | 本批之后的工作 | 可观察验收与依赖 |
| --- | --- | --- |
| D01 | 固定双 Agent 逐操作契约及纯模块本批完成；生产 adapter 后续依对应卡接入 | unknown/stale/mismatch 不产生可执行结论；vendor ACK/终态差异和无 I/O 边界有测试 |
| D02 | 非内容 Conversation/Operation observation 契约；逐字段真实 authority/resolver；有来源才接只读 API | 当前用户/Project/owner/generation 绑定；cursor/retention/restart 明确；未知不返回伪实时状态；尚无可用 source 时保持明确 unavailable |
| D03 | 既有认证 source admission 缺口单列 | 未提交 authenticated S03 候选不作为输入，不读取/恢复/重写/上传/委派，也不以替代设计绕过停止边界；需要在相应具体范围得到解决后才允许内容接线 |
| D04 | 在 D01–D03 基础上接固定 turn submit 与真实 Runtime owner | busy 不隐式 steer；同请求副作用至多一次；ACK 不冒充 completion；旧 owner/epoch 不接收 |
| D05 | output、approval response、interrupt 分别闭合 | 流式有预算/顺序；审批绑定 request/revision/已知 vendor deadline，最长 60 秒；禁 terminal yes/Ctrl-C 兜底；停止回读真实终态 |
| D06 | 真实 U3 页面/草稿/事件时间线与断线恢复 | 只读可跟 D02；内容/写入依 D03–D05；刷新/切页/双端/迟到消息不误启按钮，不重发未知 mutation |
| D07 | 指定 host/双 CLI/client/restart 与发布证据 | 只使用具体目标授权；软件 CI、构建制品和真实主机事实分别记录 |

没有真实账号/指定主机不会阻挡上述可独立的软件设计、纯模块、UI 原型和相应
模拟验证；但它们不能把真实能力状态改成 PASS。每批有明确终点和差异验证，
无需重复审计未变更的全部历史，也不因上游更新而把本固定版本追赶无限延长。

## 6. 验证、来源与维护

本批本地已经完成前端 typecheck、2267 项 Web 测试、6 项浏览器信任扩展测试和
两项构建。Vite 7.3.7 后 `pnpm audit --audit-level high` 通过，仍有 4 项 moderate，
未声称全依赖零告警。D01 与既有 S03 隔离测试共 121 项通过，其中新增 81 项；
独立复核未发现阻塞问题。全仓 Ruff、414 源文件 Mypy、改动 Python 文件的 Black、
secret/source-boundary/workflow-pin 检查通过。文档与准确提交 CI 由本批 PR 的
验证记录提供；未完成的检查不得预填 success。

本地完整 Python 回归在既有 AF_UNIX socket 测试出现 `EPERM` 后停止，定向复现
确认当前执行环境不能创建该 socket；全仓 Black 的 multiprocessing 也受此限制，
改动文件逐个 Black 检查通过。完整 Linux/原生/浏览器回归交给仓库既有 CI，
没有改测试跳过规则或将本地中止标为通过。

[PR178 初版 Release Candidate](https://github.com/ForceMind/agentbox/actions/runs/45341697820/job/138266617561)
进一步发现旧隔离构建锁中 6 个包的漏洞审计失败。后继最小补丁更新 black、certifi、
filelock、msgpack、setuptools、virtualenv，以及新 virtualenv 必需的 python-discovery。
75 个目标 CPython 3.11/Linux wheel 的哈希和 92 项活跃依赖约束已验证，完整锁审计
为 0 漏洞、0 跳过。准确环境安装、可复现制品和完整 CI 继续由该 PR 的新提交验证；
这是构建工具链修复，不改变本计划中的产品功能交付范围。

合并按既有正常 feature→CI→merge→main 回读流程，不借旧提交绿色状态。
Backend/Frontend/E2E/Security/Deployment/Release Candidate 工作流名称中的
Deployment 不表示本批实际部署到用户主机。本批不发布版本、不迁移用户数据。

T3 是设计参考，当前代码按 AgentBox 契约独立实现；没有引入 T3 server、runtime
依赖、品牌、图标、云端身份或遥测。原 Paseo provenance 保留。MIT 原文与本批
研究用途见 [第三方声明](../../THIRD_PARTY_NOTICES.md) 和
[许可副本](../../third_party/t3code-LICENSE.txt)。以后实际复制/改写源码时，必须
将每个来源和目标文件、固定 ref/hash、改动、嵌套许可与制品分发登记为 code port，
不能仍填 design reference。

上游以后新增能力以固定提交间 diff 增补本矩阵；U 编号只作来源审计子项，不改变
原 70 能力 ID 或 S/K 阶段编号。每项落地后记录代码/PR、测试范围和剩余限制，
只有全部适用验收项有证据时才报告整体功能完成。
