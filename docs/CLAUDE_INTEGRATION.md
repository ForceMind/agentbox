# Claude Code + tmux 集成

状态：Phase 6 Draft 实现。本文描述 AgentBox 当前 project-scoped Claude Code
Remote session 边界；它不是 Claude 私有状态或 UI 文本的稳定协议声明。

## 产品与架构边界

AgentBox 通过 Runtime Executor 管理现有 Claude Code，而不负责安装、更新、
登录、Provider 切换或认证目录迁移。调用链固定为：

```text
Web / CLI
    -> authenticated AgentBox API / typed local CLI
    -> versioned Unix Domain Socket
    -> non-root Runtime Executor
    -> ClaudeSessionManager
    -> TmuxAdapter + ClaudeAdapter
    -> tmux-owned interactive `claude remote-control`
```

API 和 Web 不执行 `claude`、`tmux` 或任意 subprocess。Runtime 协议仅接受
allowlisted action 与受校验的 `project_id`，不接受路径、argv、shell、tmux
flag、PID、signal 或终端输入。Phase 6 继续使用 direct typed UDS actions；在
durable Job/SSE 尚未实现前，这是一个有界、已记录的阶段性偏差。

## tmux 持久化与 Runtime identity

长期 Claude 进程由当前 Runtime 用户的 tmux server 持有，不是 Runtime
Executor 的 foreground child。因此 SSH 断开或 Runtime Executor 重启不会因
AgentBox 的 child cleanup 自动终止 Claude。tmux 是 per-user server：生产部署
必须由未来的 `agentbox-runtime` identity 建立自己的 session，不能跨用户连接
root tmux server，也不得复制 `/root/.claude`。独立 Runtime 用户须在部署阶段
自行完成 Claude 登录。

`TmuxAdapter` 只提供 detect/version/list/has/create/show-marker/capture/
kill-exact。创建使用固定 tmux command sequence：受检绝对 `sleep` 短暂占位，
原子加入 marker，设置 `remain-on-exit`，再由 `respawn-pane` 直接执行受检绝对
Claude 路径与固定 `remote-control` 参数。当前公开 tmux 手册明确说明这些命令
的多参数 command 直接执行而不经 `sh -c`；不存在拼接 shell command 或 raw
tmux command API。占位进程不会由 Runtime Executor 长期持有。

## Project 绑定与路径安全

Phase 6 不实现 Project CRUD 或 Project DB。`ProjectRegistry` 只枚举配置
`AGENTBOX_PROJECT_ROOT` 下的一级真实目录：

- development 默认 `.agentbox-dev/projects`；
- production 设计默认 `/srv/agentbox/projects`；
- `/root/projects` 仅可由开发者显式配置作 legacy validation，不是生产默认；
- 不递归扫描，不创建、clone、rename 或删除目录；
- 拒绝 absolute path、`..`、separator/control/shell punctuation、root 自身、
  missing/file target、root symlink、project symlink 和 canonical root escape；
- 使用前要求目录对 Runtime identity 可读/可进入。

Web/API 只提交 `project_id`。Runtime Executor 在自己的 registry 中重新解析
canonical path 并把它作为 Claude cwd。bind mount 在路径解析后仍可能改变
底层对象，属于当前限制；生产 mount namespace/ownership policy 在 Phase 8
重新验证。

## Session name 与 managed/unmanaged

MVP 是 one managed session per project。session 名为 bounded ASCII
`agentbox-claude-<slug>-<sha256-prefix>`；slug 只用于可读性，hash 绑定完整
project ID。原始 display name 从不直接成为 tmux target。

创建时 AgentBox 通过 tmux `new-session -e` 原子加入固定 session environment
`AGENTBOX_MANAGED_SESSION`，值是版本化的 project-derived marker。停止、capture 和重启后 rediscovery 都要求 exact name
与 exact marker 同时匹配。同名但无正确 marker 的 session 返回 collision/
unmanaged error，不会被 adopt 或 kill。现有 `claude-*` 等历史 session 只计入
unmanaged count；名称、pane、attach 和控制操作不向 Web 暴露。

同一 Runtime UID 下的其他进程原则上可以操作同一个 tmux server 并伪造
marker。这是 tmux per-user 模型的残余风险；生产依赖专用 Runtime identity、
unit sandboxing 和最小同 UID 进程集合，而不是把 marker 当作加密证明。

## Claude capability 与 authentication

`ClaudeAdapter` 只读取公开 CLI 行为：`claude --version`、`claude --help` 与在
主帮助明确出现 `remote-control` 后的 `claude remote-control --help`。功能不按
版本号猜测。只有公开帮助明确广告 auth status 时才可调用固定 `claude auth
status` 并保守解析；否则 authentication 为 `UNKNOWN`。`--version` 成功不等于
authenticated。

不读取 `~/.claude`、credential 文件、Workspace Trust JSON 或其他私有格式。
Runtime 子进程环境只继承 HOME/PATH/locale/必要 XDG/TERM；API key 环境变量不
进入普通 Phase 6 runner。Provider/Secret 管理仍属于 Phase 11。

## Workspace Trust

