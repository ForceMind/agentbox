# AgentBox Provider Manager

Status: future architecture and product backlog; not implemented

## Product Goal

AgentBox 未来允许管理员在 Linux 服务器上安全配置和切换 AI Runtime
实际调用的模型/API Provider，同时尽量保持既有 Remote Control 使用方式不变。
该能力在 Phase 11 — Provider & Secret Management 中规划，由
[GitHub Issue #23](https://github.com/ForceMind/agentbox/issues/23) 跟踪；本文件
不授权实现、Provider 切换、Secret Store 创建或任何 Codex 配置变更。

```text
Phone / ChatGPT Codex Remote
        ↓
Linux Server
        ↓
Codex Runtime
        ↓
AgentBox Provider Manager
        ↓
OpenAI / OpenAI-compatible Provider / Local Provider
```

Remote Control 管理 AgentBox 如何连接和控制 Runtime；Provider Manager 管理
Runtime 实际调用哪个模型和 API。二者必须解耦，Provider 切换不得隐式启停、
重启或重新配对 Remote Control。

## Architecture Boundary

Provider 是 Runtime-neutral Application domain，不是 Codex `config.toml` 的
别名，也不属于 Remote session 生命周期模型：

```text
Provider Manager
├── CodexProviderAdapter
├── ClaudeProviderAdapter（仅在官方 Runtime 支持时）
├── OpenAICompatibleAdapter
├── LocalModelAdapter
└── FutureRuntimeAdapter
```

Provider Manager 负责 metadata、选择、验证计划、兼容性判断和 Secret 引用；
Runtime-specific Adapter 负责把类型化 Provider 意图映射到当时公开支持的
Runtime 配置契约。调用方不得提交原始配置文本、任意配置键、环境映射或 Secret。

## Provider Domain

未来 Provider metadata 至少考虑：

- provider ID 和 display name；
- runtime compatibility；
- provider type；
- base URL 和 model；
- wire/API protocol；
- API-key environment-variable reference；
- 可选的、类型化的 Codex provider parameters；
- enabled state；
- last test state 与证据时间；
- compatibility classification。

Provider 类型至少覆盖 Official OpenAI、OpenAI-compatible HTTP provider、
Local provider 和 Runtime-native/built-in provider。不得假定它们共享完全相同
参数；Provider-specific capabilities 通过 Adapter 和版本化 typed options 扩展，
而不是放入不受约束的 JSON 或配置文本字段。

## Secret Boundary

raw API Key 不是普通 Provider 表字段。目标关系是：

```text
Provider metadata
        ↓ secret reference
Secret Manager
```

Provider metadata 只保存不透明 Secret reference 或官方支持的环境变量名称引用。
对于 Codex，优先使用当时官方支持的 `env_key` 等引用能力，不把 API Key 明文
写入 `config.toml`。Secret 值不得出现在 CLI 普通输出、Web 普通页面、logs、
Audit metadata、Git、reports、Job payload/result 或测试 fixture。

Secret Manager 的存储、注入、轮换、删除、备份和恢复边界必须在实施前另行设计
与批准。Provider Manager 不得自行退化成数据库 Token 表或通用凭据库。

## Codex Config Adapter Concept

Provider Manager 不直接字符串编辑 `~/.codex/config.toml`。未来写入路径为：

```text
Provider Manager
        ↓
CodexProviderConfigAdapter
        ↓
validate against current public Codex capability/config schema
        ↓
atomic config update
```

实施时必须依据当时最新 Codex public CLI help、public documentation、public
config schema 和 supported config keys 重新验证，不依赖私有内部文件格式，也不把
当前观测 schema 固化为永久协议。更新至少需要：

- parse existing TOML，并保留所有非 AgentBox 管理设置；
- 只修改已验证、明确归 AgentBox 管理的 typed keys；
- 写入前验证完整候选配置；
- 同目录 restrictive-permission temporary file；
- file 与 parent directory 在适用处 `fsync`；
- atomic replace；
- 写前备份、失败回滚和恢复说明；
- 基于 identity/revision/digest 的 concurrent modification detection；
- `lstat`/no-follow、owner/mode 检查与 symlink protection。

不得简单覆盖整个 `config.toml`。解析、验证、备份或原子替换任一步不确定时，
操作必须失败关闭并保留原文件。

## Provider Testing Layers

未来 `agentbox provider test <provider>` 不能只是 HTTP ping。测试至少分层：

1. Endpoint resolution；
2. Network reachability；
3. Authentication validity；
4. Provider protocol compatibility；
5. Model availability；
6. Required Codex wire API compatibility；
7. Minimal provider API request；
8. 在安全可行时执行 minimal Codex Runtime request；
9. Remote Control compatibility assessment。

输出必须分别给出 Provider Reachability、Authentication、Model、Wire Protocol、
Codex Runtime Compatibility 和 Remote Control Compatibility。Provider request
PASS 不等于 Remote Control fully compatible。测试使用最小请求、明确成本/副作用、
超时/输出上限和 Secret redaction；默认不得把 prompt、response 或认证内容持久化。

## Compatibility Model

Provider 兼容性使用独立维度和以下规划状态：

- `SUPPORTED`：由当时公开契约与完整支持矩阵确认；
- `COMPATIBLE`：验证路径通过，但不是一等官方组合；
- `EXPERIMENTAL`：有限证据可用，行为仍可能变化；
- `DEGRADED`：部分能力可用且限制已明确；
- `INCOMPATIBLE`：已验证存在阻断不兼容；
- `UNKNOWN`：安全证据不足。

示例：Remote Control `Connected`、Provider `MyAPI`、Provider API `Reachable`、
Codex Request `PASS`，同时 Remote Control Compatibility 仍可为 `EXPERIMENTAL`。
thread synchronization、conversation history、tool behavior、streaming、Responses
behavior 或 Remote state 任一异常都必须单独报告，不得被聚合 PASS 掩盖。

## Remote Control Interaction

Provider 激活前必须形成可审查的 impact plan，并判断：

- 是否只影响新请求；
- 是否需要 Runtime restart；
- 是否影响已有 Remote session 或 conversation/thread state；
- 是否需要新建 session；
- 是否需要重新 authentication。

未知或版本相关行为返回 `UNKNOWN`/`EXPERIMENTAL`，不能承诺兼容。默认不得通过
Provider 切换隐式重启 Codex、停止现有 Remote session、丢弃会话状态或触发重新
认证。需要上述动作时必须拆成显式、可确认、可回滚的计划。

## Future CLI and Web UI

规划 CLI（当前不存在）：

```text
agentbox provider list
agentbox provider add
agentbox provider edit <provider>
agentbox provider remove <provider>
agentbox provider use <provider>
agentbox provider current
agentbox provider test <provider>
```

规划 Web `Providers` 页面展示 Provider type、model、enabled/current state、last
test state 和独立 Remote compatibility，并提供 Add、Edit、Test、Set Active、
Delete。任何 Secret 输入使用专用瞬时通道；列表、详情、测试结果和审计只显示
Secret 是否已配置及引用标识，不显示值。

## Implementation Prerequisites

Phase 11 开始前必须：

1. 完成 Phase 6–10，不改变当前顺序，并获得新 Phase 的明确批准；
2. 重新验证当时最新 Codex CLI/config/provider/Remote Control 公开行为；
3. 批准 Secret Manager、Runtime identity 与 Secret 注入边界；
4. 定义 Provider schema/version migration、激活事务、backup/rollback 和恢复流程；
5. 建立 config Adapter fixture、并发/符号链接/权限测试和 Secret canary 测试；
6. 定义 Provider 与 Runtime/Remote compatibility 的支持矩阵和降级策略。

## Unresolved Questions

- Secret Manager 的具体后端、解锁与轮换模型是什么？
- Provider 激活与现有 Runtime request/session 的一致性边界是什么？
- 哪些 Codex 版本公开支持 provider `env_key`、配置验证和无损变更？
- Local provider 的网络、进程和资源所有权由哪个 Adapter/服务负责？
- 测试请求的成本、速率限制、数据保留与用户确认策略是什么？
- 哪些证据足以把 Remote Control Compatibility 从 Experimental 提升？
- Provider 删除时如何处理活动引用、Secret 生命周期与回滚备份？

这些问题在实施 Phase 获批前保持开放；本规划不选择实现或修改当前环境。
