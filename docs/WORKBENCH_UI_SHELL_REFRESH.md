# A2 UI 首批：共享外壳、工作概览与项目导航

## 来源与范围

本批接续已批准的 [整合计划](project/WORKBENCH_INTEGRATION_PLAN.md) 与
[全量交付计划](project/FULL_CAPABILITY_DELIVERY_PLAN.md)，落实 Owner 随后的
完整 UI 重设计要求；不另立功能路线图。以 Paseo 为主要信息架构参照，结合
HAPI、CloudCLI、Yep Anywhere；原型为 [固定设计稿](https://github.com/ForceMind/agentbox/tree/0402daba66399a4ee71b3d702e01d99789355bb7/design/ui-refresh)。
原型是可修改的设计提案，不代表 Owner 已批准具体颜色。此批自主采用可回退的
暖白/墨色/琥珀 CSS tokens 与系统深色偏好，不以可选审美反馈暂停正常开发。

仅迁移已存在的正式功能：

- 共享 shell 按工作、Agent 管理、管理分组；保留原 route、command center、
  Project 页面标签、健康状态与退出登录。手机原生 dialog 负责焦点约束，
  Escape/关闭返回触发器，导航、session 切换、隐藏、pagehide、offline 关闭。
- Dashboard 优先呈现有界 Job 概览与最近更新项目；技术健康/版本/能力保留在
  原生 disclosure，并明确 Control Plane 就绪不等于 Runtime/Agent 就绪。
- Projects 首先展示搜索/收藏/真实项目集合，创建与克隆表单按需展开；取消和
  Escape 清空本地草稿并返回入口，已提交操作不被宣称取消，重复 submit 被抑制。
- 保留 zh-CN/English、inert 名称渲染、44px 操作目标、键盘焦点和 reduced motion。
  终端保留原来的独立深色与 ANSI 配色，主题不会改变终端含义。

## 数据与安全不变量

[工作概览合同](WORKBENCH_WORK_OVERVIEW.md) 的当前用户最近100 Job、最多6 Project、
真实 updated_at 与 received-at、独立 loading/empty/error/permission/stale 状态及
clear-on-hide/abort/late-response fencing 原样保留。此批不改任何 API、hook、
Runtime、A3 加密准入/正文读取、认证、CSRF 或 Secret 路径。

Project、Workspace、Session、Job、Agent 和 Provider 仍是不同实体；不新增虚构的
AI Task、聊天、Files/产出/审批能力。收起技术区只影响呈现，不更改观测或权限。
不自动读取文件/补丁，不把连接、登录、就绪、进程状态合成一个绿点。

## 基线与 Git 交付

2026-10-06 通过 GitHub live read 与显式 fetch 验证 main
`a586eaec27984e0632187048cc1b82e7e29552d1` / tree
`e5d9309dca123f17f9ff9ee48df0765c332ea451`。PR147 已合并，exact-main
Backend、Frontend、E2E、Security、Deployment、Release Candidate 六套 workflow
全部 success；23 checks success / 3 prescribed skipped。早期 docs 中 PR147
pending/失败为历史快照，不能覆盖这一结果，也不把诊断补丁称为根因修复。

分支 `feat/ui-shell-overview-20261006`。首个 shell 提交
`e3628a257dbb92ed8419676618fbf0f8e703989f` 已在 GitHub 回读，tree
`cb71d9430b773f4dd6b0324c85e48e7a01b24fdc` 与本地已验 shell tree 一致。
CLI push 无写入凭据，使用已有 GitHub connector 的原子 tree/commit 与普通 ref
更新发布，不修改凭据、不 force/reset/stash/clean，也不覆盖原 worktrees。

## 验证与停止点

- 首个 shell：7 项单测、Web typecheck/lint 通过；包括分组、skip target、
  drawer cancel/focus、offline 与 route change
- 本批完整 lint/format/typecheck/test/build 已运行；1583 Web + 6 extension
  单测与17项 overview API 回归通过（exit 0）。旧 E2E 显式展开适配与新双语、
  light/dark、360/390/768/1024/1440 浏览器矩阵已完成 source 检查，真实浏览器待 CI
- 截图只采集隔离合成元数据；凭据、真实 CLI 内容和 Secret 不留存
- 必须记录实际 screenshot 像素检查、失败和修正；本地不同 Chromium 不能替代
  exact-head GitHub CI。新 head 六套全终态前不声明交付资格完成

交付为 Draft PR 和 exact-head 证据，当前任务不执行 merge、真实 host/账号、
生产 key/pin enrollment、安装激活、tag/Release 或部署。不宣称完整 UI 重设计、
A2 或 S02 全部完成。后续按原计划继续迁移，本文不添加新的能力授权。

### 候选本地验证记录

- `pnpm lint`、`pnpm format:check`、`pnpm typecheck` — exit 0
- `pnpm test` — exit 0，1583 Web + 6 extension；初轮 App 单测因 Dashboard
  新 capability link 与主导航同名而歧义，断言改为准确定位主导航后全量重跑通过
- `pnpm build` — exit 0；保留既有大于500kB bundle warning，不扩大本批为拆包
- `.venv/bin/python -m pytest -q tests/integration/test_work_overview_api.py`
  — exit 0，17 passed
- `python scripts/check-doc-links.py`、`bash scripts/check-secrets.sh`、
  `bash scripts/check-skeleton-boundaries.sh`、`git diff --check` — exit 0
- 新单测初版两处 Testing Library 不支持的 `exact` 参数已移除；最终 typecheck
  已重跑。错误日志不被描述为产品行为修正
- 交叉 source review 检出强边框对比不足，tokens 改为 light `#7c8475`、dark
  `#7c8874`；对 surface/bg 的对比分别3.84/3.56与3.85/4.26，仍待实际像素检查
- 本地正式 E2E harness 完成隔离 DB migration/build/API 启动，bundled Chromium
  缺失；system Chromium154 普通和经批准重试均在启动阶段受 AF_UNIX socket
  限制。后续同类失败停止，harness exit130（environment-blocked/interrupted）。
  没有进入页面、没有 PNG，不能称浏览器通过；由新 exact-head CI 接续取证
- 新 spec 为44 entries：20 responsive组合只由 desktop project 执行，mobile重复
  20条为 prescribed skip，另4条 interruption；不把这些 route-fixture 测试称为
  真实 Runtime/host 或端到端 API 权限证据。原正式 App/API overview E2E 保留

### 首轮 CI 与最小开发依赖修复

首轮 head `5d546fc2b0f712b266d3fc72e0743d3a4f742541` 的 Frontend、Backend、
Deployment、Release Candidate 通过；Security 的 frontend-audit 报告新上游
开发链漏洞，原失败保留：[Security run](https://github.com/ForceMind/agentbox/actions/runs/37462746670)。
E2E 此记录时仍在运行，不称截图或浏览器通过。

只在 `pnpm-workspace.yaml` / `pnpm-lock.yaml` 对受影响版本加精确 override：
`tinypool` 1.1.1→2.1.2 与 `source-map-js` 1.2.1→1.2.2，其余锁定版本不变。
官方依据：[tinypool 2.1.2 advisory](https://github.com/advisories/GHSA-85c8-ppgw-ccpr)、
[source-map-js advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q)；
[tinypool 2.0 breaking change](https://github.com/tinylibs/tinypool/releases/tag/v2.0.0)
仅移除 Node18，仓库要求 Node≥22。发布包类型对照显示 Vitest3.2.7 使用的
run/destroy/recycleWorkers/cancelPendingTasks/workerId 接口保留；实际验证仍必需。

项目声明的 pnpm11.20.0 frozen install 与 `audit --audit-level high` exit0，
0 high/critical，保留原有2 moderate，不称零漏洞。新依赖串行完整测试为
1583 Web + 6 extension，通过；默认forks隔离2项、threads17项及双端build
通过。生产license inventory实际核对8包未漂移，两个补丁均为开发链。

首轮新依赖 full Web 与 build 并行时，既有 exactStop 用例出现
PROTOCOL_INVALID/5000ms timeout（1582 passed / 1 failed），日志保留。
随后隔离与串行通过不抹除失败；根因未定，不归因为调度或新 pool，也不改
产品预算、测试断言/timeout或审计门槛。新 exact-head CI 仍是必要证据。

### 首轮真实浏览器失败与修正

[E2E run](https://github.com/ForceMind/agentbox/actions/runs/37462746684) 已终态失败：
232 passed / 24 failed / 50 prescribed skipped。20个新 responsive组合在原生
modal 的 Shift+Tab 边界断言失败；其余为2个登录版本位于新折叠区、1个旧drawer
关闭按钮定位歧义、1个紧凑克隆按钮仅32px宽。没有用已有单测或截图替代这些失败。

修正保留全部原断言：drawer 与 CommandCenter 共用显式 Tab 边界循环，native
showModal 继续负责 inert/top-layer；过滤隐藏/disabled/negative-tabindex控件，
不拦截 Escape 或浏览器修饰快捷键。primary-button 增加44px最小宽度与水平内距。
两个旧 E2E 流程真实展开系统区，关闭导航精确定位 dialog 内的按钮。
新增2项 Tab helper单测，与现有shell/command共16项通过；本地完整1585 Web +
6 extension通过，lint/format/typecheck与build复验。真实新head仍需再验。

首轮失败没有成功上传图片，不声明实际像素审查。后续失败只额外保留
ui-shell 合成 route fixture 自行截图的 PNG；仍禁用自动截图/trace/video，不上传
一般失败上下文、登录页、真实账号/凭据或终端输出。该保留步骤不改变测试通过条件。

### 第二轮浏览器与实际像素

head `76612192ad1f2def8fdcd771856321a37b0a957f` 的五套非E2E workflow全部通过，
[第二轮E2E](https://github.com/ForceMind/agentbox/actions/runs/37465293259) 为
252 passed / 2 failed / 2 flaky / 50 prescribed skipped；四次问题均在新测试
仅等待 `/logs` URL就立即Back后，期待Projects草稿消失的断言。原24个失败类中的
Tab循环、44px按钮与旧disclosure适配已通过，但不将2 flaky算作稳定通过。

隔离真实BrowserRouter/StrictMode的双语create/clone四项probe记录：
`navigate('/logs')` 返回时URL已改，旧input仍在且Logs标题未commit；等待Logs
标题后旧表单卸载，实际history Back后重新打开草稿为空、无mutation。该观测
证明URL不能替代DOM完成，不独自证明原CI因果。E2E现在在离开、Back/Forward
前确认实际目标标题和旧表单/overlay消失，保留回程input=0及全部零mutation断言，
无sleep、预算放宽或产品状态补丁；四项路由不变量回归纳入正式单测。

本次真实44张合成PNG从artifact11415596773下载并验证ZIP sha256：
`fe3a713d7f29937dabd2a4cc249b0c78e506d6df552c859be133354ce3c74916`。
独立检查12张覆盖两语言、两主题和五宽度，主实施者另实际打开5张；未见缺字、
横向裁切或内容重叠，但发现并修正三项呈现问题：手机概览标题受旧global selector
影响右对齐、New Project的Plus图标独占一行、900px高桌面侧栏退出按钮部分裁切。
修复仅提高overview selector精度、限定新建按钮inline-flex、压缩桌面导航空白，
保留44px目标。增加对应像素几何断言；导航截图仅截viewport，完整页面仍fullPage。

这些图片属于7661219，不冒充后继CSS候选截图。后继完整六套CI、实际截图与
最终像素复核仍需完成；全部失败/环境限制保留。

后继CSS/路由回归本地完整默认并发测试为1588 passed/1 failed：未改的
`wawExactStop.rc7` 在connect阶段报PROTOCOL_INVALID；与之前偶发失败同一表象，
根因未定，不能归因为本次CSS或pool。未改产品、预算或断言；随后用
`vitest run --maxWorkers=1` 检查完整suite在串行条件下的结果，仍需新exact-head
默认CI验证，不以串行结果冒充默认并发稳定性。4项持久Router回归已通过，
所有新增导航断言保持严格。
