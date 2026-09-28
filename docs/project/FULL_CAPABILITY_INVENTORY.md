# AgentBox 全量功能吸收清单

状态：2026-09-28 范围修订中的审计基线。Owner 已明确要求吸收上游**全部已有功能**；此清单取代“只吸收部分工作台功能”的范围假设。实现状态、验收状态和授权边界仍分别记录。

## 固定来源与核查方法

| 来源 | 固定提交 | 本次取得方式 | 许可与作用 |
| --- | --- | --- | --- |
| getpaseo/paseo | `30178c4f58b67f8472901356e1484022bd835de0` | 公开仓库浅克隆到临时研究目录 | Apache-2.0；daemon、Web/移动/桌面、CLI、SDK、插件、Agent、workspace |
| getpaseo/paseo-relay | `3fc41c96c8c63f3a7109e832899cc57d473c4531` | 公开仓库浅克隆到临时研究目录 | Apache-2.0；生产 Elixir 分布式 relay。主仓的旧 Cloudflare relay 不是当前生产实现 |
| getpaseo/hub | `808c1f920c0192141ebfeada529f6c653804997a` | 公开仓库浅克隆到临时研究目录 | Apache-2.0；独立 Hub、触发器、工作流、团队、可选计费/邮件 |

三个 checkout 均只读研究，未运行安装脚本、服务或真实外部账号。清单交叉读取各仓 README、public-docs、架构、CLI 目录和实际模块；文档描述只能作为产品能力线索，能否在 AgentBox 交付仍须对应代码、测试、制品与真实环境证据。新发现的功能必须增加 ID，不能藏在“等”字后面。上游提交之后新增的功能需另做差异审计，不能自动算作本固定基线已覆盖。

表中“AgentBox 状态”基于 2026-09-28 源码与 [能力矩阵](../CAPABILITY_MATRIX.md)，其中“基础”指部分软件基础，不表示产品可用；“未有”指无对应验收产品。每个 ID 都是交付清单项，不能靠导入源码或绿色 CI 单独关闭。

## A. Agent 与会话

| ID | 上游已有用户能力 | 主要源证据 | AgentBox 状态 | 验收目标 |
| --- | --- | --- | --- | --- |
| AG01 | Claude Code 原生会话、模型/模式、流式回合 | 主仓 `server/agent/providers/claude/` | WAW 基础 | 真 CLI/SDK 回合、工具事件、取消与恢复 |
| AG02 | Codex app-server 会话、模型/模式、流式回合 | 主仓 `codex-app-server-agent.ts` | WAW 基础 | 真实 thread/turn、权限与停止语义 |
| AG03 | OpenCode、Pi 与其他原生 adapter | 主仓 `server/agent/providers/` | 未有 | 每种声明支持的 provider 有运行、失败、恢复证据 |
| AG04 | GitHub Copilot、Cursor 等 ACP agent 与扩展目录 | 主仓 `public-docs/supported-providers.md`、ACP adapter | 未有 | ACP 会话协议、目录、安装与不支持状态 |
| AG05 | 自定义 provider、alias、binary、模型目录与 options | 主仓 `public-docs/custom-providers.md` | Phase 11 基础 | 受限配置、发现、验证、回滚及来源 |
| AG06 | Agent profile：provider/model/mode/thinking/features | 主仓 `public-docs/agent-profiles.md` | 未有 | 保存/应用/版本漂移与权限一致 |
| AG07 | 运行、发送、跟进、等待、attach、关闭、重启会话 | 主仓 `agent-manager.ts`、CLI `agent/` | WAW 部分 | 各生命周期区分，未知输入不重发 |
| AG08 | 持久历史、跨客户端同步、断线补拉、Resume | 主仓 `agent-storage.ts`、`timeline-sync.md` | 部分 | cursor/缺口、vendor handle、重启恢复 |
| AG09 | Archive/unarchive、软删除、自动归档 | 主仓 `agent-lifecycle.md` | 未有 | 内容/进程/工作副本归属分离且可恢复 |
| AG10 | 回退、重放、fork/rewind 及分支会话 | 主仓 Claude/Codex `rewind.ts` 与前端会话视图 | 未有 | vendor 支持矩阵、历史分支、无重复副作用 |
| AG11 | 富文本、代码、图片、附件、工具调用与时间线 | 主仓 `composer/`、`timeline/`、`attachments/` | 未有 | 内容加密/截断/渲染/版本与权限 |
| AG12 | Provider 结构化权限请求、回答与待办提醒 | 主仓 `permission-response.ts`、前端 Agent UI | 未有 | 一次性 requestId/TTL/generation、冲突与撤销 |
| AG13 | 管理的子 Agent、provider 原生子 Agent、后台/嵌套跟踪 | 主仓 `agent-lifecycle.md`、`subagents/` | 未有 | 父子/脱离/归档/失败归属及预算 |
| AG14 | 多 Agent 分工、handoff、advisor、committee 技能 | 主仓 `public-docs/skills.md`、`orchestration-workflows.md` | 未有 | 受限调用、文件归属、结果回流与权限 |
| AG15 | Agent 可调用的 MCP/工具目录与跨 Agent 协作 | 主仓 `public-docs/mcp.md`、`server/agent/tools/` | 未有 | 每项工具的项目、主体、资源与审计合同 |
| AG16 | Agent 使用统计、状态、活动提醒、通知 | 主仓 `provider-usage/`、`agent-stream/`、`push/` | 最近 Job Attention 只读候选；其余未有 | 可归因指标、过期/失败/推送许可 |
| AG17 | 自定义标题/摘要等元数据自动生成 | 主仓 `public-docs/metadata-generation.md` | 未有 | 显式模型/费用、失败与不覆盖用户输入 |

