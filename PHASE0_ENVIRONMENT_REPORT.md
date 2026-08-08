# AgentBox Phase 0 Environment Assessment

> 项目：AgentBox
> 审计时间：2026-08-06 23:46:29 +08:00
> 宿主机：`VM-0-2-opencloudos`
> 报告路径：`/root/AgentBox/PHASE0_ENVIRONMENT_REPORT.md`
> Overall status：**READY WITH WARNINGS**

## 1. Executive Summary

当前服务器具备启动 AgentBox 项目的基础条件，适合进入一个**不部署服务、不开放端口、以威胁模型、架构决策和仓库准备为主**的 Phase 1。

关键正向条件如下：

- 宿主机是 OpenCloudOS 9.4、x86_64、KVM 虚拟机，PID 1 为 systemd；`systemctl is-system-running` 返回 `running`。
- 2 vCPU、3.5 GiB 内存、根分区约 52 GiB 可用，足以进行轻量控制面原型和文档/构建工作。
- Git、GitHub CLI、Node.js、npm、corepack、pnpm、Python、GCC、Make、SQLite、tmux、bubblewrap、Codex standalone 和 Claude Code 均可用。
- GitHub CLI 的宿主机认证有效，GitHub API 可访问，经典 `repo` scope 已报告；未执行仓库创建。
- Codex 与 Claude 的安全登录状态检查均成功，未展示账号、Token 或认证配置。
- systemd system manager、cgroup v2、`/run` tmpfs 和 SQLite 均满足候选原生部署架构的基础条件。

没有确认到 Critical 或 High 级的**当前可利用**安全问题，但有多项必须优先处理的 Medium 级风险和实施门槛：

1. 当前 standalone Codex release 的 `bin` 目录和实际二进制由无本机账户映射的 UID/GID 1001 所有，且 owner 可写。`/root` 的 `0550` 权限目前阻止普通用户遍历，因此不能直接定性为现成提权漏洞；但在创建新用户、迁移文件或让 root helper 执行该二进制前，必须核验并规范所有权。
2. 存在一个已启用但当前 inactive/dead 的旧 `/etc/systemd/system/codex.service`。它以 root 运行、调用 `codex remote-control`，却指向当前不存在的 `/usr/bin/codex`，并使用 `Restart=always`。它目前不是 failed，`NRestarts=0`，但与现有 standalone 入口冲突，下一次启动/重启前必须审查处置。
3. 服务器不是空白开发机：`cloudflared` 已以 root active/enabled，且已有 SSH、x-ui、xray 相关监听。`8000` 已被占用。不得让 AgentBox 默认监听 `0.0.0.0`，也不得未经审查复用现有 Cloudflare Tunnel。
4. 当前 Codex/Claude 登录、tmux 会话、源目录均属于 root；这与候选的“Web/API 非 root”边界不兼容。未来不得简单复制 root 的认证文件或让 Web/API 继承 root 会话。
5. Git 尚未配置 `user.name` 和 `user.email`；当前目录不是 Git 仓库。首次提交前需要人工确定身份，但本阶段未修改配置、未执行 `git init`。

结论：**推荐状态为 READY WITH WARNINGS，而不是 BLOCKED**。推荐的下一步是先批准一个窄范围 Phase 1，完成身份/目录/权限模型、旧 Codex unit 处置方案、网络暴露策略和 helper 威胁模型；不要直接开始 daemon 或公网 Web 部署。

### 审计边界与非操作声明

默认命令执行环境受 Codex bubblewrap 隔离，沙箱 PID 1、网络命名空间和 systemd bus 不能代表宿主机。本报告对 OS、systemd、进程、tmux、GitHub 认证、监听端口和防火墙等关键事实使用了经授权的**宿主机只读查询**复核；沙箱失败结果没有被误写为宿主机事实。

本阶段唯一持久写入是本报告。未安装/卸载软件，未修改防火墙、SSH、网络、用户、sudoers、权限、systemd unit、Docker、Git 配置或认证；未初始化/提交/推送 Git，未创建 GitHub 仓库或 Issues，未生成 Codex Pair Code，未启动/停止 Codex daemon，未启动 Claude 或 Claude Remote Control，未创建/终止 tmux 会话，未执行 Workspace Trust。

## 2. Environment Inventory

状态含义：`PASS` 表示满足当前阶段；`WARN` 表示可继续但需处理；`ABSENT` 表示未安装或不存在；`UNKNOWN` 表示只读方式无法可靠确认；`INFO` 表示信息项。

