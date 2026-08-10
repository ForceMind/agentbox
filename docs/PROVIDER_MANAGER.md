# AgentBox Provider, Secret & Runtime Continuity Management

Status: future architecture and product backlog; not implemented

## Product Goal and Planning Guardrails

Phase 11 — Provider, Secret & Runtime Continuity Management 将允许管理员安全配置、
测试和切换 AI Runtime 使用的模型/API Provider，同时对 Runtime、Remote Control、
thread/session discovery 和上下文连续性给出分层、可验证且诚实的结果。该规划由
[GitHub Issue #23](https://github.com/ForceMind/agentbox/issues/23) 跟踪，排在
Phase 10 之后，不改变当前 Phase 顺序。

本文件只定义未来架构，不授权实现。当前不得创建 Secret Store、读取 API Key、
修改 Codex 配置、切换 Provider、重启 Runtime、修改 Remote Control 或迁移任何
session/thread 数据。

可复用的历史产品思想可以作为候选兼容策略和测试证据，但不得把旧工具曾观察到的
Codex Provider ID、SQLite、JSONL、rollout、thread/list 或 wire protocol 行为升级
为 AgentBox 永久协议。所有 Runtime-specific 行为必须在实施 Phase 11 前依据最新
公开文档、CLI、配置 schema 和受控测试重新验证。

## Architecture Boundary

Remote Control Manager 管理 AgentBox 如何连接和控制 Runtime；Provider Manager
管理 ProviderDefinition、Active Provider 和测试；Runtime Continuity Manager
评估切换对活跃工作和历史连续性的影响；Secret Manager 保管 Secret；Runtime-specific
Adapter 才能把稳定的 AgentBox 意图映射到当时公开支持的 Runtime 配置契约。

```text
Provider Manager
├── Provider Registry
├── Active Provider Binding
├── Provider Test Orchestrator
├── Runtime Continuity Manager
├── Config Transaction Manager
├── Secret Manager
└── Runtime-specific Provider Config Adapters
    ├── CodexProviderConfigAdapter
    ├── ClaudeProviderConfigAdapter（仅在官方支持时）
    └── FutureRuntimeProviderConfigAdapter
```

Provider Manager 不是 `config.toml` 的别名，也不是第二套 Remote daemon manager。
调用方不得提交原始配置文本、任意配置键、环境映射、文件路径、进程参数或 Secret。

## Provider Identity and Runtime Binding Identity

未来 domain 明确分开两种身份：

- `ProviderDefinitionID` 标识一个具体 Provider 配置。其 identity input 至少包含
  provider type、normalized base URL 和 protocol/wire API；具体规范化和 ID 算法
  留到实现阶段决定。Base URL 变化通常产生新的 ProviderDefinition，或进入显式
  transactional migration，不能静默重用旧 identity。
- `RuntimeBindingID` 标识 AgentBox 希望 Runtime/session 保持稳定的 Provider
  binding intent。它不是 ProviderDefinitionID，也不永久等同于 Codex 当前任何
  `model_provider` ID。

```text
AgentBox RuntimeBindingID
        ↓
Runtime-specific config adapter
        ↓
current public Runtime provider/session identity mechanism
```

历史 `PROVIDER_ID` / `SESSION_PROVIDER_ID` 分离思想只作为 `Runtime Continuity
Strategy`：backend 可以变化，而 Runtime binding identity 在公开支持时尽量稳定。
AgentBox 不假设 Codex 永远按 Provider ID 过滤 thread/list，不假设替换 provider
block 一定保留 thread，也不把当前 session storage 格式视为稳定接口。

## Provider Registry and Active Binding

每个 `ProviderDefinition` 规划保存以下非 Secret metadata：

- `ProviderDefinitionID`、display name、provider type；
- normalized base URL、protocol/wire API、model；
- Runtime-specific model reasoning options 和其他版本化 typed options；
- opaque Secret reference；
- detailed compatibility result、last tested time 和 lifecycle status。

Reasoning 配置由 Runtime schema、model capability 和当时官方文档定义。历史
`none/minimal/low/medium/high/xhigh` 只能作为 fixture，不进入 AgentBox 永久 enum；
Adapter capability validation 必须拒绝不支持的值。

AgentBox DB 未来分别保存 Active Provider reference 和 Runtime Binding metadata；
Secret material 留在 Secret Manager，Codex-specific binding 由 Adapter 写入受控配置。
Add/Edit/Remove/List/Test/Set Active/Rotate Secret 都是 typed use case。切换不会删除
其他 Provider，也不自动 fallback 到另一个 Provider。管理员选择的 Active Provider
在 AgentBox 重启后恢复；恢复失败时报告失败，不自动换 Provider。

删除 ProviderDefinition 前检查它是否 active、被 RuntimeBinding 引用、是最后回滚
目标，以及对应 Secret 是否存在。Active Provider 必须先显式切换。删除 metadata
和删除 Secret 是单独确认的 transaction。Secret rotation 只替换该 Provider 的
Secret material，不改变 ProviderDefinitionID、RuntimeBindingID、model 或 base URL，
随后至少重测 Authentication 与 Provider Protocol。

## Runtime Continuity Manager

`RuntimeContinuityManager` 负责：

- provider switch preflight；
- 只基于公开可靠信号的 active turn/tool call/response/writer/duplicate Runtime 检测；
- active writer protection；
- Runtime、Remote reconnect、thread resume、context 和 discovery assessment；
- 回滚后的 continuity assessment 与恢复 guidance。

如果无法可靠判断 active writer，切换流程必须要求管理员确认当前 turn 已完成，不能
通过删除 session 文件、强杀未知 writer 或修改 private state 解决冲突。Provider
Manager 本身不得声称 thread continuity。

### Continuity Capability Levels

| Level | Meaning |
|---|---|
| `LEVEL_0_PROVIDER_REACHABLE` | Provider endpoint/API 可用 |
| `LEVEL_1_RUNTIME_REQUEST` | Runtime 能完成新的最小请求 |
| `LEVEL_2_REMOTE_RECOVERY` | 切换后 Remote Control 可以恢复 |
| `LEVEL_3_THREAD_RESUME` | 切换前已有 thread 可通过公开接口继续 |
| `LEVEL_4_CONTEXT_CONTINUITY` | 新 backend 实际收到并使用此前上下文 |
| `LEVEL_5_THREAD_DISCOVERY` | 原 thread 仍可在正常 list/history discovery 中发现 |

每层必须有独立证据。上一层 PASS 不能代替下一层；例如 Runtime request PASS 不能
推导 Thread Resume、Context Continuity 或 Thread Discovery PASS。

## Compatibility Result

未来测试至少分别报告：Network、Authentication、Model Availability、Wire Protocol、
Provider API、Codex Runtime、Remote Control、Thread Resume、Context Continuity 和
Thread Discovery。每项状态为：

```text
PASS | FAIL | UNSUPPORTED | EXPERIMENTAL | UNKNOWN | NOT_TESTED
```

汇总 classification 可为 `SUPPORTED`、`COMPATIBLE`、`EXPERIMENTAL`、`DEGRADED`、
`INCOMPATIBLE` 或 `UNKNOWN`，但必须由详细 matrix 支撑。若 A→B 后请求、resume 和
context 均通过而 thread list 找不到，结果必须保留 `Thread Discovery: FAIL` 或
`DEGRADED`，不得显示 Fully Compatible。

## Provider Switch Transaction

Provider switch 是 revision-bound transaction，不是直接 edit config：

```text
Preflight
↓
Snapshot
↓
Target validation
↓
Writer/turn safety check
↓
Generate candidate config
↓
Validate
↓
Atomic apply
↓
Runtime reload/restart when required
↓
Provider verification
↓
Runtime verification
↓
Remote verification
↓
Continuity verification
↓
Commit
```

任一步失败进入 Rollback，再执行 Rollback verification。Transaction scope 至少考虑
Provider metadata、Secret reference、Runtime binding、Runtime config fragment、
Runtime profile、generated environment bindings、lifecycle state、原文件存在性与
permissions、active Runtime state、previous Provider 和 backup metadata。Domain 层
不得写死 `/root/.codex`、`/etc/codex-remote-provider` 或其他平台路径。

Rollback 必须恢复原内容、原不存在状态、permissions、Runtime lifecycle、Active
Provider、Runtime Binding、generated config/profile 和 Secret reference。只有验证
通过才能输出 `Rollback verified`；其他情况最多输出 `Rollback attempted`。未来
`provider rollback` 恢复 AgentBox 管理前或 transaction 前配置，但绝不删除 ChatGPT
login、Remote pairing、Runtime session/history 或 Projects。

## Config Transaction Manager

`ConfigTransactionManager` 是 Codex、未来 Claude 及其他 Runtime Adapter 共用的
平台能力，负责 snapshot、restrictive temporary write、parse/validate、必要的 fsync、
atomic replace、rollback、concurrent modification detection、backup 和 permission
preservation。具体文件、目录和 reload 机制由 platform/runtime adapter 决定。

`CodexProviderConfigAdapter` 禁止字符串替换 TOML。它必须：

- parse TOML 并保留所有非 AgentBox 管理配置；
- 只修改 AgentBox-controlled typed keys/blocks；
- 按最新公开 Codex schema 验证完整 candidate；
- 防止 duplicate provider block；
- 检测 concurrent manual edit、unsafe owner/mode 和 symlink/replacement race；
- backup、restrictive temp、fsync、atomic replace、rollback 和 rollback verification。

实施前必须重新确认 Codex config reload/restart、provider/session identity 和公开 resume
行为。当前观测到的配置 block、request shape 或 event 名只能保留为历史 fixture。

## Historical Identity Migration and Session Data Prohibition

未来 migration 只发现 AgentBox 可识别的旧 metadata，并以 transaction 保持可恢复性。
不得现在定义旧 ID 算法，也不得扫描和“修复”未知手工配置。

Provider Manager 永久禁止通过直接修改以下内容伪造 Provider migration 或 continuity：

- Codex SQLite/session DB；
- JSONL、rollout 或 thread metadata；
- 任何 private conversation/session artifact。

除非官方未来提供公开 migration API 并经过重新评估，否则不批量重写 history，也不
以 list 中暂时不可见推断 thread 已删除。

## Secret Manager and Platform Backends

```text
SecretManager
├── LinuxSecretBackend
├── MacOSKeychainBackend
└── WindowsDPAPIBackend
```

- Linux 使用 restrictive directory、`0700` 目录和 `0600` secret file，并严格解析
  结构化 Secret；绝不 `source secret.env`。
- macOS 以普通桌面用户身份使用 Keychain；切换可能要求显式 app/Runtime restart，
  不 logout、不删除 pairing/session，且未验证前不声称已有 task/thread seamless。
- Windows 规划 PowerShell 5.1/7、current-user DPAPI、安全 launcher/PATH transaction
  和显式 Runtime restart；不 logout、不删除 pairing/session。DPAPI Secret 不跨
  Windows user 解密。
- WSL 默认是独立 Linux Runtime；Windows native 与 WSL 不得同时写同一 Runtime
  configuration directory。

| Capability | Linux | macOS | Windows |
|---|---|---|---|
| Provider registry | Planned | Planned | Planned |
| Secret backend | restrictive file | Keychain | current-user DPAPI |
| Provider test | Planned | Planned | Planned |
| Runtime config switching | TBD by validation | TBD by validation | TBD by validation |
| Remote continuity | TBD by validation | TBD by validation | TBD by validation |
| Thread continuity | TBD by validation | TBD by validation | TBD by validation |
| Lifecycle automation | expected high; unverified | expected medium; unverified | expected medium; unverified |

实际矩阵必须由真实平台验证填写，不能宣称三平台行为一致。

Secret 永不进入 argv、URL、可避免的 ordinary TOML、logs、Audit metadata、Git、
reports、Web Storage、自动 clipboard 或 process listings。UI 只显示 masked/configured
state。Provider test 不得把 Authorization/API Key 放入 argv；可使用 trusted HTTP
library、secure in-memory header 或 restrictive temporary config，而不固定为 curl。

## Provider Test Layers and Cost Policy

测试被明确拆分：

1. **Config:** URL、protocol、model、Secret reference、typed Runtime options；
2. **Network:** DNS、TCP/TLS、endpoint；
3. **Authentication:** credential validity；
4. **Provider Protocol:** models endpoint（若支持）、当前 wire API、streaming、完成事件；
5. **Runtime:** minimal Runtime request；
6. **Remote:** Provider binding 后的 Remote availability；
7. **Continuity:** thread resume、prior context use 和 discovery。

UI/CLI 区分 Connectivity Test、Runtime Test 和 Continuity Test，并在可能产生模型
调用费用时明确提示。Official Provider 默认不运行付费 full inference；只有用户显式
选择 `Run paid model test` 才执行。第三方测试同样不得隐藏费用或数据边界变化。

如果当时 Runtime 使用 Responses 或其他 wire protocol，Adapter 必须按当时官方
request/event schema 构造测试。历史 `input array`、`response.completed` 等只作为
fixture/evidence，不成为永久规范。

## Dedicated Cross-Provider Continuity Harness

Phase 11 规划两个本地 fake OpenAI-compatible/Responses providers（Provider A/B）：

1. 在 A 上启动 Runtime 和 test thread；
2. 生成已知 context marker 并等待 turn 完成；
3. 通过 AgentBox transaction 切换到 B；
4. 在公开支持时 resume 同一 thread；
5. 请求 Runtime 引用此前 context；
6. 在可观察处验证 B 收到并使用 context；
7. 独立验证 thread identity 和 discovery；
8. 验证只产生预期 session artifacts。

Harness 不修改 session DB/JSONL/rollout。任何失败按实际维度报告，不能借较低层
成功掩盖较高层失败。

## Runtime Lifecycle and Recovery

Provider switching 复用现有 Runtime Manager 和 Remote Control Manager，不建立
official/third-party 两套平行 daemon。优先架构是同一 Codex Runtime identity、同一
Remote Manager、可切换 Provider binding。只有最新 Codex 技术事实证明必须独立
lifecycle 时，才可提出 ADR 并请求人工批准。

Phase 11 不规划自动故障转移：Provider failure 不会自动切到其他 Provider，因为这会
改变模型、成本、隐私和数据边界。若 thread 暂时未列出，UI/CLI 必须区分 `Thread not
listed` 与 `Thread deleted`。若实施时存在公开 resume-by-ID 机制，可提供当时验证过的
恢复 guidance，但本规划不写死命令参数。

## Future API, CLI and Web UX

规划 CLI（当前不存在）：

```text
agentbox provider list
agentbox provider add
agentbox provider edit <provider>
agentbox provider remove <provider>
agentbox provider current
agentbox provider use <provider>
agentbox provider test <provider>
agentbox provider continuity <provider>
agentbox provider rotate-secret <provider>
agentbox provider rollback
```

不得提供 `agentbox codex config set <key> <value>`。Provider configuration 永远是
typed operation。

Web Provider 卡片显示 Provider、Model、Type、Provider Status、Runtime Status、
Remote Status、Continuity Level 和 Last Tested。操作为 Add、Edit、Test、Activate、
Rotate Secret、Delete。Activate confirmation 显示 Current/Target Provider、Runtime
impact、Remote impact、Continuity confidence 和 Restart required，再执行 transaction。

## Audit

未来 Audit event 至少包括 `provider_created`、`provider_updated`、`provider_tested`、
`provider_switch_requested/succeeded/failed`、`provider_rollback_requested`、
`provider_rollback_verified` 和 `secret_rotated`。Audit 禁止 raw Secret、Authorization、
完整敏感 HTTP body 或 raw Runtime config。

## Implementation Prerequisites

Phase 11 开始前必须重新验证：latest Codex version、公开 config/model-provider schema、
supported wire APIs、auth model、reload/restart behavior、Remote lifecycle、thread/provider
relationship、discovery filtering、session storage、active writer、resume behavior，以及
macOS/Windows 的真实实现能力。还必须批准 Secret backend、config ownership、付费
测试、真实 Provider credentials、switch/restart 和 continuity claims。

若公开信号不足，降低 capability 为 `UNKNOWN`/`EXPERIMENTAL`/`UNSUPPORTED`，不得
读取或修改 private state 来补齐能力。

## Explicitly Not Implemented

本次规划没有创建 API、CLI、Web UI、Secret backend、systemd Provider unit、Runtime
Adapter 或 migration；没有读取 API Key/session DB，没有写入 `config.toml`，没有切换
Provider、重启 Codex、修改 Remote Control 或影响当前 Project/Runtime session。