## B. Project、Workspace 与开发工具

| ID | 上游已有用户能力 | 主要源证据 | AgentBox 状态 | 验收目标 |
| --- | --- | --- | --- | --- |
| WS01 | 本地目录、Git/GitHub Project 注册/克隆/打开 | 主仓 `public-docs/workspaces.md`、CLI `project/` | 部分 | 正式 Project ID/READY、来源与生命周期 |
| WS02 | 同 Project 多 Workspace、多 Session、并列标签 | 主仓 `workspace-tabs/`、`screens/workspace/` | 部分 | 标签不授予权限，切换/返回状态新鲜 |
| WS03 | 本地 checkout、managed worktree、PR workspace | 主仓 `worktree-core.ts`、`public-docs/worktrees.md` | 未有 | dirty/WIP、分支、共享 .git 锁、恢复 |
| WS04 | Workspace archive/restore、自动归档与清理 | 主仓 `workspace-archive-service.ts` | 未有 | metadata 与物理删除分开、引用计数 |
| WS05 | Git 状态、分支、Pull/Push、commit/PR 关联 | 主仓 `workspace-git-service.ts`、`git/` | 部分 | 固定 Git 动作、冲突与审计 |
| WS06 | Files 树、搜索/浏览、受限读取和预览 | 主仓 `file-explorer/`、`file-pane/` | 未有 | Project 范围、敏感文件、binary/size/取消 |
| WS07 | 文件编辑、上传/下载与保存冲突 | 主仓 `session/files/`、`file-upload/` | 未有 | version/CAS、路径/内容/配额与恢复 |
| WS08 | Changes、diff、双栏/统一、审查与分享 | 主仓 `git/diff-document/`、`review/` | 纯树算法已合并 | patch 权威、截断、大文件、评论范围 |
| WS09 | 独立终端、输入/输出/resize、恢复和多终端 | 主仓 `terminal/`、`public-docs/cli.md` | WAW 终端部分 | 与 Agent 会话分域；权限模型待确认 |
| WS10 | 终端命令感知、shell integration、活动 hooks | 主仓 `terminal/activity/`、`terminal/agent-hooks/` | 未有 | 明确命令来源、后台状态与权限 |
| WS11 | Workspace setup/teardown、命名脚本/服务 | 主仓 `public-docs/worktrees.md`、`session/workspace-scripts/` | 未有 | 执行权限与仓库配置来源待决策 |
| WS12 | 服务代理、动态端口、服务间访问 | 主仓 `docs/service-proxy.md`、`worktrees.md` | 未有 | 端口/Origin/请求权限、生命周期和超时 |
| WS13 | 内置浏览器、网页查看和桌面 Agent 浏览器工具 | 主仓 `public-docs/browser.md`、`browser-tools/` | 未有 | 独立浏览器信任与输入授权，真实桌面验证 |
| WS14 | 项目/工作区标记、收藏、搜索、命令中心 | 主仓 `workspace-labels/`、`command-center/` | 部分 | 多客户端同步、过期与作用域 |
| WS15 | 变化/会话/文件/终端/浏览器可调整面板 | 主仓 `screens/workspace/`、`panels/` | 未有 | 典型分辨率、键盘、焦点与恢复 |

## C. 客户端、连接、语音与开放接口