| 检查项 | 状态 | 版本或结果 | 风险 | 建议 |
|---|---|---|---|---|
| 发行版 | PASS | OpenCloudOS 9.4 | 无直接风险 | Phase 1 保留 RPM 系兼容性；不要假定等同 Rocky Linux |
| 包管理器 | PASS | `dnf`、`yum`、`rpm 4.18.2` 可用 | `dnf --version` 在只读沙箱尝试写日志而 rc=1 | 安装动作留到单独授权阶段；适配器应检测能力而非仅检测发行版名 |
| 内核 | PASS | `6.6.119-47.8.oc9.x86_64` | 见 CPU 漏洞状态备注 | 后续核对云厂商微码和内核维护状态 |
| 架构 | PASS | x86_64 | 无 | 发布物需明确支持 x86_64；ARM64 另行验证 |
| 虚拟化/容器 | PASS | KVM VM；宿主机不是传统容器 | 默认审计进程另受 bwrap 隔离 | 原生 systemd 路线可行；保持“宿主视图/沙箱视图”区分 |
| CPU | WARN | 2 vCPU，AMD EPYC 9754 | AI 会话、前端构建和后台 Job 并发能力有限 | Phase 1 设计并发上限、队列和资源配额 |
| 内存 | WARN | 3.5 GiB，总可用约 1.4 GiB（审计快照） | 并发 Codex/Claude 可能 OOM | 默认低并发；监控 RSS/OOM；不要在本阶段修改 Swap |
| Swap | WARN | 0 | 内存峰值缺少缓冲 | 是否增加 Swap 需后续独立运维评估和授权 |
| 根磁盘 | PASS | XFS 60 GiB，已用约 8.1 GiB，可用约 52 GiB，14% | 容量足够，但 AI 日志/缓存可增长 | 分离日志、缓存、项目与状态；设置保留策略 |
| inode | PASS | 约 1% 使用 | 无 | 常规监控即可 |
| 主机名 | INFO | `VM-0-2-opencloudos` | 不应把主机名作为持久身份唯一来源 | 未来生成独立 instance ID |
| systemd system manager | PASS | systemd 255；PID 1=systemd；状态 `running` | 无 | 适合 system service/socket/timer |
| systemd user manager | UNKNOWN | `systemctl --user is-system-running` rc=1；root 无可用 user bus/session | 不能依赖当前 root user manager | MVP 优先 system unit 配合 `User=`；若采用 user unit，需单独设计 linger/session |
| cgroup 与 `/run` | PASS | cgroup v2；`/run` 为 rw tmpfs、`nosuid,nodev` | 无 | UDS/PID 放 `/run/agentbox`，由 systemd `RuntimeDirectory=` 管理 |
| SELinux | WARN | Disabled | 缺少一层强制访问控制 | 不是 Phase 1 硬阻塞；helper 必须使用最小权限和 systemd hardening |
| AppArmor | ABSENT | `aa-status` 不存在；systemd 构建为 `-APPARMOR` | 缺少另一层 MAC 防护 | 不要把设计安全性建立在 AppArmor 存在的假设上 |
| 当前用户 | WARN | root，UID/GID 0，仅 root 组 | 开发和 AI 会话全部落在 root 权限域 | Phase 1 决定开发用户、服务用户、workspace 用户模型 |
| sudo | INFO | `/usr/bin/sudo`，版本 1.9.15p5；当前已是 root | 沙箱内版本检查触发 seccomp/权限错误 | 当前无需 sudo；未来不授予 Web/API 通用 sudo |
| HOME / Shell / umask | INFO | `/root`；`/bin/bash`；`0022` | root HOME 认证不能直接供非 root 服务使用 | 每个运行身份使用独立 HOME 与最小权限 umask |
| 当前 PATH | WARN | 包含重复的 `/root/.local/bin`、standalone release 和 Codex 临时 arg0 目录 | 命令解析不可复现；systemd 不继承交互 PATH | 运行时显式配置稳定入口；禁止硬编码内部 release 路径 |
| 当前目录 | WARN | `/root/AgentBox`，root:root `0755`；宿主视图非 Git 仓库 | 父目录 `/root` 为 `0550`，非 root 无法遍历 | 仅适合 root-only 临时启动；最终源码建议迁往开发用户 HOME |
| `/root/projects` | WARN | 存在，root:root `0755` | 同样受 `/root` 父目录限制 | 不作为生产 workspace 根目录 |
| AgentBox 专用用户/组 | ABSENT | `getent` rc=2 | 不能直接实施非 root 架构 | 仅在用户批准身份模型后创建；创建前先处理 UID 1001 所有权问题 |
| Git | PASS | 2.43.7 | 无 | 可用于 Phase 1 仓库准备 |
| Git 仓库状态 | INFO | 当前不是 Git 仓库；宿主机无 `.git` | 无历史、远程或分支可检查 | 本阶段不执行 `git init`；后续单独授权 |
| Git 作者身份 | WARN | global/system `user.name`、`user.email` 均未配置 | 无法进行规范提交 | 首次 commit 前由用户提供并配置，不在 Phase 0 修改 |
| Git credential helper | PASS | GitHub/Gist 范围已配置 `gh auth git-credential`；无通用 helper | 无明显冲突 | 保留 scoped helper；不要设置明文 store helper |
| Git URL rewrite | PASS | 未发现 global `insteadOf` 规则 | 无 | 后续避免带 Token 的 URL rewrite |
| GitHub CLI | PASS | `/usr/bin/gh`，2.97.0 | 无 | 可用于后续明确授权的 GitHub 操作 |
| GitHub 登录 | PASS | 宿主 `gh auth status` rc=0，`gh api user` rc=0；详情已抑制 | 组织仓库创建仍受组织策略约束 | 个人仓库创建条件看起来具备；实际 owner/visibility 需用户确认 |
| Git 协议 | PASS | HTTPS | 无 | `gh` helper 已配置；无需在 Phase 0 运行 `gh auth setup-git` |
| Codex | WARN | standalone 0.146.1；`/root/.local/bin/codex` | 文件所有权和旧 systemd unit 存在冲突 | 见第 3 节；集成前处理，不要重装/卸载于本阶段 |
| Claude Code | WARN | 全局 npm `@anthropic-ai/claude-code@2.1.223` | 当前认证和会话属于 root | 见第 4 节；未来使用 workspace 用户独立认证 |
| tmux | PASS/WARN | 3.4；2 个 detached session、2 个 Claude pane | 现有会话均属于 root，非 root Web 无法接管 | 把它们视为 unmanaged；定义 AgentBox 命名空间和会话所有者 |
| bubblewrap | PASS | `/usr/bin/bwrap`，0.11.0；`--help` rc=0 | 未做复杂/写入式非 root 沙箱测试 | 当前满足可发现性；具体隔离模型需后续安全测试 |
| Python | PASS | 3.11.6 | 无 | 可用于脚本/后端候选评估，尚未锁定技术栈 |
| pip | ABSENT/WARN | `pip3` 不存在，`python3 -m pip` rc=1；`ensurepip 23.3.1` 可用 | Python 依赖安装目前不便 | 仅在技术栈确定后按明确授权补齐 |
| venv | PASS/LIMITED | `venv` 模块可导入，`python3 -m venv --help` rc=0 | 未实际创建环境，因此端到端未验证 | Phase 0 保持只读；需要时在项目路径内验证 |
| Node.js / npm | PASS | Node 22.23.2（NodeSource RPM）；npm 10.9.8 | 来源不是发行版默认仓库 | 固定支持范围与 lockfile；不要自行更换版本 |
| corepack / pnpm / yarn | PASS/WARN | corepack 0.34.6；pnpm 11.20.0；yarn 不存在 | pnpm 未由 RPM 拥有；升级来源需统一 | Phase 1 决定包管理器后再处理 |
| 编译工具 | PASS | GCC 12.3.1；Make 4.4.1 | 无 | 足够构建常见 native 依赖 |
| 网络/加密工具 | PASS | curl 8.4.0；wget 1.21.3；OpenSSL 3.0.12 | 无 | 下载/安装仍需单独授权和校验来源 |
| 数据/归档工具 | PASS | SQLite 3.42.0；rsync 3.2.7；tar 1.35；unzip 6.00 | 无 | SQLite 适合单机 MVP；设计备份与迁移流程 |
| jq | ABSENT | 命令不存在 | 部分运维脚本不便 | 非阻塞；仅按实际需要安装 |
| Docker | ABSENT | docker/dockerd/Compose/containerd/Podman 不存在；socket 和 docker 组不存在 | 无法采用 Docker 部署 | 原生 systemd 推荐方向不依赖 Docker；本阶段不安装 |
| 防火墙实现 | WARN | iptables-legacy 1.8.9；v4 约 493 条规则，默认策略 ACCEPT；v6 0 条规则，默认 ACCEPT | 完整规则与云安全组未审计，不能推断公网可达性 | 部署前由运维审查实际路径；不修改现有规则 |
| firewalld/nftables/ufw | ABSENT | 命令或 unit 不存在 | 不能依赖这些工具 | 适配器必须检测真实实现 |
| Cloudflare Tunnel | WARN | cloudflared 2026.3.0，active/enabled，以 root 运行 | 路由目标与访问策略未知；可能承载现有业务 | 不读取/修改现有配置；AgentBox 暴露需单独设计 |
| Tailscale | ABSENT | 命令和 unit 不存在 | 无 Tailscale 私网入口 | 非阻塞；不在 Phase 0 安装 |

