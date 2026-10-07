# A2 UI 接续：既有 Workspace 页面外壳

## 基线、范围与依据

本批接续同一已批准 UI 重设计版本，不新开功能路线图。当前 main 为
`0fdeb6475487d8a2456dfcc7b04262562a8c27ac`，tree
`f3e65bf12c0846d70b5dc9d1a6cb507c719f0f8e`。PR153 与 PR155 已正常合并；
该 exact-main 六套首轮成功、26 checks 为23 success/3规定 skip，Backend 实际
3.11.16/3.12.14/3.13.16各5375 passed/88 skipped，E2E299 passed/73规定 skip。
合并头 f06 的 Backend 实际3.13.15也通过；两份版本证据分别保留。旧 READY
间歇问题仍开放，本批不再做诊断框架、负载调参或预算优化。

依据原[整合计划 A2](project/WORKBENCH_INTEGRATION_PLAN.md)、
[页面 controller 合同](WAW_R11_RC6_BROWSER_CONTROLLER.md)、
[生产组合合同](WAW_R11_CONTROLLER_COMPOSITION.md)、
[浏览器实现决策](project/WAW_BROWSER_IMPLEMENTATION_DECISION.md)与
[工作标签导航边界](WORKBENCH_PROJECT_TABS.md)，只迁移现有 `/workspace` 和
`/workspace/:workspaceId` 的呈现：Project/AgentType选择、真实状态摘要、终端
区域布局、既有操作栏、标签及 exact Stop 确认。沿用已落地的暖白/墨色/琥珀
tokens；色板是可回退实施选择，不冒称 Owner 指定。没有新增聊天、Files、分屏、
Provider配置或 Runtime 能力，也不修改版本、发布或部署。

较早的 metadata-only 文档保留历史状态；当前能力以已接受的 controller/stream
合同与实际代码为准。通用构建仍无 production trust-provider enrollment，页面
必须按真实 model 显示 Connect 不可用，不能为了设计截图注入生产替身。

## 保留的行为与权限

- `WorkspaceRoute`、`useWorkspaceController`、attachment/controller、typed ports、
  加密、parser、scheduler、trust与后端本批保持原样。只有真实功能对应的现有按钮。
  若迁移暴露必须改变业务或安全合同的问题，先提交独立有界卡片审查。
- lifecycle metadata、Runtime状态与 browser attachment admission分别显示；
  `RUNNING`不等于`CONNECTED`。操作仍由原 canStart/canStop/canConnect/
  canReconnect/canDetach/canInput与pending控制，不能由外观推导许可。
- terminal viewport/surface保持单一稳定DOM ref，不因布局、状态或disclosure
  展开重挂载。固定viewport与ResizeObserver继续提供尺寸；8px×20px cell、
  16px padding、closed renderer classes与原资源预算不变。无新renderer或缓存。
- 原输入保持uncontrolled DOM、IME与UTF-8含CR限制，使用原clearer及scope清理；
  不把输入、输出、ticket、key、frame、history写入React persistence、URL、
  storage、日志、截图或analytics。不自动重发不确定input或mutation。
- exact Stop保留原生dialog、Cancel默认焦点、Escape的pending guard与明确
  workspace/generation目标。原 runtime fingerprint/observation token及
  `Detach(ATTACH_PTY_CLOSED) → Stop` proof不变；无direct Stop旁路。
- selection、administrator Session、route、hidden/offline/pagehide/freeze与
  unmount的围栏继续生效。返回只依原controller重读；关闭导航标签不隐式
  Start/Connect/Stop。Project、Workspace、AgentType、管理员Session保持独立。
- bounded error只显示本地化文案和原technical code/request ID；用户Project名
  仍为inert Unicode。过期状态不保留旧许可或把未知结果展示为成功。

## 验证与截图

保留原页面、controller、attachment、exact Stop与真实浏览器全部断言；补齐布局
改变所需的焦点、窄屏、长inert名称、disabled操作、输入/Stop取消及稳定DOM ref
回归。用真实App/API流程检查route/Session切换、迟到回调、Back/Forward、离线
与重复操作，不能用只mock页面model的视觉测试替代既有生命周期证明。