| ID | 上游已有用户能力 | 主要源证据 | AgentBox 状态 | 验收目标 |
| --- | --- | --- | --- | --- |
| CL01 | 自托管 Web UI、同源 daemon API | 主仓 `public-docs/web-ui.md` | Web 已有 | 单一 AgentBox 登录、版本/部署一致 |
| CL02 | macOS/Linux/Windows 桌面 App、窗口、启动、更新 | 主仓 `packages/desktop/` | 未有 | 各系统安装/签名/沙箱/更新/回退 |
| CL03 | iOS/Android App、后台/离线缓存/通知/键盘 | 主仓 `packages/app/` | 手机管理部分 | 真机/商店或内部分发、恢复与权限 |
| CL04 | 完整 CLI：Agent/Project/Workspace/terminal/script/schedule/plugin/Hub | 主仓 `public-docs/cli.md`、`packages/cli/` | 管理 CLI 部分 | 命令等价表、机器输出、错误及权限 |
| CL05 | TypeScript SDK：会话、工作区、事件、provider、等候 | 主仓 `packages/client/`、`public-docs/sdk/` | 未有 | 版本化 AgentBox SDK、外部示例与取消 |
| CL06 | 直连 LAN/VPN/Tailscale、SSH transport | 主仓 `public-docs/connectivity.md` | 反向代理基础 | 地址/认证/重连/主机身份与超时 |
| CL07 | E2E relay、QR pairing、多设备与中继重连 | 主仓 `packages/relay/`；独立 `paseo-relay` | WAW E2E 基础 | AgentBox relay/配对/撤销、密钥与时序验证 |
| CL08 | 多主机列表/选择/状态同步与跨主机任务 | 主仓 `HostRuntimeController`、`hub/` | 单主机 | 多 host ID、权限、冲突、断线状态 |
| CL09 | 主体/设备授权、owner/operator/viewer、权限撤销 | 主仓 `docs/permissions.md`、`authorization/` | 单管理员 | 资源范围、grant attenuation 与审计 |
| CL10 | 本地语音识别、OpenAI 语音选项、语音会话 | 主仓 `public-docs/voice.md`、`speech/` | 未有 | 麦克风许可、隐私/费用/网络与真机证据 |
| CL11 | 中英日韩等多语言与区域格式 | 主仓 `README.*.md`、`docs/i18n.md`、`i18n/` | zh-CN/English | 用户文本目录、输入/技术标识不被翻译 |
| CL12 | 可访问性、键盘操作、快捷键、移动布局 | 主仓 `keyboard/`、`desktop/`、`screens/` | 部分 | 实际渲染、焦点、触摸、屏幕阅读器 |

## D. 扩展、编排与计划任务

| ID | 上游已有用户能力 | 主要源证据 | AgentBox 状态 | 验收目标 |
| --- | --- | --- | --- | --- |
| EX01 | 本地及 Git/npm 插件安装、升级、禁用、卸载 | 主仓 `server/plugins/`、`public-docs/plugins/` | 未有 | 供应链/来源/隔离/回滚，权限待决策 |
| EX02 | 插件面板、主题、按钮、命令、设置、附件 | 主仓 `docs/plugins.md`、`app/plugins/` | 未有 | UI 插槽、版本兼容、失效隔离 |
| EX03 | 插件 server hooks、RPC、自定义 provider/ACP | 主仓 `public-docs/plugins/reference.md` | 未有 | Runtime 主体/能力/Secret 范围待决策 |
| EX04 | 插件目录与发布、开发者 SDK | 主仓 `public-docs/community.md`、`plugin-examples/` | 未有 | 签名/兼容、审查/分发与样例 |
| EX05 | 保存的 agent profile 和编排技能 | 主仓 `agent-profiles/`、`skills/` | 未有 | 版本锁定、受控资源与手工批准 |
| EX06 | 定时任务、聊天创建、CLI 管理、heartbeat | 主仓 `schedule/`、`public-docs/schedules.md` | 未有 | 时区/DST、幂等、失败恢复、通知 |
| EX07 | 自动标题/摘要/元数据生成 | 主仓 `metadata-generation/` | 未有 | 模型选择、上下文权限和费用上限 |
| EX08 | Agent 工具调用其他 Agent、工作区、终端、浏览器 | 主仓 `server/agent/tools/`、`public-docs/mcp.md` | 未有 | 每一动作的授权、取消、审计与隔离 |

## E. Hub、团队与事件自动化

