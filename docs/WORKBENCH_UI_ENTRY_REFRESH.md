# A2 UI 接续：Login / NotFound

## 基线与有界目标

接续同一 0.3.0-rc.31 UI 版本，迁移现有登录与未找到页面的呈现、页面作用域 CSS、
typed zh-CN / English 文案和必要回归。暖白、墨色、琥珀仍是可回退的实施选择。
本地起点为 PR160 正常合并的 main d9ab2f695b175d4779471a8e152f8950e95cd321，
tree 0992054062f780523a8b53e1588a40bb139a3977，与合格 head a02d9ae 完全同树。

PR160 六套 exact-head 和六套 exact-main 均首轮成功；main 23 success / 3 规定 skip，
Frontend 1945 Web + 6 extension，Backend 实际 Python 3.11.17 / 3.12.14 / 3.13.15
各 5375 passed / 88 skipped，native 3.13.15 通过；E2E 566 passed / 222 skipped，
21 preflight，无 failed / flaky / retry。独立 source、官方日志、main tree 审查 CLEAR。
80 张 head 图经独立资格化，main 按同树继承，未声称重复查看 main 图片。
历史 native READY 间歇问题仍开放；本批不是该问题根因修复或真实 host 资格。

PR159 的 Kebui 品牌与 U0–U5 规划由独立作者协调，当前组合头为
69c5054e74cae0f8070c8feb50f559fbc10882ab。先完成本批独立源码与本合同，不抢写
CURRENT_STATE / INDEX / NEXT_ACTION。创建下一 PR 前 fresh 读取 main，正常合入
已批准规划并保留双方历史与合法 YAML；不以此卡执行项目/Runtime 名称替换或新聊天能力。

## 现有登录合同

LoginPage 仍使用 AuthProvider 的 login；只允许非空白 username 和非空 password 提交。
trim 仅用于判断可提交，传给既有 API 的 username 保持原值。既有 finally 清空 password，
保留 username；提交期间按钮禁用，inputs 原本可编辑，本批不据此自动加入新 owner / retry
框架。helpers、pre-return 控制体和 handleSubmit 保持；不得修改 AuthProvider、API、
cookie、CSRF、权限、deadline 或 Session 语义。

保留 username 的 autoCapitalize=none、autocomplete=username、autofocus、maxlength=64、
required，以及 password 的 type=password、autocomplete=current-password、maxlength=1024、
required。错误只保留规范化 code / status / retryAfter / safe request ID，不显示 server prose。
401 与 429 映射不变，retryAfter 仅为既有提示，不新增倒计时或自动重试。
request ID 仍经过 technicalApiIdentifier 后在可键盘操作的 details 中展示 TechnicalValue。

保留 ControlPlanePulse 的独立 health GET、本地管理员说明与版本；健康状态只说明 control plane。
登录后的 PublicOnlyRoute 固定 replace 到 /dashboard，产品当前没有 returnTo 恢复合同，
本批不添加。initial /auth/me、AuthBoot、401 清理与原 10 秒 API timeout 保持。
替换“Runtime 将于后续阶段提供”的过时产品介绍，准确描述现有 Project / Workspace 软件，
不宣称所有 Agent 已认证、真实 host 已通过或生产配置已完成。

## 现有未找到页面合同

NotFoundPage 位于 AppShell / guards 外部，不发送自己的 API、不显示不存在的 path / query。
只保留原单一 Link：authenticated 前往 /dashboard，其余状态前往 /login。
checking 时当前就是该页及登录目的地，Auth 状态变化后链接更新。本批不添加 history.back、
搜索、刷新、第二操作或新路由，也不把导航文案改成真实浏览器后退语义。

## 回归与图像边界

保留全部既有 App、auth、rc9 auth-shell、技术值与敏感场景断言。
新增实际 API / parser / AuthProvider / App 的必要覆盖：失败清密码保用户名、再次显式提交清旧错、
keyboard Enter 和 pending 请求计数、timeout / 网络失败后手动重试、外部或 protocol-relative
returnTo 仍固定 /dashboard，以及 NotFound auth-checking 更新、实际点击和 Back / Forward。
只有真实 RED 证明违反原合同才另立最小修复卡并独立审查，不以猜测修改认证行为。

图像仅使用新的隔离 same-origin synthetic HTTP 场景；无真实账户、登录凭据、Provider、
Pairing、output、patch、文件正文或额外 Runtime 请求。保留全局与旧敏感 suite 的
trace / video / 自动截图 off，新图使用单独精确前缀。每次显式截图前全部 input value 必须为空；
错误场景若用合成提交，产品必须先清 password，测试再清掉按合同保留的合成 username。
填充中和 pending 的功能测试不截图，不为截图改变 username 保留语义。

新 fixture 在 fulfill 前验证 origin / method / path，只放行现有必要 GET 和明确隔离的
synthetic login POST；拒绝意外 mutation、foreign origin、WebSocket。截图前检查当前 route、
fixture 来源（独立 context、精确 origin/path、受限请求和已完成 auth/me）、无 server prose /
canary / sensitive DOM / 输入值 / 非预期 storage 或请求。匿名页没有账户 DOM marker，
不注入或伪称该 marker；截图额外要求对应页根可见、AppShell 不存在。
覆盖 zh-CN / English、light / dark、360 / 390 / 768 / 1024 / 1440，加 900 / 960 原登录
断点。使用实际 DOM Range / 几何、Tab / Enter、error details、焦点和 44px targets；尊重
forced colors 与 reduced motion。旧 900px 固定列宽仅为源码风险，尚未称实际 pixel bug。

