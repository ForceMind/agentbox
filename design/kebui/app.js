"use strict";
// All records are local synthetic fixtures. There is intentionally no transport or persistence.
const state = {
  lang: "zh",
  route: "home",
  scenario: "success",
  project: "Meadow",
  agent: "Codex",
  phase: "idle",
  approval: "pending",
  revision: 1,
  draft: "",
  message: "",
  requestId: "",
  requestCount: 0,
  acceptedCount: 0,
  sendAttempts: 0,
  admitted: false,
  online: true,
  recovered: false,
  stopped: false,
  filter: "all",
  search: "",
  scroll: 0,
  large: false,
};
let composing = false;
let requestSerial = 0;
let pendingStop = null;
let recoveryGeneration = 0;
function closeDialog() {
  pendingStop = null;
  const dialog = document.getElementById("dialog");
  if (dialog.open) dialog.close();
  dialog.innerHTML = "";
}
function stopTarget() {
  return JSON.stringify([
    "demo-owner",
    state.project,
    state.agent,
    "demo-session-01",
    7,
    state.revision,
    recoveryGeneration,
  ]);
}
function canStop() {
  return (
    state.recovered &&
    state.online &&
    state.phase === "running" &&
    !state.stopped &&
    !document.hidden
  );
}
function invalidateConnection() {
  recoveryGeneration++;
  state.online = false;
  state.recovered = false;
  state.phase = "unknown";
  state.admitted = false;
  if (state.approval === "pending") state.approval = "expired";
  closeDialog();
  navigate("recovery");
}
const t = (zh, en) => (state.lang === "zh" ? zh : en);
const esc = (v) =>
  String(v).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const btn = (action, label, cls = "", disabled = false) =>
  `<button data-action="${action}" class="${cls}" ${disabled ? "disabled" : ""}>${label}</button>`;
const pill = (label, kind = "") => `<span class="tag ${kind}">${label}</span>`;
const titles = {
  home: ["工作", "Work"],
  work: ["对话工作台", "Conversation"],
  approval: ["等待你的确认", "Your approval"],
  results: ["结果检查", "Inspect results"],
  agents: ["Agent 与环境", "Agent & environment"],
  recovery: ["回来继续", "Resume work"],
  projects: ["项目", "Projects"],
  project: ["项目详情", "Project details"],
  workspace: ["高级工作台", "Advanced workspace"],
  changes: ["代码变化", "Changes"],
  login: ["登录与开始", "Sign in & start"],
  doctor: ["诊断", "Diagnostics"],
  logs: ["日志", "Logs"],
  settings: ["设置", "Settings"],
  notfound: ["找不到页面", "Page not found"],
  denied: ["无权访问", "Access denied"],
  files: ["文件与产出", "Files & artifacts"],
  history: ["历史与记忆", "History & memory"],
  handoff: ["Agent 交接", "Agent handoff"],
  team: ["协作空间", "Collaboration"],
  catalog: ["画面与状态目录", "Screen & state catalog"],
};
const title = (k) => t(...(titles[k] || titles.notfound));
function nav() {
  return `<div class="brand"><span class="mark" aria-hidden="true">k</span>Kebui</div><div><p class="eyebrow">${t("你的工作空间", "YOUR WORKSPACE")}</p><div class="nav">${["home", "projects", "agents", "catalog"].map((k) => btn("go:" + k, title(k), state.route === k ? "active" : "")).join("")}</div></div><div><p class="eyebrow">${t("最近的合成项目", "SYNTHETIC PROJECTS")}</p><div class="nav">${btn("scope:Meadow", "◌ Meadow")}${btn("scope:Observatory", "◌ Observatory")}</div></div><div class="sidebar-foot"><div class="nav">${btn("go:settings", title("settings"))}${btn("go:doctor", title("doctor"))}</div><small>${t("仅本次页面内的合成状态", "Synthetic state in this page only")}<br>U1 · Design draft 01</small></div>`;
}
function intro(k, description, action = "") {
  return `<div class="intro"><div><p class="eyebrow">${t("科布 · 设计演示", "KEBUI · DESIGN DEMO")}</p><h1>${title(k)}</h1><p>${description}</p></div>${action}</div>`;
}
function banner(head, body, actions = "", error = false) {
  return `<section class="banner ${error ? "error" : ""}" role="status"><strong>${head}</strong><p>${body}</p><div class="toolbar">${actions}</div></section>`;
}
function context() {
  return `<div class="row between"><div class="row"><span class="avatar">${state.agent === "Codex" ? "Cx" : "Cl"}</span><div><strong>${esc(state.project)}</strong><div class="muted">${esc(state.agent)} · AgentBox Runtime</div></div></div>${pill(t("合成会话", "Synthetic session"))}</div>`;
}
const seed = () =>
  t(
    "请修复合成项目 Meadow 的空状态，并补充可访问性测试。",
    "Fix the empty state in synthetic Meadow and add accessibility tests.",
  );