### 2.1 Listening Ports Snapshot

以下为宿主机只读 `ss -H -lntupn` 的脱敏快照。未记录任何公网 IP。

| 绑定范围 | 端口 | 进程 | 说明 |
|---|---:|---|---|
| wildcard TCP | 22 | sshd | SSH；IPv4/IPv6 均监听 |
| wildcard TCP | 2096、3215 | x-ui | 现有服务；用途/访问控制未审计 |
| wildcard TCP | 8000、8001、8002、8003、55309 | xray | 现有服务；`8000` 明确与常见 Web 候选冲突 |
| loopback TCP | 11111、62789 | xray | 仅本机监听快照 |
| loopback TCP | 20241 | cloudflared | 现有 tunnel 本地端点或指标端点，具体用途未读取配置 |
| UDP unconnected | 多个临时高位端口 | cloudflared | 很可能是 QUIC 出站 socket；不据此认定为公网入站服务 |

审计快照中未发现 TCP listener 占用 `3000`、`3001`、`5173`、`8080`、`8443`、`9000`；这只是瞬时结果，不构成端口保留。推荐 API/helper 间使用 UDS，Web/API 初期只绑定 loopback，并在部署前再次检查。

## 3. Codex Assessment

### 3.1 安装来源、路径和版本

- `command -v codex`：`/root/.local/bin/codex`
- 解析后的真实路径：`/root/.codex/packages/standalone/releases/0.146.1-x86_64-unknown-linux-musl/bin/codex`
- `codex --version`：`codex-cli 0.146.1`
- `/root/.local/bin/codex` 是 root 所有的 symlink，指向 `/root/.codex/packages/standalone/current/bin/codex`；`current` 再指向具体 release。
- 该布局与 standalone 安装一致；但仅凭路径不能证明历史上一定执行过哪条安装脚本。
- 内部 `packages/standalone/...` 路径仅作为诊断证据，**不得作为 AgentBox 业务代码稳定接口**。候选稳定入口应为可配置并经 `command -v`/realpath 校验的 CLI 路径。

### 3.2 多版本与 npm 冲突

- 当前 PATH 因 `/root/.local/bin` 重复出现，`type -a codex` 四次显示同一逻辑路径；所有实例解析到同一 standalone 二进制，不是四个版本。
- 活跃 npm prefix 为 `/usr`，`npm ls -g --depth=0` 未发现 `@openai/codex` 或 `codex`。
- 已检查 `/usr/lib/node_modules`、`/usr/local/lib/node_modules`、`/root/.local/lib/node_modules`、`/root/.npm-global/lib/node_modules` 及 NVM 常见目录；未发现第二份 npm Codex。
- 当前 shell 及已检查的 root bash 启动文件未发现 `codex` alias/function；未发现 wrapper 覆盖当前入口。

结论：**未发现 npm 版 Codex 与 standalone Codex 的实际冲突**。不能对任意自定义、未在 PATH 的未知目录作绝对证明，但当前解析、npm prefix 和常见安装根的证据一致。

### 3.3 Remote Control 能力

