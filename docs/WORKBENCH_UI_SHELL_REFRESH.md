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
