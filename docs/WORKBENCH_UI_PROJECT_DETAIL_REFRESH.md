# A2 UI 接续：Project 详情与待处理

## 范围与基线

本批继续同一已批准 UI 重设计版本，接续
[共享外壳、概览与项目导航](WORKBENCH_UI_SHELL_REFRESH.md)，沿用
[整合计划](project/WORKBENCH_INTEGRATION_PLAN.md) 与
[完整交付计划](project/FULL_CAPABILITY_DELIVERY_PLAN.md)。分批提交和 PR 是实现与
验证单位，不代表每批发布一个新版本；不改 package version、tag、Release 或部署。

远端基线 main 为 `9f2721ed6dc9c5e6ac41c162463f29674004ad12`，tree
`fc152423899fcc9b313c269b45022a1ed425e98d`。该 exact-main 六套 workflow 成功，
23 checks success / 3 prescribed skipped，E2E256 passed / 50 prescribed skipped。
PR152 的最终接受时限修正有三相同 Python patch 版本的真实 RED→GREEN；旧 READY
23/24 间歇超时根因仍未证明。本 UI 批不更改该诊断或任何 Runtime/Python 预算。

只迁移现有 `/projects/:projectId` 与 `/attention`，采用已落地的暖白/墨色/琥珀
tokens、系统浅深色与双语言。固定设计稿是可修改提案，颜色仍是可回退实施选择，
不以可选审美反馈暂停开发，也不把设计稿中规划中的能力变成可点击的虚假入口。

## Project 详情

- 优先显示真实 Project 摘要、READY 时的 Workspace 入口与既有 Changes 入口。
  Git、GitHub PR、标签、最近 Job 与 Project 绑定 Claude Session 仍是原领域。
- 原 Pull/Push、创建/切换分支、Draft PR 与 Claude start/stop 行为保持；分支和
  Draft PR 表单按需展开，Cancel/Escape 清草稿并返回触发器。关闭表单不是取消
  服务器已接受的操作，Job 状态仍按现有 API 读取。
- 草稿和展开状态归属于 administrator user/session + Project。两个数据 hooks
  留在稳定外层，只有草稿展示层按身份重建，避免重挂载丢失 pagehide/freeze fence。
- useProject/useClaudeProject 只修本页直接数据路径：owner、request generation、
  operation token、同步防重及 response identity 校验；旧 scope/GET/POST/poll/
  finally 不得覆盖新 scope 或解除其 pending。既有列表和全局 Claude manager 不改。
- hide/offline/pagehide/freeze 清除旧观察；独立恢复事件不能提前解除另一屏障。
  返回只 GET/readback，绝不自动重放 mutation。Project POST 不确定结果的显式
  重试继续使用既有 idempotency key 合同，不创建第二个 Job 队列或 Runtime owner。
- 已知运行中 Job 的 transient error、身份异常或 metadata 读取失败不等于 Job
  完成。显式 Refresh Project 必须只读同一已知 Job 恢复，再更新 Project/branches；
  terminal POST 也需 metadata readback。保留原 Job 与当前 Project 身份的区别。
- 显式 readback 的 request revision 永久废弃旧在途 poll。真实回归已先观察到
  同一 React batch 内 succeeded 被迟到 queued 覆盖，再验证修正后保持新结果；
  不仅依赖 loading 期间的短暂屏障或 effect cleanup 时机。

## 待处理

Attention 直接复用已验证的 useOverviewResource，仍只读取
`/api/v1/jobs?scope=mine` 的当前账户最近100项窗口，筛选 needs_attention。
loading、empty、error、forbidden、stale 独立显示；失效时不保留条目、计数、时间
或动作许可。真实 reason code 与 received-at 保留，Job ID 等技术字段按需展开；
只对有效正式 Project ID 提供链接。不渲染 result/error summary，不编造影响、
修复建议、审批、重试或 Agent 进度。

## 边界

[ADR0009](adr/0009-workbench-identity-and-content-boundary.md) 的 Project、Workspace、
administrator Session、Claude Session、Job、AgentType、ProviderDefinition 保持
独立。Project READY、进程 running、浏览器 connected 不合并成一个状态。导航、
Back/Forward、关闭页面不隐式 Start/Connect/Stop；legacy Claude Stop 不是 WAW
exact Stop。本批不新增 API、route、数据库、Files、聊天、审批、Provider 配置、
任意 shell/path 权限或自动补丁正文读取。Workspace/Changes 只回归现有导航。

## 验证与交付

需要真实 hook 与 ApiClient/AuthContext/MemoryRouter 回归，包括 A→B→A、管理员
Session 原地替换、迟到响应、旧 finally、重复提交、已知 Job readback、取消/Escape
与焦点、Back/Forward、隐藏/离线/pagehide/freeze 的交错恢复。原本只 mock hook
的页面展示测试继续保留，但不拿它们替代生命周期证明。

浏览器使用正常 App/API 流程并保留旧断言；新增严格隔离的合成 metadata fixture。
ready 页面截图覆盖 zh-CN/English × 360/390/768/1024/1440 × light/dark，两页40张；
另有代表性状态图。640 CSS px 重排只作为 desktop 200% zoom-equivalent，不冒称
执行了浏览器真实缩放。检查键盘、44px 目标、长 inert 名称、溢出与 reduced motion。