AgentBox 不传 `yes`、不发送按键、不模拟确认，也不使用未经当时公开文档确认
的 trust bypass。保守输出 fixture 可识别 trust/login interaction、ready hint
和 fatal hint：

- trust 或登录提示：`NEEDS_INTERACTION`；
- 明确 fatal hint：`BROKEN`；
- 明确 Remote ready hint：`RUNNING`，但仅作为 bounded public-output evidence；
- 其他或变化后的 UI：`UNKNOWN`，start 的首次未知观察返回 `STARTING`。

`workspace_state=INITIALIZED_BY_AGENTBOX` 仅表示本进程曾成功创建该 project 的
managed session，不代表 Claude 私有 trust 一定成立；Runtime restart 后该内存
hint 消失为 `UNKNOWN`。Trust prompt 显示
`REQUIRES_USER_CONFIRMATION`，用户须从 SSH/本地终端执行生成的 attach command
完成交互。

## 生命周期、并发与 restart

Start 顺序为 resolve project -> detect public capability -> exact collision check ->
tmux create-with-marker -> set remain-on-exit -> direct Claude respawn -> bounded
observation。未知状态不阻塞很久，也不循环重启。Claude 因 Trust 提示退出时，
AgentBox 在同一 exact marked pane 中以固定多参数 `claude --` 直接准备一个公开
交互式 Trust prompt。用户 attach 后自行确认、退出该交互 Claude，再 Stop/Start
Remote session；AgentBox 不发送按键、不接受 Trust，也不循环自动重启。
每个 project 使用 `asyncio.Lock`，tmux 操作另有 bounded semaphore；重复 Start
返回 `already_running`。

Stop 在同一 project lock 内复核 exact name 与 marker，然后只执行
`tmux kill-session -t =<safe-name>`。已停止返回 `already_stopped`。不存在
`pkill`、PID signal、`kill-server`、similar-name match 或 delete session/project。
Runtime restart 通过 registry、deterministic name、tmux marker 和 bounded pane
observation 重建状态，不依赖仅存在内存中的 session ownership map。

## Attach 模型

Web 不提供 terminal，仅显示：

```text
tmux attach-session -t =<agentbox-generated-name>
```

并在用户点击后复制。它不生成 SSH 地址。`agentbox claude attach <project>` 只在
本地 stdin/stdout 都是 TTY、session 正在运行且 Runtime 返回的 session name
通过 strict grammar 后，使用当前用户解析到的 tmux 执行 exact attach。该命令
必须在拥有相应 tmux server 的 Runtime identity 上运行；跨用户 attach 不支持。

## Recent output 安全

Recent output 仅针对 exact managed session，最多 200 行和 24 KiB。Runtime 先
限制 capture bytes，再去除 ANSI CSI/OSC 与 control characters。此处理防终端
控制序列注入，但不是 secret redaction，也不承诺能识别所有 secret。

输出是 authenticated、`Cache-Control: no-store`、`Pragma: no-cache` 的敏感
临时响应。Web 默认折叠且不自动请求，只以 React text/`pre` 渲染，不使用 raw
HTML；Hide/route unmount 清除内存。pane text 不进入 Audit metadata、AgentBox
log、DB、report、browser storage、URL 或 test screenshot/trace。Audit 只记录
`claude_output_viewed`、project ID 和 request metadata。

## API 与 CLI

API：

```text
GET  /api/v1/claude
GET  /api/v1/claude/sessions
GET  /api/v1/claude/sessions/{project_id}
POST /api/v1/claude/sessions/{project_id}/start
POST /api/v1/claude/sessions/{project_id}/stop
GET  /api/v1/claude/sessions/{project_id}/output
```

所有 endpoint 需要 authenticated admin；mutation 还要求 Origin/Host 与
session-bound CSRF，并拒绝 request body。CLI：

```text
agentbox claude status [--json]
agentbox claude list [--json]
agentbox claude start <project>
agentbox claude stop <project>
agentbox claude attach <project>
agentbox claude output <project>
```

attach/output 禁止 JSON；list 不显示 full path 或 pane content。

## Real-host validation 与限制

自动测试先于 real-host probing。允许的只读命令仅为 public help/version、tmux
version/list 和严格 current-user process observation；不得读取现有 pane 或停止
任何现有 session。专用 real test session 仅在明确测试目录、明确 test name、
exact cleanup 且不需要自动 Trust acceptance 时运行。

已知限制：Claude/tmux UI 和 public help 会变化；ready parser 是保守 hint 而非
官方 machine-readable health；tmux running 不等于 Remote connected；auth/trust
通常为 Unknown；bind mounts 与同 UID tmux tampering 不能由 path/marker 完全
消除；Phase 6 没有 Project CRUD、durable Jobs、Provider/Secret 管理、system-user
migration、installer、systemd 或 production deployment。
# Formal Project migration

Phase 7 changes Claude's public API identity to the formal opaque Project ID. API resolves it to the Project's immutable `relative_path` before sending a validated identifier over UDS. Runtime naming and markers still derive from that historical relative key, so Phase 6 managed sessions remain managed after reconciliation. Pull and branch switch fail with `PROJECT_RUNTIME_ACTIVE` while the managed Claude session is running or needs interaction; AgentBox still never auto-accepts Workspace Trust.