`codex remote-control --help` rc=0，当前版本显示：

- `start`
- `stop`
- `pair`
- `help`

没有 `status` 子命令。本阶段仅执行 help；未执行 `start`、`stop`、`pair`，没有生成或显示 Pair Code。

`codex login status` rc=0，脱敏结果为 root 用户已通过 ChatGPT 登录。未显示账号、Token、Cookie 或认证配置。该状态只属于当前 root HOME，不能代表未来 workspace/service 用户。

### 3.4 现有 service 与进程

发现 `/etc/systemd/system/codex.service`：

- unit 文件 root:root、`0644`，已 enabled；宿主机状态为 inactive/dead，`is-failed` 返回 inactive，`Result=success`，`NRestarts=0`。
- 静态脱敏检查表明：`Type=simple`、`User=root`、`WorkingDirectory=/root`、`Restart=always`，ExecStart 包含 `codex remote-control`。
- ExecStart 使用 `/usr/bin/codex`，但宿主机当前不存在该路径；现有 standalone 入口是 `/root/.local/bin/codex`。
- unit 没有显式 `start` 参数、没有 drop-in，且未发现所检查的常见 systemd hardening 指令。
- 存在一个非凭据类 Environment 指令；未发现 Token/Key/Password/Secret/Auth 类变量名。具体值未写入报告。

这不是当前活跃 daemon，但它是明确的旧配置冲突：如果未来随开机或人工启动，可能因入口缺失而失败；同时其未显式使用当前 help 列出的 `start` 子命令，实际行为需要单独复核。它也可能产生重启日志。Phase 0 不修改它。

宿主进程快照中有 2 个 root `codex` 进程，其参数均包含精确 `app-server` 参数；另有 1 个 `codex-code-mode` 进程。没有进程包含精确 `remote-control` 参数。它们很可能与当前 Codex 控制环境有关，但这是推断，不能把它们等同为独立 Remote Control daemon。

结论：**未确认正在运行的 systemd-managed Codex Remote Control daemon**；旧 unit inactive，手工 daemon 也未被可靠确认。因为当前版本无 `status`，后续适配器必须组合 unit 状态、受控进程元数据和版本能力检查，不能假设 `status` 存在。

### 3.5 文件所有权风险

宿主机视图确认：实际 standalone binary 及其 `bin` 目录为 UID/GID 1001 所有，系统中没有对应 passwd/group 条目；文件和目录均允许 owner 写入。root 的 symlink 与上层目录为 root 所有，且 `/root` 为 `0550`，当前普通用户不能遍历，因此没有证据表明此刻可由非特权用户直接改写。

建议在任何以下动作前进行一次单独授权的完整性与所有权修复评估：

- 创建可能获得 UID 1001 的新用户；
- 把 standalone release 迁出 `/root`；
- 让 privileged helper 或 systemd root unit 执行该二进制；
- 将 Codex 交给非 root workspace 用户管理。

不要在业务代码中通过内部 release 路径“绕过”这个问题，也不要在 Phase 0 自行 `chown`、卸载或重装。

## 4. Claude Assessment

### 4.1 安装与能力

- `command -v claude`：`/usr/bin/claude`
- 真实路径：`/usr/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`
- 版本：`2.1.223 (Claude Code)`
- npm global package：`@anthropic-ai/claude-code@2.1.223`
- 安装来源可判断为 root 管理的全局 npm 包；具体历史安装命令无法仅凭路径证明。
- PATH 与已检查的常见全局包目录只发现这一份 Claude；未发现 alias/function 冲突。
- `claude --help`、`claude auth --help` 均成功；主帮助显示 `--remote-control [name]` 会启动交互式 Remote Control 会话。本阶段未执行该选项。

`claude auth status` rc=0；脱敏解析显示已通过 Anthropic first-party OAuth 登录。未输出账号、Token、OAuth Code 或认证文件内容。这个状态属于 root HOME，不能证明未来非 root AgentBox 用户已登录。

### 4.2 tmux、进程与 Remote Control

- tmux 3.4 可用。
- 宿主 root tmux server 当前有 2 个 detached sessions、2 个 panes；两个 pane 当前命令均为 Claude。
- 其中 1 个 session 名称包含 Claude，0 个名称包含 AgentBox；具体名称未在报告中展示。
- 宿主进程快照包含 2 个 `claude` wrapper 和 5 个 `claude.exe` 进程，均属于 root。
- 对这些进程只做精确参数标志计数，0 个包含 `--remote-control`；参数内容和 PID 均未输出。

结论：存在正在运行的 root Claude/tmux 会话，但**没有确认正在运行的 Claude Remote Control 会话**。现有会话应视为 unmanaged，AgentBox 不应自动接管、kill、重命名或复用其 socket。

### 4.3 Workspace Trust 和身份边界

- 未启动交互式 Claude，未执行 Workspace Trust，当前 trust 状态未知。
- 不得信任 `/root` 这个宽泛目录。
- 后续只对所有权明确的具体工作树执行 trust，例如 `/srv/agentbox/projects/<owner>/<project>`；信任动作必须由对应 workspace 用户完成。
- `/root/AgentBox` 虽是具体目录，但未来非 root Web/API 无法穿越 `/root`，不适合作为长期 Claude workspace。
- tmux socket、Git 工作树和 Claude 进程必须属于同一个 workspace 用户；root helper 只允许发起白名单动作，不能把交互会话长期作为 root 运行。

## 5. GitHub Assessment

### 5.1 Git

- Git 2.43.7 已安装。
- `/root/AgentBox` 在宿主机视图中不是 Git 仓库；不存在 `.git`。沙箱中出现的只读空 `.git` 是权限隔离占位，不代表真实仓库。
- system/global `user.name` 与 `user.email` 均未配置。
- 没有执行 `git init`、status 之外的仓库操作、commit、branch、remote、push 或 force push。