截图仅允许 `ui-detail-*.png` 的合成页面，自动截图/trace/video 继续关闭；不保留
登录字段、真实账号、凭据、Pair Code、终端输出或 Secret。新 head 的真实 CI PNG
必须下载校验并实际打开审查，不能以静态 source/list/type 检查声称浏览器通过。

交付遵循 feature branch → 全量适用本地检查/独立审查 → Draft PR → exact-head
六套终态 → 正常 merge/read-back。当前仍为候选开发，真实浏览器、最终像素与
新 head 完整资格尚未取得；不声明完整 UI/A2/S02 已全部完成，不执行发布或部署。

## 2026-10-07 本地候选与独立复核

最终冻结的 hooks 回归73/73（Project29、ClaudeProject33、既有Claude11）通过，
独立页面与 Labels 39项通过。独立源码审查分别覆盖 hooks 与页面/E2E/截图边界，
均无未关闭 P0/P1/P2。已知 Job 恢复、terminal POST readback 与同 batch 迟到
poll 覆盖新 readback 的问题均先有失败回归再修正；既有列表 useProjects 与全局
useClaude manager 主体逐字未改。

本地 Node24.19.0 / 锁定 pnpm11.20.0（CI仍用既有Node22）执行 pnpm test、lint、
typecheck、format:check、build 与 audit --audit-level high 均 exit0；审计保留
2 moderate / 0 high / 0 critical，未改 lock 或预算。构建保留既有大 bundle 警告，
不靠放宽门槛消除。workflow action pins、secret-pattern、source-boundary、
735 relative docs links 和 git diff --check 均 exit0。

Playwright --list 共370项；新 spec64项中42项执行/22项规定 skip，计划新增62张
合成截图（两页40 ready +22状态），尚未运行真实浏览器。后续结果与确切远端 head
写入 PR，必须以该 head 的 CI 和原 PNG 像素实查为准，不能借用基线9f的成功。

## 2026-10-07 首轮真实浏览器发现与修正

首个完整 head `30cddb400fa100e9ec03a31e0f4af6765ead7d44`（tree
`a85d4d5913441b82dd8dd8976c57ba0197eb3988`）五套 workflow 成功；Backend 实际
3.11.16 / 3.12.14 / 3.13.15 各5307 passed /88 skipped。E2E37566122247 首轮
255 passed /43 failed /72 prescribed skipped，未合并，也未重跑旧头。

失败明确指出：Project 手机错误面板三列挤压及长技术 ID 溢出；Attention summary
取得焦点后无可见样式变化；新 fixture 遗漏原 ControlPlanePulse 的固定 healthz GET
和原 WorkspaceLabelsPanel 的特定 labels GET。补丁将本页错误面板改为可收缩单列，
保留完整技术值；两页 summary 提供明确 focus 轮廓；只补这两个现有 GET 的严格合成
response，不开放泛化请求，不减弱 unexpected/mutation/overflow/focus 断言。

失败 artifact11459575826 含106 PNG（62新页+44旧 shell），ZIP SHA256
`d81108d35c480d6fbea101bac185423878d911d32118498a8fde3631f658d1f2` 与服务端一致，
CRC/path 校验通过。主实施者打开5张原图，独立 reviewer 检查42张（跨两页/语言/
主题/全部五宽20张及全部22状态）。发现手机 forbidden 文案窄列，已由同一 grid
修正；另发现中宽英文 Refresh 图标缩小，补固定不收缩。静态图不代替焦点行为验证。

后继保留原完整矩阵与断言，增加普通合成名称的独立4张展示图、英文手机两种错误
状态2张及明确 focus2张，计划70张新 PNG。Playwright 共372项，新 spec66项中
43执行/23规定 skip；新 head 实际 CI、修正后原像素与整体资格仍待完成。原失败记录
和旧 READY 间歇根因边界均保留。

## 05:30 UTC 当前UI真实结果与资格修正接续

UI headb07ba662a8d98a9ce5c97d4c19ab8ebb57d00709的E2E37568112051首次299 passed /
73 prescribed skipped /0 failed /0 flaky。artifact11459809303包含126 PNG，
其中70新UI、56既有，ZIP SHA256
`3cee5ca64d46319ae5304dc8b5853775e245c442ed406af7633eb20b22845765`与服务端相同，
CRC和路径检查通过。错误面板重排、两个focus轮廓、768/1024英文Refresh图标及
四张普通合成展示原图均实际打开复验；四图已保存并交付，不冒称生产上线。

该头Backend实际3.13.15仍为原READY23/24 receive超时，none/ge200ms/ge250ms，
5306 passed /1 failed /88 skipped；其余五套成功。保留该失败，不盲重跑、不merge
红头，也不把后续源优化称为已经定位旧根因。

[独立PR154](https://github.com/ForceMind/agentbox/pull/154)仅移除guard=None时相邻
重复peer proof，保留exact250ms与所有授权/guard/syscall/final边界。真实18项
RED→GREEN、独立源审查及head22043ceb六套均通过后，正常merge为main1ce060f，
tree4d26fe53与合格头一致；main自己的六套仍待，不用head结果冒充main结果。

此整合从远端b07出发正常merge-forward main1ce，保持两条PR历史；旧UI源码/
E2E/workflow与b07逐字一致，移植的三个文件与main1ce逐字一致。只更新本记录与
三个项目快照。实际整合头的完整CI/新原PNG资格仍待，不新增其他UI范围或发布。
