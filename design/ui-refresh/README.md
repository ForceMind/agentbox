# AgentBox UI design study 01

**状态：待视觉审阅的独立设计提案，不是生产前端升级或发布。**

- 基线：`a1cab129f18ede5b982b6ab53d037c51771b4dea`
- 分支：`design/agentbox-ui-study-20261005`
- PR147 工作概览候选：`09e3142b145e30d60c9342f2100d6c80682824be`，仅参考合同，不编辑其 worktree
- 日期：2026-10-05

## 打开与体验

直接用现代浏览器打开 `index.html`，不需要安装依赖或登录。文件是自包含的 HTML/CSS/JS，无远程字体、脚本、API、遥测、存储、凭据或服务操作。所有数据均为虚构设计样本。

可体验 14 个页面：工作概览、待处理、项目、项目详情、Agent 工作台、代码变化、文件、产出、审批、Agent 管理、设置、首次引导、系统状态、设计导航。右上角可切换深浅主题。底部“状态演示”可查看加载、空、失败、权限和过期状态。Cmd/Ctrl+K 只导航。

移动端使用四项底部导航；工作台在对话与检查面板间切换，避免在窄屏压缩双栏。消息只留在页面内存中，不会发给真实 Agent。关闭/重新加载文件即可清除。

“规划样本”表示完整功能清单里的后续能力；不能把结构化对话、Files、审批、产出或多会话按钮当作已经实现。现有 WAW、内容准入、Runtime/Secret authority 不因设计稿而改变。

## 验证

`node design/ui-refresh/verify.mjs` 使用仓库既有 Playwright 依赖和 Chromium，运行隔离 HTTP 预览。检查 14 页 × 5 视口、交互导航、浏览器返回、modal 取消/Escape/焦点返回、搜索、长文本安全呈现、手机面板/键盘视口、状态清除和无外部请求；保存真实 PNG 和 JSON 证据。

本地 `node --check` 与内联 JS 语法通过。此 executor 的 Chromium 启动被 AF_UNIX 限制阻止，升级执行路径发生 bwrap mount 错误；没有把这两次尝试记录为视觉通过。远端专用 `UI Design Preview` workflow 仅渲染设计文件，`contents: read`，不改产品 CI/部署/权限。最终结果以 exact-head workflow 与 `verification.json` 为准。

原型中文文案已做完整首轮设计；正式迁移仍需要 zh-CN/English 双 catalog、真实屏幕阅读器与设备键盘回归，不声称完成 WCAG 审计。

详见 [设计与迁移说明](DESIGN.md)。

### 验证历史

- `073bd5b` / run `37353608583`：首轮发现 Files 样本正文用了第二个 h1，严格页面 heading 检查失败；修正正文为 h2，不放宽唯一主标题检查。该轮未生成 PNG，不能记为视觉通过。