### 5.2 GitHub CLI 与认证

- GitHub CLI：`/usr/bin/gh`，2.97.0。
- `gh config get git_protocol --host github.com`：HTTPS，rc=0。
- 宿主机 `gh auth status --hostname github.com`：rc=0。
- 宿主机 `gh api user` 只读请求：rc=0；API 返回内容被抑制。
- 认证状态报告经典 `repo` scope 存在；其他 scope、账号名和 Token 均未输出。
- `GH_TOKEN`、`GITHUB_TOKEN`、`GH_ENTERPRISE_TOKEN`、`GITHUB_ENTERPRISE_TOKEN` 未设置，因此没有环境变量覆盖当前认证。
- GitHub/Gist 专用 credential helper 已指向 `gh auth git-credential`；未配置通用 `credential.helper`，未发现 URL rewrite。

结论：当前 CLI、认证和 scope **看起来具备创建个人 GitHub 仓库的前提**。没有执行创建操作，因此无法验证目标组织的组织策略、SSO、仓库创建限制或最终 owner/visibility。还需要用户人工决定：仓库属于个人还是组织、public/private、License，以及 Git 作者身份。

不需要在当前状态下重新执行 `gh auth login` 或 `gh auth setup-git`；本阶段也没有执行它们。

## 6. Security Findings

本节只按现有证据分级，不把未来设计风险夸大成当前漏洞。

### Critical

- **未确认 Critical finding。**

### High

- **未确认当前可利用的 High finding。**

### Medium

| ID | Finding | 影响 | 当前缓解/证据边界 | 建议 |
|---|---|---|---|---|
| M-01 | standalone Codex 的实际 release `bin` 和二进制由无账户映射 UID/GID 1001 所有且 owner 可写 | 若路径被迁出 `/root`、权限放宽或未来复用 UID 1001，root 执行链完整性可能失守 | `/root` 当前 `0550`，普通用户不能遍历；没有当前利用证据 | 创建用户或集成 root helper 前核验官方安装器预期并规范所有权/完整性 |
| M-02 | 已启用的旧 root `codex.service` 指向不存在的 `/usr/bin/codex`，未显式使用 0.146.1 help 列出的 `start` 子命令，且缺少常见 hardening | 下次启动/重启可能失败、循环记录日志，且未来若修通会以 root 运行 Remote Control | 当前 inactive/dead、非 failed、0 restarts；无入口时的失败是确定风险，省略 `start` 的实际行为仍待复核 | 在独立授权步骤中审查、迁移或停用；AgentBox 不得直接接管 |
| M-03 | wildcard TCP 已有 SSH、x-ui、xray 服务；`8000` 已占用；iptables 默认策略 ACCEPT | 新服务若默认 wildcard 绑定，可能与现有业务冲突或产生非预期暴露 | v4 有大量规则；云安全组和真实外部可达性未知 | Web 初期仅 loopback；部署前做端口/iptables/云防火墙联合审查 |
| M-04 | cloudflared 以 root active/enabled，现有 tunnel 路由与访问控制未知 | 未经审查复用可能把管理面暴露到既有入口或影响生产隧道 | 配置和 Token 未读取；没有修改 service | 把现有 tunnel 当作生产依赖；AgentBox 接入需独立变更评审 |
| M-05 | SELinux disabled、AppArmor 不可用 | root helper/Web 边界缺少 MAC 防御纵深 | systemd seccomp/cgroup 能力存在 | helper 做极小白名单、UDS 对端校验和严格 systemd sandboxing |
| M-06 | 当前 Codex/Claude/tmux/认证均在 root 权限域 | 非 root Web/API 若直接调用 root HOME 会扩大权限和泄露面 | 候选架构尚未实施 | 每个 workspace 用户独立 HOME、认证、Git ownership 和 tmux socket；不得复制 root Token |

### Low

| ID | Finding | 建议 |
|---|---|---|
| L-01 | 2 vCPU、3.5 GiB 内存、无 Swap，且已有多个 AI 与网络进程 | 设计有界 Job 队列、并发限制和 OOM/磁盘监控 |
| L-02 | 内核把 `Spec rstack overflow`、`Spec store bypass`、`TSA` 报告为 vulnerable，其中部分状态提示缺少 microcode | 与云厂商核对微码和内核公告；当前报告不推断可利用性 |
| L-03 | 当前 PATH 重复并含内部 release/临时 arg0 目录 | systemd 使用明确、稳定、可配置的入口和最小 PATH |
| L-04 | `/root/AgentBox` 与 `/root/projects` 不可供普通用户遍历 | 源码和 workspace 迁往清晰的非 root 所有权边界 |
| L-05 | Git 作者身份缺失 | 首次 commit 前由用户配置 |
| L-06 | pip、jq、yarn 缺失；pnpm 不属于 RPM | 技术栈确定后按需安装，不作为 Phase 1 预先假设 |

### Informational

- Docker/Compose/containerd/Podman 不存在；不是原生 systemd 方向的阻塞项。
- Tailscale 不存在；Cloudflare Tunnel 已存在。
- root systemd user manager 当前不可用，但 system manager 正常；可以用 system unit 的 `User=` 运行非 root 服务。
- 审计时 `3000`、`3001`、`5173`、`8080`、`8443`、`9000` 无 TCP listener；不构成未来可用保证。
- Codex Remote Control 当前没有 `status` 子命令。

## 7. Recommended Directory Layout

### 7.1 对题目所列目录的评估

