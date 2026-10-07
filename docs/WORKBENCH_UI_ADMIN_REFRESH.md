# A2 UI 接续：Doctor / Logs / Settings

## 基线与范围

本批接续同一 UI 重设计版本，只迁移现有 /doctor、/logs、/settings 的呈现、页面作用域 CSS、
typed 双语文案和必要回归。保留0.3.0-rc.31；暖白/墨色/琥珀为可回退实施选择。
基线为 PR158 正常合并的 main cf710d59cd6c47d7a240c0ce25d7f006d51e374a；
tree df1e0951109f9c35c658e0edcc9b82eccce0d688，与合格e890完全一致。
六套exact-main首轮成功、23success/3规定skip；Backend实际3.11.17/3.12.14/3.13.15
各5375/88，native3.13.15通过；Frontend1900+6，E2E464/156无failed/flaky/retry。
独立main source/官方日志复核CLEAR；68张head图按精确同树继承，未重下载main图。

Doctor 保留五项 control-plane 检查和现有 Codex、Claude、tmux、Projects、GitHub 安全摘要。
Settings 只呈现原六项 policy 事实。Logs 目前只有 PlannedPage，保留明确的
“尚未实现 / 产品预览”和三项计划能力说明，不把导航入口当成日志读取已实现。

不添加 Refresh、轮询、分页、配置编辑、日志读取/下载、修复动作、凭据或 Provider 设置。
不新建权限、业务状态、Job/Audit入口、Runtime能力或秘密处理路径；无真实账号、
host激活、release/deploy。

## 现有读取与语义

三页均位于 ProtectedRoute。Doctor/Settings各自 mount 时通过 useDoctor 一次
GET /api/v1/doctor，保持90秒timeout、unmount/API替换abort及signal迟到结果围栏；
没有页面mutation、确认、Cancel或自动重试。Logs不发自己的API请求。

Doctor顶层ready只取决于五项control-plane检查，不等于所有CLI已认证或Remote可运行。
Runtime异常可仍返回control-plane ready，同时相应字段unknown和finding code；新布局
必须分别表达。三态布尔、capability、authentication、tmux与Remote状态不合并成绿点。

useDoctor只保存projected view，不保存response envelope或server error prose。
Finding code继续按既有大写grammar过滤，未知安全code使用本地通用解释和技术code。
Doctor Project Root继续SafeTechnicalValue合同，包含现有非ASCII值显示Unknown的测试；
本批不以hook注释代替实际页面行为。Settings不顺手暴露Root或额外Runtime字段。

Settings六项为environment、bind address、absolute/idle session TTL、login rate limit、
lock duration；保留现有数字/时长formatter。TechnicalValue保持English/LTR/translate=no。
Logs的三个计划说明继续区分AgentBox、Runtime和Audit，不伪造事件、统计或实时状态。

只读评估未证明本批存在需要先修复的产品问题。useDoctor没有admin/session owner key、
visibility/offline listener是实现事实；其数据是安全工作站摘要，不据此自动移植Agent管理页
ownership框架或扩大本卡范围。若实际回归发现违反既有合同，先保存真实RED并单列最小修复。

## 测试与交付

保留现有projection、技术值、rc9 manifest/secondary-route及真实App测试。
新增Doctor ready与Runtime unknown独立性、not_ready、loading/error、安全finding/长值；
Settings严格六项、三种时长单位、bind不可用和无表单；Logs明确planned且无额外请求。
真实App验证/doctor→/settings→Back的旧held response归属，以及401卸载后迟到结果
不能恢复受保护页面。不要凭空加入页面modal/Cancel/自动重试测试。

通过真实shell覆盖键盘skip link、mobile drawer Escape/焦点恢复、Back/Forward。
新图片使用同源synthetic metadata HTTP与production DTO parser，覆盖zh-CN/en、
360/390/768/1024/1440及light/dark，正常展示图与极端长技术值分开。
仅allowlist原shell metadata与/doctor GET；拒绝意外API/mutation/WebSocket/foreign origin。
trace/video/自动screenshot保持off，显式截图前检查route/account marker、无server prose或
敏感DOM，原敏感测试与全局capture配置不变。

小稳定提交、Draft PR、适用本地质量、独立source/实际像素、exact-head六套、
正常merge和exact-main回读分别取证，不借上一批检查声称本批合格。
历史native READY间歇问题继续开放；软件CI不代替真实host资格。
之后同一版本仍有Login、NotFound和跨页面一致性/导航/Session/离线收尾。


## 13:38 UTC 完整呈现与回归候选

[Draft PR160](https://github.com/ForceMind/agentbox/pull/160)已保存有界合同、七个产品
文件和七个test/helper文件的独立提交。Doctor/Settings helper与pre-return控制体
逐字保持，原状态/错误/技术值读取不变；独立source审查追踪共享CSS各断点与
嵌套runtime-details、长值/header/badge，未见source blocker。Logs继续明确planned。

新增41项：Doctor16、Settings16、Logs2、真实App5、useDoctor lifecycle2。
独立source审查与作者11文件86项实际运行通过；覆盖原检查、六policy、三种时长、
projection/finding过滤、Doctor→Settings→Back真实abort/旧HTTP、401卸载、90秒
timeout和API替换后的迟到失败。原Doctor2/useDoctor3及相关旧测试逐字保留。
首次两项test-only失败为漏计LoginPage自身health GET，已按实际合同补齐census，
全部生命周期断言保持；未发现需修改产品的RED。

本地完整1941 Web+6 extension及monorepo lint/typecheck/format/build通过；原有
Vite大chunk与npm环境配置提示保留。新browser spec另跑定向tsc/lint/format及静态
collection通过，168注册，预计102执行/66自管理矩阵重复skip。计划80metadata
PNG：60双语言五宽度两主题stress、6正常中文preview、14phone状态。真实Tab/Enter、
drawer Escape/焦点恢复、三路由Back/Forward与held Doctor跨路由用例保留。

两个HTTP guard在任何fixturefulfill前拒绝foreign origin，仅原shell与doctor GET，
拒绝WebSocket/意外mutation；截图前验证route/account marker、canary/敏感DOM/
输入/storage/traffic，既有敏感suite与全局capture-off未改。workflow只增加两条
精确ui-admin-pages前缀。首次跨node/app项目导入fixture触发TS6307，保留编译边界，
改用短独立synthetic wire builder，不新增运行时源码加载或修改tsconfig。实际8个
builder变体经production decoder通过，503fixture经真实ApiClient错误路径和fresh
嵌套对象检查通过，不拿另一份手抄payload替代实际builder验证。

新browser fixture/guard/文案/矩阵/几何断言与workflow边界已独立source review CLEAR。
当前仅source/本地回归合格；正式新browser、全部80原图、最终exact-head六套、
正常merge与exact-main仍待，不借35ba早期头或maincf710旧CI声称本批完成。
