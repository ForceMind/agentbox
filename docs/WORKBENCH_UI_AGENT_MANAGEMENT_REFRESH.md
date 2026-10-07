# A2 UI 接续：Codex / Claude 既有管理页

## 基线与范围

2026-10-07 10:55 UTC，[PR157](https://github.com/ForceMind/agentbox/pull/157)已正常
合并，main `38bd0b86d20050b7f0df734b14a29d8e1b706ded`，tree
`bc85ddcf4cf5bb4b677ce61c25de367276647056`与合格head f214相同。六套exact-main
首轮成功、23success/3规定skip；Backend实际3.11.17/3.12.15/3.13.15各5375/88，
Frontend1800+6，E2E395/115无failed/flaky/retry。独立source、官方CI、指定48图
覆盖及main回读CLEAR。历史READY间歇问题仍开放，未称根因修复。

按[同一UI版本清单](project/RELEASE_ITERATION_PLAN.md)接续现有 `/codex`、`/claude`
管理页。只重新组织安装/认证/能力/Remote状态、既有动作、Project归属tmux Session
与技术诊断；复用typed双语文案、页面作用域CSS、手机/键盘和既有操作确认。
不新建Provider、Login、WAW、Files或权限模型，不替换API/Runtime/Secret路径。
暖白/墨色/琥珀仍是可回退实施选择，不冒称Owner指定；版本仍0.3.0-rc.31。
分支 `feat/ui-agent-management-20261007`；无真实账号、vendor login、凭据/grant、
生产Pair、host激活、release或deploy。

权威是当前正式代码与已接受合同；[Codex集成](CODEX_INTEGRATION.md)、
[Claude集成](CLAUDE_INTEGRATION.md)中的历史阶段不覆盖live事实。管理页global
useClaude与Project详情的useClaudeProject是不同实现，不能把后者的全部围栏
冒称前者已有。本批不修改已闭环Project详情的业务合同。

## 保留的身份与动作

- Codex安装/冲突、三态认证、capability、Remote状态与reported/observed/inferred/
  unknown可信来源各自显示。未知不能变成在线；Remote Start/Stop不变成WAW
  exact Stop或Provider/Login。原capability/authentication/pending准入条件保持。
- Pair生成前仍要明确确认，保留Cancel/Escape、背景inert、Tab trap、焦点恢复与
  成功/错误焦点迁移。Cancel只撤销未提交确认，不声称取消已提交Runtime动作。
  仅内存展示、明确Copy、Hide/导航/90秒清除仍保留；90秒是展示期限，不是已知
  Codex code expiry，不能添加推测倒计时。recent-auth、CSRF、no-store和原85s/130s
  浏览器预算不变，原服务器prose过滤不削弱。
- Claude安装/认证/Remote capability、tmux存在/managed counts、session状态、
  tmux_running、Remote readiness与Workspace Trust不合并成一个绿点。
  Session按正式opaque Project ID归属，API到immutable relative key映射保持；
  不显示或控制unmanaged session名。既有同Project同步去重、跨Project pending/
  error归属、refresh revision/mutation overrides保持。
- Attach仍为Runtime用户终端使用的既有生成命令，明确Copy，不是Web terminal或
  自动Trust。Pane output默认不请求，明确Reveal后才读取并作inert文本；Hide、
  refresh、同Project mutation清除，响应Project匹配与旧output拒绝保持。
- 页面作用域样式避免影响共享runtime-card、Doctor和Project详情。只迁移现有
  字段、按钮与状态，不新增统计、来源判断、自动操作、内容持久化或重放。

## 先证明作用域风险，再决定修复

只读审查与59项既有pure frontend基线通过，没有已复现产品bug。正常导航/401会
卸载管理页，已有Pair导航清除、Copy/Hide、Claude显式output/Hide、同Project去重
与跨Project乱序错误归属证明；不能只因hook实现不同就宣称泄漏。

先用真实App/AuthProvider/API client与合成HTTP响应做最小test-only事件序列：
Session A已有或等待Pair/output；logout首次403触发auth/me刷新为Session B，
retry失败但页面仍authenticated。观察旧可见内容和迟到A响应是否清除/被拒，
同时确认没有隐式重放。保留90秒展示期限和clipboard失败作为有限回归风险，
不预设业务行为或虚构code expiry。

若得到RED，先独立保存测试、实际失败与生产未改的hash；提交有界修复卡并独立
审查，再改对应owner/fence或必要的呈现反馈。原断言逐字转GREEN，修复与视觉
迁移分提交。不扩架构/权限、不新建诊断框架，不用无依据的timeout/预算调整换绿。

## 交付与图像边界

保留现有页面、hook、rc9和真实App/API测试。新增loading/error/empty/unknown、
Codex unsupported/conflict/unauthenticated、Claude needs_interaction、长inert名称/
命令、局部error/pending、确认/取消/Back/late callbacks与双语键盘/手机回归。

新图仅独立合成metadata fixtures，覆盖两页zh-CN/en、360/390/768/1024/1440与
light/dark，加必要状态和四张正常展示图。Pair/output endpoint请求数必须为0；
capture前验证exact route、合成账号marker、无pair-secret/pane pre/输入值/异常
流量。可拍生成前确认框，不能请求Pair，不用遮罩保留敏感页面。原敏感suites及
全局screenshot/trace/video继续off，新artifact仅追加精确新图前缀。

小稳定提交与Draft PR先保全，适用本地质量、独立source/像素、新exact-head六套、
正常merge及exact-main回读分别取证。当前合同与只读评估完成，最小repro尚在做；
尚无新UI、浏览器或本批CI合格声明。此批之后同一UI版本仍有Doctor、Logs、
Settings、Login、NotFound五页与跨页收尾，不以本批或内部PR代替整个版本完成。

## 11:04 UTC 独立真实RED与有界修复卡

[Draft PR158](https://github.com/ForceMind/agentbox/pull/158)的test-only RED head
15fd489cceedf6342c867e53b9bc727f482341b8，tree7b1be952d45fe3ca92624a26094ac19ce437cbcc，
生产七文件相对main38bd逐字不变。新App.agentManagementScope.test.tsx共4项：
Codex Pair与Claude pane output各shown/pending。测试只替换HTTP响应，运行真实
App/AuthProvider/route/API client/product hooks；A-CSRF logout403→真实auth/me安装
同admin的Session B→B-CSRF logout500，route仍authenticated。请求顺序、身份边界、
仅一次敏感请求及无隐式重放均已通过，4项只在旧内容应不再出现的DOM断言失败。

作者与独立审查者各自实际运行得到4 failed/exit1；官方Frontend37611857222/
job112760720426也精确为4 failed/1800 passed，唯一失败就是保存的4项RED。
测试Git blob ac43445c5078dec8f74b444601c63f3a67cba36d、SHA256
5dea0491c1a5e0bba3d5a1d1fbda80bbc9c4b4cf9b84a3ab9f444d02a33a8148保持冻结。

已有授权内的修复卡限useCodex、global useClaude及必要的Codex/Claude页面局部
确认/clipboard反馈：为当前api/auth status/user/session/CSRF绑定opaque owner，
render即遮蔽旧owner状态；入口、await后、finally、TTL与clipboard回执验证owner/
request身份。取消旧pending本地观察，不能声称撤回已提交Runtime动作；旧callback
不发新请求、不清新owner、不重放。保留同Project dedup/revision/override、能力
条件、90秒展示期限和所有request预算。useClaudeProject/AuthProvider/API/Runtime/
credential/grant均不变；共享ApiClient既有全局401 fail-closed恢复不是本卡新增的
management owner隔离保证，不冒称整个auth recovery已经重做。

修复与视觉迁移分别提交。当前修复仍在实现/独立回归审查，尚不称最终GREEN、
新UI或本批完整资格；不得合并RED头或以原基线检查替代候选证据。

## 11:20 UTC 独立owner修复GREEN，另启视觉迁移

修复已另立remote commit b9e321f462bda8b5c2f9ef79a6ba79c842764803，tree
79c0e76e78a43c6d3959853d21db25907755dd39；原RED15fd仍完整在历史中。生产只改
两个management hook与两页必要的确认/Copy反馈，另有两页既有mock接口适配和
一个独立ownership回归文件。没有提前混入新视觉布局。

原4RED全文逐字转GREEN；独立7文件78/78 passed，包括新增18项first-render遮蔽、
旧closure/late result/finally、显式新scope重试、同scope去重、A→B→A、StrictMode、
unmount、90秒展示timer与clipboard回执/反馈timer。审查发现的Claude双GET一端
失败后取消剩余请求，以及metadata refresh后Copied反馈滞留，均在本卡修正并验证。
Web tsc、targeted ESLint/Prettier和diff检查exit0；未把Web tsc称为整个monorepo检查。

独立source review CLEAR，useCodex SHA256
9788435a4d9df31c28feff74293c8ead7a9dbe07d232daf8676bb1199e1657e3，useClaude为
35d7a0ec37910008543d6162a2d283700b4c34f2558c255233ae6cb7254da377，新增ownership
测试为935040ea2c4fc21ee7a968100fb7d62eac5bc921720e55e0c8364fbbe1306cf3。原4RED与
useClaudeProject段落逐字保持；共享ApiClient全局401边界、所有权限/预算不变。

此后在独立提交中继续两个页面return JSX、作用域CSS与catalog呈现。不得改已审
owner/pre-render/handler语义，保留immutable回归；新metadata图必须完全排除Pair/
output请求与内容，另加capture-off真实App浏览器验证相同A/B session流程。完整
本地质量、最终UI exact-head六套、实际PNG与main资格仍须重新取得。

## 11:51 UTC 完整管理页UI候选与本地检查

两个页面return JSX、作用域CSS及typed catalogs已另立视觉提交；相对修复48b42，
两页pre-return component body逐字相同，独立AST复核Codex21/Claude11个callback/
control/ref属性与各32个条件guards保持。原7+1页面测试正文保留，最终Codex53+
Claude33共86项，通过双语/状态/准入/Project局部错误/长inert值及确认键盘回归。

静态审查发现全局≥640px runtime-details子div仍强制min9rem双列，与新dl的2/3列
窄格嵌套冲突。仅在新页面作用域设单列、小gap和顶部对齐，另补真实dt/dd四边
containment、文字溢出与label→value顺序检查，覆盖所有40ready矩阵和4preview；
不是CSS字符串snapshot。新fixture最初只记录外域未阻断，已改最后注册catch-all
拒绝所有foreign origin、API handler再次检查；同源才fallback。两个source阻塞
都已独立复审CLEAR，没有修改产品权限或预算。

新两spec静态110 registrations（预期69执行/41自管理矩阵重复项目skip），计划
68metadata-only PNG：40ready、24双语状态/确认、4正常中文preview。独立检查
60份实际builder payload通过production DTO decoder，精确为48metadata+12scope。
独立capture-off4场景跨两端验证真实App的shown/pending Pair/output与A/B auth切换、
取消后的迟到server reply、B显式动作/Hide及无重放。不把route.fulfill完成冒称
已取消fetch仍执行late finally；忽略abort的callback/finally由冻结18项单测证明。

最终本地1900 Web+6 extension、全lint/typecheck/format/build、778 doc links、
diff检查均exit0；保留既有Vite大chunk提示。新增测试曾误用3处Testing Library
getByRole exact option，已删除无效参数（字符串name本身精确匹配）并复验；不是
产品RED或权限断言弱化。source/owner修复/fixture独立审查均CLEAR，原4RED和
ownership18文件hash保持。b9修复头六套首轮通过，但本次最终UI头/真实新browser/
68张原PNG/main资格尚待，不能借旧CI或源审查声称本批最终合格。

## 12:17 UTC 实际浏览器失败与最小测试修正

完整候选81e33db9373c7f3b911bb753ce397635a75dfc18的五套CI首轮成功；Backend
实际3.11.16/3.12.14/3.13.16各5375passed/88skipped，native3.13.16为109/1、
pinned1/33及sanitized60/1；Frontend1900+6。正式E2E37617402586/job112778964183
为458passed/156skipped/6failed，未合格、未合并、不重跑该失败头。

失败源码确定为两处新测试错误：中文正式catalog为“安装冲突”而非“冲突”；
AppShell在Session A→B时会关闭mobile drawer，旧测试却在关闭后等待抽屉里的
logout alert。只修两份新spec：精确中文值，及等待真实B-CSRF logout重试500后
通过实际导航按钮重新打开、验证完整失败提示、关闭。保留owner/CSRF/late reply/
无重放/敏感请求次数等所有断言，capture-off与产品源码不变，绝不加skip或预算。
新头仍需独立审查和实际六套CI，静态collection保持110注册。

早期1d2头E2E37615307106/job112772115065为394passed/115skipped/1failed：
中文Codex确认时背景事实badge确实溢出。11:51记录的scope CSS单列修正解决
这项生产布局问题；81e33中全部既有浏览器测试通过，不将旧失败抹去。

81e33的artifact11480484421为47,009,489bytes，SHA256
dd32caef4cf987d6417281152f57d06080601354166485972f18dca470212d4c；官方文件
materialization后验证digest/ZIP CRC/安全PNG路径。包含264PNG，其中66张本批
metadata图（计划68，中文conflict和后续unauth未执行到），无Pair/output内容。
四张正常中文desktop浅色/mobile深色已实际检查，完整66图独立逐张像素审查已完成；
当前预览不能被当成失败候选已通过的资格，最终新头仍须重新取得完整68图。

独立像素审查进一步发现Claude英文极长Project名称会在768/1024/1440把Session
状态挤成2–3行字母；正常名preview不受影响。另立最小页面CSS修正，仅将状态组
设max-width:100%与flex-shrink:0，完整Project名称仍正常换行、不截断。新增真实
DOM文字行几何检查，覆盖既有全部矩阵，不靠CSS snapshot。该问题涉及12张长名矩阵，其他54张（含4preview）通过；
两spec修正及最小CSS/几何回归独立source review CLEAR。修后实际像素仍待新
CI，不用未跑浏览器的静态检查冒称修正已验证。