| 目录 | 当前状态 | 适合用途 | 结论 |
|---|---|---|---|
| `/root/projects` | 已存在，root:root `0755`；父目录 `/root` `0550` | root-only 临时项目 | 不推荐作为 AgentBox 用户项目根；非 root、迁移和多用户边界差 |
| `/opt/agentbox` | 不存在 | 安装后的 immutable releases、启动包装、Web 静态文件 | 推荐，但不放可变项目/SQLite/日志 |
| `/opt/agentbox/projects` | 不存在 | 题目候选用户项目目录 | 不推荐；会混淆安装物、升级和用户数据 |
| `/srv/agentbox` | 不存在 | AgentBox 服务的数据域根 | 推荐作为 workspace/project 的命名空间 |
| `/srv/agentbox/projects` | 不存在 | 按用户/项目划分的 Git/Claude 工作树 | 推荐；每个子树由实际 workspace 用户所有 |
| `/var/lib/agentbox` | 不存在 | SQLite、Job 状态、instance ID、持久运行状态 | 推荐；纳入备份和 schema migration |
| `/etc/agentbox` | 不存在 | root 管理的配置、policy、非明文引用型 secrets 配置 | 推荐；配置与状态分离 |
| `/var/log/agentbox` | 不存在 | 可选文件日志 | 可选；优先 journald，只有明确需求才创建 |

### 7.2 推荐布局

| 类别 | 推荐位置 | 所有权/设计原则 |
|---|---|---|
| 开发源代码 checkout | `/home/<developer>/src/AgentBox` | 开发用户所有；`/root/AgentBox` 只作当前临时位置 |
| 安装 releases | `/opt/agentbox/releases/<version>` | root:root，只读；升级采用版本目录与 `current` symlink |
| 当前安装入口 | `/opt/agentbox/current` | root 管理 symlink；便于回滚和迁移 |
| React 静态文件 | `/opt/agentbox/current/web` | 只读；Web 服务只能读取，不得从 workspace 直接 serve |
| 用户项目/workspace | `/srv/agentbox/projects/<owner>/<project>` | 对应 workspace 用户所有；Git、Claude、tmux 同 UID |
| 配置 | `/etc/agentbox` | root 所有；Web/API 只读必要子集；secret 不进入日志/仓库 |
| 持久状态/SQLite | `/var/lib/agentbox` | AgentBox service 用户所有；数据库与项目备份分开 |
| 缓存 | `/var/cache/agentbox` | 可重建；设置大小/过期策略 |
| 日志 | journald；可选 `/var/log/agentbox` | 结构化、脱敏、限制保留；不记录 Token/Pair Code |
| systemd units（手工部署） | `/etc/systemd/system` | root 管理；helper、API、worker、socket 分离 |
| systemd units（RPM 包） | 发行版 vendor unit 目录，当前通常 `/usr/lib/systemd/system` | 不把手工配置写进 vendor 目录 |
| UDS/PID/短期运行数据 | `/run/agentbox` | `RuntimeDirectory=agentbox`；重启可丢失；socket mode `0660` |
| 临时大文件 | `/var/tmp/agentbox`（如确有需要） | 有界、可清理、不可放凭据；不要与持久状态混用 |

### 7.3 迁移、备份和多用户原则

- 把源码、安装 release、用户 workspace、配置、状态、日志严格分开，服务器迁移时可独立恢复 `/etc/agentbox`、`/var/lib/agentbox`、`/srv/agentbox/projects`。
- SQLite 备份使用一致性快照/SQLite backup API，不直接复制活跃 WAL 组合中的单个数据库文件。
- Web/API 不得获得对整个 `/srv/agentbox/projects` 的任意路径读写；文件动作需 canonicalize 路径并限定到已登记 workspace root。
- 不设置全局 `safe.directory=*`。Git 文件所有权必须与执行 Git/Claude/tmux 的 workspace 用户一致。
- Claude Workspace Trust 只授予具体工作树，不授予 `/root`、`/srv/agentbox/projects` 总根或其他宽泛父目录。
- tmux 会话按用户隔离，建议定义稳定名称规则，例如 AgentBox 内部 ID 映射，而不是直接信任用户输入作为 socket/session 名。

当前目录 `/root/AgentBox` 可用于保存本报告和 root-only 的短期 Phase 1 准备，但不应成为最终生产服务或多用户 workspace 位置。

## 8. Recommended Deployment Direction

### 8.1 推荐：原生 systemd 为主，保留有限混合部署选项

当前服务器最适合**原生 systemd 部署**：

- systemd 255 正常运行，cgroup v2 和 `/run` tmpfs 可用。
- AgentBox 需要管理宿主机 systemd、安装/升级、真实项目目录、Git、Codex/Claude、tmux；全部放进 Docker 会引入宿主 socket、目录和权限穿透，反而扩大边界。
- Docker 当前完全未安装；为 Phase 1 安装 Docker 没有必要。
- 将来可选“混合部署”：纯 Web 静态/API 层可容器化，但 privileged helper、workspace session 和宿主集成仍应原生。这个选项不在 Phase 1 实施。

### 8.2 候选架构适配性

| 方向 | 适配性 | 预检查结论 |
|---|---|---|
| Web/API 非 root | 适合，但尚未具备身份/目录 | 必须创建专用低权限身份；不能使用 root HOME 或 root tmux socket |
| 独立 privileged helper | 适合，且必要 | root 运行，但只接受结构化白名单 action；绝不接受任意 shell/命令/环境变量/路径 |
| Unix Domain Socket | 很适合 | 使用 `/run/agentbox/helper.sock`、`0660`、专用 group、`SO_PEERCRED`；设置消息大小和超时 |
| SQLite | 适合单机 MVP | `/var/lib/agentbox`；WAL/备份/迁移/单 writer 策略需设计 |
| React 静态前端 | 工具链具备 | Node/npm/pnpm 可用；build artifact 只读部署到 `/opt`，不直接访问 workspace |
| SSE | 推荐作为默认状态流 | 适合 Job 状态、事件和脱敏日志；断线重连与事件游标较简单 |
| WebSocket | 有条件使用 | 仅用于需要双向交互的 PTY/终端；鉴权、限流、尺寸限制、idle timeout 必须独立设计 |
| 后台 Job 模型 | 必须 | 安装、升级、诊断、Git、daemon/session 操作需有 durable state、幂等、取消、超时、审计与恢复 |

