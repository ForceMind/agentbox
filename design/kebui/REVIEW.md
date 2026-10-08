# U1 draft 01 review record

时间：2026-10-08 UTC（会话权威 UTC；不使用沙箱操作系统的历史日期）。检查者：原型实施者，自查，不是独立评审。

## 实际通过

1. `python build.py`：exit 0，生成自包含 `index.html`（初稿57,384 bytes；修正后大小与最终 hash 见产物及 `SHA256SUMS`）。
2. `node --check app.js`、`node --check verify.cjs`：exit 0。
3. 已安装 Prettier 3.9.6 格式化源码、CSS、验证脚本和文档；不下载新依赖。初次误指定本地 3.6.2 路径产生 MODULE_NOT_FOUND，改用实际已装 3.9.6 后成功；不是产品失败。
4. `JSDOM_PATH=<existing jsdom module> node verify-dom.cjs`：exit 0，jsdom 26.1.0。三旅程的成功/失败/中断、IME、Enter不提交、Ctrl+Enter、重复发送/批准、审批失效/新revision、只读回查、合成exact Stop取消/回读、detach区别、转义输入、Project/Agent匹配、作用域清除、离线清除正文均通过。
5. 21 画面 × 2 语言 × 2 主题 × 6 场景 = 504 DOM渲染组合通过。**这不测 CSS 几何、可见性、像素、真实焦点或屏幕阅读器。**
6. 原型源码不包含 fetch、WebSocket、XMLHttpRequest、Worker、存储 API 或外部脚本/资源；CSP明确禁用connect/form/object。此结论为静态/DOM证据，浏览器网络观察尚未执行。

证据文件：`evidence/dom-verification.json`。原型与主 checkout 分离；本批未写主源码、未远端提交、未发布站点。

## 真实浏览器：NOT RUN

本地 `/usr/bin/chromium` 存在，但普通启动以及一次已获准的执行环境升级尝试均在启动阶段失败：

```text
FATAL: chrome/browser/process_singleton_posix.cc:297
socket() failed: Operation not permitted (1)
```

两次 exit 1，没有打开页面、点击或生成截图。按协调要求停止尝试，不绕过该限制。没有把本地DOM测试写成浏览器PASS，也没有伪造PNG或宣称像素验收完成。

`verify.cjs` 已改为默认加载标准 `playwright` 模块与其安装的浏览器，支持可选模块/可执行路径变量；不硬编码本沙箱路径，不自动安装依赖。后续由集成者放入现有允许运行 Chromium 的 CI。

## 待执行矩阵与缺口

- Chromium三条完整实际点击路径，包括失败/中断、重复操作、Back/Forward、dialog Escape及焦点返回。
- 360/390/768/1024/1440px × zh-CN/English × 浅/深主题 × 六核心组的页面几何检查。
- 1440/390px、六组、浅/深主题共24张代表图；必须真正打开原图像素检查，截图数量不是完整验收。
- 21画面的大字体设计模式；真实浏览器200%缩放、长项目名/长中文英文消息压力测试尚未执行。
- 各扩展页目前的失败/中断/空/未知主要用共用状态说明，尚不是全功能状态机。任务取消、交接/路由、Files/Artifacts、历史/记忆、协作仅明确规划说明。
- 真实浏览器可访问性、键盘焦点/读屏、反复开关dialog、横竖屏、软键盘、安全区、物理Android/iOS均 NOT RUN。
- 参考截图与具体产品页面取证仍有 UNKNOWN，详见证据表；本批不宣称完整U0退出。
- Logo/强调色是探索方案；未完成最终资产确认。
- 生产S03/WEV/K2/K3合同、网络接口、真实账号/Agent/host、跨设备恢复、发布/部署全部不在本次交付范围。

## 下一项有界工作

集成到独立 `design/kebui/` 范围，保持生产包/路由不变；执行随包浏览器脚本，修复实际发现的问题，人工查看代表图，补齐缺项后再判断“U1可评审”门槛。当前可描述为“合成原型实现与DOM自查已交付，浏览器/像素资格待CI”，不能描述为“完整UI已完成”。