| ID | 上游已有用户能力 | 主要源证据 | AgentBox 状态 | 验收目标 |
| --- | --- | --- | --- | --- |
| HB01 | 自托管 Hub 控制台、组织/成员/邀请 | 独立 Hub `src/organizations/`、`src/invitations/` | 单管理员 | AgentBox 品牌与多主体权限/迁移 |
| HB02 | Hub 登记多个 daemon，权限、撤销和活动 | Hub `src/daemons/`；主仓 `server/hub/` | 单主机 | host 身份、grants、离线/重连/审计 |
| HB03 | GitHub App、事件触发与仓库配置同步 | Hub `src/provider-applications/`、`src/triggers/` | GitHub 管理基础 | App 授权、webhook 签名、仓库边界 |
| HB04 | Slack/Discord/Linear 连接、事件/回复 | Hub `src/provider-applications/`、`src/routes/api/integrations/` | 未有 | 外部消息显式授权、去重、回复范围 |
| HB05 | 触发器、过滤、线程/Issue/PR 持续会话 | Hub `src/triggers/`、`public-docs/hub/triggers/` | 未有 | 主体/事件 ID、白名单、重放/撤销 |
| HB06 | YAML 工作流、条件、分类器、上下文与限时 | Hub `src/workflows/`、`public-docs/hub/workflows.md` | 未有 | 签名来源、有限输出 schema、恢复 |
| HB07 | 计划触发器、执行状态、活动记录、附件 | Hub `src/agent-executions/`、`src/attachments/` | Job 基础 | 执行归属、持久化、重试与裁剪 |
| HB08 | GitHub 配置自动同步、版本激活/回滚 | Hub `src/config/`、`src/project-deployments/` | 未有 | 提交 pin、审核/权限、原子激活 |
| HB09 | 组织 API、API key、OpenAPI 与 CLI 部署 | Hub `src/public-api/`、`src/cli-authorizations/` | 未有 | OAuth/key 范围、审计、版本化 |
| HB10 | Embedded/PostgreSQL 部署与迁移 | Hub `src/db/`、`README.md` | SQLite 单机 | 多实例/数据迁移/备份/恢复 |
| HB11 | 可选邮件邀请/通知 | Hub `src/email/` | 未有 | 发件授权、模板、退订与 Secret |
| HB12 | 可选 Stripe 计划/试用/计费 | Hub `src/billing/` | 未有 | 独立商业决定、财务正确性与外部账户 |

## F. 运维、发行与恢复

| ID | 上游已有用户能力 | 主要源证据 | AgentBox 状态 | 验收目标 |
| --- | --- | --- | --- | --- |
| OP01 | daemon 的安装、启动/停止、配置、诊断与日志 | 主仓 `packages/server/`、CLI `daemon/` | 单机管理基础 | 现有 installer/systemd/Doctor 同等入口 |
| OP02 | 桌面更新 stable/beta、回退与 App store 分发 | 主仓 `public-docs/updates.md`、`desktop/diagnostics/` | rc 制品基础 | 各平台签名、可见版本、回退 |
| OP03 | Docker 自托管 Web/daemon/Hub、反向代理 | 主仓 `docker/`；Hub `Dockerfile` | 原生 systemd | AgentBox 镜像、rootless、数据/Secret 边界 |
| OP04 | 生产分布式 relay 部署、节点路由与负载 | 独立 relay `lib/`、`README.md` | 未有 | 协议互通、节点失效、容量与监控 |
| OP05 | 备份、跨设备/跨主机恢复、迁移和诊断导出 | 主仓 `docs/architecture.md`；Hub `src/db/` | 部分 | DB/Project/插件/会话分别恢复 |
| OP06 | 使用说明、SDK/CLI 文档、示例与帮助入口 | 三仓 docs、examples、public-docs | 部分 | AgentBox 产品文案和来源准确 |

合计 **70 个 ID**。这里的一个 ID 可以包含多个并列操作；阶段验收时必须展开成实际操作清单和失败矩阵，不能把 ID 数字当完成百分比。

## 范围决定与现有冲突

上游已有的普通 shell、任意 daemon 可读文件预览、任意插件/server RPC、工作区 setup scripts，以及多主体 Hub 权限，和 AgentBox 当前 [不可变边界](PRODUCTION_READINESS_PLAN.md#24-不可变边界)存在实质冲突。Owner 已收到明确选择题；答复前不实施这些冲突能力，仍继续来源、UI、只读领域和既有 R12 软件工作。答复后将具体能力逐项映射为受限等价实现或正式架构变更，不能以“全部功能”四字推定无限主机权限。

任何需要外部 Hub App、Slack/Discord/Linear 账号、邮件、Stripe、手机商店、证书、生产域名、真实 Provider Secret 或付费调用的验收仍需具体范围和实际证据。全部功能的目标不等于这些外部操作已经执行或得到无限授权。

## 下一步

1. 核对 70 个 ID 与代码、文档和真实上游包，修正遗漏及现有/未有状态。
2. 扩展 [实施计划](WORKBENCH_INTEGRATION_PLAN.md) 的目标、阶段与估算，保留已合并的 A0/A1 结果和 C3-b WIP。
3. 按 Owner 对权限冲突的选择冻结新架构，依次交付可独立验证的 AgentBox 功能切片。