截图只使用明确的synthetic metadata、无terminal正文的非连接状态与确认框。
已有连接/加密/终端行为测试继续禁止trace、video及截图。新图片采用专用
`ui-workspace-*.png`前缀与精确artifact allowlist，不扩大敏感内容留存。
ready metadata覆盖zh-CN/English×360/390/768/1024/1440×light/dark；另有
loading/empty/unregistered/error/forbidden/stale/revalidating/disabled/dialog
等实际状态样本。检查44px controls、overflow、keyboard focus、reduced motion；
真实CI原PNG必须校验并打开复查，不用build或图片文件列表代替像素验收。

按小稳定提交、Draft PR、适用本地检查、独立source/像素审查、exact-head六套、
正常merge与exact-main回读完成。本卡是普通呈现层迁移，不是新业务/安全合同。
本页最初只记录范围；尚未实施或取得本批新测试/浏览器/CI资格。

## 08:05 UTC 首份呈现源码checkpoint

已完成页面/CSS/双语catalog首份呈现迁移，Project与Agent选择紧凑呈现，terminal
为主区域，labels为侧栏，Runtime低优先技术字段进入原生details。Workspace ID、
reconciliation_required、错误与provider不可用等原关键事实保持可见。原model、
controller、route、typed ports、terminal metrics/ANSI classes与输入/Stop事件
逻辑保持；没有新增业务能力。

原18项页面单测通过、Web TypeScript通过、Prettier解析通过，作为可恢复源码快照
先正常提交。新增禁用/稳定DOM/Stop回归与实际App/API浏览器用例仍在实现，尚无
本批真实浏览器/原PNG或新exact-head CI通过声明。后续正常追加提交，不改写历史。

## 08:14 UTC 页面回归与浏览器候选

原18项页面断言保留，新增canX/pending矩阵、Stop pending的Cancel/Escape、
稳定viewport/surface/clearer及非loaded状态等回归，页面105项、相关5文件153项
通过。TypeScript、targeted ESLint、Prettier与diff检查通过；新增测试首轮的一项
React19 ref额外undefined参数假设错误已修正，不是产品RED→GREEN。空Runtime
disclosure在没有loaded metadata时省略；仅Workspace范围把标签checkbox的实际
hit area做到44px，保留原事件/checked/disabled及forced-colors原生呈现。

新ui-workspace浏览器候选静态收集66项，预期45执行/21规定skip；计划42张PNG，
20 ready矩阵、20双语手机状态样本、2中文展示。仅固定API白名单/合成metadata，
实际App路由与controllers，未注入native或managed-provider替身；capture要求
固定Workspace路径、空surface/input、无password与server-prose，两个artifact
allowlist只追加ui-workspace前缀。TypeScript首轮test.use reducedMotion类型错误
已按既有contextOptions修正并复测。此刻仍未运行实际浏览器或取得像素资格。

独立审查提出一个尚未证实的既有controller重入风险：同一task内重复确认Stop，
第二次fence可能中断第一项pending请求。将先以现有controller fixture做最小
test-only验证；尚未修改controller，不放宽新浏览器断言。若成立，必须给出
源代码依据、真实RED与有界修复卡片，再处理该部分；普通布局与证据准备继续。

## 08:17 UTC 既有重复Stop的真实RED

在未改动controller上，现有fixture新增一个最小case：同一committed confirmStop
连续调用两次，并让transport真实响应AbortSignal。实际结果是仅1个Stop POST，
但firstSignalAborted=true、stopTarget=null、pending=null、WAW_ACTION_STALE。
原始case与格式化后case均exit1（1 failed/24 skipped）；ESLint、TypeScript与
diff-check均exit0。测试先settle held transport再断言，没有遗留未完成任务。

新增test-only回归位于useWorkspaceController.test.tsx，Git blob
`ffaff74fbc2ee89727631bff7b130fc375122d3d`；controller blob仍为
`ffedceac76ffb43efbf21e6220e5559e3b655f7c`，产品diff为0。这证明既有重复确认
会中断第一项操作，不是布局新增缺陷，也没有证据表明发送了重复Stop。
已提出同步、scope-bound single-flight owner的最小修复卡片，产品修正尚未开始。
保留真实RED与原全部断言；本候选因此未合格，不能merge或宣称浏览器通过。