## 独立审查修正 · 2026-10-08 02:38 UTC

审查实际指出的原缺陷全部保留为失败证据，而不是覆盖成初次通过：

- 已核验后 offline 没清除 recovered，未知状态仍可能打开 Stop。
- Stop dialog 在 hidden 后仍开放，旧确认能修改 stopped；最终确认未重新比较目标。
- Agent picker 在确认前清空草稿/审批并改变 Agent，取消不能恢复。
- skip link 的 `#main` 误入 hash 路由，被当404并清草稿。
- 停止后再次核验把 phase 设置为 running，与 stopped=true 矛盾。
- 审批申请者固定 Codex，与已选 Claude Code 不一致。

实际在未修改旧HTML上执行 `verify-regressions.cjs`：8项 FAIL，exit 1（`evidence/regressions-red.json`）；相同回归在集成目录新HTML上8项 PASS，exit 0（`evidence/regressions-green.json`）。这包括新增请求ID/创建次数/接受次数的验证，旧版本因无这些证据而失败。基线读取只用于证明RED，未写旧目录。

修正：统一失效清理与关闭dialog；Stop绑定owner/Project/Agent/session/epoch/revision/recovery generation，确认时检查dialog仍开放、在线、已核验、running、未停止、页面可见与精确目标一致。新的显式核验清除旧确认，已停止fixture保持停止。Agent picker仅保留临时选择，确认才清理并commit；取消/Escape不改变范围。skip只focus main，不改变URL/路由。审批显示当前真实（合成）申请者。

发送回归增加合成requestId、requestCount、acceptedCount、sendAttempts；失败测试断言实际消息和新请求ID，重试复用ID，重复发送不增加接受次数；revision断言严格before+1；运行中detach不改stopped；作用域确认清理与取消保存分开。

已重新生成HTML、格式化、语法检查，并重跑504组合DOM检查与8项回归，均exit 0。`verify.cjs`补充同样的离线/hidden失效、旧确认、恢复停止事实、Agent取消/Escape、真实键盘skip、请求计数与作用域清理。浏览器仍NOT RUN；其中hidden/offline用明确注入事件验证handler，不冒充物理OS切后台资格。

### 最后的小缺陷与键盘加强 · 02:42 UTC

新工作只选择failure场景时尚无requestId，原retry按钮可点却无效果。新增回归在修正前实际exit 1（`evidence/retry-red.json`），现改为禁用retry并说明先提交合成请求；真实合成失败请求建立后才启用。最终10项回归exit 0，504 DOM组合仍通过。

浏览器脚本增加Enter后textarea实际包含新增换行的断言、isComposing的Meta事件不发送、Meta+Enter提交与新failure场景的retry禁用/启用。DOM已验证isComposing和Meta+Enter处理逻辑；浏览器仍NOT RUN，Mac物理键盘/IME仍未资格化。审批revision与TTL仍是合成状态演示，不是实际协议验收。

## 2026-10-08 02:49 UTC 实际 Chromium 与像素修正

head65b56574 的 E2E37719502975/job113123651430 真实 Chromium151.0.7922.34
通过三旅程、120核心画面几何、21页390px大字体、键盘/回退/失效回归，零外部请求和
pageerror。Artifact11524474223（2,569,439bytes，SHA256
`595f14654b69b744e064764eb0dd7b04e80079b18e6607e8d68d250fe54c2dbc`）
含24PNG，来源精确head已核对。该结果取代本批此前“浏览器全部NOT RUN”的历史状态，
但仅对该head成立，本地浏览器仍受EPERM限制。

