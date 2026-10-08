# Kebui U1 · Design draft 01

日期：2026-10-08 UTC。状态：**可打开的合成原型；受控 Chromium 与 24 图范围复核通过；完整候选 CI/合并以 PR163 为准，物理设备未验。**

直接双击 `index.html`，无需安装依赖、服务器或网络。首页是 `#home`；`#catalog` 列出全部 21 个画面。HTML 包含所有 CSS/JS；其他文件不是打开时的依赖。

顶部持续显示“设计演示，不连接 Agent”。所有项目、消息、身份、编号、代码、时间和结果都是合成数据。没有后台 API、模型调用、真实账号、仓库读取或运行命令。CSP 禁止网络连接、外部资源、表单提交和对象嵌入；不使用 cookies、localStorage、IndexedDB 或 service worker。刷新清除整个演示。

## 交付物

- `index.html`：自包含离线原型。
- `tokens.css`、`styles.css`、`app.js`：可审查源码。
- `build.py`：Python 标准库生成 HTML，运行 `python build.py`。
- `REFERENCE_EVIDENCE.md`：来源证据与缺项；没有转载第三方私人截图。
- `reference-board.html`：可直接打开的文字型参考板；是设计整理，不是参考产品截图。
- `COMPONENTS_AND_MAPPING.md`：tokens/组件说明、六组画面、已实现与未实现的产品映射。
- `REVIEW.md`：实际检查范围、失败记录、NOT RUN 与下一步。
- `verify-regressions.cjs`：独立审查问题的11项回归（含RED→GREEN证据）；证据位于 `evidence/regressions-{red,green}.json`。
- `verify-dom.cjs`：jsdom 逻辑检查；不具备布局或浏览器资格。
- `verify.cjs`：可移植 Chromium 点击/几何/截图验证脚本，交给允许启动浏览器的 CI 执行。
- `evidence/dom-verification.json`：实际 DOM 测试结果；真实 Chromium 图像和报告由 CI artifact 保留，详见 REVIEW。

## 三条旅程如何点击

### A · 交代工作并检查结果

1. 首页 → 新建工作 → 显式选择 Project 与 Codex / Claude Code → 确认范围。
2. 编辑合成请求；Enter 换行，Ctrl/Cmd+Enter 提交。中文 IME 组合事件不提交。
3. 查看“已接受，尚未开始” → 点击“演示：开始执行” → 点击“读取完成证据”。这两个按钮是显式推进 fixture，不是假实时动画。
4. 检查结果 → 显式读取合成正文 → 统一 diff / 原文 → 返回原对话。
5. 失败：顶部场景选“失败”，提交后无接受回执，显式重试。中断：选择“中断”提交或点击“演示断线”，状态 UNKNOWN，进入恢复，不重发。

### B · 等待用户确认

1. 首页待确认条目 → 申请者/owner/Project/两个合成路径/request/revision/有效性/后果。
2. 成功场景批准 → 演示回读批准 → 后续执行；可独立拒绝。
3. 失败或中断场景批准 → 提交结果 UNKNOWN → 只读回查 → 旧 revision 失效。
4. “演示过期”使旧按钮失效；显式获取新请求增加 revision。重新确认只覆盖新 revision。

有效期为场景模型，不是真实倒计时 TTL。没有真实请求或审批。

### C · 手机回来继续

1. 手机宽度下打开 `#recovery`，或执行对话点击断线。
2. 成功/中断场景 → 重新核验身份与状态 → 显示合成运行状态，原请求不重发。
3. 失败/未知场景核验仍未知，不允许停止未知目标。
4. 已核验后 → 查看精确停止目标 → 可取消、也可确认合成停止与回读。
5. 退出查看不停止运行；中断轮次、任务级取消、exact Stop 分开。任务级取消明确为 K3 规划，不假装已实现。

## 设计控件

- 顶部：场景（成功/失败/中断/过期/空/未知）、浅深主题、zh-CN/English。
- 设置：大字体展示（非浏览器 200% 缩放资格）、身份失效模拟。
- 手机：导航按钮打开原生 dialog；检查页为单主区；按钮目标至少 44 CSS px；safe-area 输入区。
- 同一作用域草稿保留在内存中；新工作、Project/Agent/身份切换清除旧正文和审批。不支持真正跨设备持久恢复。
- 浏览器离线/页面隐藏清除已准入正文并进入重新核验状态。恢复不回放任何写操作。

## 可移植验证

在已有 Node 工程、已安装 `playwright` / `jsdom` 的环境中运行：

```sh
python build.py
node --check app.js
node verify-dom.cjs
node verify-regressions.cjs
node verify.cjs
```

脚本默认 `require('playwright')` 和 Playwright 已安装的 Chromium。可选 `PLAYWRIGHT_PATH` 指向已安装模块；`CHROMIUM_PATH` 指向允许的本地浏览器。DOM 脚本可选 `JSDOM_PATH`。没有自动安装或下载。

浏览器脚本意图覆盖：三旅程、IME、重复发送/批准、返回/前进、作用域清除、21 页面、五宽度 × 双语言 × 双主题 × 六核心组、390px 大字体及零外部请求。成功时生成 24 张六组桌面/手机浅深截图及 `evidence/verification.json`。脚本存在不等于执行通过。

## 重要边界

U1 是设计准备，不是 K2/S03/WEV 或 K3–K7 已完成。既有 Job 不改名为 AI Task；不解析终端文本为工具事件；本原型不进入现有生产路由、不替换 rc31 页面。技术服务/API/包/仓库/数据库名保持不变。

墨绿强调色、简化 k 标记是可撤销设计提案，不是已获 Owner 最终确认的 Logo/配色。初始离线制作阶段没有远端提交；后续源码和证据已通过 PR163 交付。没有发布站点、部署或真实 host 激活。

## 本轮实际资格（2026-10-08）

源码67d79b05的真实Chromium151.0.7922.34通过三旅程、120几何、21页手机大字体、
11回归和504DOM组合。24图经独立像素范围复核，旧toast遮挡与手机上下文缺失已修。
截图/功能不是最终品牌定稿；真实Agent/账户/设备无接线或资格声明。
本次后继文档包不改变HTML/交互源码；完整六套CI与合并终态见
[PR163](https://github.com/ForceMind/agentbox/pull/163)。
