# Workspace Metadata Workflow

## 当前能力

管理员可从 Project Detail 打开工作区，或在 `/workspace` 选择一个正式 READY
Project 及 Claude/Codex。页面按精确 Project/AgentType 查询已注册的 workspace，
读取记录与 Runtime 状态，显式发起 Start，并通过二次确认执行 exact Stop。

这仍是 metadata/control 工作流。浏览器终端未开放，页面始终显示
`NOT ADMITTED`；Connect/Reconnect/Detach/input 不会为了演示而获得假响应或无用
票据。真实 CLI、加密通道、PTY、legacy interlocks 与主机验证仍在 Stage F。

## 查询与权限

`GET /api/v1/workspaces` 识别可选 `project_id`（canonical `prj_` + 32 hex）和
`agent_type`（`claude|codex`）。SQL 先精确筛选，再执行现有授权策略，最后使用
32 条响应上限。两项筛选同时提供时，唯一 Project/AgentType pair 返回 0 或 1 条。
未授权目标不泄漏；无筛选时保持已有行为。响应 `Cache-Control: no-store`。

客户端要求返回行与选择的 Project/AgentType 完全一致，并拒绝多行、未知字段、
无效状态和 unsafe numeric generation/revision。旧 metadata 接口的 generation
仍为 JSON number，因此超过 JavaScript safe integer 的 metadata 会 fail closed；
不会舍入后发出 Stop。实际 control generation 继续使用 canonical decimal string。

## 操作与状态

- READY 项目列表加载失败时给出刷新入口；未选项目、无 READY 项目、加载中、
  未注册、查询失败各有明确展示。未注册不能从浏览器自行造 host/binding/path。
- Start 始终是显式操作，只针对选中的已注册、允许启动的记录。HTTP 回包仅确认
  lifecycle 请求，随后重新读取 metadata/Runtime；不会成为 terminal admission。
- 页面将持久记录、Runtime 观察结果与浏览器连接状态分开。Runtime 的 UNKNOWN、
  COLLISION、BROKEN、MISSING 或 recovery-required 状态阻止相关操作。
- Stop 的第一次点击只创建确认目标；确认固定 workspace/generation，并记录已观察
  Runtime 的 generation/binding/epoch fingerprint。选择、会话或目标改变后失效。
  取消、Escape 不发送 Stop；只有确认才携带原 exact generation 发出请求。
- server 从可信 row/coordinator 生成并验证完整 Runtime identity。浏览器不会伪造
  public metadata 未提供的 host/binding authority，也不是 Runtime 准入 authority。
- 查询、Start 和 Stop 结果均有 selection/auth/request fencing；迟到响应不能覆盖
  新选择或新会话。失败不自动重试有副作用的操作。
- 页面不获取或保存 ticket、terminal bytes、input history 或 transcript。

## 文件与验收映射

| 责任 | 实现 | 验证 |
| --- | --- | --- |
| 授权后的精确查询 | `apps/api/src/agentbox_api/workspaces.py` | `tests/integration/test_waw_workspace_api.py`：32 条边界、两 AgentType、非法筛选、授权隔离 |
| metadata closed decoder | `workspaceMetadata.ts` | `useWorkspaceController.test.tsx`：scope mismatch、多行/未知字段、unsafe generation |
| 选择、Start、Stop 协调 | `useWorkspaceController.ts` | READY、未注册、显式操作、二次确认、旧 lookup/Start、Runtime recovery/mismatch |
| Runtime 查询隔离 | `useWorkspaceStatus.ts` | query/auth/reload scope、错 workspace 回包、旧响应与 unmount |
| 浏览器首选语言驱动的`zh-CN`/English页面和原生确认框 | `WorkspacePage.tsx` / `WorkspacePage.css` | 两种locale的unit tests及真实Chromium desktop/mobile metadata E2E |
| 项目入口 | `App.tsx` / `ProjectDetailPage.tsx` | route/deep-link tests；URL 无票据 |
| 浏览器工作流 | `apps/web/e2e/workspace-metadata.spec.ts` | synthetic metadata、CSRF、exact Stop、取消/Escape/焦点、禁用终端、无横溢出、44px controls、无 Web Storage |

Web feature 文件均在 `apps/web/src/features/workspace/`，Page 文件在
`apps/web/src/pages/`。实际测试命令、结果、CI 与 merge read-back 见
`project/CURRENT_STATE.md`；项目剩余计划见 `project/EXECUTION_PLAN.md`。

## 证据限制

浏览器测试通过 mock metadata 驱动真实 App/Chromium，不使用真实 Provider、CLI
或 Linux host。视觉 QA 图片仅含 synthetic metadata，不包含终端、票据或凭据，
不作为 terminal/host 证据。现有完整 E2E harness 仍关闭截图、trace 和视频。