function home() {
  return (
    intro(
      "home",
      t(
        "把事情交代清楚，让工作自然向前。",
        "A clear request. A quieter way to move work forward.",
      ),
      btn("new", t("＋ 新建工作", "＋ New work"), "primary"),
    ) +
    `<div class="grid"><section><input class="filter" id="search" aria-label="${t("搜索此演示中的工作", "Search work in this demo")}" placeholder="${t("搜索此演示中的工作", "Search work in this demo")}" value="${esc(state.search)}"><div class="tabs">${[
      ["all", "全部", "All"],
      ["attention", "待确认", "Approval"],
      ["running", "执行中", "Running"],
    ]
      .map(([k, z, e]) =>
        btn("filter:" + k, t(z, e), state.filter === k ? "active" : ""),
      )
      .join(
        "",
      )}</div><div id="conversation-list">${rows()}</div><p class="notice">${t("列表排序固定，不因新进度在点击时移动。搜索仅涵盖三个合成工作。", "Stable ordering. Search covers these three synthetic work items only.")}</p></section><section class="stack"><div class="card"><p class="eyebrow">${t("需要你", "NEEDS YOU")}</p><p class="metric">01</p><h3>${t("一项操作等待确认", "One operation to review")}</h3><p class="muted">${t("范围、后果和申请者，一起看清楚。", "See the requester, scope and consequences together.")}</p>${btn("go:approval", t("查看确认卡 →", "Review approval →"), "link")}</div><div class="card subtle"><h3>${t("继续，而不是重新开始", "Pick up where you left off")}</h3><p class="muted">${t("断线后先核验身份与状态，不自动重发。", "After disconnecting, verify identity and state. Never replay writes.")}</p>${btn("go:recovery", t("试试手机恢复 →", "Try mobile recovery →"), "link")}</div></section></div>`
  );
}
function rows() {
  const data = [
    [
      "approval",
      "Meadow",
      t("让空状态更有帮助", "Make empty states helpful"),
      t(
        "Codex 请求修改两个示例文件",
        "Codex requests changes to two fixture files",
      ),
      t("待确认", "Approval"),
      "warn",
    ],
    [
      "work",
      "Observatory",
      t("整理下一次发布说明", "Shape the next release notes"),
      t(
        "Claude Code · 已接受，尚未执行",
        "Claude Code · Accepted, not started",
      ),
      t("执行中", "Running"),
      "good",
    ],
    [
      "results",
      "Meadow",
      t("检查按钮的键盘焦点", "Check button keyboard focus"),
      t("两项合成测试结果可检查", "Two synthetic test results to inspect"),
      t("未读结果", "Unread result"),
      "",
    ],
  ];
  const found = data.filter(
    (r, i) =>
      (state.filter === "all" ||
        (state.filter === "attention" ? i === 0 : i === 1)) &&
      r.join(" ").toLowerCase().includes(state.search.toLowerCase()),
  );
  return found.length
    ? `<div class="list">${found.map((r) => `<button class="conversation" data-action="fixture:${r[0]}"><span class="avatar">${r[0] === "work" ? "Cl" : "Cx"}</span><span class="copy"><h3>${r[2]}</h3><p>${r[1]} · ${r[3]}</p>${pill(r[4], r[5])}</span><span class="time">09:41</span></button>`).join("")}</div>`
    : `<div class="empty"><h3>${t("没有匹配的工作", "No matching work")}</h3><p>${t("换个词，或清除筛选。", "Try another term or clear the filter.")}</p>${btn("clear-search", t("清除筛选", "Clear filters"))}</div>`;
}
function phaseLabel() {
  return {
    idle: t("尚未提交", "Not submitted"),
    accepted: t("已接受 · 尚未开始", "Accepted · Not started"),
    running: t("执行中", "Running"),
    succeeded: t("合成结果已核验", "Synthetic result verified"),
    failed: t("提交失败 · 未接受", "Send failed · Not accepted"),
    unknown: t("结果未知", "Outcome unknown"),
    interrupted: t("当前轮次已中断（演示）", "Current turn interrupted (demo)"),
  }[state.phase];
}
function work() {
  let next = "";
  if (state.phase === "accepted")
    next = btn(
      "advance",
      t("演示：开始执行", "Demo: start execution"),
      "primary",
    );
  if (state.phase === "running")
    next = btn(
      "advance",
      t("演示：读取完成证据", "Demo: read completion evidence"),
      "primary",
    );
  if (state.phase === "succeeded")
    next = btn("go:results", t("检查结果", "Inspect results"), "primary");
  if (state.phase === "failed")
    next = banner(
      state.requestId
        ? t("没有收到接受回执", "No acceptance receipt")
        : t("已选择失败场景", "Failure scene selected"),
      state.requestId
        ? t(
            "请求保留在草稿中。显式重试仍使用同一演示请求 ID，不创建第二份工作。",
            "The request stays in your draft. Explicit retry uses the same demo request ID without creating duplicate work.",
          )
        : t(
            "请先在下方提交合成请求，收到失败结果后才能重试。",
            "Submit a synthetic request below first. Retry becomes available after the failed attempt.",
          ),
      btn(
        "retry",
        t("重试此请求（演示）", "Retry request (demo)"),
        "",
        !state.requestId,
      ),
      true,
    );
  if (state.phase === "unknown")
    next = banner(
      t("连接中断，结果未知", "Disconnected. Outcome unknown."),
      t(
        "不自动补发。先重新核验状态，再决定下一步。",
        "No automatic resend. Verify current state before the next action.",
      ),
      btn("go:recovery", t("重新核验", "Verify state")),
    );
  return (
    intro(
      "work",
      t("一个项目，一位明确的执行者。", "One project. One explicit executor."),
      btn("new", t("新工作 / 切换范围", "New work / change scope")),
    ) +
    `<div class="grid"><section>${context()}<div class="message user"><div class="by">${t("你 · 合成消息", "You · Synthetic message")}</div><p>${esc(state.message || seed())}</p></div><div class="message"><div class="row"><span class="avatar">k</span><div><strong>Kebui</strong><p class="muted">${t("实际执行者始终可见；不自动选择或切换。", "The actual executor stays visible. No automatic selection or switching.")}</p></div></div></div><section class="card"><div class="row between"><h3>${t("工作进展", "Work progress")}</h3>${pill(phaseLabel(), state.phase === "failed" ? "bad" : "good")}</div><ol class="timeline"><li><strong>${t("上下文已明确", "Context selected")}</strong><p>${esc(state.project)} / ${esc(state.agent)} / demo-owner · ${esc(state.requestId || "demo-request-unsubmitted")}</p></li><li><strong>${phaseLabel()}</strong><p>${t("演示事件来源：内存 fixture · 更新 09:41", "Demo event source: in-memory fixture · Updated 09:41")}</p></li></ol>${next}<div class="toolbar">${btn("disconnect", t("演示断线", "Simulate disconnect"))}${btn("interrupt", t("中断当前轮次", "Interrupt current turn"), "", state.phase !== "running")}${btn("cancel-task", t("取消任务（规划）", "Cancel task (planned)"))}${btn("go:workspace", t("高级检查", "Advanced inspection"))}</div></section><form class="composer" id="composer"><label for="draft" class="muted">${esc(state.project)} · ${esc(state.agent)} · ${t("仅输入合成内容", "Synthetic text only")}</label><textarea id="draft" placeholder="${t("描述你想完成的事…", "Describe what you want to get done…")}" ${["accepted", "running", "unknown"].includes(state.phase) ? "disabled" : ""}>${esc(state.draft)}</textarea><footer><small>${t("Enter 换行 · Ctrl / ⌘ + Enter 提交", "Enter for newline · Ctrl / ⌘ + Enter to send")}</small><button type="submit" class="primary" ${["accepted", "running", "unknown"].includes(state.phase) ? "disabled" : ""}>${t("发送演示请求", "Send demo request")}</button></footer></form></section><section class="context-panel stack"><div class="card"><p class="eyebrow">${t("工作现场", "WORK CONTEXT")}</p><h3>${esc(state.project)}</h3><p>${t("示例设计系统与组件体验", "Example design system & component experience")}</p><hr><small>${t("实际执行者（合成）", "Executor (synthetic)")}</small><p>${esc(state.agent)}</p><small>${t("授权边界", "Authority boundary")}</small><p>${t("单一 Project；无真实读取与写入", "Single Project; no real reads or writes")}</p>${btn("go:agents", t("查看环境详情", "View environment"), "link")}</div><div class="highlight">${t("可信结果与 CLI 退出是两回事。这里所有结果都是明示的合成样本。", "A trusted result is separate from CLI exit. Every result here is an explicitly synthetic fixture.")}</div></section></div>`
  );
}
function approval() {
  const a = state.approval;
  const pending = a === "pending";
  return (
    intro(
      "approval",
      t("只确认眼前这项有范围的操作。", "Approve only this bounded operation."),
    ) +
    `<div class="grid"><section class="stack">${context()}<div class="card"><div class="row between"><h2>${t("更新空状态文案与测试", "Update empty-state copy and tests")}</h2>${pill({ pending: t("待确认", "Pending"), approved: t("演示回读：已批准", "Demo readback: approved"), rejected: t("已拒绝", "Rejected"), expired: t("请求已过期", "Request expired"), unknown: t("提交结果未知", "Submission unknown") }[a], pending ? "warn" : "")}</div><p class="muted">${esc(state.agent)} · ${t("当前申请者。批准不授予永久权限，也不授权发布或部署。", "Current requester. Approval is not permanent permission and does not authorize publishing or deployment.")}</p><dl class="facts"><dt>${t("身份 / 项目", "Owner / Project")}</dt><dd>demo-owner / ${esc(state.project)}</dd><dt>${t("操作目标", "Target")}</dt><dd>demo/EmptyState.tsx<br>demo/EmptyState.test.tsx</dd><dt>${t("后果", "Consequence")}</dt><dd>${t("演示修改 2 个合成文件；不触及真实仓库。", "Simulate editing 2 fixture files; no real repository access.")}</dd><dt>${t("请求 / 版本", "Request / revision")}</dt><dd>demo-approval-01 / r${state.revision}</dd><dt>${t("有效期", "Validity")}</dt><dd>${t("此演示场景内有效；过期场景立即失效。无真实 TTL。", "Valid in this demo scene; the expiry scene invalidates it. No real TTL.")}</dd></dl><div class="toolbar">${btn("approve", t("批准当前操作（演示）", "Approve operation (demo)"), "primary", !pending)}${btn("reject", t("拒绝", "Reject"), "", !pending)}${btn("expire", t("演示过期", "Simulate expiry"), "", !pending)}</div></div>${a === "unknown" ? banner(t("提交后断线，不能假定已批准", "Disconnected after submit. Approval is unknown."), t("不会自动重试审批。只读取状态，或取消本次演示。", "Never retry approval automatically. Read state only or cancel this demo."), btn("read-approval", t("只读回查（演示）", "Read status only (demo)"))) : ""}${a === "expired" ? banner(t("旧请求不可操作", "Old request is not actionable"), t("重新取得新 revision 后才能再次确认。", "A fresh revision is required before approval."), btn("fresh-approval", t("获取新请求（演示）", "Get fresh request (demo)"))) : ""}${a === "approved" ? banner(t("演示权威状态已回读", "Synthetic authoritative state read back"), t("仅 demo-approval-01 的当前 revision 被批准；尚未表示工作完成。", "Only this revision of demo-approval-01 is approved. This does not mean the work is complete."), btn("approval-continue", t("查看后续执行", "View execution"), "primary")) : ""}${btn("go:home", t("返回工作列表", "Back to work list"))}</section><div class="card context-panel"><p class="eyebrow">${t("确认前检查", "BEFORE APPROVING")}</p><h3>${t("范围不能悄悄改变", "No silent scope changes")}</h3><p>${t("切换项目或身份会清除草稿、结果正文和旧审批。旧请求不能跨作用域复用。", "Changing Project or identity clears drafts, result bodies and old approvals. Requests cannot cross scopes.")}</p>${btn("switch-owner", t("演示身份失效", "Simulate identity loss"))}</div></div>`
  );
}
function results() {
  return (
    intro(
      "results",
      t(
        "先确认来源，再显式打开正文。",
        "Check the source, then explicitly open the body.",
      ),
      btn("back-work", t("← 返回原对话", "← Back to conversation")),
    ) +
    `<div class="grid"><section class="stack"><div class="card"><div class="row between"><h2>${t("空状态可访问性", "Empty-state accessibility")}</h2>${pill(t("合成结果", "Synthetic result"), "good")}</div><p>${t("2 个示例文件 · 2 项合成断言 · 不代表真实测试运行。", "2 fixture files · 2 synthetic assertions · Not a real test run.")}</p><dl class="facts"><dt>${t("来源", "Source")}</dt><dd>demo-result-01 / ${esc(state.project)} / ${esc(state.agent)}</dd><dt>${t("结果依据", "Evidence")}</dt><dd>${t("预置样本，不从终端文本或 Job 状态推导。", "Hard-coded fixture; not derived from terminal text or Job status.")}</dd></dl></div><div class="card"><div class="row between"><h3>demo/EmptyState.tsx</h3>${pill(state.admitted ? t("已显式读取样本", "Fixture explicitly read") : t("正文未读取", "Body not read"))}</div>${state.admitted ? `<div class="tabs">${btn("diff-unified", t("统一 diff", "Unified diff"))}${btn("diff-raw", t("原文", "Raw text"))}</div><pre class="code" id="diff"><span class="removed">- &lt;button&gt;Go&lt;/button&gt;</span>\n<span class="added">+ &lt;button aria-label="Create your first project"&gt;\n+   Create project\n+ &lt;/button&gt;</span></pre><p class="notice">${t("惰性文本展示；不执行 HTML、Markdown 或脚本。", "Inert text only; HTML, Markdown and scripts are never executed.")}</p>` : `<p>${t("本次读取仅展示内置合成文本，不访问目录或网络。", "This read shows built-in synthetic text only. No filesystem or network access.")}</p>${btn("read-result", t("读取合成正文", "Read synthetic body"), "primary")}`}</div>${btn("invalidate-result", t("演示正文失效", "Simulate content expiry"))}</section><div class="card context-panel"><h3>${t("验证结果", "Validation results")}</h3><ol class="timeline"><li>${t("合成断言：焦点可见", "Fixture assertion: visible focus")}</li><li>${t("合成断言：名称清楚", "Fixture assertion: clear accessible name")}</li></ol><p class="muted">${t("真实 CI 状态：UNKNOWN。没有 PR、远端提交或发布。", "Real CI status: UNKNOWN. No PR, remote commit or release.")}</p></div></div>`
  );
}
function recovery() {
  return (
    intro(
      "recovery",
      t(
        "先找回确定的状态，再继续行动。",
        "Recover confirmed state before taking action.",
      ),
    ) +
    `<section class="stack">${context()}${banner(state.recovered ? t("演示回读完成", "Demo state readback complete") : t("连接断开 · 执行结果未知", "Disconnected · Execution outcome unknown"), state.recovered ? t("demo-owner / Project / 会话已重新核验。没有重放请求或审批。", "demo-owner / Project / session reverified. No request or approval was replayed.") : t("上次看到执行中，不等于现在仍在执行，也不代表成功。", "Last seen running does not mean still running, and does not imply success."), btn("recover", t("重新核验身份与状态（演示）", "Verify identity & state (demo)"), "primary"))}<div class="card"><h2>${state.recovered ? (state.stopped ? t("精确目标停止回读（合成）", "Exact-target stop readback (synthetic)") : t("工作仍在执行（合成回读）", "Work is running (synthetic readback)")) : t("等待可信状态", "Awaiting trusted state")}</h2><dl class="facts"><dt>${t("会话目标", "Session target")}</dt><dd>demo-session-01 / epoch 7</dd><dt>${t("原请求", "Original request")}</dt><dd>demo-request-01 · ${t("未重发", "not replayed")}</dd><dt>${t("最近已知", "Last known")}</dt><dd>09:41 · ${t("合成时间", "synthetic time")}</dd></dl><div class="toolbar">${btn("resume", t("返回当前工作", "Return to work"), "", !state.recovered)}${btn("stop-dialog", t("停止运行：查看精确目标", "Stop runtime: inspect exact target"), "danger", !canStop())}${btn("detach", t("退出查看（不停止）", "Leave view (does not stop)"))}</div></div><p class="notice">${t("浏览器刷新将重置整个演示。未实现跨设备持久恢复，也不自动发送任何写操作。", "Refreshing resets the entire demo. Cross-device persistence is not implemented. No writes are automatically sent.")}</p></section>`
  );
}
function agents() {
  return (
    intro(
      "agents",
      t(
        "连接、认证与执行资格分别呈现。",
        "Connection, authentication and execution qualification stay separate.",
      ),
    ) +
    `<div class="grid"><section class="stack">${["Codex", "Claude Code"].map((a) => `<div class="card"><div class="row between"><div class="row"><span class="avatar">${a === "Codex" ? "Cx" : "Cl"}</span><h2>${a}</h2></div>${pill(t("仅合成身份", "Synthetic identity"))}</div><dl class="facts"><dt>${t("运行环境", "Runtime")}</dt><dd>AgentBox Runtime / demo-environment</dd><dt>${t("连接", "Connection")}</dt><dd>${t("合成在线；无实际连接", "Synthetic online; no actual connection")}</dd><dt>${t("账户认证", "Authentication")}</dt><dd>UNKNOWN · ${t("未登录真实账户", "No real account sign-in")}</dd><dt>${t("执行资格", "Qualification")}</dt><dd>${t("真实 host 未核验", "Real host not qualified")}</dd></dl>${btn("choose:" + a, t("为新工作选择", "Select for new work"))}</div>`).join("")}</section><div class="card context-panel"><h3>${t("显式选择，不是自动路由", "Explicit choice, not auto-routing")}</h3><p>${t("更换 Agent 会开始新的演示工作，不继承旧审批或上下文权限。Provider、登录、Remote 和 Workspace 仍是不同的域。", "Changing Agent starts a new demo work item. It inherits no approval or context authority. Provider, login, Remote and Workspace remain separate domains.")}</p></div></div>`
  );
}
function catalog() {
  return (
    intro(
      "catalog",
      t(
        "全部画面可打开；规划能力始终明确标记。",
        "Every screen opens; planned capabilities are always labeled.",
      ),
    ) +
    `<div class="inventory">${Object.keys(titles)
      .filter((k) => k !== "catalog")
      .map(
        (k, i) =>
          `<button data-action="go:${k}"><small>${String(i + 1).padStart(2, "0")} / ${["home", "work", "approval", "results", "agents", "recovery"].includes(k) ? "CORE" : "EXTENDED"}</small><strong>${title(k)}</strong><small>${t("合成设计画面 · 非生产能力", "Synthetic design surface · Not production capability")}</small></button>`,
      )
      .join("")}</div>`
  );
}
function extra() {
  const r = state.route;
  let body = "";
  if (r === "projects")
    body = `<input class="filter" placeholder="${t("合成项目列表（固定两项）", "Synthetic projects (two fixed fixtures)")}" disabled><div class="list">${["Meadow", "Observatory"].map((p) => `<button class="conversation" data-action="project:${p}"><span class="avatar">◌</span><span><h3>${p}</h3><p>${t("正式 Project 概念的合成样本", "Synthetic sample of a formal Project")}</p></span></button>`).join("")}</div>${btn("new-project", t("演示创建 / clone 表单", "Demo create / clone form"))}`;
  else if (r === "project")
    body = `${context()}<hr><p>${t("项目边界内的最近工作与受限检查。这里没有任意目录选择器。", "Recent work and bounded inspection within a Project. No arbitrary-directory selector.")}</p><div class="toolbar">${btn("go:work", t("继续对话", "Continue conversation"), "primary")}${btn("go:changes", title("changes"))}${btn("go:workspace", title("workspace"))}</div>`;
  else if (r === "workspace")
    body = `${context()}<hr><h2>${t("CLI 高级检查", "Advanced CLI inspection")}</h2><pre class="code">${t("设计占位：不连接终端，不执行命令。", "Design placeholder: no terminal connection, no commands.")}\nSession: demo-session-01\nRuntime: agentbox-runtime</pre><div class="toolbar">${btn("detach", t("Detach / 退出查看", "Detach / leave view"))}${btn("go:recovery", t("Reconnect / 核验恢复", "Reconnect / verify"))}${btn("stop-dialog", t("Exact Stop / 查看目标", "Exact Stop / inspect target"), "danger")}</div>`;
  else if (r === "login")
    body = `<h2>${t("欢迎回来", "Welcome back")}</h2><p>${t("这是合成登录演示，不要输入账号、密码或凭据。登录与新环境初始化分开。", "Synthetic sign-in demo. Do not enter accounts, passwords or credentials. Sign-in is separate from environment initialization.")}</p><div class="toolbar">${btn("demo-login", t("以合成身份继续", "Continue as synthetic owner"), "primary")}${btn("init", t("查看初始化边界", "Inspect initialization boundary"))}</div>`;
  else if (r === "doctor")
    body = `<h2>${t("每一层，各自确认", "Verify each layer separately")}</h2><dl class="facts"><dt>Control Plane</dt><dd>${t("合成 READY", "Synthetic READY")}</dd><dt>Runtime</dt><dd>UNKNOWN</dd><dt>Agent login</dt><dd>UNKNOWN</dd><dt>Remote</dt><dd>${t("未核验", "Not verified")}</dd></dl><p>${t("Control Plane READY 不代表 Runtime、账户或 Agent 可运行。", "Control Plane READY does not qualify Runtime, accounts or Agent execution.")}</p>${btn("diagnose", t("演示只读诊断", "Demo read-only diagnostic"))}`;
  else if (r === "settings")
    body = `<h2>${t("外观与语言", "Appearance & language")}</h2><p>${t("仅改变本页面；不保存到账户或设备。", "Changes this page only; not saved to an account or device.")}</p><div class="toolbar">${btn("theme", t("切换浅 / 深主题", "Toggle light / dark"))}${btn("language", t("切换 English", "Switch 中文"))}${btn("large", t("切换大字体", "Toggle large text"))}</div><hr><h3>${t("权限与保留策略", "Permission & retention policy")}</h3><p>${t("生产设置只读边界保持。此原型没有设置 API、记忆写入或真实账户。", "Production read-only policy remains intact. This prototype has no settings API, memory writes or real account.")}</p>${btn("switch-owner", t("演示切换身份并清除范围", "Simulate identity change & clear scope"))}`;
  else if (r === "notfound" || r === "denied")
    body = `<div class="empty"><p class="eyebrow">${r === "notfound" ? "404" : "403"}</p><h2>${r === "notfound" ? t("这条路径没有工作", "No work at this path") : t("当前身份不能查看此项目", "This identity cannot view this Project")}</h2><p>${t("不显示之前的正文或敏感上下文。", "No previous body or sensitive context is shown.")}</p>${btn("go:home", t("返回工作入口", "Return to work"), "primary")}${btn("go:login", t("切换身份", "Change identity"))}</div>`;
  else {
    const descriptions = {
      logs: t(
        "日志读取 / 下载未实现。这里仅说明状态，不伪造日志流。",
        "Log reading / download is unimplemented. No fabricated live log stream.",
      ),
      files: t(
        "Files / Artifacts 需独立准入、来源与正文合同。此处仅预演导航，不开放文件读取。",
        "Files / Artifacts require independent admission, source and body contracts. Navigation preview only; file reading unavailable.",
      ),
      history: t(
        "K6 规划：历史、偏好与记忆须分别定义保留和删除范围。本页不保存内容。",
        "K6 planned: history, preferences and memory need distinct retention and deletion scopes. This page stores no content.",
      ),
      handoff: t(
        "K4–K5 规划：当前 Codex → 未来 Claude Code 审查。需明确交接合同，不能换头像冒充执行者切换。",
        "K4–K5 planned: current Codex → future Claude Code review. Explicit handoff contracts required; an avatar swap is not executor handoff.",
      ),
      team: t(
        "K7 规划：成员、可见范围、指派、审批者与撤销待资格化。没有邀请或共享行为。",
        "K7 planned: membership, visibility, assignment, approvers and revocation need qualification. No invitations or sharing occur.",
      ),
    };
    body = `${pill(t("规划功能 · 不可执行", "Planned · Not executable"), "warn")}<h2 style="margin-top:20px">${title(r)}</h2><p>${descriptions[r] || ""}</p>${btn("explain-planned", t("查看不可用原因", "Why unavailable?"))}`;
  }
  return (
    intro(
      r,
      t(
        "独立设计演示，不改变现有生产页面。",
        "Standalone design demo. Existing production pages are unchanged.",
      ),
    ) + `<section class="card">${body}</section>${scenarioNote()}`
  );
}
function scenarioNote() {
  return state.scenario === "success"
    ? ""
    : banner(
        t("此页面的场景", "Scene for this screen"),
        {
          failure: t(
            "读取失败。未显示旧内容，可显式重新读取。",
            "Read failed. Stale content is hidden; explicitly read again.",
          ),
          interrupted: t(
            "连接中断。停止自动写入；恢复时只读取状态。",
            "Disconnected. No automatic writes; recovery reads state only.",
          ),
          expired: t(
            "权限或内容已过期。旧操作失效。",
            "Permission or content expired. Old actions are invalid.",
          ),
          empty: t(
            "没有可见记录。创建功能须独立取得准入。",
            "No visible records. Creation needs separate qualification.",
          ),
          unknown: t(
            "状态 UNKNOWN。不能推断成功或失败。",
            "State UNKNOWN. Neither success nor failure can be inferred.",
          ),
        }[state.scenario] || "",
        btn("scene-reset", t("返回成功示例", "Return to success fixture")),
      );
}
function render() {
  document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
  document.body.classList.toggle("large", state.large);
  document.title = `${title(state.route)} · Kebui U1 Design Demo`;
  const views = {
    home,
    work,
    approval,
    results,
    agents,
    recovery,
    catalog,
    changes: results,
  };
  document.getElementById("app").innerHTML =
    `<a href="#main" class="skip">${t("跳到内容", "Skip to content")}</a><div class="demo-bar"><strong>${t("设计演示，不连接 Agent · 所有数据均为合成", "Design demo, no Agent connection · All data is synthetic")}</strong><span>U1 / 01 · ${t("非最终品牌定稿", "Exploratory design")}</span></div><div class="layout"><aside>${nav()}</aside><div class="shell"><header class="topbar"><div class="row">${btn("menu", "☰ " + t("导航", "Menu"), "mobile-menu")}<span class="page-label">${title(state.route)}</span></div><div class="toolbar"><label><span class="eyebrow">${t("场景 ", "SCENE ")}</span><select id="scenario" aria-label="${t("演示场景", "Demo scenario")}">${[
      ["success", "成功", "Success"],
      ["failure", "失败", "Failure"],
      ["interrupted", "中断", "Interrupted"],
      ["expired", "过期", "Expired"],
      ["empty", "空状态", "Empty"],
      ["unknown", "未知", "Unknown"],
    ]
      .map(
        ([v, z, e]) =>
          `<option value="${v}" ${state.scenario === v ? "selected" : ""}>${t(z, e)}</option>`,
      )
      .join(
        "",
      )}</select></label>${btn("theme", document.documentElement.dataset.theme === "dark" ? "☀" : "◐")}${btn("language", state.lang === "zh" ? "EN" : "中文")}</div></header><main id="main" class="main" tabindex="-1">${(views[state.route] || extra)()}</main></div></div>`;
  document
    .querySelector('[data-action="theme"]')
    .setAttribute("aria-label", t("切换主题", "Toggle theme"));
}
function navigate(route) {
  clearToast();
  closeDialog();
  if (state.route === "work") state.scroll = window.scrollY;
  state.route = titles[route] ? route : "notfound";
  if (route === "denied" || route === "notfound") {
    state.admitted = false;
    state.draft = "";
  }
  if (location.hash.slice(1) !== state.route) location.hash = state.route;
  render();
  window.scrollTo(0, 0);
}
function resetScope() {
  clearToast();
  recoveryGeneration++;
  closeDialog();
  state.draft = "";
  state.message = "";
  state.requestId = "";
  state.requestCount = 0;
  state.acceptedCount = 0;
  state.sendAttempts = 0;
  state.phase = "idle";
  state.approval = "pending";
  state.revision++;
  state.admitted = false;
  state.recovered = false;
  state.stopped = false;
  state.online = true;
  state.scroll = 0;
}
let toastGeneration = 0;
let toastTimer;
function clearToast() {
  toastGeneration++;
  clearTimeout(toastTimer);
  document.getElementById("live").replaceChildren();
}
function toast(message) {
  clearToast();
  const generation = toastGeneration;
  const el = document.getElementById("live");
  const text = document.createElement("span");
  text.textContent = message;
  const dismiss = document.createElement("button");
  dismiss.dataset.action = "dismiss-toast";
  dismiss.textContent = t("关闭", "Dismiss");
  el.append(text, dismiss);
  toastTimer = setTimeout(() => {
    if (generation === toastGeneration) clearToast();
  }, 6000);
}
function modal(html) {
  closeDialog();
  const dialog = document.getElementById("dialog");
  dialog.innerHTML = html;
  dialog.showModal();
}
function newWork(selectedAgent = state.agent) {
  modal(
    `<h2>${t("从明确的工作范围开始", "Start with an explicit scope")}</h2><p>${t("继续将清除旧草稿、正文与审批。只用于合成演示。", "Continuing clears the old draft, body and approval. Synthetic demo only.")}</p><label for="project-choice">Project</label><select id="project-choice"><option>Meadow</option><option>Observatory</option></select><label for="agent-choice">${t("实际执行者", "Actual executor")}</label><select id="agent-choice"><option>Codex</option><option>Claude Code</option></select><div class="toolbar">${btn("create-work", t("确认范围并继续", "Confirm scope & continue"), "primary")}${btn("close", t("取消", "Cancel"))}</div>`,
  );
  document.getElementById("project-choice").value = state.project;
  document.getElementById("agent-choice").value = selectedAgent;
}
function send() {
  if (composing || ["accepted", "running", "unknown"].includes(state.phase))
    return;
  const draft = document.getElementById("draft");
  const value = (draft?.value || state.draft).trim();
  if (!value) {
    toast(t("先输入一条合成请求。", "Enter a synthetic request first."));
    return;
  }
  if (!state.requestId || state.phase !== "failed" || state.message !== value) {
    state.requestId = `demo-request-${++requestSerial}`;
    state.requestCount++;
  }
  state.sendAttempts++;
  state.message = value;
  state.draft = value;
  if (state.scenario === "failure") state.phase = "failed";
  else if (state.scenario === "interrupted" || state.scenario === "unknown")
    state.phase = "unknown";
  else {
    state.phase = "accepted";
    state.acceptedCount++;
    state.draft = "";
  }
  render();
}
function setScene(scene) {
  recoveryGeneration++;
  closeDialog();
  state.scenario = scene;
  state.admitted = false;
  state.recovered = false;
  state.stopped = false;
  state.approval = scene === "expired" ? "expired" : "pending";
  state.phase =
    scene === "failure"
      ? "failed"
      : ["interrupted", "unknown"].includes(scene)
        ? "unknown"
        : "idle";
  if (scene === "empty") {
    state.search = "no-fixture-match";
    state.message = "";
  } else state.search = "";
  if (state.route === "recovery") state.online = false;
  render();
}
document.addEventListener("click", (event) => {
  if (event.target.closest(".skip")) {
    event.preventDefault();
    document.getElementById("main").focus();
    return;
  }
  const target = event.target.closest("button[data-action]");
  if (!target || target.disabled) return;
  const [action, ...parts] = target.dataset.action.split(":");
  const value = parts.join(":");
  const dialog = document.getElementById("dialog");
  if (action === "dismiss-toast") {
    clearToast();
    return;
  }
  if (action === "fixture") {
    resetScope();
    state.project = value === "work" ? "Observatory" : "Meadow";
    state.agent = value === "work" ? "Claude Code" : "Codex";
    state.phase = value === "work" ? "accepted" : "idle";
    navigate(value);
    return;
  }
  if (action === "go") {
    if (dialog.open) dialog.close();
    navigate(value);
    return;
  }
  if (action === "filter") {
    state.filter = value;
    render();
    return;
  }
  if (action === "scope" || action === "project") {
    resetScope();
    state.project = value;
    navigate("project");
    return;
  }
  if (action === "choose") {
    newWork(value);
    return;
  }
  switch (action) {
    case "menu":
      modal(
        `<h2>${t("导航", "Navigation")}</h2>${nav()}${btn("close", t("关闭", "Close"))}`,
      );
      break;
    case "cancel-task":
      toast(
        t(
          "任务级取消需 K3 合同，此原型不把轮次中断或 exact Stop 当作任务取消。",
          "Task-level cancellation needs the K3 contract. Turn interruption and exact Stop are not task cancellation.",
        ),
      );
      break;
    case "new":
      newWork();
      break;
    case "close":
      closeDialog();
      break;
    case "create-work": {
      const p = document.getElementById("project-choice").value,
        a = document.getElementById("agent-choice").value;
      resetScope();
      state.project = p;
      state.agent = a;
      state.draft = seed();
      dialog.close();
      navigate("work");
      break;
    }
    case "theme":
      document.documentElement.dataset.theme =
        document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      render();
      break;
    case "language":
      state.lang = state.lang === "zh" ? "en" : "zh";
      render();
      break;
    case "large":
      state.large = !state.large;
      render();
      break;
    case "clear-search":
      state.search = "";
      state.filter = "all";
      render();
      break;
    case "advance":
      if (state.phase === "accepted") state.phase = "running";
      else if (state.phase === "running") state.phase = "succeeded";
      render();
      break;
    case "retry":
      if (state.phase !== "failed" || !state.requestId) break;
      state.sendAttempts++;
      state.acceptedCount++;
      state.phase = "accepted";
      state.draft = "";
      render();
      break;
    case "disconnect":
      invalidateConnection();
      break;
    case "interrupt":
      state.phase = "interrupted";
      render();
      toast(
        t(
          "只中断当前轮次；运行环境未停止。",
          "Only the current turn was interrupted; the runtime was not stopped.",
        ),
      );
      break;
    case "approve":
      if (state.approval !== "pending") break;
      state.approval = ["failure", "interrupted", "unknown"].includes(
        state.scenario,
      )
        ? "unknown"
        : "approved";
      render();
      break;
    case "reject":
      state.approval = "rejected";
      render();
      break;
    case "expire":
      state.approval = "expired";
      render();
      break;
    case "fresh-approval":
      state.revision++;
      state.approval = "pending";
      state.scenario = "success";
      render();
      break;
    case "read-approval":
      state.approval = "expired";
      render();
      toast(
        t(
          "合成回查：旧请求已失效，没有重放审批。",
          "Synthetic readback: old request expired. Approval was not replayed.",
        ),
      );
      break;
    case "approval-continue":
      state.phase = "accepted";
      navigate("work");
      break;
    case "read-result":
      if (state.scenario === "success" || state.scenario === "empty") {
        state.admitted = true;
        render();
      } else
        toast(
          state.scenario === "failure"
            ? t(
                "读取失败；未展示正文。请显式切换成功场景再读取。",
                "Read failed; no body displayed. Explicitly switch to Success and read again.",
              )
            : t(
                "准入已失效或结果未知；不显示旧正文。",
                "Admission expired or result unknown; no old body displayed.",
              ),
        );
      break;
    case "invalidate-result":
      state.admitted = false;
      render();
      toast(
        t(
          "正文已清除，需要重新准入。",
          "Body cleared; new admission required.",
        ),
      );
      break;
    case "diff-unified":
      document.getElementById("diff").textContent =
        '- <button>Go</button>\n+ <button aria-label="Create your first project">Create project</button>';
      break;
    case "diff-raw":
      document.getElementById("diff").textContent =
        '<button aria-label="Create your first project">Create project</button>';
      break;
    case "back-work":
      navigate("work");
      window.scrollTo(0, state.scroll);
      break;
    case "recover":
      if (state.scenario === "failure" || state.scenario === "unknown") {
        toast(
          t(
            "核验失败或状态未知；没有重放，也不能停止未知目标。",
            "Verification failed or state unknown. No replay; unknown targets cannot be stopped.",
          ),
        );
      } else {
        closeDialog();
        recoveryGeneration++;
        state.recovered = true;
        state.online = true;
        state.phase = state.stopped ? "interrupted" : "running";
        render();
      }
      break;
    case "resume":
      navigate("work");
      break;
    case "detach":
      navigate("home");
      toast(
        t(
          "已退出查看；这不是停止运行。",
          "Left the view; this did not stop execution.",
        ),
      );
      break;
    case "stop-dialog":
      if (!canStop()) {
        toast(t("先重新核验精确目标。", "Reverify the exact target first."));
        navigate("recovery");
        break;
      }
      modal(
        `<h2>${t("确认精确停止目标", "Confirm the exact stop target")}</h2><dl class="facts"><dt>Owner</dt><dd>demo-owner</dd><dt>Project</dt><dd>${esc(state.project)}</dd><dt>Session</dt><dd>demo-session-01 / epoch 7</dd><dt>Agent</dt><dd>${esc(state.agent)}</dd></dl><p>${t("这是合成 exact Stop 回读演示；无真实进程被停止。退出查看或中断轮次都不是停止运行。", "Synthetic exact Stop readback only; no real process is stopped. Leaving the view or interrupting a turn is not runtime stop.")}</p><div class="toolbar">${btn("stop-confirm", t("停止此合成目标并回读", "Stop synthetic target & read back"), "danger")}${btn("close", t("取消", "Cancel"))}</div>`,
      );
      pendingStop = stopTarget();
      break;
    case "stop-confirm":
      if (
        !dialog.open ||
        !pendingStop ||
        !canStop() ||
        pendingStop !== stopTarget()
      ) {
        closeDialog();
        toast(
          t(
            "停止确认已失效，请重新核验目标。",
            "Stop confirmation expired. Reverify the target.",
          ),
        );
        break;
      }
      pendingStop = null;
      state.stopped = true;
      state.phase = "interrupted";
      dialog.close();
      navigate("recovery");
      break;
    case "switch-owner":
      resetScope();
      dialog.close();
      navigate("denied");
      break;
    case "demo-login":
      resetScope();
      navigate("home");
      break;
    case "init":
      toast(
        t(
          "初始化需要独立环境资格；演示不创建账户或主机。",
          "Initialization needs separate environment qualification. The demo creates no account or host.",
        ),
      );
      break;
    case "diagnose":
      toast(
        t(
          "合成检查完成：Runtime、认证与真实 host 仍为 UNKNOWN。",
          "Synthetic check complete: Runtime, authentication and real host remain UNKNOWN.",
        ),
      );
      break;
    case "new-project":
      modal(
        `<h2>${t("创建 / clone 项目（规划演示）", "Create / clone Project (design demo)")}</h2><p>${t("正式实现需 Project 合同。此处不收集真实 URL、路径或凭据。", "Production needs the Project contract. No real URL, path or credential is collected here.")}</p><div class="toolbar">${btn("sample-project", t("使用预置合成项目", "Use preset synthetic Project"), "primary")}${btn("close", t("取消并清除", "Cancel & clear"))}</div>`,
      );
      break;
    case "sample-project":
      dialog.close();
      resetScope();
      state.project = "Observatory";
      navigate("project");
      break;
    case "explain-planned":
      toast(
        t(
          "尚无独立的数据、权限或保留合同资格；仅供设计评审。",
          "Independent data, permission or retention contracts are not qualified. Design review only.",
        ),
      );
      break;
    case "scene-reset":
      setScene("success");
      break;
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "draft") state.draft = e.target.value;
  if (e.target.id === "search") {
    state.search = e.target.value;
    document.getElementById("conversation-list").innerHTML = rows();
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "scenario") setScene(e.target.value);
});
document.addEventListener("submit", (e) => {
  if (e.target.id === "composer") {
    e.preventDefault();
    send();
  }
});
document.addEventListener("compositionstart", () => {
  composing = true;
});
document.addEventListener("compositionend", () => {
  composing = false;
});
document.addEventListener("keydown", (e) => {
  if (
    e.target.id === "draft" &&
    e.key === "Enter" &&
    (e.ctrlKey || e.metaKey) &&
    !e.isComposing &&
    !composing
  ) {
    e.preventDefault();
    send();
  }
});
window.addEventListener("hashchange", () => {
  const route = location.hash.slice(1) || "home";
  if (route === "main") {
    document.getElementById("main").focus();
    return;
  }
  if (route !== state.route) navigate(route);
});
window.addEventListener("offline", invalidateConnection);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) invalidateConnection();
});
document.getElementById("dialog").addEventListener("cancel", () => {
  pendingStop = null;
});
document.getElementById("dialog").addEventListener("close", () => {
  // A queued close event from the previous dialog must not invalidate a newer open dialog.
  if (!document.getElementById("dialog").open) pendingStop = null;
});
state.route = location.hash.slice(1) || "home";
if (!titles[state.route]) state.route = "notfound";
render();