推荐控制边界：

```text
Browser
   |
   v
AgentBox Web/API (non-root, loopback/受控入口)
   |
   +-- SSE: job/status/log events
   +-- WebSocket: only authenticated PTY when needed
   |
   v
/run/agentbox/helper.sock (0660 + SO_PEERCRED + framed allowlisted RPC)
   |
   v
AgentBox Privileged Helper (root, minimal surface)
   |
   +-- systemd allowlist
   +-- verified install/update actions
   +-- bounded ownership/path actions
   +-- launch session work as the selected workspace UID
```

helper 必须拒绝：任意 shell 字符串、任意 argv passthrough、任意环境变量注入、未登记路径、符号链接逃逸、直接返回认证文件、Pair Code 入日志。Codex/Claude/tmux 的长期进程应属于 workspace 用户，而不是 helper/root。

网络方向上，Web/API 首期只绑定 loopback 或由 systemd socket 接受本机连接；不要直接使用 wildcard port。现有 cloudflared 是否作为入口，需要在后续独立审查 tunnel route、Access policy、TLS、认证和回滚方案。

## 9. Blocking Items

### 9.1 对推荐 Phase 1 的判断

对于第 11 节所提议的“决策、威胁模型、ADR、仓库准备”型 Phase 1，**没有系统级硬阻塞**。因此总体状态不是 BLOCKED。

但以下是必须设置的阶段门槛：

1. **首次 Git commit 前**：由用户确定并配置 Git `user.name`/`user.email`，并确认源码最终目录/所有者。
2. **创建任何新 Linux 用户前**：核对将分配的 UID/GID，不得在未处理 Codex UID/GID 1001 所有权异常时复用 1001。
3. **任何 Codex daemon 集成前**：人工审查并决定旧 `codex.service` 的迁移、停用或替换；不得让 AgentBox 自动改写或启动它。
4. **任何 root helper 执行 Codex 前**：验证 standalone 二进制完整性、所有权和稳定入口；业务代码不得引用内部 release 路径。
5. **任何非 root Claude/Codex/tmux 实施前**：确定 workspace UID、HOME、认证、Workspace Trust、Git ownership 和 tmux socket 策略；不得复制 root 凭据。
6. **任何 Web/API 启动或网络暴露前**：重新检查监听端口，避开 `8000` 及现有服务；审查 iptables、云安全组和 cloudflared 路由；初始只允许 loopback/UDS。

如果用户要求 Phase 1 立即创建用户、启动服务或开放入口，上述第 2—6 项会成为实际阻塞；推荐 Phase 1 明确排除这些动作。

## 10. Non-blocking Items

- Docker、Docker Compose、containerd、Podman 缺失：原生 systemd 方向不依赖它们。
- Tailscale 缺失：可继续；远程接入方案以后单独选择。
- pip、jq、yarn 缺失：不妨碍架构和仓库准备，技术栈确定后按需安装。
- Python venv 只验证模块/help，未实际创建：Phase 0 的只读限制所致。
- root systemd user manager 不可用：system manager 正常，可先使用 system unit + `User=`。
- SELinux disabled/AppArmor 不存在：不是立即开发阻塞，但提高了 helper 自身隔离要求。
- 无 Swap 和资源较小：不阻塞轻量 Phase 1，但需要从第一版设计并发控制。
- 内核 CPU 漏洞状态：需要云厂商/内核维护核对，不阻塞文档与 ADR 工作。
- 当前候选空闲端口只是快照：无需在 Phase 1 预留或开放端口。
- 当前 GitHub 组织级创建权限未知：个人仓库前提看起来具备；最终 namespace 由用户决定。

## 11. Proposed Phase 1 Scope

建议 Phase 1 仍保持窄范围，不实现 AgentBox 产品功能，不部署 daemon，不开放端口：

1. **项目与仓库决策**
   - 确认 repository owner、public/private、License、Git 作者身份。
   - 确认源码目录和开发用户；决定是否从 `/root/AgentBox` 迁往 `/home/<developer>/src/AgentBox`。
   - 在单独授权后初始化本地 Git；GitHub 仓库创建另行确认，不批量创建 Issues。

2. **ADR 与威胁模型**
   - 固化 Web/API、helper、workspace user、systemd、tmux、Codex/Claude 的信任边界。
   - 定义白名单 RPC schema、UDS peer credential、路径 canonicalization、审计/脱敏规范。
   - 决定 SSE/WebSocket 分工、Job 状态机和 SQLite 并发/备份策略。

3. **生命周期与发现契约**
   - 定义 CLI discovery 顺序：configured path → `command -v` → realpath/版本/能力；内部 standalone path 仅作诊断。
   - 定义版本能力矩阵，尤其是 Codex `remote-control status` 不可假设存在。
   - 定义 existing/unmanaged session 与 AgentBox-managed session 的边界和命名规则。

4. **安全整改计划（先计划，后单独授权执行）**
   - 对 Codex UID/GID 1001 所有权、旧 `codex.service`、root 认证和 tmux 会话制定迁移/回滚步骤。
   - 对现有 cloudflared、iptables、x-ui/xray 设立“不触碰”清单和端口分配流程。
   - 设计 systemd hardening baseline 和最小权限 service accounts。

