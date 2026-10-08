# AgentBox Project Context Index

## 2026-10-07 Kebui 产品标识落实（18:04 UTC）

PR161 已正常合并为 main `8027628f2cf9937d65626e8a9e87eed2f59c7675`，
tree `de3a2410de75159f3b33acbefbdec4913b18b3f6` 与合格 head14211671 相同；
六套 exact-main workflow 全部 completed/success（E2E37660979034、
Backend37660978927、Frontend37660978852 等）。Login/404 与当前 U2 跨页证据已闭环。

接续 Owner 的新名称要求，按 K1 落实[有界产品标识层](../KEBUI_PRODUCT_IDENTITY.md)：
README、Web 外壳/登录产品简介、页面标题和静态元数据使用 Kebui（科布）；
技术 API/CLI/Runtime/包/服务/数据库名、旧链接与 rc31 版本保持兼容。
本批仍待新 exact-head CI 和浏览器证据；不以基线六绿代替本批验证。
U1 新设计与原型、Chat/Task 和真实 host/release/deploy 仍未交付，不因更名获得资格。
下方旧 pending/失败记录完整保留为历史快照。


## 2026-10-07 Kebui 计划闭环，Login/404 与跨页候选（16:12 UTC）

[PR159](https://github.com/ForceMind/agentbox/pull/159) 已于 15:45:37 UTC 正常合并为
main `99ae3d67981e860ea4f6cabb8c6dd416b358a8d0`，tree
`a8ac8ca6bc56357a79b4be3839187c294704b297` 与合格组合 head 69c5054 完全一致。
六套 exact-main 首轮成功，23 success / 3 规定 skip；Frontend 1945+6，
Backend 实际 3.11.17/3.12.15/3.13.15 各 5375/88，native 实际 3.13.16；
E2E 566/222、21 preflight，无 failed/flaky/retry。独立终审 CLEAR。
九份 planning docs 与双方历史保全；原 2 moderate 审计与 native READY 历史限制保留。

[Draft PR161](https://github.com/ForceMind/agentbox/pull/161) 接续同一 rc31 版本的
[Login/404 合同](../WORKBENCH_UI_ENTRY_REFRESH.md)，仅五个产品文件的呈现与
typed 双语。Login helper/submit/input/error 逐字保留，AuthProvider/API/guards/
Session/10 秒 timeout 不变；404 只有原状态对应 Link。新增 26 项实际回归，
完整 1971 Web+6 extension、lint/typecheck/format/build 通过；独立 source CLEAR。
旧 404 E2E 只更新标题文字期望，无产品 RED。

首个组合 head `0042964b5b6e552e9d344be2670e3ac867c69d77` 已正常吸收 main 99ae3d6；
初始九份规划文档逐字一致，四键 YAML 有效。16:10 时五套 CI success、E2E 仍在运行。
新 browser 静态 132 注册，预计 84 执行/48 自管理矩阵重复 skip，计划 60 PNG；
所有截图只在输入清空后采集，旧敏感套件 capture-off 不变。
尚未取得新 browser/原图/最终 head 六套/main 资格，不借旧头或 main 结果称完成。

[跨页验收映射](../WORKBENCH_UI_U2_CLOSURE.md) 复用现有导航、Session、401、
logout、离线/隐藏恢复与 sensitive currentness 回归；仅补 Attention/Changes 以及
已有 history 流程的精确 document.title，单独 test-only 提交并独立审查。
不增加产品行为、新 fixture/框架/矩阵或截图数量，最终以包含这些断言的组合头资格化。
该收口完成后只称 U2 既有页面软件闭环，U1 新 Kebui 原型仍待；真实 host/device、
双 CLI、trust/Secret、恢复与 release/deploy 继续分别取证。下方旧快照完整保留。


16:22 更新：0042964 的 E2E37648558752/job112885601067 首轮终态为
642 passed / 270 skipped / 8 failed，五套其余 workflow 成功。失败均为新 entry spec
finally 错用严格 release（未 held 或已 release）；仅改用既有 dispose 做 cleanup，
显式 release 保留并等待 held。产品/预算/断言/skip 不变，不重跑失败头取绿。
后继组合 head 含跨页标题与该 test-only 修正，仍需完整自身资格；未提前称图像通过。

## 2026-10-07 PR160 闭环与 Kebui 计划合并协调（15:20 UTC）

[PR160](https://github.com/ForceMind/agentbox/pull/160) 已于 14:55:47 UTC 正常合并为
main `d9ab2f695b175d4779471a8e152f8950e95cd321`；tree
`0992054062f780523a8b53e1588a40bb139a3977` 与合格 head
`a02d9ae1f1cb043fbdd90afbab4dd22960f2a1c8` 一致。六套 exact-main workflow
均 completed/success，含 [Backend](https://github.com/ForceMind/agentbox/actions/runs/37640824200)、
[Frontend](https://github.com/ForceMind/agentbox/actions/runs/37640823875) 与
[E2E](https://github.com/ForceMind/agentbox/actions/runs/37640823989)。该批原生 dialog
断言更正、独立端口 RED→GREEN 及 80 张 metadata 图资格记录由其交付证据保留；
本次文档协调不冒称重新执行像素审查，也不将历史 READY 间歇问题写成已修复。

[PR159](https://github.com/ForceMind/agentbox/pull/159) 的文档修正 head
`af09af8b9affa13ea69e7474c529c9badecb1482` 六套已成功。现正常 merge-forward
上述合格 main，保留两个父提交及双方全部状态正文；CURRENT_STATE 仍是四键 YAML。
此前“保持 Draft 交回协调”是上一批停止点；本次已接续既定合并协调，组合 head
须重新通过适用检查、独立审查及六套 CI，随后正常 Ready/merge 并验证新 exact-main。
当前记录不提前宣称组合 head 或未来 main 已合格，不使用旧头六绿替代新证据。

U2 的 Doctor/Settings/Logs 呈现已合并；Logs 功能仍未实现、Settings 仍仅六项
只读事实。接下来只有 Login、NotFound/404 与跨页一致性收尾，不重复已有页面。
U1 的新 Kebui 参考板/tokens/高保真及三条可点击原型仍未交付；U3 继续受 K2/K3、
S03/WEV 合同约束。无 Chat、Files 或权限扩展，版本仍 rc31，无 release/deploy。
下方 14:22/14:14 及更早的 pending/Draft/失败记录均为历史快照，完整保留。

## 2026-10-07 Agent管理闭环，管理摘要浏览器更正（14:22 UTC）

[PR158](https://github.com/ForceMind/agentbox/pull/158)已于12:47:59 UTC正常合并为
main `cf710d59cd6c47d7a240c0ce25d7f006d51e374a`，tree
`df1e0951109f9c35c658e0edcc9b82eccce0d688`与合格head e890完全相同，parents为
38bd/e890。六套exact-head首轮成功、24success/2规定skip；六套exact-main首轮
成功、23success/3规定skip。main Backend实际3.11.17/3.12.14/3.13.15各5375/88，
native实际3.13.15为109/1、pinned1/33deselected、sanitized60/1；Frontend1900+6，
E2E464passed/156skip、21preflight，无failed/flaky/retry。独立source/官方日志/
main精确回读CLEAR，历史native READY间歇问题仍开放，不称根因修复。

本批68张metadata图资格为54张逐字节继承已审原图+14张新/变化实际复查；真实长
Project名压缩Claude状态的12图问题已修正并通过Range几何断言。四张正常中文
preview保留原Library身份、无重复上传。最终head artifact11482507396含278PNG，
不冒称全部278已审；main同树继承head图，未下载或冒称查看main重复截图。
独立4项真实RED、bounded auth-owner修复、视觉和测试更正提交分别保留；
[合同与失败记录](../WORKBENCH_UI_AGENT_MANAGEMENT_REFRESH.md)不抹去旧失败。

按同一rc31 UI版本接续[Doctor/Logs/Settings只读呈现卡](../WORKBENCH_UI_ADMIN_REFRESH.md)。
Doctor保留五项control-plane检查与现有安全Runtime摘要，ready不代表所有Agent
已可运行；Settings仅原六项policy只读事实；Logs仍明确尚未实现/产品预览。
不添加配置写入、日志读取/下载、刷新轮询、权限或Runtime能力。保持原useDoctor
一次GET/90s/abort/投影、SafeTechnicalValue与身份边界，当前未证明需先修产品bug。
[Draft PR160](https://github.com/ForceMind/agentbox/pull/160)已保存七产品文件与七个
新test/helper文件，产品helpers/pre-return不变，独立source/单测源码审查CLEAR。
41项新回归，定向86项与完整1941 Web+6 extension、全lint/typecheck/format/build
通过。两个初始测试错误只漏计LoginPage的health GET，未发现产品RED。新browser
静态168注册（102执行/66规定重复skip），计划80metadata图，实际8DTO变体经
production decoder通过；只新增精确artifact前缀，保持capture-off与原安全边界。
2c4正式E2E为564passed/222skip/2fail，仅新mobile用例把原生dialog误交显式role
helper；test-only修正已独立CLEAR，原产品不变。80张原图已实际独立审查，另发现
既有端口8080被分组为8,080；4项真实RED单独保存后仅该字段改TechnicalValue，
原4项逐字GREEN、独立27项通过，其他数量/时长格式保持；修后完整1945 Web+6 extension通过。新head六套与
22张Settings变化图及main资格仍待，不借失败头或旧图称本批合格。
之后仍有Login、NotFound及跨页面收尾，不以本批代替整个版本完成。
无新账号、凭据/grant、host激活、release/deploy；旧pending均为历史快照。


## 2026-10-07 Kebui 品牌与长期产品方向

Owner 选定 **Kebui（科布）** 作为面向用户的战略品牌方向，产品官方品牌读音暂定
**KEH-boo**，中文名为 **科布**。品牌灵感来自 Qebui/北风意象，但不宣称复原
古埃及精确发音。主传播语为 **One conversation. Every agent. / 一次对话，调动所有 Agent。**

本次只形成长期品牌和产品演进文档，不打断当前 rc31 UI/release 有界工作，不立即
重命名 repository/package/service/API/DB 标识，也不改变 Runtime、Secret、权限、
host 或发布边界。过渡结构为 **Kebui（用户产品） -> AgentBox Runtime（执行引擎）**，
后续是否完整迁移 Runtime 名称需单独 ADR。

- [Kebui 品牌规范](KEBUI_BRAND.md)
- [Kebui 产品演进计划](KEBUI_PRODUCT_PLAN.md)
- [Kebui UI 与交互设计](KEBUI_UI_DESIGN.md)
- [Kebui UI 分阶段交付与验收](KEBUI_UI_DELIVERY_PLAN.md)

2026-10-07 14:14 UTC 校正：main 已是 PR158 合并后的 `cf710d59`，Codex/Claude
管理页不是待开发项。Doctor/Settings/Logs 由 [Draft PR160](https://github.com/ForceMind/agentbox/pull/160)
接续，精确头 `2c4bf603` 五套成功、E2E 失败，尚未闭环；其后为 Login、404、跨页检查。
这是 U2 当前 rc31 工作。U1 新 Kebui 高保真/可点击原型仍未交付；后继 CI 与状态
以 [当前快照](CURRENT_STATE.md) 和各 PR live head 为准，下方旧候选记录仅为历史。

`kebui.com` 与 `qebui.com` 在 2026-10-07 规划时被查询为可注册；在 Owner 明确
确认购买前，仓库不得写成“已拥有”。

## 2026-10-07 Changes闭环，Agent管理UI候选（11:51 UTC）

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
[Draft PR158](https://github.com/ForceMind/agentbox/pull/158)已先保存15fd的4项真实RED，
独立复现与官方Frontend4fail/1800pass吻合；独立b9修复使原RED逐字GREEN，78项
owner回归/source CLEAR，不改useClaudeProject/API/AuthProvider/权限/预算。
两个页面视觉另立提交，pre-return/guard/handler保持。完整候选本地1900 Web+6
extension及lint/typecheck/format/build通过，两个页面86项呈现回归保留原8项。
新browser静态110注册（69执行/41规定重复skip）、68metadata图和独立capture-off
scope场景；CSS嵌套列与fixture origin守卫的源审发现已修并独立CLEAR。最终UI
exact-head六套、真实browser/原PNG与main仍待，保持Draft，不借b9六绿冒称本批合格。
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

## 2026-10-05 PR #143 已闭环；native A3 六套 CI 全绿、像素收尾

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
最终 publication/END 与显示生命周期保持分层。第七轮 head
`f67b93dfa0678ee0f04ea187a91d9a8cddb35c07` 六套 CI 首次全绿；Backend 三版本各
5276 passed/88 skipped，14项真实 native 全通过；E2E212 passed/30 prescribed
skipped/0 failed/0 flaky，新增52项正式 App desktop/phone 全通过（212还包括
16项纯 Node checks）。[Current state](CURRENT_STATE.md) 保留六轮失败、真实
原因与双 loop 同条件 red/green，不用已排除的裸 adapter 竞态假设解释 CI。

原始 artifact 摘要已核验并打开四张 PNG，发现 full-page 截图滚动位置及 phone
刷新按钮换行问题；仅进行小幅视觉/截图收尾，最终候选的 exact-head CI 与像素
复核尚待完成。PR #144 仍 Draft，main 仍为上述 #143 merge。通过后按正常
Ready/merge、parents/tree read-back 与 exact-main 六套 CI 闭环。
无生产 key loader/pin enrollment、installer 开关、真实 host listener/账号或发布。
未配置安装仍 unavailable；真实 host/physical client/CLI 验收仍 NOT RUN。

本地最终 A3 matrix428 passed，Web1480 tests 与 extension6 tests、正常质量门禁、
独立 crypto/interop 与 source review PASS。此 executor 的 AF_UNIX 创建限制与
旧全量 pytest 因共享 /tmp ENOSPC 终止仍是失败历史，不能改记本地全量 PASS；
真实 numeric-UID、UDS、HTTPS 与浏览器资格来自上述 CI，不来自本地跳过项。



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


- **当前优先级（2026-10-04）**：#140 已正常合并，exact-head/post-main 六套
  CI 全终态 SUCCESS。当前推进 [独立 encrypted single-read](../WORKBENCH_A3_ENCRYPTED_SINGLE_READ.md)
  的 synthetic Git→fresh A3 Noise→opaque relay→Web 软件链；真实 host/device
  验收继续 NOT RUN，生产 resolver/key/relay/UI 与 release 仍分开。

- [Development handoff](DEVELOPMENT_HANDOFF.md)：2026-10-04 接续入口；
  PR #136 完整 fresh-install 已实现，documentation-inclusive CI 全绿；
  已正常合并为 7d052155；当前进入真实首装资格化准备。
- [Deployable release plan](DEPLOYABLE_RELEASE_PLAN.md)：Owner 自行运行一键安装的
  首版目标、实际命令入口、PC/手机范围及部署链剩余依赖。
- [Cross-platform Web bootstrap proposal](../adr/0010-cross-platform-web-bootstrap.md)：
  已批准 PC/手机浏览器的 HTTPS 信任前提、与原生保护的差别及实际验收条件。
- [Deployable cgroup compatibility proposal](../adr/0011-deployable-cgroup-compatibility.md)：
  已批准 systemd 255 受限子树方案；不等同旧 private 合同，激活仍须真实证据。

- [Release iteration plan](RELEASE_ITERATION_PLAN.md)：当前唯一目标是首个可用单机 RC；
  明确软件候选、真实目标验收和后续逐版本吸收的退出条件与范围冻结。
- [Full capability delivery plan](FULL_CAPABILITY_DELIVERY_PLAN.md)：Owner 将范围扩展为
  吸收全部现有上游功能；按三仓固定提交与 70 项 ID 组织一条分阶段实施路线。
- [Full capability inventory](FULL_CAPABILITY_INVENTORY.md)：主仓、生产 relay、Hub
  的功能、现有 AgentBox 状态与逐项验收目标；权限冲突另有待确认选择。
- [Workbench integration plan](WORKBENCH_INTEGRATION_PLAN.md)：Owner 已批准软件实施；
  v1 保留 A0/A1 技术基线与来源规则；全量范围以 v2 为准。
- [Workbench identity and content ADR](../adr/0009-workbench-identity-and-content-boundary.md)：
  Project、WAW、会话与 UI tab 分域，内容仍须 A3 专项协议和审查。
- [A3 Git Changes metadata](../WORKBENCH_A3_GIT_CHANGES.md)：
  READY Project 范围内的只读路径/状态分页合同，不授予正文或 patch 读取。
- [A3 Git patch content contract](../WORKBENCH_A3_PATCH_CONTENT_CONTRACT.md)：
  reader/selector 已随 #138/#139 合并；纯 content codec 候选不开放加密通道。
- [A3 Git child cwd](../WORKBENCH_A3_GIT_CWD.md)：
  Linux-only 子进程目录 descriptor 前后身份验证基础；尚无内容读取动作。
- [A3 staged reader candidate](../WORKBENCH_A3_STAGED_READER.md)：
  Runtime 内部有界暂存 patch 观察、对象库快照与仍未开放的内容门禁。
- [Project work tabs](../WORKBENCH_PROJECT_TABS.md)：
  固定上游来源、AgentBox 路由身份和纯导航生命周期；多会话仍待后续阶段。
- [Project search](../WORKBENCH_PROJECT_SEARCH.md)：
  固定上游匹配算法来源、只读 Project 列表搜索和未完成的 WS14 同步能力。
- [Project favorites](../WORKBENCH_PROJECT_FAVORITES.md)：
  WS14 每位管理员的收藏状态、CAS 并发与 Control Plane 元数据候选合同。
- [Project and Workspace labels](../WORKBENCH_PROJECT_LABELS.md)：
  WS14 共享标签目录、正式 Project/Workspace 分配及可见客户端刷新边界。
- [Command center](../WORKBENCH_COMMAND_CENTER.md)：
  WS14 固定页面/正式 Project 导航及精确 Workspace 标签选择，当前 Session 隔离。
- [Production readiness plan](PRODUCTION_READINESS_PLAN.md)：2026-09-08 已批准执行计划；
  R12 软件接线、客户端、真实主机/CLI、恢复与有限生产的依赖、验收和授权范围。
  R12-A已开始；软件执行、host资格化与生产准入分开记录。
- [R12 target record](R12_TARGET_RECORD.md)：目标输入、已确认软件边界、外部阻断与当前派工。
- [R12 API bootstrap](../WAW_R12_API_BOOTSTRAP.md)：固定installer-owned mode、默认兼容、
  root-owned读取、启动currentness与API生产入口契约。
- [R12 Runtime key port](../WAW_R12_RUNTIME_KEY_PORT.md)：C1固定Runtime-only key custody、
  同一manifest authority绑定、epoch时点与关闭契约；C2/C3尚未完成。
- [R12 fixed vendor enrollment](../WAW_R12_VENDOR_ENROLLMENT.md)：
  非Secret CLI版本/输出摘要的固定来源、文件身份及同一Runtime authority配对候选；
  不含真实目标采集或主机激活。
- [R12 fixed auth probe](../WAW_R12_RUNTIME_AUTH_PROBE.md)：C2的closed native ABI、
  同generation借用、offline status、shared cache与cleanup契约；实现与host资格分开。
- [R12-C3-b production composition](../WAW_R12_C3B_PRODUCTION_COMPOSITION.md)：
  唯一authority的资源签发、native owner、Project绑定与后续 `_main` 接线缺口。
- [R12-D installer socket substrate](../WAW_R12_D_INSTALLER_SOCKETS.md)：
  固定具名 socket unit、Runtime 资源目录、安装/回滚与尚未激活的现场边界。
- [R12-D API disabled resources](../WAW_R12_D_API_RESOURCES.md)：
  固定关闭态 API profile、单例锁目录与文件，及后继 CAS 更新门禁。
- [R12 Runtime fixed profile](../WAW_R12_RUNTIME_PROFILE.md)：
  Runtime私有关闭态profile、固定加载及 `_main` 拒绝静默回退的入口边界。

本目录是治理执行入口。每个任务执行前按顺序读取：

1. `CHARTER.md`
2. `CURRENT_STATE.md`
3. `NEXT_ACTION.md`
4. `ROADMAP.md`
5. `DECISION_INDEX.md`
6. `GOVERNANCE.md`
7. `GOVERNANCE_AUTOMATION.md`
8. `EXECUTION_PLAN.md` — 当前目标、阶段状态、职责、验收与交付流程。

- [Workstation evolution](../WORKSTATION_EVOLUTION.md)：2026-09-08 增量任务的
  事实基线、七仓研究、取舍、WEV-1 契约与阶段验收记录。
- [Capability matrix](../CAPABILITY_MATRIX.md)：设计、实现、验证、产品状态分别记录；
  R12 不因新增产品研究而开放。

- [WAW encrypted stream supplemental decision](WAW_ENCRYPTED_STREAM_DECISION.md): accepted full wire/admission/trust contract under explicit Owner-delegated software decision authority; R4/R5 are merged and Runtime/API integration is in progress.

- [Fixed Noise NX core](../WAW_NOISE_CORE.md): implementation limits, independent vector provenance and Python/WebCrypto interoperability.

- [Remaining development plan](REMAINING_PLAN.md): latest assessed goals, finite slices, model routing, confirmed defects and contract decisions.

- [Opaque AWCE framing](../WAW_AWCE_FRAMING.md): exact envelope layout, bounded Python/Web codecs, header builders, cross-language checks and unimplemented crypto/session boundaries.

- [Executable provenance](../WAW_EXECUTABLE_PROVENANCE.md): descriptor-held Runtime inventory verification and its launch/host limits.
- [Interactive CLI assessment](../WAW_INTERACTIVE_PROFILE_ASSESSMENT.md): current code/vendor documentation gaps requiring a complete execution-profile contract.
- [Fixed interactive process](../WAW_FIXED_INTERACTIVE_PROCESS.md): R10 inert
  packaging inputs, digest-pinned policy boundary, and R11/R12 separation.
- [R11 production integration](../WAW_R11_CONTROLLER_COMPOSITION.md): accepted
  rc6–rc9 composition, failure, artifact/operations and bilingual UI contract.
- [R11 execution plan](../WAW_R11_EXECUTION_PLAN.md): delivered rc6–rc9 work-unit
  ownership, state-machine, Project binding, controller and acceptance plan.
- [R11 rc8 artifact and operations rehearsal](../WAW_R11_RC8_ARTIFACT_OPERATIONS.md):
  frozen provenance, artifact-only synthetic and dual-artifact operations
  evidence, current candidate status, and the R12 boundary.

- [R11 rc6 first use](../WAW_R11_RC6_FIRST_USE.md): typed Project binding,
  generation-one creation and Runtime executable-evidence checkpoint, with its
  verification and remaining boundaries.
- [R11 rc6 binding replay](../WAW_R11_RC6_BINDING_REPLAY.md): exact API/Runtime
  replay, inventory-finalization gate, drift fences, installer boundary and
  explicit Linux/host evidence limits.
- [R11 rc6 browser controller](../WAW_R11_RC6_BROWSER_CONTROLLER.md): controller
  cursor/input/control fences, fresh-redraw contract and page-composition limits.

- [Authentication timing diagnostic](../AUTH_TIMING_DIAGNOSTIC.md): isolated numeric observations, failure/privacy rules, regression evidence and unknown historical latency cause.

- [Browser tokenizer foundation](../WAW_BROWSER_TOKENIZER.md): incremental UTF-8/VT typed tokens, independent limits, explicit failure boundary and remaining controller/renderer contracts.

- [WAW application cryptography](../WAW_APPLICATION_CRYPTO.md): exact implemented handshake/channel, deadline/publication rules, independent vectors/interop and native-browser evidence.

- [Full WAW wire profiles](../WAW_WIRE_CONTRACT.md): complete direction schemas, exact-byte relay/trace, failure/retry decisions, parser budgets and measured verification.

- [Staged admission](../WAW_STAGED_ADMISSION.md): ticket burn/reservation, required Audit, atomic publication, reader handoff, cleanup and the distinct active-lifecycle obligations.

- [Runtime encrypted stream](../WAW_RUNTIME_ENCRYPTED_STREAM.md): actual Runtime crypto/session/server, exact cleanup and trusted deployment-port boundaries; current review status is explicit.

- [API ciphertext relay](../WAW_API_CIPHERTEXT_RELAY.md): native WebSocket, Runtime ciphertext relay, active permission/publication fences and current shared-budget status.
- [Browser trust records](../WAW_BROWSER_TRUST_RECORDS.md): canonical public record/signature foundation and the remaining provider/lifecycle boundary.
- [Managed browser trust provider](../WAW_BROWSER_TRUST_PROVIDER.md): inert MV3 source build, deployment cross-pins, Native Messaging/trustd authority and qualification boundary.
- [Browser implementation decision](WAW_BROWSER_IMPLEMENTATION_DECISION.md): accepted R9 trust/controller/bounded-renderer contract and qualification split.
