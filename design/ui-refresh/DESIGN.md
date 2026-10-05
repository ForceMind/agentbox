# AgentBox：完整工作现场

## 设计主张

这是供用户选择的视觉方向，不是已批准的品牌或生产迁移方案。保留 AgentBox 名称：暖白纸感、墨色文字、克制的琥珀色定位标记；深色采用墨绿灰背景和同一套信息层级。原创线框盒子作为工作容器意象，不复制竞品商标或页面。

首页不再是技术控制面卡片墙。按“需要我处理 → 正在进行的后台操作 → 项目入口”组织；把 Doctor、版本与连接条件移到清楚可达的管理区。进入项目以后，界面转换为连续工作现场：左侧导航保留上下文，主要区域是当前工作，右侧检查文件/变化/产出/固定 CLI 输出；并非把所有页面都改成聊天窗口。

## 已核实的参照与取舍

2026-10-05 阅读现有研究与官方资料。官网与 README 演示是产品公开展示，不是本次安装运行竞品或性能测量。代码没有从第三方复制。

| 参照 | 吸收的模式 | AgentBox 的取舍 |
|---|---|---|
| [Paseo](https://paseo.sh/) / [Workspace 文档](https://paseo.sh/docs/workspaces) / [官方仓库](https://github.com/getpaseo/paseo) | Project → Workspace → Session；会话标签、Files/Changes 检查面板；工作状态分组 | 完整功能清单的主要参照。现阶段保持 Project+AgentType WAW 身份，不用新标签假造任意多个会话。完整工作上下文仅标为规划样本 |
| [CloudCLI / Claude Code UI](https://github.com/siteboon/claudecodeui) | Project/Session 左树、Chat/Files 切换、手机底部导航 | 日常导航与管理导航分组；窄屏采用单列接续，不复制视觉皮肤 |
| [HAPI](https://github.com/tiann/hapi) | 清爽会话、创建前确认机器/目录/Agent、折叠工具活动 | 引导先项目与 Agent，再展示真实连接条件；没有假“一键全部就绪” |
| [Yep Anywhere](https://github.com/kzahel/yepanywhere) | 跨项目 inbox、完整/精简会话、手机 diff 后的审批 | 待处理优先；审批显示对象、范围、单次限制和失效条件；不解析终端文字成为审批 |
| [Happy](https://github.com/slopus/happy) | 手机接续与待审批体验 | 手机任务型导航和安全确认；不引入另一套认证或加密执行链 |
| [Codexia](https://github.com/milisp/codexia) | 项目、工作区与会话的层次 | 让深工作有足够空间，技术诊断次级 |

没有证据确认“Cindy”的准确官方身份，因此没有据此添加链接或设计事实。仓库中 2026-09-28 的完整 Paseo 功能吸收目标优先于早期的部分吸收假设。

## 信息架构与页面清单

| 页面 / hash | 可审阅的具体体验 | 当前能力与计划映射 |
|---|---|---|
| 工作概览 / overview | 待处理、后台工作、最近项目、状态样本 | A2/WEV-2，沿用 PR147 当前用户最近100 Job、最多6 Project 的窗口；不展示 AI 进度 |
| 待处理 / attention | 原因 → 影响 → 下一步，技术细节折叠 | 现有 Job `needs_attention`；Agent 审批另域 |
| 项目 / projects | 搜索、收藏、标签、新项目入口 | WS01/WS14 已有领域；归档仅规划 |
| 项目详情 / project | 项目摘要、Agent 入口、Git 摘要、资料 | 正式 Project ID/READY，内容和进程权限独立 |
| 工作台 / workspace | 对话、工具活动、composer，右侧检查面板；手机切换 | A6/AG11 结构化会话、WS15 面板规划；既有 WAW CLI 保留 |
| 代码变化 / changes | 紧凑文件列表 + 同屏统一 diff/完整原文 | WS08：已合并统一视图软件；A3 默认未配置不可用、生产仍需独立准入。双栏/审查/分享后续 |
| 文件 / files | 项目树与纯文本只读预览 | WS06/A3 待实现；WS07 编辑/上传/保存冲突未开放 |
| 产出 / artifacts | 从工作中提取文档/图/变化检查入口 | AG11/Task 的规划索引，不拿 Job 当 Task |
| 操作审批 / approval | 单次范围、文件对象、来源、先看变化、允许/拒绝/暂缓 | A7/AG12，绑定 requestId/generation/expiry，与 Phase11 Provider approval 分域 |
| Agent 管理 / agents | 安装、登录、执行、连接四个独立状态 | 现有 Claude/Codex 管理领域，Remote/Pairing/Auth 分开 |
| 设置 / settings | 外观、语言、快捷导航、信任、帮助 | 现有设置/Doctor；Provider Manager A8 规划，不新增 Secret 表单 |
| 首次使用 / onboarding | 选择项目 → Agent → 条件检查 | 现有 create/clone 领域重排；不承诺真实 CLI/云端一键 setup |
| 系统状态 / system | 连接准入条件、未知、诊断折叠 | 原 Doctor / Runtime 能力；control-plane ready 不是 WAW admitted |
| 设计导航 / map | 所有屏幕与试用方式 | 只属于评审原型，不进入正式产品导航 |

完整功能 inventory 的 A–F 组继续作为最终范围，不能因本稿没有画完每个扩展设置页而缩小范围。多主机、原生客户端、语音、插件、MCP、任务编排、Hub/团队、计费与发行等后续能力在相应 WS/AG/CL/EX/HB/OP 合同成熟后扩展管理区或独立工作上下文；本次不伪造已接通的入口。

## 共享设计系统

- 布局：桌面 212px 导航 + 灵活主体；常规内容 38px 内边距；工作台独立滚动并保留 composer；800px 以下单列、四项底部导航
- 层级：页面 32px / 工作台 23px；区块17px；正文12–13px；元数据10–12px。正式实施继续验证用户字体缩放并提高需要持续阅读的最小字号
- 字体：系统 sans + CJK fallback；技术标识/代码单独 monospace；不请求远程字体
- 颜色：浅色 `#f6f5f1` / `#fffefa` / `#252825`；强调 `#d77836`；深色 `#202320` / `#272b27` / `#eeeee7`；提示用文本与图形而非仅颜色
- 间距：4/8/12/16/20/24/32/40；面板12px、按钮7px、标签4px圆角；边框承担层次，避免大量投影
- 组件：固定页面 shell、工作标签、panel/list-row、status badge、context heading、empty/error/loading、受控 disclosure、native dialog、command search、composer、文件树、统一 diff、approval scope
- 输入：所有主操作可键盘访问；focus-visible 3px；modal Escape/取消/焦点返回；手机 drawer 约束焦点；窄屏主要触摸目标44px
- 动效：只用于轻微导航反馈；尊重 reduced motion；不以动画表示未经验证的进度

## 状态与事实保真

1. 进程运行、浏览器连接、任务状态、历史可恢复性、观察有效性分开，不用一个绿点覆盖所有维度。
2. Job 是后台技术操作，不是 AI Task。首页计数只能反映允许读取的有界窗口。
3. Project `updated_at` 不改叫“最近使用”，重新连接不改叫 Resume，登录不等于就绪。
4. loading / empty / error / permission / stale 单独渲染；无效时不保留行、计数、时间或动作许可，不能显示假0。
5. 真实实现保留 hidden/pagehide/freeze/offline/auth/scope/unmount fences、晚回复抑制、原始有效期与 clear-on-hide；样本状态切换不被描述为运行了真实 lifecycle 合同。
6. 文件/补丁必须显式请求、完整验证、按来源持有期限展示。设计不能为节约点击自动预读或合并权限。
7. exact Stop、disconnect、turn interrupt、archive、close tab 分开。原型 Stop 只演示确认，不调用任何进程。
8. 不在普通 API/日志/存储里放 Runtime 内容/Secret；不引入任意 shell、cwd、命令或文件系统 gateway。

## 迁移顺序：沿用既有功能计划

| 批次 | 范围与依赖 | 验收和停止点 |
|---|---|---|
| 0. 视觉方向确认 | 当前完整原型、实际桌面/手机图、用户反馈 | 确认风格与信息架构后才做生产大范围迁移；当前稿不自动成为品牌规范 |
| 1. 共享外壳与基础组件 | A2：tokens、导航分组、按钮/列表/状态、保留旧路由 | zh-CN/English、keyboard/focus、360/390/768/1024/1440、no horizontal overflow，旧管理入口可达 |
| 2. 工作概览/项目/待处理 | PR147 完成后复用已验 hook/API；不改数据权威 | 当前100/6窗口、失败/权限/过期、真实updated_at、no Runtime fan-out，existing lifecycle tests全部保留 |
| 3. Changes 审查布局 | WS08 已验 unified reader；紧凑树与内容并列 | 保留用户显式读取、complete END、original owner/lifetime/取消/清除、raw fallback；无自动预取与导出权限 |
| 4. Files 与面板 | A3/WS06/WS15 各自先冻结有界内容合同 | 路径/敏感/编码/binary/大文件/取消/过期/键盘/手机，未合格能力继续 unavailable |
| 5. 结构化工作与审批 | A6/A7 adapter、AG11/AG12 协议；主机开放依赖A5 | 不解析TUI伪事件；requestId/generation/expiry、uncertain ACK不重发、turn interrupt与Stop分开 |
| 6. 后续能力接入 | A8 Provider、A9 Task/Worktree 和完整 inventory的后续组 | expand-first schema/回退/WIP保全；保持各项目已有生产、Secret与发布门禁 |

每批独立 feature branch → exact-head CI → 普通合并 → exact-main 回读。当前设计分支不合并生产、不发布、不改变其它功能候选，未授权 host/credentials/deployment 不执行。

## 现状像素观察

已查看 PR147 `09e3142` 的6张真实 CI 概览图与手机裁片：功能布局未发现横裁切、缺字或异常页尾；待处理、进行中、最近项目和空态均可见。现有布局的主要设计问题是同权管理入口、技术标识和说明占主要篇幅、手机长页与标题层次不统一。Changes 的旧实际截图进一步显示补丁内容在长列表后，促成本稿文件列表与 diff 同屏的决定。这个功能像素结论不代表新稿已验证，也不表示现状美观。