5. **最小仓库治理材料**
   - README/定位、LICENSE、SECURITY、CONTRIBUTING、ADR 索引、兼容性矩阵与 Phase 计划。
   - 暂不创建完整工程骨架，不实现 Web/API/helper，不安装依赖，不创建 GitHub Issues。

Phase 1 结束条件应是：关键身份/目录/安全决策有书面 ADR，旧环境冲突有可回滚整改方案，仓库归属与 Git 身份明确；仍未在生产端口启动 AgentBox。

## Appendix A. Failed and Unknown Check Ledger

以下记录关键失败命令、退出码、脱敏输出和处置。语义性非零退出码也保留，避免把“未找到/未运行”伪装成成功。

| 命令 | Exit | 脱敏结果 | 原因分析 / 最终判定 |
|---|---:|---|---|
| `systemctl is-system-running`（默认沙箱） | 1 | `Operation not permitted` | bwrap 无宿主 bus；宿主只读复核 rc=0、`running`，以后者为准 |
| `ss -H -lntupn`（默认沙箱） | 0 但有 stderr | 无法打开 netlink socket | 沙箱网络命名空间/权限限制；宿主复核 rc=0 并已脱敏记录 |
| `iptables -S`（默认沙箱） | 3 | permission denied | 沙箱能力不足；宿主复核 rc=0，默认策略/规则计数已记录 |
| `gh auth status --hostname github.com`（默认沙箱） | 1 | 认证/网络检查失败，详情抑制 | 沙箱网络边界导致不可信；宿主复核 rc=0，`gh api user` rc=0 |
| `systemd-detect-virt --container`（宿主） | 1 | `none` | 语义性负结果：宿主不是传统容器；KVM VM 检测 rc=0 |
| `aa-status --enabled` | 127 | command not found | AppArmor 工具/能力不存在 |
| `python3 -m pip --version` | 1 | `No module named pip` | pip module 缺失；`ensurepip --version` rc=0，未执行安装 |
| `command -v pip3 virtualenv yarn jq` | 127/未找到 | command not found | 工具缺失；均为非阻塞，不安装 |
| `command -v docker dockerd docker-compose podman containerd` | 127/未找到 | command not found | Docker 栈未安装；socket/unit 也不存在 |
| `command -v firewall-cmd nft ufw` | 127/未找到 | command not found | 当前实现为 iptables-legacy，不是这些前端 |
| `command -v tailscale tailscaled` | 127/未找到 | command not found | Tailscale 未安装 |
| `systemctl is-active codex.service` | 3 | `inactive` | 语义性状态码；unit enabled 但 inactive/dead |
| `systemctl is-failed codex.service` | 1 | `inactive` | unit 当前不是 failed；`Result=success`、`NRestarts=0` |
| `systemctl --user is-system-running`（宿主当前 root 上下文） | 1 | bus/session unavailable，详情抑制 | root user manager 不可用；system manager 正常 |
| `loginctl show-user root ...` | 1 | 当前无可查询 logind user state | 不影响 system service；user-unit/linger 仍未配置 |
| `git -C /root/AgentBox rev-parse --is-inside-work-tree` | 128 | `not a git repository` | 当前目录确实未初始化；未执行 `git init` |
| `git -C /root/AgentBox status ...` | 128 | `not a git repository` | 同上；没有伪造 Git status |
| Git system/global `user.name`/`user.email` query | 1 | no value | Git 作者身份未配置 |
| `getent passwd 1001` / `getent group 1001` | 2 | no entry | standalone Codex 所有者 UID/GID 无本机映射 |
| `getent passwd agentbox` / `getent group agentbox` | 2 | no entry | AgentBox 专用身份尚不存在；本阶段不创建 |
| `sudo --version`（默认沙箱） | 1 | 版本显示后出现 setresuid/audit 限制 | bwrap/seccomp artifact，不证明宿主 sudo 故障；当前为 root，无需 sudo |
| `dnf --version`（默认只读沙箱） | 1 | 显示 4.16.2 后无法写 hawkey log | dnf 的日志写入与只读根冲突；`command -v dnf` 成功，不在 Phase 0 运行安装 |
| `timedatectl show -p Timezone`（默认沙箱） | 1 | bus unavailable | 报告时间取 `date` 的 `+08:00` 和会话环境 `Asia/Beijing`；未声称宿主 timedatectl 成功 |

Codex `--version`/help/status 均 rc=0，但在默认只读沙箱提示无法创建 PATH aliases；该写入尝试被只读挂载阻止，版本/能力结果仍有效，没有发生持久修改。

## Appendix B. Recommended Next Action Order

1. 用户确认 Phase 1 只包含决策、ADR、仓库准备，不包含服务/端口/用户修改。
2. 确定 Git 作者身份、repository owner/visibility/License 和源码最终所有者/路径。
3. 在创建任何用户前，制定 Codex UID/GID 1001 所有权核验与修复方案。
4. 审查旧 `codex.service`，决定迁移/停用/替换；在单独授权前保持不变、不启动。
5. 完成 Web/API、root helper、workspace 用户、UDS、路径和审计日志的威胁模型与 ADR。
6. 定义 read-only discovery contract、版本能力矩阵和 unmanaged session 规则。
7. 仅在用户再次批准后初始化 Git/创建最小治理文件；GitHub 仓库创建再单独确认。
8. FHS 目录、用户、unit、依赖安装和网络入口全部留到后续明确授权阶段；部署前重新审计端口、iptables、云安全组和 cloudflared。

---

**Phase 0 到此停止。未自动进入 Phase 1。**
