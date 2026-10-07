# Current Authorized Action

## 2026-10-07 Changes闭环，接续Agent管理呈现（10:57 UTC）

[PR157](https://github.com/ForceMind/agentbox/pull/157)已正常合并为main
`38bd0b86d20050b7f0df734b14a29d8e1b706ded`，tree
`bc85ddcf4cf5bb4b677ce61c25de367276647056`与合格f214相同。六套exact-main首轮
成功，23success/3规定skip；Backend实际3.11.17/3.12.15/3.13.15各5375/88，Frontend
1800+6，E2E395/115无failed/flaky/retry。独立source/官方CI/main回读CLEAR；指定
48图覆盖为42metadata同字节验证继承+6新A3实际审查，不冒称210图全部审过。
主干与head同树，未重复下载main图。旧READY间歇问题仍开放，无release/deploy。

同一UI版本接续[Codex/Claude管理页合同](../WORKBENCH_UI_AGENT_MANAGEMENT_REFRESH.md)，
从该合格main新建feat/ui-agent-management-20261007。仅现有管理页呈现、typed双语、
必要回归和不请求Pair/output的合成metadata图；Agent/Provider/Login/Remote/Pairing/
WAW身份继续分域。先以真实App合成HTTP最小验证session原地替换与迟到Pair/output，
若RED先保存证据和独立小修卡，不能把不同hook实现直接称bug或自动扩权限。
当前只有合同/只读评估及59项既有基线PASS，repro进行中，尚无新实现/CI/像素资格。
本批后仍有Doctor/Logs/Settings/Login/NotFound五页与跨页收尾，见
[同一版本清单](RELEASE_ITERATION_PLAN.md)。版本仍rc31，无真实账号/凭据/host操作。
下方旧pending为当时快照，live Git/GitHub优先。


## 2026-10-07 Workspace闭环，Changes呈现候选（09:51 UTC）

[PR156](https://github.com/ForceMind/agentbox/pull/156)已正常合并为main
`5ca2f1d348e03796c317d9c7c66f2582f240490f`，tree
`58679a774e6dfc8786a796091dcac33f330ae711`与合格头01af67相同。
六套exact-main首轮成功，23success/3规定skip；Backend实际3.11.16/3.12.14/
3.13.16各5375/88，Frontend1771+6，E2E344/94，无failed/flaky。独立source、
exact Stop所有权、42/42新原图与官方main日志审查CLEAR。head实际3.13.15成功
另记；旧READY间歇问题仍开放，未称根因修复。正常Stop修正保留单独RED/fix提交。

同一UI版本继续[Changes呈现合同](../WORKBENCH_UI_CHANGES_REFRESH.md)，从该
合格main新建feat/ui-changes-reader-20261007。仅现有路径树/staged reader的布局、
typed双语文案与必要回归；A3读取/权限/owner/TTL/取消/预算不变，新截图只采合成
metadata/unavailable，既有授权synthetic patch证据边界保留。
[Draft PR157](https://github.com/ForceMind/agentbox/pull/157)已保存产品与回归，独立source
审查CLEAR；1800 Web+6 extension、全lint/typecheck/format/build、768 doc links通过。
首轮两个App测试旧语言期望与新spec folder标点已明确修正，原失败保留；非产品bug。
新spec计划42metadata PNG，静态70注册（49执行/21规定skip），既有native再增双端
英文DOM/geometry2项；实际浏览器、新exact-head六套与像素资格仍待，保持Draft。
剩余既有页面集中列于
[逐版本计划](RELEASE_ITERATION_PLAN.md)，不增加功能、不改版本、不发布/部署。
下方旧pending/Draft均为当时快照，live Git/GitHub优先。


## 2026-10-07 Workspace呈现迁移与exact Stop所有权（08:33 UTC）

[PR153](https://github.com/ForceMind/agentbox/pull/153)已正常合并为main
`0fdeb6475487d8a2456dfcc7b04262562a8c27ac`，tree
`f3e65bf12c0846d70b5dc9d1a6cb507c719f0f8e`。六套exact-main首轮成功，23success/
3规定skip；Backend实际3.11.16/3.12.14/3.13.16各5375/88，E2E299/73，无failed/
flaky。同树f06头实际3.13.15成功另记，旧READY间歇问题仍开放，未宣称根因修复。

接续原A2同一UI版本的[Workspace外壳合同](../WORKBENCH_UI_WORKSPACE_REFRESH.md)，
[Draft PR156](https://github.com/ForceMind/agentbox/pull/156)已保存页面、CSS、
双语catalog、105项页面测试和合成App/API浏览器候选；计划42PNG、静态收集66项。
原route/model、terminal refs/metrics/ANSI、input/currentness/Detach proof与后端不改。

新增最小回归确证旧confirmStop同task重复会abort第一请求：只1POST但旧target/
pending清空。RED head2267ed3已保存，官方Frontend1failed/1760passed。后继修复
单独提交，同步绑定exact confirmation与当前scope的owner，原RED逐字转GREEN；
旧scope finally、失败后显式重试、取消/身份/离线撤销及attached proof边界均有
回归，独立193项通过与source CLEAR。没有新增业务能力、安全权限、时限放宽、
自动重放或Runtime修改；这不涉及历史READY成因。

当前候选仍待完整本地检查、实际浏览器/原PNG、exact-head六套与正常merge/main
回读；不能把基线或focused结果当作本批资格。保持Draft，不部署、发布、接触真实
账号或激活host。下方旧段落为当时快照，live Git/GitHub优先。

## 2026-10-07 分进程发布覆盖合格，接续本批UI（07:13 UTC）

[PR155](https://github.com/ForceMind/agentbox/pull/155)已正常合并为main
`7ab227a378873f6d79d77c59db2228f7e047eb65`，tree
`560633fd9b465cd13e83e5c1f641f8146486f79f`，与合格head f04b813逐字相同。
该exact-main六套workflow首轮终态成功，26checks=23success+3规定skip；Backend
实际3.11.17/3.12.14/3.13.15各5375 passed/88 skipped，E2E256 passed/50规定skip、
无failed/flaky。新增process15、原transport69、guard-budget1、新pure49均实际通过，
独立source、coverage和官方main日志复审通过。

新增覆盖复用既有exec API/Runtime fixture，仅默认关闭的有界scalar见证与新process
场景；精确CHECKED/LIVE_REPLY/ACK、COMPLETE和后台currentness均观察真实调用。
原direct test及8ms companion逐字保留，production与exact250ms未动。旧main1ce
的3.13.15 READY23/24失败仍保留为开放availability/qualification问题；本批不是
根因修复，不将GIL假设或.16通过改称.15问题已解决，不替换旧断言或盲重跑。

[UI PR153](https://github.com/ForceMind/agentbox/pull/153)已审head
`621402c21ef874961ef092a4aa2579ac71ae2012`此前六套首轮通过，Backend实际3.13.16，
E2E299 passed/73规定skip。126张真实PNG（70新UI）校验后实际复查21张，四张展示
图已交付；这些是该旧头的证据。本次正常merge-forward main7ab，保留621和7ab
两条历史，Web与workflow逐字保持621，新增五文件逐字来自合格main，仅另更新
本批记录与三个项目快照。实际新UI head的六套、原PNG与最终main回读仍须取得。

处置已明确：原READY历史问题持续开放，新增分进程覆盖作为补充软件证据；
按既定feature→CI→merge→exact read-back继续同一UI版本，不另起诊断框架或负载
调参。不新增本批以外页面/功能，不改变版本、发布、部署或真实host/Secret边界。
详见[UI记录](../WORKBENCH_UI_PROJECT_DETAIL_REFRESH.md)与
[分进程覆盖合同](../WORKBENCH_A3_PROCESS_PUBLICATION_COVERAGE.md)。下方为历史快照。

## 2026-10-07 Project详情UI接续peer-proof合格修正（05:30 UTC）

main已正常合并[PR154](https://github.com/ForceMind/agentbox/pull/154)为
`1ce060f57afde6f7369e815a969aeb03eab2b012`，tree
`4d26fe53de38c96aa39732a9fcc020d9c96bdf8c`，与六套首轮成功的head22043ceb精确一致。
18项真实native回归先确认重复成本RED，再以不变测试GREEN；GREEN实际
3.11.16/3.12.15/3.13.15各5325 passed/88 skipped，其中3.13.15与18项RED同patch。
E2E256 passed/50 prescribed skip，26 checks=24 success+2 prescribed skip。
post-main六套正在执行，当前不称其通过；旧READY间歇根因仍独立开放。

[UI PR153](https://github.com/ForceMind/agentbox/pull/153)原b07ba66的E2E299 passed/
73 prescribed skip、70张新图已校验交付，Project错误卡片、键盘focus和Refresh
图标修正经实际像素复查；该头Backend3.13.15原READY23/24失败保留，未合并。
当前从b07正常merge-forward main1ce，保留两条历史；Web产品/测试/工作流逐字保持
UI已审版本，接入的core两行、18项回归与合同逐字来自已合格PR154。

下一步验证实际整合头的本地适用检查、独立移植审查、六套终态及全新截图；同时
完成main1ce回读。仅两者资格完整后正常Ready/merge并验证最终main。当前不是
完整UI版本收官，不新增页面/能力、release、部署或host激活；PR149/151保持冻结。
详见[本批记录](../WORKBENCH_UI_PROJECT_DETAIL_REFRESH.md)与
[peer-proof合同](../WORKBENCH_A3_PEER_PROOF_DEDUP.md)。下方旧状态均保留为当时快照。

## 2026-10-07 Project 详情与待处理 UI 候选（03:15 UTC）

live main 已核对为 `9f2721ed6dc9c5e6ac41c162463f29674004ad12`，tree
`fc152423899fcc9b313c269b45022a1ed425e98d`。PR148 UI 首批、PR152 最终接受时限
修正均已正常合并；exact-main 六套 workflow 成功，23 checks success / 3 prescribed
skipped，E2E256 passed / 50 prescribed skipped。main Backend 实际3.13.16；同树
PR152 head 的真实 RED→GREEN 实际3.13.15，不把版本变化称为旧 READY 根因修复。
PR150 代码经 PR148 合入，后已关闭为 incorporated，未宣称单独 merged。

本次继续同一已批准 UI 版本的[Project 详情与待处理](../WORKBENCH_UI_PROJECT_DETAIL_REFRESH.md)，
不另开功能路线图或发布。仅迁移既有功能，补齐 Project/adminSession 所有权、
草稿与晚到响应隔离、Cancel/Escape/Back/Forward、离线与隐藏恢复。独立 hooks
73项、页面及 Labels 39项回归通过；三项已复现 Job readback/poll 问题已修并复审
CLEAR。最终全量本地 test/lint/typecheck/format/build/audit 与边界检查通过；
Draft PR、新 exact-head 六套 CI 和真实截图审查仍待完成。

候选从上述 main 新建 feature branch；合格后依既定 feature → CI → merge →
exact read-back 接续。无 API/Runtime/A3/Secret/权限/pin/预算变更，无真实账号、host
激活、release 或部署。原 READY23/24 间歇问题仍独立开放，PR149/151 保持冻结；
下方旧 main、未合并、等待 GREEN 和“不 merge”文字均为当时历史快照。

## 2026-10-06 PR148 UI 候选质量回归快照（13:07 UTC）

[Draft PR148](https://github.com/ForceMind/agentbox/pull/148) 已交付共享外壳、
概览与项目导航候选；main仍为 `a586eaec27984e0632187048cc1b82e7e29552d1`。
已发布head `76612192ad1f2def8fdcd771856321a37b0a957f` 的Backend/Frontend/
Security/Deployment/Release Candidate五套通过；E2E252pass/2failed/2flaky/
50 prescribed skip，后继正在修测试的实际DOM导航等待并完善已截图发现的CSS。

审计补丁仅更新开发链tinypool2.1.2/source-map-js1.2.2，0high/critical，保留
2moderate；不降低门槛。44张真实合成图已下载校验，独立12图检查与主实施者
像素检查完成，具体失败、修正、测试与原始边界见
[交付记录](../WORKBENCH_UI_SHELL_REFRESH.md)。本节是指定时间快照，后继
exact-head与最终CI以PR148 live记录为准，不宣称本快照已全部通过。

本有界批次不merge/release/deploy；不改Runtime/A3/认证/Secret、文件读取权限
或真实host准入。既有完整能力计划继续有效，本批不另开路线图或审美等待门槛。


## 2026-10-06 UI 首批实施与 PR147 live 状态校正

GitHub live main 已是 `a586eaec27984e0632187048cc1b82e7e29552d1`，
PR147 已合并，exact-main 六套 workflow success（23 checks success / 3 prescribed
skipped）。下方 PR147 Draft/pending/失败文字保留为历史，不覆盖此结果。

Owner 要求完整 UI 重设计并授权正常开发自主继续；当前有限批次为
[共享 shell、工作概览与项目导航](../WORKBENCH_UI_SHELL_REFRESH.md)。
沿用原批准计划，仅重新呈现已存在功能；暖白/墨色/琥珀为可回退实施假设，
不是宣称 Owner 已认可品牌。首个 shell head `e3628a257dbb92ed8419676618fbf0f8e703989f`
已发布回读，页面迁移与1583 Web/6 extension/17 API本地测试通过；
真实浏览器受本地启动限制，等待新 exact-head 六套 CI 与截图。Draft PR 交付，
此批不 merge/release/deploy，不改变 Runtime/A3/认证/Secret 或真实 host 门禁。



## 2026-10-05 工作概览浏览器/像素通过；native3.13 CI 关闭原因诊断

[PR #147](https://github.com/ForceMind/agentbox/pull/147) 保持 Draft，main仍为
`a1cab129f18ede5b982b6ab53d037c51771b4dea`。当前已推 head
`09e3142b145e30d60c9342f2100d6c80682824be` / tree
`806123f6fdd11d4ced2b5e4f542eed9a0573e194` 的 Frontend、Security、Deployment、
Release Candidate、E2E 五套成功。[实际 E2E](https://github.com/ForceMind/agentbox/actions/runs/37350114064)
232 passed/30 prescribed skipped/0 failed/0 flaky（含8项新概览正式App/API
桌面手机双语言、既有64项native；232中16项仍为pureNode）。6张概览原PNG
实际打开且独立功能像素PASS，artifact11363160449 ZIP摘要
`7398c39a542659861914df6f1fcae9c9f250c2544dee08ceed4cdba5aa9c058c`。
这不是对整体美观的认可；新的全量UI设计另线讨论，本卡不加布局/功能。

两轮 Backend 都仅Python3.13在未改动的 native READY测试遇到PATCH_REVOKED；
3.11/3.12与native job通过。历史原因未知；受控300ms CURRENT_REPLY延迟
能复现250ms fail-closed表象，但不是原CI因果证明。本地3.13.5原序前缀受
AF_UNIX平台阻碍，不能替代CI3.13.15。没有改产品预算/断言或重跑旧头。
本候选仅为该测试加入显式opt-in、最多4条固定phase/reason及封顶计数的
failure-only诊断，并保留原异常；不记录正文/凭据/路径，不称为修复。
新增诊断安全测试后3.12/3.13.5各69项通过，完整新head CI仍待采证。
详见[有界合同与失败记录](../WORKBENCH_WORK_OVERVIEW.md)。

尚未Ready/merge，主干与生产均未改动；无生产key/pin、host/账号或发布。
下方pending/失败均保留为当时快照，不能覆盖本节较新的实际结果。

## 2026-10-05 A2 / WEV-2 工作概览候选

当前独立 branch `codex/a2-work-overview-20261005` 从已闭环 main
`a1cab129f18ede5b982b6ab53d037c51771b4dea` / tree
`26f245acde25737aa9c8ef47e408ad9c56a8006a` 接续原计划。
[有界工作概览合同](../WORKBENCH_WORK_OVERVIEW.md) 已冻结：Dashboard
优先显示当前 user 最近100条 Job 的待处理/排队/运行中窗口与最近6个 Project
元数据；计数明确有界，项目时间仅表示真实 updated_at。复用已有认证与目录
权限，不调用 Runtime/reconcile、Git status 或文件正文。失效快照清除，
loading/empty/error/permission/stale 分开；原健康与就绪入口保留。

七文件 #145/#146 闭环快照修正在 exact base 校验后随本批应用，原失败保留。
本候选 source/tests/translations/docs 同批；版本同步 rc31，不发布 tag/Release。
完整新 head 六套 CI、正式 App 桌面手机截图与独立像素、正常 merge 和 main
六套仍待完成，不借旧 CI 宣称本卡通过。完成此卡后停止，只给 Files 下一卡；
WS08 split 属最终范围但不是本卡，不称 A2/S02 整体完成。
无生产 key/pin、真实 host/账号、安装激活、release/deploy。


## 2026-10-05 #145 / #146 已闭环：统一视图与主干质量复核通过

#145 已交付正式 Changes 页有界统一diff（hunk、旧/新补丁坐标、增删文本、
完整原文fallback、键盘与手机wrap）。最终feature head
`63da1b1539ed68186b249e905e8b14c568ce1673` 六套首次CI与独立六图pixel
PASS；首轮巨大留白的失败证据保留，最终滚动区域定位修正已验。

#145 merge `c93ed22a57b2667d8f6b13fdb3fd3720001e72f2` 的旧rc7 lifecycle
单测导致Frontend失败，其余五套通过。后继test-only #146 不改产品5ms预算、
测试timeout、断言或UI；历史成因仍为强支持推断，原失败未抹除。最终head
`1c4d5c30d62531eebb219e1afea82a11059175bb` 六套首次workflow全SUCCESS。

#146 于2026-10-05T16:21:56Z正常合并。最新main
`a1cab129f18ede5b982b6ab53d037c51771b4dea`，parents为上述c93ed22与
1c4d5c3；tree `26f245acde25737aa9c8ef47e408ad9c56a8006a` 与head完全一致。
新exact-main六套首次workflow均SUCCESS（23成功/3预期skip）：
[Frontend](https://github.com/ForceMind/agentbox/actions/runs/37340266309)
1554 Web+6 extension、原rc7三项110ms通过；
[Backend](https://github.com/ForceMind/agentbox/actions/runs/37340266512)
三版本各5284 passed/88 skipped与14项native process；
[E2E](https://github.com/ForceMind/agentbox/actions/runs/37340266503)
224 passed/30 prescribed skipped/0failed/0flaky，包括64项formal native
桌面/手机，224还含16项pureNode检查。

main artifact11359310257 ZIP摘要已实际校验为
`818a8d6b7441f77a8aa6580f2dd65658975b411c28a29a3c56b93733ba746ba4`。
未声称重复main图像素审查：production UI/native fixture/E2E与已独立pixel-PASS
的63da1b1未改。最终feature图artifact11355935840摘要为
`73d1faf08c60a7b1e973a32c562801eab98b16e2a64d2fe888aa62f029347186`。

本有界卡到此停止，下一功能仅建议、未启动；不称整个S02/WS08完成。
默认未配置仍unavailable；无生产key/pin、host/installer激活、真实账号或发布。
下方所有pending与失败描述是当时快照，不覆盖本节最新闭环事实。


## 2026-10-05 #145 已合并；main Frontend 单测时钟修正候选

#145 最终 head `63da1b1539ed68186b249e905e8b14c568ce1673` 六套首次CI
和独立六图像素均PASS。main `c93ed22a57b2667d8f6b13fdb3fd3720001e72f2`
于15:40:24Z正常合并，parents/tree已显式核对，tree仍为
`44630157273d4eea963d5738ed930eb257b7847e`。长补丁巨大留白已修正。

exact-main五套workflow SUCCESS，但[Frontend](https://github.com/ForceMind/agentbox/actions/runs/37334720162)
失败：既有 rc7 lifecycle socket/backpressure 用例 timeout5000ms，加一个
PROTOCOL_INVALID unhandled rejection；1553 passed/1 failed。不能称main全绿。
当前独立 `codex/rc7-lifecycle-test-clock` 只固定该测试的performance elapsed clock，
沿用相邻协议单测的既定方式；产品5ms预算、测试timeout和全部断言不变。
[诊断与限定修正](../WORKBENCH_RC7_TEST_CLOCK.md) 保留同条件8ms暂停红绿；
真实CI无内部时钟数据，历史成因仍为有强支持的推断。待独立review、新head与
新main六套终态，禁止重跑旧失败取绿或借旧head过关。未新增功能/部署权限。


## 2026-10-05 PR #145 首轮 CI 全绿，长补丁纵向布局收尾

head `a49230f574c8b71394b20c1a102015ad3b61b9ec`、tree
`64ede3e2adae935fc5b6e7305e6f054c100b6125` 的六套首次 workflow 均
SUCCESS；[Backend](https://github.com/ForceMind/agentbox/actions/runs/37328655732)
三版本各5284 passed/88 skipped，14项真实 native process 通过；
[E2E](https://github.com/ForceMind/agentbox/actions/runs/37328655879) 为
224 passed/30 prescribed skipped/0 failed/0 flaky，包含64项正式 native
桌面/手机场景。224中16项仍是纯Node checks，不全称浏览器用例。

实际打开并独立复核全部6张 PNG 后，长内容主截图出现巨大页尾留白：desktop
1280×7427，phone1073×65772；两张 multiple-hunks 图正常。首轮 pixel verdict
为 FAIL，PR仍Draft且未合并。CSS 的 absolute 辅助标签缺少定位祖先与现象
一致；本候选仅为滚动区域添加 position:relative、给说明文字增加焦点框间距，
并补页面 scrollHeight 相对 reader 卡片底部的有界断言。现有横滚/键盘/生命周期
断言不放宽。原因推断与新图通过仍须由新 exact-head CI/像素结果验证。

首轮 artifact11353574147 ZIP SHA256 为
`b8b7523f33d6d49933f571ae7c5d399f9f65cc100470117932416da0a4a18980`；
旧图与失败事实保留。不得用首轮全绿替代修正候选、新图或 exact-main 资格。
下节初始候选的 pending 描述是当时快照；本批权限/生产/host/发布边界不变。


## 2026-10-05 S02 / WS08 统一 diff 视图软件候选

从已闭环 #144 的 main `3e313b36b7cfc7c1de1c54cc20164ae223fcd122`
（tree `d2fa9213b40db3a5f2b9236646da7fdc50c39645`）新建
`codex/s02-changes-unified-diff`。实际 fetch、open PR 与 exact-main 六套
SUCCESS 已复核；旧 worktree/历史不改写。本批先冻结
[有界统一 diff 合同](../WORKBENCH_CHANGES_UNIFIED_DIFF.md)，再实现正式
Changes 页的 hunk、旧/新行号、增删文本、统一/完整原文切换及默认换行。

只消费既有 completed owner 的完整 END 已验证文本；不新增 reader、网络、
预取、缓存、存储、复制/导出或权限。取消、刷新、route/hide/auth/trust/offline、
原始 expiry 等旧 fence 一并卸载模型。头部和坐标只是补丁声明，不生成源身份。
256 KiB / 4,000行 / 64 hunks / 单行8,192 UTF-16 units 是独立显示上限，
越界或未知/畸形/binary/metadata-only 输入整体显示完整原文，不截断；CRLF、
Unicode、EOF marker 均保留。原文不由 parsed model 重建。

独立 source review 发现的 `/dev/null` 一侧虚构 unchanged gap 已修正并加
真实 Git mutation 回归。focused Web 88项与 Git fixture 8项复核 PASS；
新增 native fixture 与原 fixture unit 合计33 passed。旧52项 native browser
保留，新增12项，当前列表共64项。实际 browser/桌面手机 PNG、新 exact-head
六套 CI、normal expected-head merge 和 exact-main 六套均尚待运行/核验；
不借用 #144 的证据宣称本候选通过。下节记录旧批次真实闭环，历史失败仍保留。

默认未配置仍 unavailable；未进行生产 key/pin、host listener/installer 激活、
真实账号、physical client/CLI、release/deploy。此卡只关闭可见统一视图增量，
不称 S02/WS08 整体完成，也不自动启动下一功能。


## 2026-10-05 PR #144 已闭环：正式 App native A3 与真实 CI 像素通过

最终 head `ec89d73c64ed6b5b87371d9a72209e79ccc36760` 六套首次 workflow 均
SUCCESS（24 jobs SUCCESS、2项历史 rc8 SKIPPED）；独立 source/doc 与实际
四张中文 desktop/phone PNG 像素复核 PASS。下方较早的 pending/失败叙述保留
为历史，不能继续作为当前状态。

PR [#144](https://github.com/ForceMind/agentbox/pull/144) 已于
2026-10-05T13:59:54Z 正常合并。main read-back 为
`3e313b36b7cfc7c1de1c54cc20164ae223fcd122`，parents 为
`61a5efce6ab43754a2acdb313d5e21ee83f64c52` 与上述 head；tree
`d2fa9213b40db3a5f2b9236646da7fdc50c39645` 与已验 head 完全一致。

exact-main 六套首次 workflow 均 SUCCESS（23 jobs SUCCESS、3 SKIPPED：push
的 dependency-review 与两项历史 rc8）。[Backend](https://github.com/ForceMind/agentbox/actions/runs/37321159493)
三版本各5276 passed/88 skipped，全部14项 native 通过；
[E2E](https://github.com/ForceMind/agentbox/actions/runs/37321159428) 为212 passed/
30 prescribed skipped/0 failed/0 flaky，包括新增52项正式 App native 场景。
212中有16项纯 Node cleanup/counter checks，不能全称浏览器测试。

最终 head artifact11349880911 ZIP SHA256 已核验为
`f41b7b4346bf32acf763153e1269cbfc2b33adb861560deb157370af99c8e723`；
四张原始 PNG 均已打开，固定导航置顶、phone 刷新单行、中文无缺字，完整验证
状态与 inert text/focus 清晰。完整24KiB与未执行性由 E2E 断言证明，截图仅呈现
可滚动区域。同 tree 的 main artifact11350222710 摘要亦已核验为
`0cd6b83f513096b1dd3826a6c068f09d2ebed401acdb246051203bdc88f263db`，
但未重复做 main 图像素审查。

这是 CI 跨进程软件闭环。默认未配置仍 unavailable；生产 key/pin enrollment、
installer/listener 激活、真实 host/physical client/CLI、账号或发布仍未执行。
后续只可按实际已批准计划进入独立下一批，不把更多 fixture/helper 数量当产品进展。

## 2026-10-05 PR #144 第七轮：六套 CI 首次全绿，像素收尾

head `f67b93dfa0678ee0f04ea187a91d9a8cddb35c07`，tree
`dc5a7665ab2e97c8ac5126bc9941a5922be27af0` 的 Security、Frontend、Backend、
Deployment、Release Candidate、E2E 六套首次 workflow 均 SUCCESS。
[Backend](https://github.com/ForceMind/agentbox/actions/runs/37315024413) 三版本各
5276 passed/88 skipped，14项真实 separate-process native 场景全通过。
[E2E](https://github.com/ForceMind/agentbox/actions/runs/37315024259) 为212 passed/
30 prescribed skipped/0 failed/0 flaky；新增52项正式 App desktop/phone native
场景全通过。212含16项纯 Node cleanup/counter 测试，不能全称浏览器测试。

该结果验证最小 guard 排序修正后的真实链；受控双 loop 同条件旧逻辑8ms三次
失败、新逻辑8/10ms三次通过的 red/green 证据仍保留。没有延长产品 deadline、
原始 selector expiry 或缓存正向授权，也未靠旧 head 重跑取绿。

artifact `11347219368` 的 ZIP SHA256 已核验为
`15b68f796cd93320a0459a218179a9a3709b47b215cc0fb221d9f6bf90a93fac`。
四张原始 PNG 已打开：中文、完整补丁与 inert text 清楚，页面无水平溢出；
full-page 截图却保留键盘聚焦后的滚动位置，使固定导航出现在图中部，且 phone
刷新按钮沿用旧页面的换行问题。当前仅修复按钮不换行、截图前回到顶部并断言
位置；最后候选仍需自己的六套 CI 与实际 PNG 复核，不提前记像素 PASS。

PR #144 仍 Draft；main 仍为 `61a5efce6ab43754a2acdb313d5e21ee83f64c52`。
通过最终像素复核后正常 Ready/merge，read-back parents/tree，再等 exact-main
六套 CI。下方六轮失败及本地环境限制全部保留。软件资格不包含生产 key/pin、
installer/listener 激活、真实 host/physical client/CLI 或发布。

## 2026-10-05 PR #144 第六轮 CI：guard 排程复现与最小去重候选

head `07bc1b673992024d3d08f831c56903f3a897f036`，tree
`f5b64d79209ea8df9aed85fd4941cdae111f6918` 的五套非 E2E workflow SUCCESS。
[Backend](https://github.com/ForceMind/agentbox/actions/runs/37308011282) 三版本各
5261 passed/88 skipped，native14全通过。[E2E](https://github.com/ForceMind/agentbox/actions/runs/37308011439)
为185 passed/30 prescribed skipped/27 failed。固定计数表明 READY、Git read、
nonce burn 已完成；多数失败还已发 INIT/CONFIRM/READ、消费3–6条 opaque records
并收到多次 fresh currentness reply，随后关闭。不是 bootstrap 未启动的旧问题。

两个独立 event loop 的受控 socketpair 复现已确认 guard 排程成本：24KiB读取
约500次CURRENT RPC；仅给各回复增加8ms时，LIVE在首PAGE阶段排队耗尽250ms；
9/10ms时更早失败。同一 event loop 测试会掩盖该排程问题。

经独立排序审查，当前只在两个产品文件去掉更早的重复检查：私有 wait 的就绪
结果仍由 syscall caller 做最后完整fresh guard；公开readable接口保留返回前
完整guard。serve wrapper依赖profile既有前后admitted.context复验，不再额外
先查一次。所有actual-write、idle、partial、after-decode、peer/expiry fences
及250ms/1s/原始TTL均不变，无缓存授权。相同8/10ms双loop复现现可到完整END；
最终本地A3合集428 passed，Ruff/Black403/mypy390、独立crypto/interop和
source review均PASS；新实际CI仍需完成，不能提前称本次E2E已修复。前六轮
失败保留。


## 2026-10-05 PR #144 第五轮 CI：完整主例通过，仍有失败与不稳定结果

诊断 head `e9bee683da60ebaceb5b2ee7a35e03b3bc315af3`，tree
`6192d162bc71978143c05becf4e00d5ed3861339` 的五套非 E2E workflow SUCCESS。
[Backend](https://github.com/ForceMind/agentbox/actions/runs/37304874938) 三版本仍为
5261 passed/88 skipped，全部14项 native 场景通过。

[E2E](https://github.com/ForceMind/agentbox/actions/runs/37304874934) 为205 passed/
30 prescribed skipped/2 failed/5 flaky。desktop/phone正常主例均已走完实际
Git→独立 API/Runtime→完整 END→DOM；但仅诊断变动不能称作修复。desktop
bootstrap rotation 的前置 patch 未出现、phone tampered-END 状态仍失败，另5项
需重试才通过；该 head 仍不具备合并或截图资格。8项新 counter runner 只是纯
Node 测试，不计作 browser 验收。

由于首个主例这次成功，首例专用诊断未输出。当前仅将原固定计数移到本 spec
的 unexpected-attempt afterEach，保持已有 schema、原错误、timeout 与 cleanup。
既有 bundle RLock 的真实数据库双线程对照还排除了裸 adapter 的重叠观察假设；
未据此修改产品。继续依据实际失败计数定位，不重跑旧 head 碰绿，不放宽断言。
前五轮失败与 flaky 事实保留；PR #144 仍 Draft。


## 2026-10-05 PR #144 第四轮 CI：真实 browser 已启动，读取尚未完成

head `5cc923d97334dcb6702d3e6020d18c39fa610a47`，tree
`27575e3408cd1d6c4ebcc58abed628c999b0fe9c` 的五套非 E2E workflow SUCCESS。
[Backend](https://github.com/ForceMind/agentbox/actions/runs/37300295937) 三个 Python
版本各5261 passed/88 skipped，全部14项 native separate-process 场景继续通过。
API import 配置修复已使真实数字 UID、HTTPS 与正式 App 浏览器流程启动。

[E2E](https://github.com/ForceMind/agentbox/actions/runs/37300295948) 为174 passed/
30 prescribed skipped/30 failed。新增52项通过22项（独立 bootstrap 拒绝与
binary/oversize/sensitive 状态）；其余30项共同依赖的正常读取未到完整 patch/END，
后续显示撤销前置条件因此未满足。正常内容与像素资格仍未通过，不能把22项
拒绝场景成功改称完整 reader 成功。

完整真实 WebCrypto/controller/native factory 的本地网络 stub 在递增时钟和
5/25/75/125ms 单 writer/ACK/heartbeat 排程下均完成 END；Runtime socketpair
交错 LIVE/publication 也通过。这些阴性复现不能替代实际 transport 证据。当前
仅添加失败时的固定有界帧/owner计数，定位真实链首个失败；不记录正文、context、
nonce、selector、key 或异常原文，不放宽 deadline/断言。诊断不是修复声明。
前四轮失败保留；PR #144 继续 Draft，真实完整读取与截图核验仍待完成。


## 2026-10-05 PR #144 第三轮 CI：native 全通过，隔离 API 初始化待修

head `33d34817f60931af8ad6ab637faac60864ded1a5`，tree
`2195b026d6dd2b596b207d2dce729f6856da69af` 的 Backend、Frontend、Security、
Deployment、Release Candidate 五套 SUCCESS。[Backend](https://github.com/ForceMind/agentbox/actions/runs/37297380826)
的 Python3.11/3.12/3.13 各5259 passed/88 skipped；三个版本均通过全部14项新增
真实 native separate-process 场景，包括完整 Git→END、revoke 与原始 expiry。

[E2E](https://github.com/ForceMind/agentbox/actions/runs/37297380712) 仍为152 passed/
30 prescribed skipped/52 failed；新增浏览器场景共同错误已缩小为 API child
初始化中的 `PermissionError`，尚未获得 browser 或像素资格。fixture 在自身
TEST配置之前导入 `agentbox_api.main`；该模块 import-time 的默认 app 会访问
checkout 的 development data 目录。修复只将 child 的已有 synthetic TEST 配置
提前绑定到其私有临时目录，不放宽 checkout/UID 权限或更改产品 main。

本 head 本地 A3 unit matrix411 passed；Ruff、Black402、mypy389、Web1480+6及
五门 PASS，独立 source review PASS。前三轮失败保留；当前 PR 仍 Draft，新的
exact-head 全部 CI 和真实中文 desktop/phone pixels 仍是退出条件。


## 2026-10-05 PR #144 第二轮 CI：12/14 native 用例通过

测试修复 head `2dd83b45be8cf18e76046c128b588ebe734352fe`，tree
`4af7f9d16753fc13e6695c530b8236b13f0e9782` 的六套 CI 均已终态：Security、
Frontend、Deployment、Release Candidate SUCCESS；Backend、E2E FAILURE。
[Backend](https://github.com/ForceMind/agentbox/actions/runs/37293090283) 三个 Python
版本各5223 passed/88 skipped/2 failed；新增14个 native 场景已通过12个，包括
实际独立 Runtime/API、Git staged patch、crypto v2 与完整 END。剩余两项属于
测试工具：revoke 写入 naive datetime 不符合 UTC6DateTime，及 test WebSocket
client 未处理服务器正常20秒 PING。修复采用既有 transaction_now，并在原有绝对
deadline 内严格处理有限 RFC6455 controls；不延长 selector expiry 或弱化断言。

[E2E](https://github.com/ForceMind/agentbox/actions/runs/37293090286) 为152 passed/
30 prescribed skipped/52 failed。152包含旧144项和8项纯 Node cleanup 回归，
不能当作新增 browser 通过。清理错误已修复，52项现暴露共同原始错误
`process-start:RuntimeError`；数字 UID child 启动原因仍需有界 probe 证实。
当前仅完善测试启动诊断和读取受限时的 fixture 自有只读源码副本，保留已修复
的 setup primary error。仅测试 start 控制等待改为45秒，容纳最多四次各5秒
的源码探针；未改变生产代码、UID 隔离、TLS/crypto 或产品 deadline。
截图上传仍 SKIPPED；真实 Chromium formal-route desktop/phone 与像素资格仍待
新 exact-head CI。PR #144 保持 Draft；前两轮失败均保留。


## 2026-10-05 PR #144 首轮 CI 与测试边界修复

首个 head `d05068d7c067e8a1a08eb64edcd413e6e2f315c7`，tree
`bbf9e1cdaa98339b35c55e2f7b811e1933c6e6ff`，已发布为 Draft
[#144](https://github.com/ForceMind/agentbox/pull/144)。Security、Frontend、Deployment、
Release Candidate 首轮 SUCCESS。Backend 三个 Python 版本各5193 passed/88 skipped/
11 failed；[Backend](https://github.com/ForceMind/agentbox/actions/runs/37288879743)
的11项新增完整读取均在 INIT 后等待 ATTEST 时 EOF。测试客户端错误使用裸
SHA256(selector)，遗漏协议既有 domain 前缀；Runtime 正确拒绝错 context。
修复仅调用正式 selector_commitment helper，并补完整握手/裸 hash 拒绝对照。

[E2E](https://github.com/ForceMind/agentbox/actions/runs/37288879748) 首轮144 passed/
30 prescribed skipped/52 failed；新增52个 formal-route desktop/phone场景都被
fixture 清理 numeric-UID/root-owned 临时目录的 EACCES 覆盖，原始 setup/test
错误不可见，不能推断那些场景已通过。截图上传 SKIPPED，仍无本候选像素资格。
修复仅在 CI supervisor 持有的目录描述符范围清理自己的临时子树，先确认 child
退出，再确认 cleanup；Node保留原始错误和独立 cleanup 失败，并只记录固定
stage/role/type。独立审查还要求 setup 中途失败时保留 partial child custody。

上述首轮失败保留；没有放宽 Runtime/crypto/UID/TLS/原始 expiry、超时或断言，
没有重跑旧 head 冒充修复。新候选仍须全量 exact-head CI、真实跨进程/browser/
权限及截图证据，之后才能按正常流程审阅合并。


## 2026-10-05 PR #143 已闭环；native A3 合同审查中

PR [#143](https://github.com/ForceMind/agentbox/pull/143) 已正常合并。
最终 head `ad9d199c3ca08661cfb8171e1a782060cc694534` 的六套 workflow
均 SUCCESS（24 jobs SUCCESS、2 项历史 rc8 SKIPPED）；main 显式 fetch/read-back
为 `61a5efce6ab43754a2acdb313d5e21ee83f64c52`，tree
`ec1ca86988ea4e84e7aa1d818e5d85a4b967cf08` 与 head 完全一致。
parents 为 `b7dd51d3288022f12604656515aafe7e11a00d3e` 和上述 head。

exact-main 六套首次 workflow 均 terminal SUCCESS（23 jobs SUCCESS、3 SKIPPED：
push 的 dependency-review 与两项历史 rc8）。[Backend](https://github.com/ForceMind/agentbox/actions/runs/37267834425)
三个 Python 版本各 5119 passed/88 skipped；[E2E](https://github.com/ForceMind/agentbox/actions/runs/37267834421)
144 passed/30 prescribed skipped，包括新增28个desktop/phone场景。
最终 head 已补齐 CJK 字体并完成实际截图复核；同 tree 的 main 截图 artifact 已核验
摘要，但没有重复进行像素复核。下方旧 CI 失败、teardown race 与缺字事实作为历史
保留，不能再将旧 head 的待补状态当作当前未完成门槛。

当前独立 branch `codex/a3-native-changes` 从该 main 接续
[A3 native transport 合同](../WORKBENCH_A3_NATIVE_TRANSPORT.md)：正式 App factory、
独立 A3 HTTPS bootstrap consumer、分离 API/Runtime 的 bounded metadata/opaque UDS。
合同已独立审查冻结，源代码已实现并完成独立 source review；跨进程 currentness、
最终 publication/END 与显示生命周期保持分层。新批次尚未运行 exact-head CI。
无生产 key loader/pin enrollment、installer 开关、真实 host listener/账号或发布。
未配置安装仍 unavailable；真实 host/physical client/CLI 验收仍 NOT RUN。

本候选本地 evidence：受影响 Python matrix 294 passed；Web 全量1480 tests 与
extension6 tests、lint/format/typecheck/build PASS，最后恢复文案20项回归 PASS。
独立 A3 crypto vector、codec/crypto/Changes interop 与 bridge isolation PASS。
新增14个 separate-process native tests 因此 executor 禁止 AF_UNIX 创建而 SKIPPED，
同一临时测试通过 sandbox escalation 后仍受限；CI 遇此限制必须 FAIL。新增52个
正式 App desktop/phone browser cases 仅 collect，实际浏览器/像素尚未运行。
全量本地 pytest 曾出现 UDS/host 限制，并因共享 /tmp ENOSPC 在约40%处异常终止，
exit1，不能记 PASS。空间恢复后使用 workspace TMPDIR 重跑受影响 matrix；旧全量
失败记录保留，新 exact-head 六套 CI、实际权限/UDS/browser pixels 仍是退出条件。


## 2026-10-04 DOM 已通过，CJK 截图资格待补

head `d0648eed7d14c5ae35ba6ca2df0e71f252b4171f` 的
[E2E](https://github.com/ForceMind/agentbox/actions/runs/37217280128) SUCCESS：
144 passed/30 prescribed skipped，包含全部28个新增desktop/phone场景，无本head重跑。
取消+刷新同步已在实际浏览器通过。artifact `11308473073` ZIP SHA256
`c59ab6ccc847bc4d762f721e004b2ba3185a7979d42d912763bc46ba5eb0fc76` 已下载核验。

实际像素复读发现CI runner缺少中文glyph：两个viewport的中文控件/说明呈方框。
DOM字符串断言与无overflow虽通过，仍不能称截图可读或完成视觉验收。仅为E2E
Ubuntu runner安装官方`fonts-noto-cjk`并以`fc-match`核对CJK fallback，再跑新head
全量CI与截图复读；不增加产品字体/framework依赖、不改UI/权限/crypto或放宽断言。
本地不安装/执行浏览器；前两次失败和本head DOM成功事实均保留。待可读截图和
新head全部checks终态后才能审阅merge，真实host/pin/production仍未开放。


## 2026-10-04 第二轮 CI 与 metadata teardown 同步

第二个head `aa811006bc347fd7c3e4a2e29d387e0fdeda9241` 的Backend/Frontend/
Security/Deployment/Release Candidate均SUCCESS；[E2E第二轮](https://github.com/ForceMind/agentbox/actions/runs/37216455336)
142 passed/30 prescribed skipped/2 failed。环境隔离修复已使新增26/28用例通过；仅
两个viewport的cancel+delayed-END用例出现`A3 fixture bridge closed`，含原retry均失败。
截图上传步骤因job失败SKIPPED，不能把生成的未回读图片当作已验收截图。

取消用例最后点击metadata刷新，却未等GET/Git结束即关闭fixture stdin；peer取消
未回复的metadata handler，Node child-exit拒绝pending route promise。独立逐行审查
确认该race，并在真实Node bridge/Python/Git无浏览器对照复现：不等metadata就close
返回同一bridge-closed错误，先await metadata再close则成功。CI是否完全闭合仍待新head。

本次只增强该用例：点击前注册精确metadata GET的waitForResponse，验证200/body
finished，再等success.txt行重新显示；保留原cancel、noPatch、selector observations=1
和原有timeouts，随后才teardown。没有产品、crypto、权限、bridge或Settings修改。
原两次失败history保留；新head仍须全量CI、desktop/phone全部用例及截图read-back。


## 2026-10-04 首轮 CI 与 fixture environment 修复

PR [#143](https://github.com/ForceMind/agentbox/pull/143) 首个 head
`892dbd87f8ab1bf14016c2581e42bb47f3cdbf3e`，tree
`4b950105e7709b68bb7bcc9e4720c6e7bc9f3193`，唯一parent为 `b7dd51d`。
Backend（三Python版本/native）、Frontend、Security、Deployment、Release Candidate
首轮均SUCCESS。[E2E 首轮](https://github.com/ForceMind/agentbox/actions/runs/37207300345)
FAILURE：既有116 passed/30 prescribed skipped，新增28个desktop/phone场景均因fixture
bridge启动失败而失败（含原配置retry），截图步骤SKIPPED，不能称浏览器验收通过。

现有Settings故意让environment优先于显式构造：fixture子进程继承外层E2E的
AGENTBOX_DATABASE_URL/data/root/Origin/secret，误接已初始化的共享测试DB，在ready
之前抛AdminAlreadyInitialized。独立重建环境也观察到AUTH_ORIGIN_INVALID。
仅在Node fixture child spawn时剥离AGENTBOX_*，使用既有临时DB/testOrigin/synthetic
构造输入；不改产品Settings优先级、Origin/session/crypto或timeout/断言。原staged/
readback worktrees保留，在独立ci-fix worktree顺序提交，不改写旧head。

actual Node bridge污染环境回归执行真实bridge（仅恢复临时transpile文件原dirname），
注入production/invalid DB/wrong root/Origin/synthetic key，确认isolated metadata和
真实ASGI bootstrap成功且未读patch；缺失fixture executable确认startup失败不暴露bridge。
此检查不启动浏览器。既有actual Git/API/opaque→WebController七场景继续PASS。
新head全部CI与desktop/phone截图仍须核验；不重跑旧失败head掩盖问题。真实host/key/
pin/production仍NOT RUN。下方首个候选本地记录保留，不替代本节CI状态。


## 2026-10-04 A3 Changes-page staged reader 软件候选

已显式 fetch/read-back 核对 #142 merge `b7dd51d3288022f12604656515aafe7e11a00d3e`，
tree `2cdfa72e7ca99b57312dadf156af1b74d82db15e`；#142 exact-head 六套
workflow 均 SUCCESS。旧 staged/readback worktrees 全保留，新独立
`feature/s02-changes-a3-reader` 接续 [Changes-page 软件合同](../WORKBENCH_A3_CHANGES_READER.md)。

本批加入独立 staged-observation metadata route、purpose-specific A3 trust port、
显式点击/完整 END 后 inert text 展示和 page-owned lifecycle。API 新边界仅用 typed
metadata port，不导入/执行 Runtime；生产 source 默认缺失且拒绝注入，正式页面无
A3 adapter/pin 时明确不可用。实际 Git→API route→existing admission→opaque relay→
Web DOM 将由 isolated fixture 与新 exact-head CI Chromium 验证；此刻浏览器尚未运行，
不称生产可用或真实 host PASS。
无新 listener、WAW trust fallback、真实 key/pin enrollment、安装激活或发布。

本地检查与独立 source review 已完成；新 exact-head CI、merge/read-back 尚未运行，
不能使用 #142 的 CI 替代本候选证据。后续为候选审阅、Draft PR 与新 CI。
下方旧批次边界保留为历史，不覆盖本合同已批准的 source-only 页面接线。


## 2026-10-04 A3 admission/lifetime software continuation

#141 已正常合并为 `1c2befb9be47c8f7181accd67965e4187fcf06cf`，tree
`9c79cb24a121ff7641e191547a10823df3e1caef`；exact-head/post-main 六套首次
CI 全 SUCCESS。当前独立批次为 [default-off admission 与 crypto v2 lifetime](../WORKBENCH_A3_ADMISSION_LIFETIME.md)：
复用现有 API session/READY 与 Runtime binding/lifecycle owner，专用 synthetic
key/opaque TEST wiring，以及原始 selector lifetime 的 authenticated remaining-ms
桥接。plaintext/context/AAD v1 不变，无生产 route/key/pin/host/UI 激活。
候选需完成源代码独立审查、全量适用检查和新 exact-head CI；下方为历史批次。


## 2026-10-04 独立 encrypted single-read 软件批次

从 verified #140 merge `57cb8cd` 继续已批准 S02；执行
[独立 A3 加密单次读取](../WORKBENCH_A3_ENCRYPTED_SINGLE_READ.md) 的完整
synthetic Git→同一 held view→all-capacity preflight→fresh NX→opaque relay→Web
verified bytes。先完整 source/security review、focused/full quality 与独立 crypto/
真实跨语言测试，再提交 exact manifest 供 parent candidate review；发布 Draft 后
核验新 exact-head 六套 CI，全终态成功再正常 merge/read-back。
production resolver/key/relay endpoints、UI、Files/unstaged、真实 host/device、
deploy/release 不在本批。下方 codec-only 为上批历史边界，不覆盖当前已批准软件范围。

## 2026-10-04 独立 A3 content schema/codecs（当前批次）

已显式 fetch/read-back 核对 #139 正常合并为
`587fe8eabf7e5d5e4d3a561091ec00c3e9f40881`，tree
`5fecc5a36e0367ee6c92b6caea405ec9ec592ceb`，parents 为
`35d25bdccbb9311a57fc06a0683f4f60bf50dd9c` 与
`744ac4719e072f072c4bc07d5c00b31fdc3f53ad`。#139 exact-head 六套
workflow SUCCESS（24 jobs SUCCESS、2 历史 rc8 SKIPPED）；post-main 六套
首次 attempt 全 SUCCESS（23 SUCCESS、push dependency-review 与两项 rc8 共
3 SKIPPED），没有失败重跑或 pending。证据保存在
[PR #139](https://github.com/ForceMind/agentbox/pull/139)。旧 selector worktrees
与原历史提交全部保留；本批从 exact main 新建独立
`codex/s02-content-channel-codecs`。

本批仅落实 [A3 schema/codecs 合同](../WORKBENCH_A3_CONTENT_CODECS.md)：
独立 version/domain 与 typed formal Project/binding/session/Runtime epoch/
selector commitment/staged side/request nonce；四类 canonical flat JSON
plaintext records、严格 bounded parser、全量分页预检、单次 transcript 顺序/
complete/hash/expiry/close 模型及 Python/Web exact-byte/negative/interop vectors。
完整 PAGE plaintext（含 JSON metadata）保持 ≤16 KiB、最多 16 页；256 KiB 是
reader ceiling，不是可传输保证。固定测试 metadata 下实际上限 191,504 bytes，
191,505 先报 PATCH_TOO_LARGE，不输出 partial success。

未实现 Noise handshake/AEAD、生产 admission/currentness resolver、全局 nonce
ledger、Runtime RPC/socket/API relay 或 public patch UI；没有生产入口调用这些
纯函数。caller-fed context/time 只是模型输入，不能证明 READY/active session
或生产 authorization；下一层仍须 trusted resolver、独立 pin、新 CipherStates、
计时/revocation/visibility fencing 与 crypto vectors。真实 host/device 仍 NOT RUN，
不因 codec PASS 宣称 encrypted transport working。

当前动作：完成本候选的 canonical 全量质量检查、codec/crypto/selector 回归与
只读独立审查后再发布 Draft PR；require 新 exact-head 全部 CI 终态，再正常
merge/read-back。#139 CI 不能代替本批 evidence。下一批是独立 crypto-profile/
admission composition 合同，不能跳过 key-confirmation/transport schema、生产
currentness/replay/deadline 所有权或将 WAW state 复用为内容通道。


## 2026-10-04 Runtime-only staged selectors（当前批次）

已通过显式 main fetch/read-back 核对 PR [#138](https://github.com/ForceMind/agentbox/pull/138)
正常合并为 `35d25bdccbb9311a57fc06a0683f4f60bf50dd9c`，tree
`e74ef60de8c60650008ecd49f049526627f13557`；parents 为
`7fa54c3f5e3ce7e96c3d2cb33828c759665d81d2` 与
`f2148148fde8b2056630f6ddf67d3db411678e14`。#117 已因保留历史而间接
MERGED（GitHub 记录 f214814）；其原 head `8ef72862514c27b01f5f52a532e0ac4e16f20775`
与本地原提交 `ea6d638` 均保留，未改写旧 branch/worktree。

#138 exact-head 六套 workflow 全成功；post-main 六套 workflow 的最新结果也均
SUCCESS。post-main Frontend 初次在既有 late-Stop-receipt case 出现 5000ms timeout
与 PROTOCOL_INVALID，同一 SHA 仅重跑失败 job 后成功；首轮失败仍保留，根因未
宣称修复，未修改断言或 timeout。post-main 最新 job 汇总为 23 SUCCESS/3 SKIPPED
（push 的 dependency-review 与两项历史 rc8）；skipped 不算 pass。

Owner 已要求持续完成计划。本批从上述 exact main 的独立 feature branch
`codex/s02-runtime-staged-selectors` 实施下一项 Runtime-only staged selector：
完整 sorted staged snapshot（含全部 path/mode/HEAD/index OID）、当前正式 Project
binding、Runtime epoch、可信 API session scope、entry index 与 staged side 绑定；
TTL 最多 30 秒，token 校验与实际 patch read 共用同一个 held observation。
保留 #138 全部 Git isolation、双观察、资源与 cleanup 边界。

可信 current-context resolver 暂未接入生产：必须由未来的 Runtime composition
提供当前 READY formal mapping、有效 session scope 和 epoch；本批 fixture 回调
不构成生产 admission。没有 Runtime RPC、encrypted content channel、API/Worker
plaintext、WAW frame、UI、Files/unstaged、provider 或真实 host 激活。v1 metadata
schema 与 strict clients 不变；真实 host/device 验收仍为 NOT RUN。

当前动作：闭合本批必要 negative/race/expiry/cancel/cleanup 测试和质量检查，
完成源代码审查后再发布 Draft PR；待新 exact-head CI 全部终态，按授权流程进行
后续正常交付。旧 reader/v1 的 CI 不能替代本批证据。下一项是单独审查的 encrypted
content admission/transport 合同及接线，不能从内部 selector 的完成推导其已开放。

## 2026-10-04 软件续建优先级（覆盖下方历史冻结）

Owner 在首装软件合并后明确表示暂时不做真实测试、继续开发，并要求列出
后续计划。本次按该最新指令暂缓真实 host/device/login/reboot/upgrade/rollback
验收，继续不依赖现场输入的软件工作；这些现场项目仍为 **NOT RUN**，不视为
通过、取消或已交付可用版本。此段覆盖下方“不得推进 #117/S02”及先完成现场
验收才可开发后续软件的历史顺序限制，不改变 Runtime/Secret/发布门禁。

已核对 `origin/main = 7fa54c3f5e3ce7e96c3d2cb33828c759665d81d2`，
PR #136/#137 已合并；不重做 first-install composition。当前唯一实现批次是
S02 的 [Runtime-only staged reader](../WORKBENCH_A3_STAGED_READER.md)：
复用 Draft [#117](https://github.com/ForceMind/agentbox/pull/117) 的
`8ef72862514c27b01f5f52a532e0ac4e16f20775`，在独立 reconciliation branch
保留两边历史，不改写旧分支/WIP。原 head 六套 workflow 为 terminal SUCCESS，
但与当前 main 有四份治理文档冲突，且没有 GitHub review submission/thread；
旧 CI 不能当作新 reconciliation head 的证据。

范围仅为 tracked regular staged add/modify/delete 的 bounded reader、必要
安全修复/测试与合同。selector、Runtime RPC、独立加密 content channel、
patch UI、Files 编辑和 provider 功能均不在本批。先闭合配置/对象 provenance、
helper/network 隔离、超时/取消与双观察，再核验新 exact-head CI；自查须如实
标注，不称独立审查。全部 S00–S14 仍按 [全量计划](FULL_CAPABILITY_DELIVERY_PLAN.md)
的依赖逐批推进，真实支持与发布分别依赖实际证据。


## 2026-10-04 continuation verification

The Owner resumed AgentBox development in the current session. PR #136 head
`d6ee8c7c9635e2b5ecd58f18048fa8c1aaa59474` has six terminal successful workflows
(24 successful jobs and two prescribed historical rc8 skips). PR #136 was normally merged after the Owner confirmed continuation and repository
operations. Main read-back is `7d0521556727d64c80d02d69aea7b9d9b06432af`,
with parents `769197ed9dda2873b0b066a073efb7319d0665c1` and
`d6ee8c7c9635e2b5ecd58f18048fa8c1aaa59474`. Its tree exactly matches the
verified PR head. Post-merge CI is pending at this snapshot; no target-host
operation or product qualification is claimed.

This documentation-only continuation reconciles the stale #135 roadmap/index
and historical target inputs with the implemented `setup-fresh-waw` sequence.
See [target inputs](R12_TARGET_RECORD.md) for the actual remaining qualification
requirements. Do not redo composition, open #117, or substitute more fixture
checks for real fresh-host/client/login/reboot/upgrade/rollback evidence.
Repository link checking and `git diff --check` pass; the existing six workflow
results validate d6ee8c7 only, not a later documentation commit.


## 2026-10-04 hand off PR #136

Owner has paused this development session and will continue with another AI.
Do not redesign the first-version route or repeat #131/#134/#135.

Durable `main` is
`769197ed9dda2873b0b066a073efb7319d0665c1` (PR #135 merge).
Continue Draft PR #136 / branch
`codex/r12-fresh-install-composition`.

The last code-only exact head before handoff is
`815adfcb60a72c7de48cdfcdc2007c338b7b03cd`; all six workflows reached
SUCCESS on that exact head. Handoff/documentation commits after it intentionally
advance the branch, so the first action for the next developer is:

1. read live PR #136 head and changed files;
2. require Backend, Frontend, Security, Deployment, E2E and Release Candidate
   to be terminal SUCCESS on that **new exact head**;
3. fix any real documentation/format/test regression without weakening
   installer recovery or Runtime/native isolation;
4. if exact-head remains clean, mark #136 ready if necessary, merge normally
   with exact-head protection, and read back `main`.

Do not reopen #133. Do not replace release-qualified enrollment with installer
vendor execution. Do not substitute the diagnostic simple-empty-HOME Codex
digest for the accepted native-auth digest
`76522c70a3df95fdd59bc4851200017bf42947a49d47e216c95bb0dea1579d9c`.

After #136 merge, the next substantive gate is **real first-install
qualification**, not another composition redesign. Use the same immutable
candidate artifact and exercise:

`setup-fresh-waw -> HTTPS entry -> administrator bootstrap -> real Claude login
and turn -> real Codex login and turn -> resize/detach/reconnect/exact Stop ->
PC/Android/iOS -> service reboot -> host reboot -> upgrade -> rollback`.

Record concrete evidence and failures. A green fixture/CI composition must not
be described as a completed real-host or physical-client qualification.
Only after these gates close should the candidate be frozen and published as
the first immutable deployable release. #117 and unrelated workstation
features remain out of scope.

## 2026-10-03 finish qualified enrollment and merge #135

The production native qualification is now proven. Fixed Codex 0.159.3 runs
through `agentbox-waw-pane-bootstrap --auth-probe` after the narrow AF_UNIX
local-IPC seccomp compatibility repair, while AF_INET and all network
connect/bind/listen/send/recv operations remain denied. The accepted
unauthenticated framed digest is
`76522c70a3df95fdd59bc4851200017bf42947a49d47e216c95bb0dea1579d9c`.

Current action is to inspect the final documentation-inclusive exact head of
Draft #135. All Backend, Frontend, Security, Deployment, E2E and Release
Candidate workflows must reach terminal SUCCESS. Fix real failures without
weakening the native isolation or substituting the simple empty-HOME digest.
Then exit Draft if necessary, merge normally with exact-head protection and
read back `main`.

After #135 merge, start a fresh feature branch from the new main and compose
the already-built first-install pieces into one recoverable sequence:

`deferred apply -> dependencies -> fixed vendors -> manifests/policies ->
qualified vendor enrollment -> activation -> setup-waw-web`.

The composed path must keep explicit plan/recover semantics and may not execute
a vendor CLI from the Root installer. After complete fresh-install composition,
continue real Claude/Codex login/input/output/resize/detach/reconnect/exact Stop,
PC/Android/iOS, service/host reboot, upgrade/rollback and immutable release.
Do not advance #117 or unrelated workstation features.

## 2026-10-02 Runtime-only vendor observation/enrollment

Live GitHub state is now `main` =
`3da84df5fcc8b5543405f651d1a78c21ea9a8376`; PR #131 is merged and must not
be repeated. Continue the same first deployable release.

The immediate narrow batch is branch
`codex/r12-vendor-observation-digest`. It fixes the confirmed Codex
unauthenticated digest mismatch by making the actual pinned-vendor observation
use the same length-framed `waw_vendor_probe_output_digest(stdout, stderr)`
contract as the production Runtime parser, with a regression that rejects raw
stdout+stderr concatenation semantics.

Current action: push/read back this exact branch head, open the PR, require the
normal exact-head CI contract, fix any real failures, merge normally and read
back main. Do not weaken the parser or replace framed output with a synthetic
digest.

After that merge, implement the actual Runtime-only observation/enrollment
composition: derive the fixed Claude/Codex versions and Codex unauthenticated
framed digest from qualified Runtime-owned observation rather than operator-
supplied synthetic values, then compose deferred fresh install -> fixed
dependencies/vendors -> manifests/keys/public observations -> enrollment ->
`setup-waw-web` -> actual HTTPS entry.

Only after the composed install is closed proceed to real Claude/Codex
login/input/output/resize/detach/reconnect/exact Stop on PC/Android/iOS,
service/host reboot, upgrade/rollback and immutable release publication.
Do not advance #117 or unrelated workstation features.

## 历史行动记录

## 2026-10-01 qualify deferred fresh install and compose prerequisites

PR #129 merged at 7761310; exact source afafe55 has 24 SUCCESS/two prescribed
SKIPPED and actual official native/signature/version/unauthenticated evidence.
Continue on codex/r12-first-install with uncommitted deferred apply/resume and
its staged intent test. 160 affected checks/Ruff/372-file mypy pass. The mode
discrepancy was proven to be sandbox setgid removal by isolated probes; unchanged
tests outside that restriction passed 119 cases. Commit this batch and inspect
exact-head Linux CI; no assertion/permission relaxation is needed.

Then finish fixed Web/runtime dependencies and derive version/auth registration
from actual isolated observations, compose deferred apply/vendor/manifest/
enrollment/setup into the download entry, and qualify the complete installed
CLI/browser/reboot/upgrade/rollback path. Goal and first-version scope unchanged.

## 2026-10-01 verify actual native vendors then close initial install sequencing

PR #128 merged at 4f849be; source 131aadb reached 24 SUCCESS/two prescribed
SKIPPED. Current vendor bootstrap pins Claude 2.1.286/Codex 0.159.3 official
downloads and publishes verified ELF files create-only. Local real downloads
passed SHA/ELF checks; 153 affected regressions/Ruff/372-file mypy pass. Codex's
287086056-byte binary requires a fixed-path/kind-only 384 MiB pin; other/default
limits and legacy 256 MiB Codex pins remain. Inspect actual Linux signature,
version and unauthenticated-output evidence plus exact-head CI before merging.

Next compose fresh-install defer-activation, fixed Web/runtime dependencies,
native vendor installation and actual version/auth observation into manifest/
enrollment/setup. Do not make the operator supply synthetic vendor versions or
digests. Then qualify maintenance and the full installed CLI/browser/recovery
path and publish the immutable artifact/install command. No unrelated features.

## 2026-10-01 finish setup qualification and initial-install prerequisites

PR #127 merged at 753e8be; exact source ba13d10 has 24 SUCCESS/two prescribed
SKIPPED. The setup-waw-web WIP is on codex/r12-web-setup and composes the enrolled
installation under one lock, with consent/preflight before certificate effects
and no Runtime restart on recovery. 42 affected regressions/Ruff/369-file mypy
passed; the setup cases passed again after ingress preflight. Inspect exact-head CI.

Next add the initial-install prerequisite sequence: fixed dependencies and
actual vendor distribution/enrollment, maintenance sandbox evidence, then the
version-pinned download/apply/setup entry. Keep the explicit actual PC/mobile
CLI/input/reconnect/exact Stop and reboot/upgrade/rollback gates. Do not describe
the enrolled-host setup command as the final self-install command.

## 2026-10-01 verify ACME/maintenance then compose the install entry

The current certificate batch adds fixed, explicitly consented ACME issuance,
private policy/storage, sealed TLS pair recovery, and a daily Root-only Web
maintenance service/timer. Bootstrap refresh supports automatic and operator-
managed TLS; certificate renewal never touches Runtime services or credentials.
40 local affected regressions/Ruff/367-file mypy pass. Inspect exact-head CI and
the actual distro Certbot parser check; generated certificates are not public
CA evidence and the maintenance service sandbox still needs Linux execution.

Next finish fixed dependency installation without adopting/stopping unrelated
services, exercise the actual maintenance unit, and compose one operator setup
sequence for PKI, publication, Origin and WAW/HTTPS activation. Then close real
vendor CLI, PC/mobile input/reconnect/Stop and install/reboot/upgrade/rollback
acceptance before publishing the artifact and self-install command. Keep the
same first-version target and source version; no unrelated features.

## 2026-10-01 verify fixed Web activation then automate certificate/setup

PR #126 merged at ebf06758b93423b7110539854e9d30dd80b4266f; source f72ea3a
has 24 SUCCESS/two prescribed SKIPPED, with GitHub/fetched origin/main read-back.
Continue on codex/r12-web-certificates. The merged batch
adds configure-waw-web/activate-waw-web: verified current overlay, fixed TLS
provenance/hostname/validity/key checks, offline atomic Origin/proxy configuration,
and HTTPS-only restart with WAW-started admission and fixed failure cleanup.
32 focused regressions/Ruff/365-file mypy pass. Actual native PID-1
DynamicUser/LoadCredential/TLS/write-denial passed, run 36862158050/job
110368738448. Public CA/user-host/client/CLI qualification remains separate.

Next compose explicit operator-approved automatic certificate issuance and
renewal, public bootstrap refresh before expiry, and the single installer
setup sequence. Retain the final PC/mobile real CLI/input/reconnect/exact Stop,
reboot and upgrade/rollback gates. No user SSH target or new feature is needed;
the operator supplies domain/certificate/ACME choices in the installer itself.

## 2026-10-01 qualify ingress then compose self-install activation

PR #125 merged at f2af937; source 4f86c4d reached terminal 24 SUCCESS/two
prescribed SKIPPED. Both GitHub and fetched origin/main were read back.
Publication lifecycle/CLI, independent nginx configuration and DynamicUser/
LoadCredential service are composed as software. Actual nginx TLS/static/API
routing passed all four installer matrix combinations, run 36859319313.
Local 43 affected regressions/Ruff/362-file mypy pass; local systemd/nginx
checks skipped. Continue on codex/r12-web-activation from merged origin/main.

Next compose fixed nginx dependency checks, certificate provisioning/renewal,
exact allowed Origin and trusted proxy configuration, and explicit service
activation with systemd credential/read-only path evidence. Do not add CAP_CHOWN
or use the API static route as the HTTPS profile entry. Then prove API/Worker
write denial, publication/rollback and actual PC/mobile CLI/reboot/recovery;
finish the self-install artifact and command. The first full deployable version
remains the sole iteration; no user-host activation or release is implied.

## 2026-10-01 publish Root-owned HTTPS entry and independent serving

e1055e0 reached terminal 24 SUCCESS/two prescribed SKIPPED and actual native
PID-1 complete_remote_stopped_observed=true evidence. Current distinct HTTPS
consumer/lease, explicit secure-document selector and twelve-field canonical
public encoder have 70 Web/17 backend focused regressions and static checks.
Inspect this batch's exact-head CI before relying on it.

Next implement the Root-only public bootstrap/static overlay transaction and
independent serving at the accepted HTTPS Origin, with immutable assets,
API/Worker write denial, exact proxy routing/CSP and source/build replacement
recovery. Do not inject bootstrap into an API-controlled HTML route or call
Web trust independent/native-equivalent. Then close actual browser/core CLI
and composed installer/reboot/upgrade/rollback evidence plus the final
self-install command. This is one full deployment version, not a new scope.

## 2026-10-01 verify complete Remote evidence then HTTPS Web bootstrap

537b02d reached terminal 24 SUCCESS/two prescribed SKIPPED. Current complete
UID observer and observed confidence are connected through Runtime conflict,
protocol/API and Web. 173 backend regressions/Ruff/356-file mypy and eleven
Web DOM/hook tests/typecheck pass; two mocked Chromium desktop/mobile render
checks pass. Inspect the actual native PID-1 observer result and exact-head CI.
Permission, namespace, PID or alternate-executable uncertainty stays UNKNOWN;
never use the old boolean negative as STOPPED. The vendor Remote implementation
itself is not qualified by synthetic/current-process observations.

Then implement ADR 0010's canonical root-owned HTTPS public bootstrap and
distinct Web trust provider, with independent static serving and exact Origin/
CSRF/CSP boundaries. Complete the PC/mobile core input/output/resize/detach/
reconnect/exact Stop path, then isolated composed installation and real CLI/
reboot/upgrade/rollback evidence. No scope expansion, extra product version or
production/readiness claim substitutes for the full first self-installable
version.

## 2026-10-01 verify activation then close Codex Remote and HTTPS Web

41280ce reached terminal 24 SUCCESS/two prescribed SKIPPED. Current fixed
activation composes offline/idle guards, enrolled public-fingerprint comparison,
Root-private recoverable journal, paired profiles, scoped drop-in and ordered
named socket/service start. 49 focused regressions/Ruff/354-file mypy pass.
Inspect its exact-head CI. Service-manager active status alone is not usable
graph or target qualification; retain actual install/CLI/reboot/rollback gates.

Next implement positive, complete and fresh Codex Remote evidence without
converting ordinary process absence into ABSENT. Then the accepted HTTPS Web
trust/bootstrap profile must provide PC/mobile input/output/resize/detach/
reconnect/exact Stop. Validate the composed installer/application on isolated
Linux before claiming a deployable artifact. Scope remains this single full
self-installable version; no unrelated capability expansion or user-host
activation/publication is implied.

## 2026-10-01 compose fixed offline activation

001c4bd currently has terminal 24 SUCCESS/two prescribed SKIPPED, actual
absence/full/partial cleanup Linux probe evidence, and a retained first-run
sanitizer/tmux DCS failure that passed on same-head retry without a code fix.
Current policy preparation adds only three fixed cross-pinned global policies
while profiles stay disabled; 24 regressions/Ruff/352-file mypy pass. Inspect
its exact-head CI before relying on the new candidate.

Next complete the fixed systemd drop-in, named socket and paired profile
activation transaction with offline/idle evidence and recoverable failure
states. Existing services/processes may not be silently killed or adopted.
Then close positive Codex Remote and the accepted HTTPS PC/mobile core flow.
No new workstation feature, product version, user-host activation or release
is authorized by these internal software checkpoints; the full self-install,
CLI, reboot and upgrade/rollback delivery objective remains open.

## 2026-10-01 verify absence/cleanup Linux evidence then fixed activation

Both stores now have explicit new-epoch CAS operations, composed into the
existing Runtime-only cleanup acknowledgement with interrupted-write retry.
ccf8bf5 reached terminal 24 SUCCESS/two prescribed SKIPPED. Current follow-up
adds distinct absence records and exact empty-generation removal/partial retry.
152 local regressions, Ruff and 351-file mypy pass. Inspect the actual native
PID-1 producer/cleanup probe and exact-head CI before relying on Linux evidence.
It exercises real removal/ENOENT, not a host reboot or cross-invocation CLI
recovery. Preserve all generation floors, binding/host provenance and
fail-closed multi-generation ambiguity; never kill/adopt unknown groups.

Then complete fixed installer activation, positive Codex Remote evidence and
the accepted HTTPS Web PC/mobile flow. The sole delivery target remains the
full self-installable browser/CLI version; these internal batches do not close
reboot/upgrade/rollback acceptance or constitute separate product versions.

## 2026-10-01 verify FD persistence then close epoch recovery

The fixed Runtime stores and actual FD-backed observation factory are wired
in _main, with exact systemd invocation identity, fixed private directories,
finite Workspace/workload policy values and guarded persisted empty evidence.
85 focused tests/351-file mypy/Ruff pass. Synchronize this same Draft/version
and inspect the native PID-1 factory/store read-back. Then close explicit
Runtime epoch/generation provenance transitions and abandoned cgroup cleanup;
existing floors currently reject changed epochs, so reboot readiness remains
unproven. Follow with fixed activation, positive Codex Remote and HTTPS client
core/recovery flow. Do not equate stores being wired with full recovery.

## 2026-10-01 bind fixed stores and real FD observations in production

Port forwarding is synchronized as e474466733d75bb78a08e4b3644b97d8f466b437.
Three Backend checks are confirmed live; inspect their terminal results before
relying on full exact-head evidence. Continue the actual fixed instances/factory
below; optional forwarding is deliberately not the completion condition.

The application/server now forwards existing durable ports into registry;
43 construction/cleanup regressions and 349-file mypy/Ruff pass. Synchronize
this ownership gap fix on the same Draft/version, then build the fixed Runtime-
owned storage instances and real cgroup observation factory in _main. Preserve
explicit epoch/provenance transitions and positive empty cleanup; do not label
optional-port forwarding alone as recovery-ready. Actual creator evidence is
already recorded at d313624; no unchanged native probe rerun is needed.

## 2026-10-01 compose durable recovery and fixed activation

Actual creation helpers passed native PID-1 cgroupfs in Deployment
36766671223/job 110062461054 (three proof booleans true, mount 418).
d313624 has terminal 24 SUCCESS/two prescribed SKIPPED. Do not rerun unchanged
checks. Next connect existing Runtime-only Workspace/cgroup stores and a real
FD-backed attestation factory through application/server/bootstrap/_main;
provide cleanup/restart evidence, then fixed policy/socket/profile activation.
Use the existing contracts and current version, preserving exact Stop,
controller limits, private-key boundaries and no generic shell/filesystem path.
Continue positive Codex Remote plus HTTPS PC/mobile workflow afterward.

## 2026-10-01 complete delegated lifecycle and activation

The new isolated Deployment PID-1 fixture directly executes actual creation
helpers under a transient DynamicUser Runtime service (existing unit refusal,
unique cleanup marker, explicit metadata fixture). Inspect its real cgroupfs
result before claiming the creation path is host-verified. Continue durable
ports/activation afterward; a passing probe does not satisfy whole CLI recovery.

Creation wiring is synchronized as 714473bf786c7eaa33084eaa53608153fd3b5d40.
Its five pending CI jobs are confirmed live. Revalidate exact-head results,
then proceed with actual helper evidence and the remaining lifecycle ports.

Manifest preparation fa2ae6e passed terminal CI (24 SUCCESS/two prescribed
skips). Current code wires scoped root/workload creation to the actual Runtime
resource/provider path, with owner/mount/domain/controller/limit guards and
101 focused passes/349-file mypy. Synchronize this batch and obtain actual
Linux helper evidence; ordinary directory fixtures do not prove cgroupfs.
Then compose durable cgroup/workspace attestation and cleanup/restart behavior,
and fixed installed policy/socket/profile activation. Missing attestation ports
in the production builder must not be treated as recovery-ready defaults.
Continue positive Codex Remote and HTTPS Web/client acceptance within the same
first version; do not publish a deployable claim from internal green checks.

## 2026-10-01 validate complete issuer then activate bounded resources

Complete issuer is synchronized as fa2ae6e3c25f1e22923bb7aa0401e392c67654cf.
Its five pending CI jobs are confirmed live. Revalidate this exact head and
inspect failures rather than restarting unchanged runs, then proceed below.

The key batch a417add has terminal 24 SUCCESS/two prescribed SKIPPED. Complete
manifest preparation is now wired to its fixed Runtime public pin via the
installer command, with strict installed-resource observations, all 13 records,
explicit prefix/link recovery, plan-without-writes and disabled profiles.
33 focused tests/348-file mypy/Ruff pass. Synchronize the same Draft/version,
inspect Linux packaging/Backend evidence, then implement delegated root/workload
allocation and verified policy/socket/profile activation. Keep vendor login,
positive Codex Remote state, HTTPS trust/client flow and real recovery acceptance
as required first-version work; never treat prepared manifests as usable release.

## 2026-10-01 connect Runtime public pin to complete manifest issuance

Key initialization software and formatting correction are synchronized as
a417addf315ed9f1caf037d4ab18af351ef6961c. Its five pending CI jobs are live;
finish exact-head revalidation without restarting unchanged runs. Then wire
the existing HostOperations public-pin result into the complete issuer.

591d86f passed terminal exact-head CI (24 SUCCESS/two prescribed SKIPPED).
Runtime-only fixed initial-key command and installer public-output consumer
are implemented in the current batch, with 92 regressions/346-file mypy.
Synchronize this software, inspect its Linux checks, then connect the command
to the root-owned full v2 manifest issuer using restart-safe physical root
identity and one immutable helper release. Do not output/read private key bytes
in Installer/API/Worker, silently rotate lost enrolled keys, or activate profiles
without complete verified resources. Delegated root/workload creation, positive
Codex Remote evidence, HTTPS Web and actual PC/mobile CLI/recovery flow remain
first-version work. No new product version or later functionality is authorized.

## 2026-10-01 issue installable resources using the restart-safe profile

d41974d passed the actual Linux FD check and complete Backend/native/install/
client jobs. Its Release audit found four virtualenv advisories; the current
minimal fix pins 21.7.13 and required python-discovery 1.6.0 with verified
official wheel hashes and three-Python dependency closure. Synchronize and
inspect its exact-head audit/artifact checks, then continue actual manifest
issuance/key initialization and activation below. These remain one unfinished
first-version delivery, not completed product increments.

3b00cb4's real scoped PID-1 probe passed twice, with equal physical identity
and equal/reused namespace/mount numbers. Backend failed the real FD test on
an existing mnt_id parser tab-offset bug, corrected in the current follow-up.
One existing wire fixture also failed; bounded numeric diagnostics are added
without relaxing its 5ms budget/assertions. Synchronize this correction and
inspect exact-head Linux results. Continue the issuer/key/delegation/client
work below once these direct startup checks are established.

The synchronized 530fdf5 startup correction passed all 24 checks/two prescribed
skips. Current uncommitted code fixes install-time namespace IDs and helper
current-symlink paths, as recorded in ADR 0011. Commit this correction on the
same Draft/version and inspect its real Linux FD/two-instance PID-1 evidence.
Then implement the complete root-owned manifest issuer and Runtime-only key
initialization, followed by delegated workspace allocation and profile/socket
activation. Do not publish hand-filled numeric namespace IDs, mixed helper
releases, plaintext key output, or enabled profiles without validated resources.
Positive Codex Remote evidence and HTTPS Web/client/core/recovery acceptance
remain required. Keep the four user-path delivery checklist open; no later
features, product-version bump or subagents are part of this continuation.

## 2026-09-30 finish installation resources for the fixed production entry

The production self-conflict correction is synchronized as 530fdf51d517da7245eb1cd253c5bb4368ec18f3;
finish its pending exact-head CI before relying on complete Linux evidence:
formal binding reads must permit the WAW start whose legacy probe they serve,
while managed_conflict_states continues to deny overlapping legacy admission.
Both AgentType integration start/Stop tests pass with explicit vendor fixtures.
This correction stays within the existing startup scope and product version.

The b966480 Release Candidate audit found three new urllib3 2.7.0 advisories.
The follow-up pins official 2.8.0 plus independently verified PyPI wheel hash,
without bypassing audit. Finish the resulting exact-head checks, then continue
the installer resources below; dependency repair is part of this same version.

The filesystem-v2 _main candidate now composes the existing application using
fixed identities/resources, fresh fail-closed conflict probes and signal cleanup.
Focused application and Runtime regressions pass; the previous exact head's
Backend failure is a confirmed Black mismatch corrected in this batch.
Continue on Draft #125 and the same product version. Verify this batch's CI,
then implement complete installer resource issuance/enrollment and delegated
workspace creation before profile activation. Resolve positive Codex Remote
STOPPED evidence rather than relabeling UNKNOWN as absence. Follow with the
accepted HTTPS Web bootstrap and actual PC/mobile core workflow. Current code
has not been activated on a real host and is not a deployable-version claim.
Preserve the four-path checklist in RELEASE_ITERATION_PLAN; no later features,
additional candidate versions or subagents are authorized by this continuation.

## 2026-09-30 direct scoped startup wiring

The real systemd 255 probe passed (36708294115 / 109863711328). Current
uncommitted Runtime wiring adds the versioned delegated-subtree-v1 policy,
fixed path, exact template pin, UID/GID and RO/RW mount verification, and the
enrollment-only drop-in. 135 focused cases / 339-file mypy / Ruff pass.
88d1e99's native incomplete-DCS exit test failed with 1::; the follow-up keeps
the expected exit/time bound and adds bounded numeric-only failure diagnostics.
Commit this wiring on the same Draft, inspect Linux failure evidence, and
continue complete manifest/enrollment/_main within the four user-path checklist.
Do not call internal slices complete versions or expand unrelated recovery,
abstractions, labels, navigation or the 70-item backlog.

## 2026-09-30 resume accepted Web / cgroup architecture A

Owner approved the recommended HTTPS Web profile and 255-compatible scoped
delegation (“按你说的做”). ADRs 0010/0011 are accepted for software work;
do not ask the same architecture questions again. Continue the same Draft,
version and complete deployment goal, with no subagents or later features.

First run scripts/probe-waw-delegation.py through the Deployment Ubuntu 24.04
root CI fixture. It must prove actual scoped RW/global RO, limits, own-PID
movement and cleanup under native PID 1. If it fails, use the exact error to
correct the selected design; never substitute a simulated pass or unrestricted
cgroup mount. After proof, version and implement the exact Runtime path/policy
contract, non-secret manifest generation and _main. Then implement the accepted
Web trust bootstrap and actual PC/mobile core flow. No deployable claim yet.

## 2026-09-30 await the concrete architecture choices

Exact head a091701 on Draft #125 has 24 SUCCESS / two prescribed SKIPPED,
no pending/failing check. Backend run 36701077638 is terminal successful;
there is no live CI task left to poll or rerun.

The same unresolved architecture dependency has persisted for three goal
turns: Owner must answer the already submitted ADR 0010 Web-trust question
and ADR 0011 server/cgroup choice. Do not treat elapsed time or automatic
continuation as approval. Full deployment is unfinished; keep the goal's
complete scope. Stop automatic goal work at this dependency, preserve all
source/branch/artifact evidence, and resume the same version after answers.
These two post-CI docs remain local WIP for the next code batch; no version,
merge or public release is made for a status-only checkpoint.

## 2026-09-30 cgroup deployment prerequisite

9dda54d exact-head CI is now terminal. Keep Draft #125 and the same version;
the full deployable flow remains incomplete. Current compatibility correction
rejects private/strict on systemd <257 instead of pretending the directive's
boolean-era introduction covers those modes. 54 cases passed (one local
systemd-analyze skip), mypy/Ruff pass. ADR 0011 is Proposed, with an explicit
Owner choice requested for 255-compatible scoped delegation versus a newer
private-namespace target. ADR 0010's Web trust question is still pending.

Preserve all code and original checkout WIP. Do not issue/activate a cgroup
manifest until the selected versioned namespace/path contract and actual
Runtime observations exist; do not replace independent client trust before
the Web decision. Non-secret independent work may continue where possible.

## 2026-09-30 next after 9dda54d deployment matrix

Draft #125 head 9dda54d has successful Deployment run 36697969316, including
the actual root native-helper build/retry and Runtime-owned epoch check.
Inspect the still-running Backend/Frontend/Release/E2E checks on this same
head, repair concrete failures, then continue actual manifest generation and
the production Runtime graph. This snapshot is post-commit local doc WIP;
carry it into the next code batch instead of restarting CI for a status-only
commit. Full browser trust decision and core-flow qualification remain open.

## 2026-09-30 explicit staged recovery and fixed epoch candidate

Current PR #125 follow-up adds resume-install/bootstrap --resume for fresh
pre-activation staging only, with same artifact/transaction and preserved
account/configuration evidence. It also fixes Runtime-owned epoch bootstrap
without weakening the generic root-parent writer. Old/unknown/migrated/
activated/preflight/account-creation/upgrade stages are not auto-resumed.
Those remaining recovery states remain in the full delivery objective.

03ca4ed completed CI but failed the Release sudo prohibition. Move the root
fixture into Deployment; keep that assertion and release dependencies intact.
Local 47 focused cases, 124 broader cases (3 Linux skips and one known Mac
permission case deselected), 337-file mypy, Ruff and boundaries pass.
Commit/push this repaired batch to the same Draft; inspect actual Linux
epoch/root build evidence before continuing manifest generation and _main.

## 2026-09-30 deployment Draft CI repair

Continue PR #125, keeping the same version and Draft state. First checkpoint
c05cc3d passed actual Linux/root helper build/retry but failed the source
boundary and later root-polluted configuration read. Current repairs relocate
fixed execution into HostOperations and isolate root CI data/config/bytecode.
Local boundary, 37 focused cases (two Linux skips), 336-file mypy and Ruff pass.
Push the repaired head and inspect its Linux CI. Do not rerun an unchanged
failed head or call a partial installer a deployable version.

## 2026-09-30 Deliver the Owner's self-deployed PC/mobile version

Use DEPLOYABLE_RELEASE_PLAN. Owner will run the final server installer
themselves; do not ask again for an SSH deployment target. Finish the
current codex/r12-deployable-runtime branch from main 19f8c51.
Fixed enrollment publication/plan/recovery and interpreter selection are
uncommitted software WIP, with 59 focused tests, two selection tests,
333-file mypy and Ruff passes. No deployment or full core-flow claim follows.

The pinned downloader is now local WIP: fixed version/digest, HTTPS-only fixed
repository source, bounded safe extraction, verify/plan before optional apply.
Downloader/interpreter/publication tests passed 39 cases with local fixtures;
no Linux install or published URL follows from this result.
Native helper generation is now wired before activation and recorded with an
exact source/binary ledger; installed-state and recovery/retention readers
validate it explicitly. Linux/root actual-build and failed-build retry tests
are added to CI; local 145 passes plus one existing Mac permission failure
and two Linux skips are not target evidence. Full mypy passed 336 files.
Next close explicit whole-installer staged recovery, then generate actual
trusted manifests and wire the single production _main graph.
Close the positive Codex Remote conflict-state source without
turning UNKNOWN into ABSENT. Owner selected PC/mobile browsers first; ADR 0010
is a concrete Proposed Web trust profile awaiting architecture authorization.
Preserve the existing managed gate until that decision and implementation.
No subagent was started.

The eventual version is fixed only when its deployable software/installation
scope is complete; do not bump rc numbers for these debugging checkpoints.

## 2026-09-30 Close rc30 protocol-check failure

`64f3e69` passed dependency audits and all other jobs, but the complete
Python 3.13 job failed the same KEY_ATTEST trace twice. Current work retains
the 5 ms CPU limit, preallocates immutable scalar rules, adds real-clock
KEY_ATTEST regression coverage and bounded test-only failure diagnostics.
537 focused Python 3.13 cases passed locally. Run the new head's Linux CI;
if it fails, use the numeric diagnostic to locate the cause rather than
rerunning unchanged failures. Only terminal successful required checks allow
normal Ready/merge/read-back. No target-qualified or usable RC is claimed.

## 2026-09-30 Finish current rc30 candidate

The `4e9c394` frontend audit exposed high-severity brace-expansion findings.
After the additional moderate recursion-complexity advisory, the final
same-version patch pins only 1.1.21/5.0.12, preserves the audit level,
passes frozen installation, audit, 1201 Web/6 MV3 tests and lint/types/build.
Run this new head's required CI; repair failures without relaxing assertions.
Then normal Ready/merge/read-back follows the current AGENTS.md authority.
Main-agent risk checks are self-review, not independent PASS. After this
rc30 batch, the same first-usable-RC objective still needs production `_main`,
installer enrollment publication, positive legacy Codex Remote state and
client/target qualification. No S02–S14 work is started.

## 2026-09-30 R12 rc30 vendor enrollment candidate

当前只推进 [首个可用单机 RC](RELEASE_ITERATION_PLAN.md) 的 R12 依赖。
Draft #122 已对齐 `origin/main`，此前 head `8d11561` 的 26 项 CI 已终态
（24 success、2 prescribed skips）。当前 rc30 后继批次新增 installer
可复用的严格数据编码与真实文件/父目录替换、cleanup 失败测试；163 项
定向测试及 Ruff/Black 通过，待新 head 的 exact-head CI。
根据当前 AGENTS.md Review Protocol 完成主智能体自查并准确标注；
修复发现、相关回归与新 head 的必需 CI 通过后，可按已授权流程正常合并。
旧文档的额外独立审查机械门槛与当前 AGENTS.md 不符，不再作为恢复前提。
原 C3-b WIP 保全；#117 与 WS14 后续功能不进入本版。随后才处理
production `_main`、installer writer 与 D/E/F，真实 host/Secret/CLI/
recovery 验收仍需具体输入和授权。以下记录为历史行动项。

## 2026-09-29 首个可用 RC 收口

Owner 要求按版本迭代，不再以 70 项全量清单驱动并行旁支。当前唯一产品
目标与退出条件见 [逐版本计划](RELEASE_ITERATION_PLAN.md)。
`origin/main = 3a23f350582287de6b00499b8d4daa5d69c52011` 是 rc29
软件候选；六类 post-main workflow completed/success，但 R12 真实
host/client/CLI/recovery 未验收，不能称完整可用版本。

下一项是取得 Draft #122 的独立 Architecture/Security/Test 结论，处理
R12-C3-b 原工作区 WIP，再完成 `_main`、D/E/F 软件与制品。#117 保持
Draft，WS14 新功能暂停；现场输入缺失时报告本版阻断，不转去扩大功能
范围。Host、Secret、付费调用、重启、生产及发行仍按具体授权执行。
以下旧行动项保留为历史记录，不再驱动新的 WS14 批次。

## 2026-09-29 WS14 Workspace label command choices

`origin/main` remains rc27 merge
`458e7a5c9a87d50ebd9a4cd1040e7a51b148929a` with six successful
post-main workflows. Security-critical R12 rc28 Draft #122 has 26
terminal head checks (24 success, two prescribed skips) but awaits an
independent Architecture/Security/Test review; #117 remains Draft for the
same separate review gate. Continue independent WS14 software on
`codex/workbench-command-labels`: query-only label choices for an exact
formal Workspace route, current-session metadata validation, existing
CAS/Origin/CSRF API, exact ACK and GET readback, local panel invalidation,
pending/hidden/conflict fences, localization, desktop/mobile validation,
version and exact-head CI, then normal merge/read-back. The rc28 action
below is historical; real host/Secret/production gates remain untouched.

## 2026-09-29 WS14 visible-client label refresh

PR #120 delivered rc26 as merge
`88d2db79dd3cf58cfe0093ee90963f1ecfd45d35` with exact parents
`cab33679ec91bc2e46384f24e9a8cd3e4e985fa9` and
`816920a3c301569b8cd64ef99e7532537804d111`; six post-main workflows
completed successfully. On `codex/workbench-label-live-refresh`, finish
rc27's bounded visible-client Project/Workspace label refresh, prove
external-change convergence and hidden/pending/read fences, update the
version and acceptance record, then run exact-head CI, normal merge and
read-back. Cross-host synchronization remains S08. #117 stays Draft until
its independent security-critical review; R12 real-host/Secret/production
gates remain separate. The rc26 action below is historical.

## 2026-09-29 WS14 Workspace labels

Finish rc26 on `codex/workbench-workspace-labels`: shared-catalog formal
Workspace assignments, explicit Project+Workspace delete-impact count,
current-session Web readback and localized states. Run migration/foreign-key,
CAS/concurrency, API auth/Origin/CSRF, full Web/build, desktop/mobile browser
and release-version checks. Update exact local evidence, push feature branch,
obtain terminal exact-head CI, then normal merge and exact main/PR/workflow
read-back. Keep #117 Draft until its independent security-critical review;
continue R12 host and Secret gates separately. The prior rc25 action below
is historical and no longer directs this branch.

## 2026-09-29 WS14 Project label manager Web UI

PR #118's exact head `b7a529dfe92fabd0b83486ee6082296c64713fc9`
passed 26 terminal checks. GitHub generated main merge
`36aa7294c4d9c8eaa3283281022e61cf8bbc4f69` with that head as second
parent, but PR #118 remains OPEN in the API and no post-main workflows are
listed. Preserve both facts; do not force push, fabricate a merged PR state
or close the PR merely to remove the inconsistency. On
`codex/workbench-project-labels-ui`, finish rc25 Project-page label
create/assign/edit/delete with current-session GET readback, exact server
ACK, confirmed delete count, localization, desktop/mobile browser evidence,
version and regression checks under
[Project labels](../WORKBENCH_PROJECT_LABELS.md). Run exact-head CI, normal
merge and read-back. Subsequent Workspace assignment and cross-host label
sync remain separate. Draft A3 PR #117 awaits independent security-critical
review; R12 `_main` and real-host/Secret/production gates remain open.

## Historical 2026-09-29 WS14 label catalog and formal Project assignments

PR #116 delivered rc23 command-center navigation as merge
`3e0069381a4d8f867e333191f298b4847256d751`; six post-main workflows
succeeded. Draft PR #117 passed exact-head CI but remains unmerged pending
independent security-critical review and separate A3 content gates. Continue
on `codex/workbench-project-labels`: finish rc24 additive migration,
per-admin immutable label catalog, ordered Project assignment CAS, atomic
rename/delete, strict authenticated Origin/CSRF/no-store API, Audit,
capacity/concurrency/upgrade/restart tests and source/version records under
[Project labels](../WORKBENCH_PROJECT_LABELS.md). Then run exact-head CI,
normal merge and read-back. The Web picker and Workspace assignment follow
on the same shared label identity; they are not implied by backend delivery.
R12 `_main` still needs target fixed inputs and positive legacy Codex Remote
state; real-host/Secret/production gates remain separate.

## Historical 2026-09-29 WS14 authenticated command center

PR #115 delivered the internal staged Git selection policy as merge
`885c623cf1114d23c5fdc13503f4a2a598985c5b`; all six post-main
workflows succeeded. On `codex/workbench-command-center`, finish the rc23
fixed page/formal Project navigation UI under
[Command center](../WORKBENCH_COMMAND_CENTER.md): current-session API read,
desktop/mobile dialog, keyboard/focus behavior, stale-session fences,
localized errors, version and browser evidence. Then run exact-head CI,
normal merge and read-back. Wider command actions remain bound to their own
future permissions and service contracts. Resume A3 object-store provenance
and descriptor-held staged extraction as the independent content track.
R12 `_main` still requires actual fixed inputs and a positive legacy Codex
Remote state source; real-host/Secret/production gates remain separate.

## Historical 2026-09-29 A3 staged selection policy

PR #114 delivered rc22 Project favorites UI and its six post-main workflows
completed successfully. On `codex/workbench-staged-read-policy`, finish the
Runtime-only staged path/index eligibility check and negative fixtures under
[A3 patch content contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md).
Run exact-head CI, normal merge and merge read-back. Next, prove object-store
provenance and a descriptor-held bounded staged extraction before any
selector or encrypted content route. R12 `_main` still requires actual fixed
inputs and a positive legacy Codex Remote state source; the production
profile must keep failing closed until that graph is complete.

## Historical 2026-09-29 WS14 Project favorites UI and native read-back

PR #113 merged as `8fb017f3e294c4a303547da729b007e9605ed9a0`
with exact parents; its post-main Backend native job first failed on an
incomplete tmux pane-death status, then a same-SHA failed-job rerun succeeded.
Validate the scoped transitional-state test repair on rc22's exact head.
On `codex/workbench-project-favorites-ui`, complete the rc22 favorite control
under [WS14 favorites](../WORKBENCH_PROJECT_FAVORITES.md): server revision
ACK, conflict/uncertain GET read-back without PUT replay, session/visibility
fencing, desktop/mobile screenshots, local tests and exact-head CI. Then
normal merge and read-back. Named labels and command center remain later
WS14 slices; A3 content and R12 real-host gates remain separate.

## Historical 2026-09-29 WS14 Project favorites

PR #112 merged as `01a0ecd5eb21f74fe8605913bffd0c98bf322165`
with exact parent read-back and six successful post-main workflows. On
`codex/workbench-project-favorites`, finish the rc21 additive per-admin
preference schema, transactional revision/CAS service and typed authenticated
GET/PUT API under the [favorites contract](../WORKBENCH_PROJECT_FAVORITES.md).
The API must never call Runtime. Verify migration, concurrent writes, stale
conflicts, auth/CSRF/Origin and restart before exact-head CI and normal merge.
The Web toggle/pending/conflict flow, labels, ordering and command center
remain separate WS14 slices.

## Historical 2026-09-29 S02/WS14 Project search

PR #111 merged as `2d64ccde14877118f13f9c843d0c0aae0808dce0` with
exact parent read-back and six successful post-main workflows. Continue on
`codex/workbench-project-search`: verify the pure ranked matcher and the
authenticated Projects page against loaded formal Project data, nonmatching
and failed/loading states, desktop/mobile layout and visible rc20 version.
Retain the pinned source and attribution in
[Project search](../WORKBENCH_PROJECT_SEARCH.md), then run exact-head CI,
normal merge and read-back. Search remains read-only page state; favorites,
sync and the command center need separate contracts. A3 Git object provenance
and R12 `_main` are still unfinished, with real-host/Secret/production gates
separate.

## Historical 2026-09-29 S02/A3 descriptor-bound Git cwd

PR #110 merged as `6cd045dd8831283e2c0d0333a39461671b04bf76` with
exact parent read-back and six successful post-main workflows. Continue on
`codex/workbench-git-fd-cwd-v2`: verify the Linux-only fixed process runner
cwd descriptor inheritance and name-swap fail-closed behavior, then run
exact-head CI, normal merge and read-back. No Runtime action, API route or
patch bytes are added. The [cwd proof](../WORKBENCH_A3_GIT_CWD.md) and
[A3 patch contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md) retain object
store and index provenance, sensitivity and encrypted content as future
gates. The Owner's broad shell/file/plugin/Hub choice remains unanswered.

## Historical 2026-09-29 S02 Project work tabs

PR #109 merged as `1e3f463c5aafcc9ffdd266a94cfe35bfdca46c0a`
with exact parent read-back and six successful post-main workflows. Continue
on `codex/workbench-project-tabs`: finish bounded Project/Changed Paths/
Workspace navigation tabs with actual desktop/mobile rendering, route and
session fencing, and no implicit Runtime lifecycle operation. Record fixed
upstream source and legal attribution in
[Project work tabs](../WORKBENCH_PROJECT_TABS.md). Then run local regression,
exact-head Linux CI, normal merge and read-back. WS02 multiple conversations
and split panes remain separate. A3 patch content still needs complete Git
object provenance and child-cwd proof before extraction; broad permissions
await the Owner's semantic choice.

## Historical 2026-09-29 S02/A3 descriptor-held Git foundation

PR #108 merged as `692f58a5823c4a8fbb438e61f6575fc88150753f`
with exact parent read-back and six successful post-main workflows. On
`codex/workbench-git-content-root`, finish the internal rc17 Project/Git
descriptor custody and negative tests, then exact-head Linux CI, normal
merge and read-back. This source increment must expose no file bytes, Git
patch action, API route, browser selector or general filesystem gateway.
Afterward, prove complete object-store and child-cwd provenance before the
staged-only patch reader. The [A3 patch contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md)
keeps encrypted delivery, unstaged content and real-host qualification as
separate steps. Broad shell/file/plugin/Hub authority still awaits the
Owner's semantic choice.

## Historical 2026-09-29 S02/A3 patch content boundary

PR #107 merged as `87c0913f86324588608b191a8318115b36a59fbc` with
exact parent read-back and all six post-main workflows successful. Continue
on `codex/workbench-patch-contract` from that merge. Freeze the bounded,
sensitivity-aware Runtime Git patch reader and separate encrypted content
admission in [A3 patch content contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md),
then establish descriptor-held Project/repository and Git store/index
provenance before the staged-only Runtime extraction slice. No browser
content route precedes those proofs. Require fixed Git argv, current
Project/snapshot validation, bounded bytes/lines, helper-execution negatives
and explicit unsupported states. Unstaged content additionally needs
descriptor-bound working-file acquisition.
Document-only changes keep rc16; source behavior changes receive the next
aligned release candidate. Ordinary shell, arbitrary file browsing and
plugin/Hub authority still await the Owner's semantic choice. R12 `_main`
and real host/Secret/production gates remain separate.

## Historical 2026-09-29 S02 Changed Paths page

PR #106 merged as `c285872546f81c173c3e40e1711e8506c164cebc` with
exact parent read-back and six successful post-main workflows. Continue on
`codex/workbench-changes-tree`: connect its authenticated rc15 Project API
to a read-only AgentBox Changed Paths page. The candidate uses the migrated
folder ordering without fabricated line stats, presents staged/unstaged
metadata, and clears stale observations on Project/session change or browser
hide. Local Node 22 Web 1149/1149, MV3 6/6 and desktop/mobile browser E2E
100 pass/28 prescribed skips. Run exact-head Linux CI, normally merge and
read back. Then scope the next A3 sensitivity-aware patch/content contract;
ordinary shell, arbitrary file browsing and plugin authority still depend
on the pending Owner choice. See [A3 Git Changes](../WORKBENCH_A3_GIT_CHANGES.md).

## Historical 2026-09-28 S02 A3 bounded Git Changes metadata

PR #105 merged as `7ffc1734b0ce5a4f6fdc5575eaeac6804f2aca5c`
with exact parent read-back and six successful post-main workflows. R12's
Runtime profile gate is now software-delivered but enabled-mode composition,
positive legacy conflict observation, fixed manifest/native inputs and real
host/client/CLI evidence remain separate unfinished work.

Continue on `codex/workbench-git-changes` under
[A3 Git Changes metadata](../WORKBENCH_A3_GIT_CHANGES.md): complete fixed
Runtime `git.changes.list`, strict RPC, READY Project API, pagination and
negative tests. Local Git/Project API/release matrix (164 pass), Web/MV3
version/build checks and browser E2E (98 pass, 28 prescribed skips) now
pass. Run exact-head Linux CI, normally merge and read back. Then
connect the authenticated page to this real list and the migrated tree/order
logic; patch bodies and Files access need their own bounded sensitivity
contract. The pending broad-permission decision does not block this read-only
Project metadata slice.

## Historical 2026-09-28 R12 Runtime fixed deployment profile

PR #104 merged as `e6a5bf36636c5baf1225368c0acea1d89a73762e`
with exact parent read-back and six successful post-main workflows. Continue
on `codex/r12-runtime-deployment-profile`: the installer creates only the
canonical `disabled` Runtime profile at the fixed private path; an exact
loader checks parent and leaf provenance, and `_main` may run legacy mode
only when the profile remains disabled at startup. Explicit
`filesystem-v2` fails until the full application graph is wired. Local
installer/profile and focused entrypoint tests pass; Linux exact-head CI
and merge are pending. See [Runtime profile](../WAW_R12_RUNTIME_PROFILE.md).

After this software guard, replace the deliberate enabled-mode rejection
with one production composition from activated sockets, Runtime-only key,
epoch, verified manifest, deferred provider, current Project bindings and
one bounded bidirectional conflict authority. Installer CAS transactions
must coordinate API and Runtime profiles; no real host mode switch, Secret
or credential operation follows from a software merge.

## Historical 2026-09-28 R12-C3-b dynamic Runtime conflict state

PR #103 merged as `72b87c8333896eb6403e3a7e02516e4dcdf910c3`
with exact parent read-back and six successful post-main workflows. Continue
on `codex/r12-runtime-conflict-probe` with an internal, read-only snapshot
that maps current formal Project IDs back to their unique Runtime relative
keys and reports WAW supervisor/inflight/quarantine state to the existing
legacy conflict coordinator. Missing binding, ambiguity, concurrent change
and unknown state must block, never imply absence. Local executor tests pass;
Linux exact-head CI and merge are pending. See
[C3-b composition closure](../WAW_R12_C3B_PRODUCTION_COMPOSITION.md).

After this snapshot, bind a single closed production conflict probe to the
same executor and legacy managers. The legacy Claude/Codex observations need
bounded, fresh, read-only source evidence within the R12 start envelope;
do not use an always-ABSENT callback or a stale manager status cache to make
the software path appear complete. The [official Codex CLI command reference](https://learn.chatgpt.com/docs/developer-commands)
does not document `remote-control status`; local `codex-cli 0.153.4` help
also lacks it. Confirm a positive target-specific daemon state source rather
than interpreting an absent process match as stopped. Then close `_main` and remaining installer
manifest/native inputs, keeping real host/key/client/CLI gates separate.

PR #104's Linux native job reported 106 passed and one `tmux wait-for`
timeout in a pane-death test. The follow-up polls the exact retained pane
state and exact exit code within the same five-second budget, eliminating a
one-shot hook/waiter ordering race without relaxing the behavior assertion.
Require a new exact-head native/Backend pass before merge.

## Historical 2026-09-28 R12-D API disabled profile and singleton lock

PR #102 merged as `f70a3fdfda2439ad91a58aa9c38deb0e9c0f7417`
with exact parent read-back and six successful post-main workflows. Continue
R12-D on `codex/r12-api-profile-provision`: install the exact disabled
`/etc/agentbox/waw-api-profile.v1.json` and fixed
`/run/agentbox-waw-api/waw-api.v1.lock` with their loader-required owners
and modes. Existing valid `filesystem-v2` profile bytes must be preserved;
unknown or unsafe existing objects fail closed. No activation or mode update
is authorized by this software batch. Local fixture tests pass; Linux
installer/Backend CI and merge remain pending. See
[R12-D API resources](../WAW_R12_D_API_RESOURCES.md).

After exact-head CI and merge, continue the fixed public anchor/manifest and
Runtime `_main` composition. The separate mode CAS updater, static key
creation, external vendor enrollment and real host/client/CLI gates remain
later work. Keep the original checkout's WIP intact.

## Historical 2026-09-28 R12-D dormant installer socket substrate

PR #101 merged as `3d0ba375b5a616f1432789eb430ef1a7de4f3347`
after 24 exact-head successes, two prescribed skips, and six successful
post-main workflows. Continue R12-D on `codex/r12-installer-waw-sockets`:
install two fixed named socket units without enabling them; provision only
fixed non-secret directory structure; keep PID1 G3/HG-04 `NOT RUN`.

The current software candidate checks new directory collisions instead of
adopting them, stops any installed exact package WAW units before Runtime,
and removes newly introduced units when rolling back to an older backed-up
release. Simulated x86_64 fixture tests pass locally, but Linux
`systemd-analyze`, native installer CI and real host evidence are pending.
Next, run exact-head CI and normal merge/read-back, then continue fixed
manifest/policy/key provisioning and `_main` composition under separate
software and host gates. [R12-D socket substrate](../WAW_R12_D_INSTALLER_SOCKETS.md)
records the exact paths and incomplete inputs.

## Historical 2026-09-28 R12-D named socket admission refinement

PR #100 delivered the C3-b authority-deferred resource foundation as merge
`e3eb23930f6a34720ccf3ef604619acbc2d6cf4c` after exact-head CI and
six successful post-main workflows. Continue the production `_main` and
installer/client software work; do not claim host qualification.

Before writing two systemd socket units, close the loader's old FD ordering
assumption. [systemd.socket](https://github.com/systemd/systemd/blob/main/man/systemd.socket.xml)
does not guarantee relative order across socket units targeting one service.
Current `codex/r12-waw-socket-names` software candidate requires exact-two
unique control/stream `LISTEN_FDNAMES`, validates each FD's fixed path and
provenance, then normalizes the result. Linux CI and later PID 1 host evidence
must separately prove delivery; G3/HG-04 remain `NOT RUN`.

## 2026-09-28 C3-b deferred resource foundation — software candidate

Owner-approved [full capability plan](FULL_CAPABILITY_DELIVERY_PLAN.md) keeps
R12 production Runtime integration first. The latest main is rc14 merge
`986e8fa87c6d14030677c026342813c6921cc6f9`. An isolated branch
`codex/r12-c3b-resource-factory` carries the authority-deferred provider,
fixed executable/descriptor resource builder, distinct application owner,
native auth-probe path and cleanup repairs. Local related tests and Linux-target
type checking pass; exact-head CI and merge are pending. This is no production
entrypoint or host qualification.

The next software action is `_main` composition using installed activated
sockets, Runtime-only static key, epoch store and external vendor enrollment
without introducing a second authority. Keep the original checkout's C3-b
provider/tests, `.reasonix/`, `build/` and planning WIP intact. The exact
remaining issues and acceptance tests are in
[C3-b composition closure](../WAW_R12_C3B_PRODUCTION_COMPOSITION.md).

## R12-C2 C3-a composition closure delivered for review; C3-b next — 2026-09-15

M4 executor integration is delivered by PR #95: final head
`dfcefe87a2d53bac6eff73c7a63ea42d9ef52caf` completed all 26 terminal checks
(24 success, two prescribed rc8 skips), merged normally as
`4f374aef102c820a001517e14c49803da3e0ff73` with exact parent read-back, and
all six post-main workflows succeeded. Preserve this result.

The current branch `codex/r12-runtime-main` carries C3-a: the one-shot
`bind_native_probe_path` closing the owner↔factory↔process-port construction
loop, vendor digest per-entry `max_bytes`, the fixed-composition pin moved to
`WAWProductionAuthOwner`, and the API client per-action envelope
(`workspace.workspace.start` at 9.0s), closing decision
`R12-AUTH-PROBE-BUDGET-V1`. Independent review PASS with no P0/P1. Owner
review is held before merge per the 2026-09-15 milestone-review instruction.

C3-b after review/merge: production executor provider and the `_main`
production branch (activated sockets, static key, epoch store, provider,
application builder). Production profiles additionally require external
enrollment inputs (`vendor_version`, `codex_unauthenticated_output_sha256`,
D/G/H) and fail closed without them. No actual host/client/key/CLI activation
follows from the software merge.

## R12-B delivered; C1 candidate and C2 native work

R12-B/rc11 is delivered by PR #90: final head `64d45e7...` completed the exact
26-check contract, normal merge `e126e47172491f382efb2f5daaeac1e22a550ad6`
has verified parents and six successful post-main workflows. Preserve this result.
Continue the independently reviewed C1 static-key candidate on
`codex/r12-runtime-key`, followed by C2 fixed auth-isolation/executor and C3 main.
Native C2 work has separate file ownership; Python shared-file writes wait for C1
delivery. No actual host/client/key/CLI activation follows from the software merge.

## 2026-09-08 approved R12 execution

The Owner explicitly approved [PRP-2026-09-08-v1](PRODUCTION_READINESS_PLAN.md)
and instructed execution. Begin R12-A contract/input closure, then continue
dependency-ready R12-B/C/D/E/F software work on feature branches with CI,
normal merge and exact read-back. One persistent Goal is active; the main agent
owns the checklist and shared files. Mac Chrome/Edge terminal and mobile
management/exact Stop follow the plan's suggested scope, without claiming new
platform qualification.

Concrete host, Origin, client distribution and real key/login/paid-call/reboot
scope remain external inputs. Missing host evidence does not block independent
software work. Host/client activation and production/publication retain the
separate boundaries in the approved plan. The WEV-1 section below is historical
delivery context, not the current execution instruction.

## 2026-09-08 workstation evolution

The Owner requested a bounded incremental audit/research/implementation task.
Use [WORKSTATION_EVOLUTION](../WORKSTATION_EVOLUTION.md) as its task record and
[CAPABILITY_MATRIX](../CAPABILITY_MATRIX.md) as the evidence index. The current
software increment is WEV-1: invalidate browser Runtime observations after
interruption and re-read them on return before exposing lifecycle controls.
No automatic Start/Resume/Connect, new API/DB domain or production activation is
authorized by this increment. Branch: `codex/workstation-evolution`.

The seven-project research and WEV-1 implementation are merged through PR #87.
Head `80a6972466a514aa67577bb7812cf4c649a5983c` passed the complete 26-check
contract (24 success, two prescribed skips); merge
`b3e9cd5dbfbdca0c5e0cd652dc0cce7e1e53214e` has verified parents and six successful
post-main workflows. Preserve the completed tests, reviews and delivery record.

The next product-flow action is to establish the concrete R12 target and
authorized Runtime/Project/trust/key handling, then implement and verify the
five gates below. No other proposed feature is implicitly activated by WEV-1.
Later Files/Diff, Attention/Approval, Discovery/Resume and Task/Worktree proposals
need their own bounded contracts. R12 is still blocked on concrete target,
Runtime/trust/Secret scope and real-host evidence. The completed R11 record
below is historical context, not a command to repeat its work.

R12 must close all five [production bootstrap and host gates](../WORKSTATION_EVOLUTION.md#r12-production-bootstrap-and-host-gates):
production API mode/composition; Runtime filesystem-v2 builder and concrete
executor/key provider; activated sockets and peer/cgroup/isolation; managed CRX,
Native Messaging and trustd enrollment; real CLI login, input, return/reconnect,
exact Stop and reboot recovery. This is implementation plus host acceptance,
not a feature-flag change or a request to rerun synthetic tests.

Action ID: `DELEGATED-RUNTIME-RELAY-2026-09-03`

The Owner explicitly delegated software goal, plan and architecture decisions to
the Coding Agent and instructed continued development. The complete reviewed
[WAW stream supplement](WAW_ENCRYPTED_STREAM_DECISION.md) is accepted for software
implementation under [GOVERNANCE](GOVERNANCE.md). The previous R3 confirmation
blocker is resolved. Do not request the same software approval again.

## Active implementation

- rc8 is delivered by PR #83: documentation head
  710ceef696757a8a1f2a9165f2312672db57bb1e completed 26 exact-head checks,
  merged normally as 95bf65d6114008b962985f7311941499c961a7b8 with exact
  parents 87f5bce and 710ceef, and all six post-main workflows succeeded. This
  remains software-only evidence; no tag, release, host activation or R12
  qualification occurred.
- RC9 is delivered through PR #85: exact-head CI, normal merge, merge read-back
  and all post-main workflows succeeded. Preserve the immutable locale rule (only
  `navigator.languages[0]`, `zh` primary → `zh-CN`, otherwise English) and
  preserve technical values without translating or humanizing external protocol
  strings. R11 software rc6–rc9 is complete as software evidence; do not extend
  that result to R12.
- The fixed rc8 predecessor/artifact operations jobs are now version-aware and
  fail-closed: rc8 executes them successfully, while rc9 skips exactly those
  historical jobs and still requires current-candidate artifact checks and
  `release-gate` success. Preserve the fixed rc8 contract; skipped, failing or
  unknown results must never count as pass.

- rc9 version text is Python `0.3.0rc9`, npm `0.3.0-rc.9`, MV3 `0.3.0.9`.
  Production output must retain no test bypass; the distinct-origin Workspace
  harness is E2E-only and sensitive artifacts remain disabled. R12 stays
  independent, unstarted and host-gated. No tag, GitHub Release, production
  deployment, Provider credential operation or real host activation occurred.

- Historical rc6 work-unit and checkpoint evidence remains in the execution
  plan and current-state record. The rc8 and rc9 actions above are the current
  authoritative sequence.

- Historical rc9 foundation commit `184781c...` completed 20/20 exact-head
  checks. Its shared catalog, error-code mapper and route-state manifest are
  now incorporated in the delivered rc9 implementation; the page migration and
  bilingual visual matrix are no longer a pending implementation item. Current
  evidence is recorded in `CURRENT_STATE.md`; its CI/merge record is delivered.

- Preserve merged R0/R1/R2/R9.1/R10.1 and the verified delivery record, PRs #67–#72.
- R3/R4 are merged as PR #73 after 19/19 checks and exact read-back.
- R5 is merged as PR #74 after 19/19 checks and exact read-back. Cold-start/GC
  parser failures are fixed without relaxing the 5 ms budget.
- R6 is merged as PR #75 after 19/19 checks and exact read-back; staged ticket
  authority, atomic publication, reader handoff and cleanup/Audit fences delivered.
- R7 is merged as PR #76 after final independent PASS, 19/19 exact-head checks
  and exact read-back; Runtime encrypted stream/server and publication fences delivered.
- R8 is merged as PR #77 after independent PASS, 19/19 exact-head checks,
  normal merge, exact read-back and six successful post-main workflows.
- R9 is merged as PR #78 after independent PASS, 19/19 exact-head checks,
  normal merge `15a4632f915dd1e1bde19425e313b52ada27166f`, exact read-back and
  six successful standard post-main workflows.
- R10/rc5 is delivered by PR #79: final head `0d9e7c7...` completed 20/20
  exact-head checks and merged as `341a69bf...`; exact parent read-back, all six
  post-main workflows and dynamic Dependency Graph completed SUCCESS.
- PR #80 repair head `bbdd67c...` has terminal 20/20 CI after fixing the shared
  descriptor-release/inode-reuse issue. It verifies the current first-use/
  evidence checkpoint. Native/format follow-ups completed in `4222242...` 20/20
  CI. Do not merge before replay, controller composition and the remaining rc6
  acceptance set.
- Current evidence: the final local core matrix completed 216 plus 5 focused
  cases; independent Sol/xhigh review completed 244 cases with 1 Linux-only skip
  and 9 deselected, plus 8 encrypted-server non-UDS cases. Review is PASS with no
  remaining P0/P1/P2. Twenty-eight real-UDS cases are locally unverified because
  this environment returned `PermissionError` during socket setup. Ruff, Black,
  Linux-target mypy (256 sources), doc links (240) and `git diff --check` pass.
- The current uncommitted bounded-redraw slice has a neutral 24-row/60 KiB
  contract with row 25 and byte 61,441 as discarded sentinels. Held-FD tmux
  capture proves socket/pane/retained-pidfd identity before and after one shared
  one-second deadline; supervisor capture/cursor/baseline publication is atomic,
  and production capture callbacks are removed from registry/service/bootstrap.
  The unified focused matrix completed 341 tests with 9 Linux-only skips and 2
  local UDS cases deselected; independent Sol/xhigh review reports PASS with no
  P0/P1/P2. The new Linux native case requires exact-head CI; local UDS setup
  remains unverified after `PermissionError`.
- Head `adf44fc0...` ran the new real Linux capture successfully, then failed the
  native job at teardown because the test killed tmux before calling a helper
  that expects the tmux socket. The test-only follow-up removes that invalid
  cleanup assertion. Commit/push it and require a fresh exact-head native/full
  Backend pass before recording bounded redraw complete.
- Follow-up `f37f92d9...` completed the required 20/20 exact-head matrix. Linux
  native completed 73 cases; Backend Python 3.11 completed 3629 passed/44 skipped,
  with 3.12/3.13 also successful. Treat bounded redraw as verified and continue
  with `WAWRuntimeApplication` production composition and singleton ownership.
- The current `WAWRuntimeApplication` composition is uncommitted: typed Runtime
  key/executor providers and activated sockets have distinct one-shot ownership;
  stream, control and legacy share application start/close tasks and one dispatch
  gate. Partial production builders are private and weak-map provenance is gone.
  Incomplete construction retains a typed retryable owner. Provider closure waits
  for stream/control/lifecycle/legacy clean evidence. Independent Sol/xhigh review
  reports PASS with no P0/P1/P2; Linux-target mypy covers 260 sources. Production
  main, real key/provider and host activation remain disabled.
- `WAWRuntimeApplication` head `628e9c00...` completed 20/20 exact-head checks.
  Continue rc6 with the API singleton, one attachment/bind/control/relay owner and
  lifespan shutdown ordering; keep real key/provider and production activation in
  their existing host-gated scope.
- `AttachmentAuthority` shutdown fencing is implemented and independently reviewed:
  pending tickets burn, cleanup obligations survive invalidation, and only exact
  cleanup/Audit ACK reaches clean. Commit and exact-head verify this foundation,
  then implement the process lock and single bind/control/relay lifespan owner.
- Bind/control shutdown evidence is also complete locally: pending exchange,
  detached task, retained peer or uncertain FD close prevents clean. Commit and
  exact-head verify it, then continue process lock and stream-owner composition.
- Begin rc7 with named test-only checkpoints, manual promises, fake monotonic clocks
  and controlled partial-write sockets. Prove admission/stream/restart/shutdown/Stop/
  browser-lifecycle failure invariants before advancing to rc8 artifact rehearsal
  and rc9 full browser-selected bilingual UI.
- First integration head `e210d749...` completed 17/20 checks. Three Backend
  matrix jobs exposed one shared legacy regression: a clean non-fixed server could
  no longer restart without consuming a second epoch. The local reviewed fix
  restores only that compatible restart; fixed/control/poisoned/incomplete shutdown
  stays terminal. Follow-up `c534fe437...` completed the fresh exact-head 20/20
  matrix. Continue the remaining rc6 controller composition; do not merge rc6 until the full
  controller composition and rc6 acceptance set are complete.
- Locale remains fixed per document from only `navigator.languages[0]`: primary
  `zh` → `zh-CN`; all other, missing or malformed values → English. Technical
  identifiers remain English.
- Keep R7/R8 active lifecycle obligations explicit: 30s stale/60s grace,
  15min idle/8h absolute, Runtime health, current auth and positive cleanup.
- Resolve remaining software contracts with documented rationale and independent
  review under the delegated authority, rather than another mechanical Owner gate.

Each stage follows feature branch → exact-head terminal CI → normal merge →
exact read-back, updating CURRENT_STATE, the remaining plan and relevant scope
documents. Complex work uses sol; routine implementation/verification uses terra.

## Remaining evidence boundaries

Mac remains the development platform. Real host activation, production keys or
Provider Secret operations, publication and support promises require a concrete
scope/target and real evidence. Software decisions do not certify those gates.
The independent trust-provider deployment and actual CLI/PTY/isolation/restart
qualification remain required before full product completion. No synthetic
handler or passing codec test may be presented as a working terminal.
