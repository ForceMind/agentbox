# A2 / WEV-2 工作概览：有界只读投影

## 范围与入口

本卡落实 [整合计划 A2](project/WORKBENCH_INTEGRATION_PLAN.md) 与
[WEV-2](WORKSTATION_EVOLUTION.md) 的 Dashboard 首屏工作概览。
位于原控制平面健康、就绪、版本与能力区之前，保留原入口；不替代 Workspace、
Project detail 或 Attention。首屏显示待处理、进行中的工作、最近更新的项目。

基线 main `a1cab129f18ede5b982b6ab53d037c51771b4dea` / tree
`26f245acde25737aa9c8ef47e408ad9c56a8006a`，已有 #145/#146 六套主干资格。
本卡不借用旧 CI/像素认定新实现通过。七文件旧批闭环补丁在该 exact tree
核验后随本批落实，保留旧失败与当时 pending 历史。

## 真实来源与权限

- `GET /api/v1/jobs?scope=mine`：沿用 Session 认证，从 authenticated.user_id
  取得请求者；SQL `requested_by` 过滤先于 `LIMIT 100`，随后
  `created_at DESC, id DESC`。不接受调用者指定 user_id。省略 scope 保留旧
  管理员列表合同；既有 Attention UI 改用 mine，确保首页链接的窗口一致。
- `needs_attention` 进入待处理；`queued` / `running` 进入进行中。其他状态
  不推断为待办；进度百分比、自由 phase/summary、CLI/TUI 输出均不呈现。
  计数只覆盖返回的最近创建100条，不是全量积压、全部任务或 AI 思考进度。
  每栏最多显示最新6条，标题计数覆盖完整返回窗口；不发 status 历史全量查询。
- `GET /api/v1/projects/recent`：沿用现有单 active admin 的共享 Project 目录
  权限，不新增 owner/role/ACL。固定最多6条，`archived_at IS NULL` 且 state
  非 archived，按真实 `updated_at DESC, id DESC` 排序。只读 DB metadata，
  不调用 `_reconcile`、Runtime workspace discovery、Claude session 或 Git status。
- Project 更新时刻是既有 DB 元数据更新时间，不是访问、使用、Agent 心跳或内容
  修改时间。已知 naive UTC DB 值经现有 aware_utc 明确序列化 UTC 偏移，不改变
  存储、不写访问时间。`git` / `github` / `claude_state` 保持 null。
- 两条 HTTP GET 复用既有 schema，`Cache-Control: no-store`，无新 DB 表/索引、
  scheduler、task registry、内容通道或生产权限。数据库仍按其既有索引执行排序，
  此卡限制返回/呈现/请求数量，不声称无关数据量下恒定查询成本。

## 生命周期与呈现

每源单次 GET，15秒沿用 API timeout，初次或显式刷新时读取。无 interval、后台
轮询、自动重试或持久存储。快照旁显示本设备收到响应的时间，不冒充服务器
观察时间或健康 TTL。

hidden / pagehide / freeze / offline 立即 abort 并清空行、计数和时间。返回
visible / pageshow / resume / online 时每源只读一次，重复事件不重复请求。
已取消的晚响应不能复活；切换 user/session/api、卸载或失去认证时旧源失效。
刷新期间按钮禁用；隐藏/离线时点击刷新不会绕过生命周期门槛。

Jobs 和 Project 源独立报告 loading / empty / error / permission / stale。
失败或未授权不能呈现“0”，也不展示 server prose。401 仍沿用全局登录恢复；
403 明确权限提示。项目名用 inert React 文本/`bdi`，技术标识沿用安全 formatter。
只为有效正式 Project ID 提供原详情路由；点击链接由原页再次执行其认证/权限。

## 验收与停止条件

- 后端：匿名/伪造/过期/撤销 Session，其他用户更近期 Jobs 不挤走本用户窗口，
  100/6上限、同时间 ties、真实时刻、归档过滤、no-store，无 Runtime/写入
- Web：真实状态分组、六条展示与窗口计数，缺失/畸形/过量 metadata 失败，
  loading/empty/error/permission/stale，隐藏/离线/page/freeze、晚响应、auth/
  session/卸载 fence；不把自由正文/百分比当进展
- 正式 App + HTTP API：隔离 DB seeded metadata，实际登录，在桌面/手机、
  zh-CN/English 显示三栏与原健康入口、键盘刷新、Attention/Back 路径；另有
  网络 fixture 验证中断状态。截图只包含合成 metadata，不含真实凭据/终端
- 独立 source 与实际 PNG 像素检查；exact-head 六套 CI 全终态后交父级复审，
  按正常 Ready/merge/read-back/exact-main 六套闭环。未运行和失败分别记录

若必须新建调度/任务源、扩大权限、无界 Runtime fan-out、读文件正文、生产
key/pin/host/账号、安装激活、发布/部署，则停止相关步骤另列合同，不暗中扩域。
完成本卡后停止；只提出 WS06 Files 下一卡，不实施。WS08 双栏/审查/分享仍为
最终清单范围；当前不顺带扩大 diff 样式，也不宣称 A2/S02 整体完成。

## 当前验证记录

本地 Web 完整1574 passed；修正 lifecycle latch 后 focused32/32，extension6/6。
Python 新增与相关回归175 passed（含新17项），独立新 API17项亦通过；
lint/format/typecheck/build、doc links 与安全边界检查通过。新 metadata GET
使已审 route 数从53增至54，脚本新增 exact `/recent` guard，不放宽 mutation。
独立 source review 发现刷新会重置 offline/pagehide/freeze latch，改为 useRef
跨 refresh 保留；三条独立 React probe 及明确 stop→refresh→resume 回归通过。

本地正式 E2E 首轮发现 video 配置不能置于 describe，已移至文件级。次轮因
本机缺 Chromium 而终止；官方浏览器安装下载为无效ZIP，日志保留。这些不是
浏览器通过证据。完整新 head 远端 CI 与实际 PNG 像素尚未产生；最终结果需
exact commit/read-back 记录，本段不是软件 Ready 声明。


### 首轮 exact-head CI 的失败记录

首轮 head `70db127464cae286f33735c1aff2692b0f66a9b5` 的 Frontend、Security、
Deployment、Release Candidate 通过。Backend 3.11/3.12 与 native 通过，3.13
为5301 passed/1 failed/88 skipped：未改动的 native admission 测试在 READY
前收到 PATCH_REVOKED EOF。受控延迟 CURRENT_REPLY 300ms 可使固定250ms
currentness fail-closed 产生同一表象，但原 CI 未记录底层关闭原因，因此历史
因果未证实，没有据此改 Runtime、预算、断言或单测 timeout，也未重跑旧头。

[E2E 首轮](https://github.com/ForceMind/agentbox/actions/runs/37347713899)
228 passed/4 failed/30 skipped；新概览4个状态场景通过，4个主流程均在焦点
样式断言失败。鼠标登录后直接 programmatic focus 不保证 :focus-visible，
新测试改为真实 Tab 到刷新按钮、确认 focus-visible 和前后样式差异再 Enter，
不删除视觉/键盘断言、不通过额外CSS掩盖。完整新 exact-head CI/像素仍待验。