实际打开home1440-light与work390-dark原图发现旧Stop失效通知持续覆盖后续画面；
同时截图直接设置running却继承未提交requestId，视觉证据不一致。保留旧图及成功CI
为历史，不称该图全部合格。修正toast可关闭/6秒到期、导航/作用域清理与新消息代次
保护；新定向回归先在旧HTML真实RED，再新HTML GREEN。截图fixture每画面重新建立
一致合成Project/Agent/requestId/状态，Results样本显示合成已准入结果；浏览器先测
真正读取动作，再拍示例。未隐藏通知来绕过断言。后继head和24张新图须重新验证。

参考来源本轮补读官方公开文本，详情追加到REFERENCE_EVIDENCE。HAPI/CloudCLI的
AGPL许可不同于既有Paseo Apache来源，不迁用其代码/资产；截图与真实产品流程仍UNKNOWN。

## 2026-10-08 02:59 UTC 手机信息可达性补修

最新e7d5e928设计job113125470989通过全部DOM与Chromium检查；artifact11525585683
含24图，2,478,836bytes，SHA256
`eaef328328f7d7a14cff2eab2c4b7b05c08e5eec063678713b2c026cba2a924b`。
独立逐张打开24原图确认旧toast已消除，没有像素溢出或遮挡；但指出手机隐藏了
context-panel，致工作授权边界、审批身份失效入口和结果真实CI未知说明不可达。
这是响应式信息完整性缺口，不能用静态像素CLEAR掩盖。

删除1100px以下对context-panel的display:none，让其随单列布局自然堆叠，保留
全部说明与操作；为五宽/两语言/两主题的每个核心画面增加面板实际可见性断言。
截图样本固定revision1，避免连续重置导致无意义的样本版本差异。
原图与旧成功CI保留历史；后继head需重新执行与复查全部24图。

## 2026-10-08 U1 可评审产物与品牌主干闭环（03:06 UTC）

PR162 已合并的 main `29adec75b1c6c7912ceacd53a3cbed416ac4aa79` 六套 exact-main
CI 全 completed/success，E2E37719258137；tree 与合格品牌 headfc182c86 一致。
既有 U2 页面与 Kebui 产品标识已软件闭环，AgentBox Runtime/CLI/API 兼容不变。

[PR163](https://github.com/ForceMind/agentbox/pull/163) 的原型 source head
`67d79b05b39fcf4488f1bc84731891f2004d8784` 已实际通过独立设计
job113127190644 / E2E37720626557：Chromium151.0.7922.34三条旅程、120核心画面
几何（五宽/双语/双主题）、21页手机大字体、11项DOM回归、504DOM组合和零外部请求。
[离线入口与说明](README.md)现已存在；21画面和未来能力均明确合成。

Artifact11525846639有24张原图，2,637,482bytes，SHA256
`6dbebb91e6e234f33361b70697d33f53b1b9319bc0c29473b6adf7cac27f3d09`已核对。
独立像素资格为10张改变原图重新打开、14张与前轮已审原图逐字节相同；手机授权上下文、
身份失效入口、真实CI未知说明均已恢复可见，旧通知覆盖和截图状态不一致已修正。
这是明确范围的设计可评审资格，不是整体美观、真实设备或生产功能PASS。

最终文档包据此更新旧“U1未交付/浏览器NOT RUN”顶层状态，保留全部旧失败历史。
source67d79b的完整候选CI尚待终态；本次仅文档/证据清单变更，后继documentation-inclusive
head亦需独立六套CI、正常merge与exact-main回读，最终结果记录于PR163，不借旧绿通过。

当前版本软件/UI收尾范围：既有U2页面、Kebui标识、U1可打开合成设计与本轮实际验证。
U0公开文字来源已补核，参考图片/部分固定版本仍UNKNOWN；不转载私人Cromma内容，
不复制AGPL来源代码。Logo/颜色是探索稿；后续U3–U5、真实host/双CLI/客户端/恢复和
release/deploy仍是独立合同与目标证据，不因原型可点就宣称已完成。
下方旧时间点的pending/未交付与NOT RUN作为历史保留，不能覆盖本节或live GitHub。
