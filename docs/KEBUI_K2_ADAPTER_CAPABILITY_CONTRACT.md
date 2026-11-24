# Kebui K2 固定 Adapter Capability 合同

状态：**D01 的只读、可执行描述器；真实 adapter、software operation qualification 与 host qualification 尚未交付。**
日期：2026-11-23（America/Los_Angeles）。基线：`ForceMind/agentbox@13b2877823d5338cd4044ead39d658a0c89e96de`。

## 1. 本次交付与边界

本合同落实 [当前能力缺口中的 D01](project/KEBUI_DELIVERY_EVIDENCE_AND_GAPS.md)：把 vendor
名字细化为固定 revision 下的逐 operation 合同，并把源码研究、我方实现资格、目标主机资格分开。
它承接 [K2 架构](KEBUI_K2_CONVERSATION_ARCHITECTURE.md) 与
[inert admission 合同 §9](KEBUI_K2_INERT_ADMISSION.md#9-fixed-vendor-evidence-informing-this-candidate)
已选定的 vendor 版本，不升级到 T3 当前使用的其他版本。

交付文件：

- `packages/agentbox-runtime/src/agentbox_runtime/kebui_adapter_capabilities.py`：标准库实现、不可变
  typed descriptor、固定 operation 集合、identity 比对、分域 assessment。
- `tests/unit/test_kebui_adapter_capabilities.py`：跨 vendor 语义差异、缺失/漂移 identity、越界
  operation、资格不能相互提升、无 production consumer 等负例。
- 本合同：逐操作 source、输入、ACK、终态、恢复与未验条件。

该模块与 Phase 11 的 `runtime_capabilities.py` / Runtime `capabilities.py` 分开；research
profile ID 不属于已安装 CLI 的 capability set，也不是 wire profile、launch profile 或可调用 RPC。
没有生产 import、route、CLI 参数、进程、probe、队列、数据库、Secret 或内容接线。
原有 WAW exact Stop、S03 隔离候选、single writer、Runtime 生命周期与 Secret authority 保持原边界。

本次授权来自当前 T3 融合任务及 [GOVERNANCE](project/GOVERNANCE.md) 的软件决策委托。
真实 host 激活、source admission、凭据处理和生产承诺继续按既有具体条件执行。

## 2. 固定来源与证据的三个域

| Research profile | Executable version | Source repository / revision | SDK |
| --- | --- | --- | --- |
| `kebui-codex-app-server-research-v1` | Codex `0.159.3` | `openai/codex@01fc69f4026735edfdf6789820549727a4867b11` | 无 |
| `kebui-claude-sdk-research-v1` | Claude CLI `2.1.286` | `anthropics/claude-agent-sdk-python@1ef6d8c71bb0e44a6b33fe61497864f21e17fdb7` | Python SDK `0.2.163` |

Codex 版本与 revision 沿用此前已核对的
[release](https://github.com/openai/codex/releases/tag/rust-v0.159.3)。Claude 的
[固定 `_cli_version.py`](https://github.com/anthropics/claude-agent-sdk-python/blob/1ef6d8c71bb0e44a6b33fe61497864f21e17fdb7/src/claude_agent_sdk/_cli_version.py)
声明 bundled CLI `2.1.286`。这证明 SDK 包的版本绑定；未证明本地或目标主机已安装、运行该 binary。

| Evidence domain | `supported` 的准确含义 | 当前状态 |
| --- | --- | --- |
| `source_research` | 固定 revision 的源码中存在所列 method/type/surface；只承诺这一层事实 | 已核实的 surface 为 `supported`，尚未建立的 surface 为 `unknown` |
| `software_qualification` | 我方该 operation 的真实 adapter、source 提取器和失败恢复合同已在对应固定构建上通过 | 初始范围内全部 `unknown`；明确排除的 operation 为 `unsupported` |
| `host_qualification` | 具体 host、安装、executable digest、Runtime epoch、workspace/policy 与该 operation 的真实证据匹配且有效 | 全部 `unknown` |

本次 unit tests 验证的是**描述器的隔离与拒绝规则**，不能充当真实 adapter 的
`software_qualification`。SDK types、上游通过的测试、fixture replay、自己的机器能启动 CLI
也不能替代目标主机资格。未来真实证据必须保留 provider instance / installation / execution
identity；只按 `claude` 或 `codex` 分类会错误共享不同登录、主机与权限的能力。

### 2.1 代码中的 source anchor

每个 anchor 带完整 path、symbol、固定 revision 下的 Git blob OID。下表的 OID 是
**Git 对象标识**，不是 executable SHA-256、下载包校验值或供应链签名。

| Source ID | Path（相对上述对应 repository） | Git blob OID |
| --- | --- | --- |
| C-method | `codex-rs/app-server-protocol/src/protocol/common.rs` | `c37c4956f1c3cbf21f293ca2aa41a6fec209bcfa` |
| C-turn | `codex-rs/app-server-protocol/src/protocol/v2/turn.rs` | `f938d179e697fa116666d6673ec249805f6f614e` |
| C-thread | `codex-rs/app-server-protocol/src/protocol/v2/thread.rs` | `2e166d5506b10996e2da286feb6082d6b8711340` |
| C-item | `codex-rs/app-server-protocol/src/protocol/v2/item.rs` | `04f68a3351c765d6c2be8d492b1a3cded43a22bb` |
| A-client | `src/claude_agent_sdk/client.py` | `a9c11f0cd93cb7420510e58c12dec5fda6af7bbd` |
| A-query | `src/claude_agent_sdk/_internal/query.py` | `6019124aadd73b10d0822120a4b6392c70cea450` |
| A-types | `src/claude_agent_sdk/types.py` | `882cc8040c9549a12cd21cc4195455056703a07a` |
| A-history | `src/claude_agent_sdk/_internal/sessions.py` | `ed4f30aa4ee484808c84d171fc5bd03e6c289fb6` |

这些源码只用于研究；本片没有 vendor SDK 依赖、源码 vendoring 或自动下载/升级器。

## 3. 描述器接口与拒绝规则

`fixed_profiles()` 返回两个 frozen profile；每个 profile 的 operations、input names、source
anchors 和 unresolved requirements 都是 tuple。`AdapterSelection` 仅接受有界 identity hints：
`agent`、`profile_id`、`executable_version`、`source_revision`、`sdk_version`。调用者提供这些值
不构成可信安装证据；接口也不接受 host-qualified 标志、可执行路径、凭据、prompt 或 command。

`assess_capability(selection, operation)` 返回以下互不替代的结论：

- `identity_state`：完整 exact pin 匹配是 `supported`；任一已给 pin 冲突是 `stale`；缺 pin 是
  `unknown`。已知冲突优先于另一个缺失字段，无 semver 近似、自动升级或另一 vendor fallback。
- `source_research`：固定研究记录保持原事实；例如选择了新版本时，旧 revision 的研究仍存在，
  但 `identity_state=stale` 明确说明该研究不能套用于当前选择。
- `software_qualification`、`host_qualification`：分别报告实现和目标证据；没有提升接口。
- 综合 `state`：闭合集合外 operation、初始 K2 明确排除项、或尚无 qualified source deadline 的
  `respond_approval` 为 `unsupported`；其余范围内 identity 冲突为 `stale`；其余当前为 `unknown`。
  综合状态永远不会是 `supported`。approval 附 `approval_deadline_unqualified` blocker，
  不把该执行限制误记为 vendor 不具备 approval method。
- `execution_allowed` 是只读、恒为 `False` 的属性，不能由 source `supported` 或
  `dataclasses.replace` 添加一个 field 改成运行许可。真正的 dispatch 必须经现有 Runtime authority。

`unsupported` 表示**此我方 profile 不提供该 operation**，不表示 vendor 产品从未具备它。
未知 agent 返回 `unknown`；尚未研究成功的方法也保留 `unknown`。不因没有找到一个符号就断言
vendor 不支持。非法类型、过长值、path 或任意 payload 抛固定错误码，不回显输入值。

本片没有时钟或 TTL，也没有伪造 host observation。这里的 `stale` 只表达 pin 漂移；后继 host
证据过期、Runtime epoch 或 generation 改变仍必须分别失效，不能拿本描述器的 pin 匹配代替。
本描述器列出输入**要求**，不实现 vendor payload validator、真实 source authentication 或授权检查。

## 4. Codex 逐操作矩阵

以下 input 是将来 Runtime adapter 必须满足的关联要求，不是允许 Browser 自由指定 native
options。所有 workspace/cwd、permission policy、owner/generation 均由现有 Runtime 决定。

| Operation | 固定 native surface / input 要求 | ACK 和终态 | 恢复 / 当前范围 | Source |
| --- | --- | --- | --- | --- |
| `open_session` | `thread/start`；Runtime 解析 workspace 与固定配置 | response 只确认 protocol 操作；不是 turn 终态 | 创建结果不确定时不自动再创建 | C-thread、C-method |
| `start_turn` | `turn/start`；`threadId`、input，以及 Runtime 证明无 active turn | response 携带 Turn；独立匹配 `turn/completed` 和终态 status 才可能证明本 turn 终止 | durable accept/fence、UNKNOWN 不重发；busy 不得变 steer | C-turn、C-method |
| `observe_output` | `item/agentMessage/delta`、`item/completed`、`turn/completed`；匹配 thread/turn/item | item 完成不等于 turn 完成；内容不进入 metadata ledger | fresh source、gap detection 与读授权另行实现 | C-item、C-turn、C-method |
| `respond_approval` | command/file-change approval 的原 RPC request ID、thread/turn/item 与原生 decision | 写入 response 不等于 vendor 已使用批准，更不等于 turn 完成 | 有效 deadline 未资格化，当前 `unsupported`；不 replay | C-item、C-method |
| `respond_question` | `item/tool/requestUserInput`；question IDs 与 answers | response 不是 turn 终态 | 初始 profile `unsupported`，需独立 question/content 合同 | C-item、C-method |
| `interrupt_turn` | `turn/interrupt`；`threadId`、`turnId` 与 current owner/generation | 空 response 只确认 control RPC；须精确 terminal event | 不凭 timeout、进程 exit、CLI idle 或 reconnect 推断取消 | C-turn、C-method |
| `read_history` | `thread/read`、`thread/turns/list`、`thread/items/list`；授权 thread 与有界分页 | 是 history observation；不是当前执行的 terminal proof | 只允许重新授权的读；需 retention/gap 规则 | C-thread、C-method |
| `resume_session` | `thread/resume`；既有 thread 与受管 workspace/execution | response 不是不确定 prompt 的送达或完成证明 | 不自动重发 prompt；不借原生 path/history override 扩大作用域 | C-thread、C-method |
| `steer_turn` | `turn/steer`；`expectedTurnId`、thread、input | protocol reply 不是终态 | native surface 已见；初始 profile `unsupported` | C-turn、C-method |
| `fork_thread` | `thread/fork`；qualified fork point | fork response 不是原 turn 终态 | 初始 profile `unsupported`；需 conversation/workspace/checkpoint 一致性 | C-thread、C-method |
| `rollback_thread` | 本固定 source 尚未建立对应 surface | ACK/terminal 未建立 | research `unknown`；初始 profile `unsupported` | C-method |
| `queue_turn` | 没有我方持久 Task/queue 合同 | ACK/terminal 未建立 | 初始 profile `unsupported`，由 K3 独立处理 | 无 qualified source |

关键约束来自实际源码：

1. [`turn/start` processor](https://github.com/openai/codex/blob/01fc69f4026735edfdf6789820549727a4867b11/codex-rs/app-server/src/request_processors/turn_processor.rs#L651-L715)
   可以 steer 已存在 turn，因此 busy fence 必须在我方唯一 owner 的效果边界做。
2. [`turn.rs`](https://github.com/openai/codex/blob/01fc69f4026735edfdf6789820549727a4867b11/codex-rs/app-server-protocol/src/protocol/v2/turn.rs#L284-L335)
   把 start response、steer expected turn 和 interrupt response 分开；协议 response 不保证任务成功。
3. [`history projection`](https://github.com/openai/codex/blob/01fc69f4026735edfdf6789820549727a4867b11/codex-rs/app-server/src/request_processors/thread_lifecycle.rs#L919-L932)
   可把旧 `inProgress` 显示为 interrupted；这种恢复投影不能解除 delivery UNKNOWN 的 reservation。
4. [`approval types`](https://github.com/openai/codex/blob/01fc69f4026735edfdf6789820549727a4867b11/codex-rs/app-server-protocol/src/protocol/v2/item.rs#L1549-L1652)
   中的 `startedAtMs` 是开始时间，不自动成为已资格化 expiry。permissions approval、MCP elicitation
   与其他 server requests 不因 command/file-change 两种 surface 已见而一并开放。

## 5. Claude 逐操作矩阵

这里研究的是固定 Python SDK source 及其绑定 CLI 版本。SDK 中存在 method/type，不等于 native
CLI 在我们的 session/source/host 组合中已经验证相同语义。

| Operation | 固定 surface / input 要求 | ACK 和终态 | 恢复 / 当前范围 | Source |
| --- | --- | --- | --- | --- |
| `open_session` | `ClaudeSDKClient.connect`；Runtime-owned workspace/options，不传初始 prompt（`None`，不是空字符串） | connect 包含 transport/initialize；不是 turn 终态 | 不确定结果不自动再建 session | A-client、A-query |
| `start_turn` | `query`；session ID、prompt，以及无 active turn | 返回只说明 `transport.write` 完成；未建立 vendor 收到的 ACK；需精确 ResultMessage 关联 | UNKNOWN 不重发，string/stream 都不能隐式构成 queue | A-client、A-types |
| `observe_output` | `receive_messages`、StreamEvent、ResultMessage；session/prompt origin/message identity；partial events 另需 `include_partial_messages` | `success` subtype 仍可能 error/cancel；ResultMessage 结束一个 turn，不保证整个 run 或 background task 结束 | current source、内容隔离与 gap 规则另行资格化 | A-client、A-types、A-query |
| `respond_approval` | `can_use_tool` / `control_response`；exact control request、tool-use ID、allow/deny | response 写出不是执行完成 | vendor deadline 未资格化，当前 `unsupported`；取消或重启后不 replay | A-query、A-types |
| `respond_question` | 本研究未建立独立 question surface | ACK/terminal 未建立 | research `unknown`；初始 profile `unsupported` | A-types |
| `interrupt_turn` | `interrupt`；Runtime-owned session 与 exact owner/generation | control reply 不是取消终态；native request 没有 turn ID | 需 Runtime 对当前 turn 的精确 guard、关联取消原因与独立 background lifetime | A-client、A-query、A-types |
| `read_history` | `get_session_messages`；session ID、Runtime 解析 project directory、有界 limit/offset | 空列表不能区分找不到、非法 ID 或无可见消息；不是取消证明 | 禁止缺省扩大到 Runtime HOME 跨 project 扫描；授权/retention 独立 | A-history |
| `resume_session` | `ClaudeAgentOptions.resume` 与 `connect` | initialize 不证明先前 prompt 完成 | 不自动重发、不挪用 SDK materialization 的 credential 行为 | A-types、A-client |
| `steer_turn` | `query` 不能被研究者自行当作 exact-turn steer | 未建立 | research `unknown`；初始 profile `unsupported` | A-client |
| `fork_thread` | `ClaudeAgentOptions.fork_session`、resume、resume_session_at | resume/fork 初始化不是原 turn 终态 | native options 已见；初始 profile `unsupported` | A-types、A-client |
| `rollback_thread` | file rewind 不等于 conversation + filesystem 原子 rollback | 未建立 | research `unknown`；初始 profile `unsupported` | A-client、A-types |
| `queue_turn` | 没有我方持久 Task/queue 合同 | 未建立 | 初始 profile `unsupported`，由 K3 独立处理 | 无 qualified source |

来源细节：

- [`client.query`](https://github.com/anthropics/claude-agent-sdk-python/blob/1ef6d8c71bb0e44a6b33fe61497864f21e17fdb7/src/claude_agent_sdk/client.py#L272-L313)
  写 transport 后返回；这与 Codex 的 RPC reply 不应归一成同一个“已执行”。
- [`Query.interrupt`](https://github.com/anthropics/claude-agent-sdk-python/blob/1ef6d8c71bb0e44a6b33fe61497864f21e17fdb7/src/claude_agent_sdk/_internal/query.py#L706-L794)
  发送 subtype `interrupt` 并等待 control response。默认 60 秒是请求等待 timeout，不能充当 approval deadline。
- [`ResultMessage`](https://github.com/anthropics/claude-agent-sdk-python/blob/1ef6d8c71bb0e44a6b33fe61497864f21e17fdb7/src/claude_agent_sdk/types.py#L1340-L1377)
  的 is_error、terminal_reason、origin 必须组合解释；local command 或 injected turn 不能错误归属用户 prompt。
- [`wait_for_result_and_end_input`](https://github.com/anthropics/claude-agent-sdk-python/blob/1ef6d8c71bb0e44a6b33fe61497864f21e17fdb7/src/claude_agent_sdk/_internal/query.py#L1053-L1075)
  明确 background 工作可跨越 result；单个 ResultMessage 不能证明整个进程树已停止。
- [`get_session_messages`](https://github.com/anthropics/claude-agent-sdk-python/blob/1ef6d8c71bb0e44a6b33fe61497864f21e17fdb7/src/claude_agent_sdk/_internal/sessions.py#L1059-L1080)
  的缺省目录搜索与空结果含义要求我方额外约束，不能直接暴露为 Web 文件读取入口。

## 6. 吸收 T3 思路的具体转换

固定研究源：`pingdotgg/t3code@d73e41a3fa379b591d9fb59d722d2569ec05994b`。
本次吸收的是架构原则与 operation 分解；上游 method 的存在不授予 AgentBox Runtime 执行权限。

| T3 依据 | 本片转换 | 后继接线约束 |
| --- | --- | --- |
| [ProviderAdapter 的 operation/capability contract](https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/packages/provider-core/src/server/ProviderAdapter.ts) | 按 operation 描述 ACK/terminal/recovery，不能只认 provider 名 | 绑定 installation/instance/owner；保留 vendor 差异 |
| [Providers：只声明真实能力、permission option 不伪造](https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/internals/03_providers.md) | research、software、host 分域；默认 deny；显式未支持/未知/漂移 | exact pending approval + deadline；无 terminal “yes” 或 Ctrl-C 替代协议 |
| [Architecture：事务记录与提交后的 effects、process-bound 恢复](https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/internals/01_architecture.md) | 所有 mutation 描述标明禁止自动 replay；ACK 与 terminal 分开 | 复用已有 admission/fence 方向与唯一 Runtime owner，不新增 supervisor/Task 队列 |
| [Connection runtime：连接与订阅新鲜度分别处理](https://github.com/pingdotgg/t3code/blob/d73e41a3fa379b591d9fb59d722d2569ec05994b/docs/internals/09_connection-runtime.md) | read/resume 不作为 UNKNOWN 的终态证据 | reconnect 只恢复有授权的观察，不重新发 prompt/approval |

T3 的任意 workspace path、account 范围文件读、full-access shell、managed login/token broker
不能照搬。AgentBox 的 formal Project、Runtime 唯一 authority、现有 Secret 分域与受限 typed action
仍是集成边界。上游支持 checkpoint/fork/rollback 的统一接口，也不改变我们固定 vendor 版本的
研究结果；操作 conversation 与文件树必须共同资格化后才能提供“回滚成功”。

## 7. 后续交付需要关闭的具体缺口

1. **D01 后续软件资格**：固定真实 extractor 与 adapter revision，逐 operation 保留 captured
   vendor source fixture、input/ACK/terminal 的真实关联以及 loss/duplicate/out-of-order/cancel
   负例；fixture 和 real run evidence 分开。当前模块不解析 vendor JSON，也不证明这项已完成。
2. **D03 source admission**：在既有批准的 source/wire/Secret 边界建立真实可信来源。本片没有读取、
   恢复、改写或接入此前禁止的 authenticated S03 候选。
3. **D04 owned execution**：以现有 Runtime owner/current-context/reservation 实现同底层 execution
   的 TUI/structured 单 writer；新 conversation/tab 或换 request ID 不能绕过旧 UNKNOWN 占用。
4. **D05 controls**：approval deadline 取已资格化 source deadline 与我方最多 60 秒上限的较早值；
   不知道 source deadline 时不开放批准。interrupt 必须匹配当前 owner/generation/turn，ACK 后继续
   等待正面终态。Claude 的无 turn-ID control 需要额外证明效果边界不会误打下一 turn。
5. **D02 / D06 / D07**：真实非内容 observation、cursor/gap/retention/restart、Web 状态与具体目标
   host qualification 分别完成；状态页面不能把本 research catalog 渲染成已安装/已登录/可运行。

## 8. 本地验证记录

以下命令在本任务共享 feature checkout 的 `.venv` 执行；没有启动真实 CLI、host 或 provider：

```bash
.venv/bin/python -m pytest tests/unit/test_kebui_adapter_capabilities.py tests/unit/test_kebui_s03_boundaries.py -q
.venv/bin/python -m ruff check packages/agentbox-runtime/src/agentbox_runtime/kebui_adapter_capabilities.py tests/unit/test_kebui_adapter_capabilities.py
.venv/bin/python -m black --check --workers 1 packages/agentbox-runtime/src/agentbox_runtime/kebui_adapter_capabilities.py tests/unit/test_kebui_adapter_capabilities.py
.venv/bin/python -m mypy packages/agentbox-runtime/src/agentbox_runtime/kebui_adapter_capabilities.py tests/unit/test_kebui_adapter_capabilities.py
```

已执行 pytest：**121 passed，exit 0**（81 个本片 descriptor case + 40 个既有 S03 隔离 case）；
ruff：**exit 0**；black：两文件无需格式调整，**exit 0**；
mypy：**2 source files 无问题，exit 0**。最终候选完整 CI 以本分支实际运行记录为准；本地描述器
验证不能冒称真实 adapter 或 host qualification。