## 交付次序与剩余范围

小稳定提交先保存源码；Draft PR、适用本地完整质量、独立 source / 实际原图、
exact-head 六套、正常 merge、exact-main 六套和实际 tree 分别取证。
与 PR159 串行移动 main，不借旧批次 CI 或旧图声称新候选已完成。
本批后同一版本只剩跨页面一致性、现有导航 / 标题 / 主题 / 双语 / mobile / Escape /
焦点 / Back / 刷新 / logout / 401 / offline 的收尾证据；复用已有 currentness 与敏感 suites。
不新建测试平台、业务功能或安全权限，无 release / deploy / 真实 host 激活。

## 15:51 UTC 源码与本地候选

已分别提交合同、五个产品文件、三个新回归文件、404 数字行高微调及隔离 browser
覆盖。Login helpers/pre-return/handleSubmit、输入/error JSX 与 baseline 逐字一致；
404 原 status-dependent Link 不变。source review 与补充 capture/CSS review 独立 CLEAR。
新 26 项为 Login presentation 8、NotFound 2、真实 App 16；作者连同旧 Login/App
53 项通过，独立 35 项通过。没有产品 RED；实际键盘 Enter 仍待 browser，而非拿
Vitest fireEvent 当原生键盘证据。request ID 72/73 字符、控制字符/markup/对象边界
经实际 parser 测试；API timeout 仍 10 秒，429 没有倒计时或隐式重试。

本地完整 1971 Web + 6 extension、monorepo lint/typecheck/format/build 与 784 相对
doc links 均 exit 0。保留原 Vite 大 chunk 与 npm 环境配置提示，不修改依赖或 budgets。
独立复核发现 404 巨字 line-height=1 可能与严格字体 Range 行框不兼容；只调整到
1.25 并保留全部几何断言，尚未实际浏览器复现，不能称产品 RED 或已验证像素修复。

新 ui-entry-pages spec 静态 132 注册，预计 84 执行 / 48 自管理矩阵重复 skip；
计划 60 图为 48 空表单/404 双语主题宽度、6 清空输入后公开错误、4 health 状态、
2 已认证 404。使用 production App / AuthProvider / API parser 与独立受限 HTTP；
synthetic login 只在测试显式允许的次数内，body 原地校验、不保存或输出。
首次源码自查修正 bdi selector、超长 request ID 与 missing path 广义 canary 误用；
missing path 在 URL 合法存在，只要求页面不回显。原 password-bearing auth suites
保持 capture-off；唯一旧 E2E 修改为 404 标题文字期望，原可见/语义断言不变。

PR159 已于 15:45:37 UTC 正常合并为 main
99ae3d67981e860ea4f6cabb8c6dd416b358a8d0，tree
a8ac8ca6bc56357a79b4be3839187c294704b297，与合格组合头 69c5054 相同。
九份 planning docs 已重新读取；main 六套仍由该批作者跟进，不能提前称合格。
本批正常 merge-forward 保全其文档后再取得新 exact-head CI 与原图，不覆盖双方历史。
此刻实际 browser / 60 图 / exact-head 六套 / main 资格尚待，没有创建或合并本批 PR。

## 16:18 UTC 同一候选纳入跨页标题收口

[Draft PR161](https://github.com/ForceMind/agentbox/pull/161) 已创建，初始组合 head
0042964b5b6e552e9d344be2670e3ac867c69d77 的五套 workflow 已首轮 success，
Frontend 官方日志确认 1971+6，E2E37648558752 仍在运行。该头不提前称全部合格。
PR159 的 main99ae3d6 六套首轮成功并独立闭环，规划整合不再 pending。

独立只读盘点发现跨页唯一需要补充的是 Attention/Changes 精确 document.title 与
既有 history 后的 title；其余导航/modal/Session/offline/currentness 已有实际回归来源。
本候选以单独 test-only 提交在五个既有 spec 加 21 行、移除 1 行等价 toHaveTitle：
复用 assertRc9Title，不导入产品 catalog，保留 DOM/URL/lifetime 与全部原断言。
五文件静态注册前后同为 502，忽略行号后 identities 完全一致；typecheck/lint/format
均 exit 0。没有新增 fixture、case、skip、matrix、timeout 或截图，产品字节不变。
[U2 验收映射](WORKBENCH_UI_U2_CLOSURE.md) 将这些既有证据逐项列明；最终组合
head 的 browser/60 图/六套与 post-main 才能关闭该记录，不另起纯断言产品版本。

一次后续 npm exec 查询 registry 返回 HTTP403，已停止该网络路径；最终定向检查与
build 使用原已安装 pnpm 的本地入口，均 exit 0。未尝试绕过网络或 local browser 限制。

## 16:22 UTC 首轮浏览器失败与严格 hold 清理更正

16:22 更新：0042964 的 E2E37648558752/job112885601067 首轮终态为
642 passed / 270 skipped / 8 failed，五套其余 workflow 成功。失败均为新 entry spec
finally 错用严格 release（未 held 或已 release）；仅改用既有 dispose 做 cleanup，
显式 release 保留并等待 held。产品/预算/断言/skip 不变，不重跑失败头取绿。
后继组合 head 含跨页标题与该 test-only 修正，仍需完整自身资格；未提前称图像通过。

原 helper 的 release 明确拒绝未到达或重复释放，dispose 才是幂等清理。
三个 finally 改 dispose，两处正常显式 release 前 waitUntilHeld；不修改共享 helper。
实际最终 browser/pixel 仍待，新本地 type/lint/format 与 132 静态注册保持。
