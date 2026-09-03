# WAW-3 Recovery Contracts

## 范围和阅读路径

本阶段补齐现有恢复边界，未开启真实 WebSocket、Noise、PTY、CLI、host 或
Provider login。它是 software/synthetic evidence，不是完整 WAW-3 或生产证明。

- 操作者：先读下面的恢复结果，再看 `project/EXECUTION_PLAN.md` 的未完成阶段。
- 开发者：按实现映射使用纯 reducer；不要把分类结果当作 ticket 或 Runtime authority。
- 测试者：运行映射中的负例；Linux 专用 socket/权限矩阵以 exact-head CI 为准。

安全契约来源是 `WEB_AGENT_WORKSPACE_ARCHITECTURE_AUTHORIZATION_REVIEW.md`
的 Connection Lease、Reconnect and Output Continuity、Failure and Recovery。
此文档记录实现，不改变历史 architecture approval status。

## 恢复结果

| 条件 | 软件行为 | 禁止推断 |
| --- | --- | --- |
| Fresh attach，`null/null` 或 `0/null` hint | 允许进入既有 attachment admission 检查 | 不是已连接，不替代 writer cleanup / ticket / Noise |
| 正 cursor + 当前 Runtime epoch，workspace scope 相同 | 同代 bounded replay 分类；新 attachment 使用新 lease | 不代表旧 attachment 可写，不提供 exactly-once input |
| API authority 变化 | 浏览器清除旧 attachment/cursor，需显式重新连接；分类器仅接受 fresh hints | API epoch 是随机 namespace，不能比较数值大小；不应因此将 workspace 持久状态设 UNKNOWN |
| Runtime epoch 变化 | 清除 cursor/attachment，进入 `RECONCILIATION_REQUIRED` 提示并阻止新 admission | 不生成跨 epoch GAP，不自动 restart/adopt/respawn |
| Generation、binding、host identity 变化 | 旧 identity/cursor 不可恢复；需要可信新状态和对应恢复核对 | 同一个 workspace ID 不足以证明同一进程 |
| 浏览器进入后台 | 丢弃当前 attachment authority，暂停输入，返回前台不自动重连 | 后台不继续显示可靠 connected；不重发输入 |
| 输入写入不确定 | 保留 `input_uncertain`，后续 output/GAP 不能解除输入暂停 | ACK 不证明 Agent 消费；不保存或重放 input bytes |
| Detach cleanup 超时/错 owner/不完整 proof | 保留 writer slot，等待精确的正向 cleanup proof | 断线或超时本身不证明 PTY 已关闭 |
| Exact Stop 已完成或 Agent 已退出 | 迟到事件不能复活 UI；只允许用户显式新 Start | 不自动重启或扩大 Stop target |

## 身份与数值约束

Workspace scope 包含 Project、Workspace、AgentType、generation、binding revision/digest、
host ID/revision、Runtime epoch、API authority epoch、Session ID/auth epoch。
Attachment scope 另外含 attachment ID、lease number，mode 固定 `writer`。

纯 Python identity 复用 canonical validators；Web 使用 bounded decimal strings，
先检查类型/长度/ASCII 格式再做 `BigInt` 比较。generation/epoch/lease 等正数为
`1..2^64-1`；output cursor 最大 `2^64-2`，`2^64-1` 仅为 GAP exclusive endpoint。
`0` 是无历史 hint，不是实际 output observation。

Durable generation 当前由 SQLite signed-64 `Integer` 存储，分配到
`2^63-1` 时 fail closed。协议可表示范围不等于存储可分配范围；本阶段不迁移
数据库、不宣称完整 uint64 durable storage。

## 浏览器状态契约

- Start、Connect/Reconnect、Stop 使用递增的**页面内 request attempt**，与 wire
  request ID 分开；旧响应必须匹配本次 attempt 和 exact workspace scope。
- `start_accepted` 只绑定 metadata。`attachment_prepared` 也不等于连接成功；
  只有当前 attachment 的 `admitted` 能进入 connected。
- 新 prepare 必须匹配本次 connect attempt；不能替换已占用的 attachment，
  同一 API authority 内不能复用旧 attachment/lease。
- API/Runtime restart notification 携带 exact previous 和 next scope，防止
  迟到 restart notification 覆盖新连接。API epoch 可变小；Runtime epoch 必须变大。
- Runtime recovery flag 不能由 API restart、普通 reconnect 或 Start 清除。
  `recovery_reconciled` 是未来可信 control adapter 的输入，需匹配当前 scope
  和更高 generation；它本身不执行 host reconciliation 或授予权限。
- `output_observed` 单独推进 cursor，重复/回退为 no-op；不能从 cursor 跳跃
  推断丢失。`gap` 必须来自当前 Runtime event 的明确 half-open 区间 `[from,to)`，
  重复 GAP 不推进 cursor。此 reducer 的数字 GAP 不代替 future fresh redraw marker。
- React state 仅保存有限 metadata/cursor，无 ticket、terminal payload、input map
  或 transcript。真实 transport adapter 仍需先验证来源和加密 admission；
  tuple equality 不是密码学认证。

## 实现与验收映射

| 责任 | 实现 | 有意义的验证 |
| --- | --- | --- |
| Resume identity/hint 分类 | `packages/agentbox-core/src/agentbox_core/waw_recovery.py` | `tests/unit/test_waw_recovery.py`：canonical/type/overflow、session/auth、同代 replay、API fresh、Runtime/generation mismatch |
| Lease cleanup owner 与 deadline | `packages/agentbox-core/src/agentbox_core/waw_lease.py` | `tests/unit/test_waw_lease.py`：owner mismatch、错/迟到 ACK、30/60 秒边界、clock、并发 writer reservation |
| Runtime prepare hint 检查 | `packages/agentbox-runtime/src/agentbox_runtime/waw_lifecycle.py` | `tests/unit/test_waw_lifecycle.py`：fresh/replay hint 闭集；沿用 identity/liveness 检查 |
| Synthetic stream generation/epoch | `waw_stream_bridge.py` / `waw_supervisor.py` | `tests/unit/test_waw_supervisor.py`：真实 supervisor + FakeTransport 实例；同代 output、错 epoch/generation、缺 context |
| Browser event reducer | `apps/web/src/features/workspace/workspaceState.ts` | `workspaceState.test.ts`：完整字段逐项 stale、attempt、lease、数字边界、GAP、uncertainty、restart/recovery、Stop |

## 尚未覆盖的产品能力

尚未接入真正的终端或浏览器 stream adapter；未实现完整 API/Runtime restart 的
跨进程 durable transaction、真实 host reboot reconciliation、Noise key rotation、
mobile keyboard/真实网络中断的 terminal E2E。现有 `AttachmentAuthority` 仍负责
实际票据和 writer 准入，纯 recovery classifier 不替代它。

所有真实 host、transport、recovery 操作须经过现有独立证据与授权要求。
阶段实际命令、结果和 merge read-back 见 `project/CURRENT_STATE.md`，待验收项
见 `project/NEXT_ACTION.md`。

## Shared supervisor follow-up on Mac

The supervisor now accepts only the concrete `WAWClaudeCommand` and
`WAWCodexCommand` classes through a closed `WAWManagedCommand` union. The actual
class fixes AgentType; the complete durable stop binding and marker must match.
Commands are revalidated before transport start, including executable drift;
unknown objects/subclasses do not become a generic command gateway.

Both AgentTypes exercise the same input/output/resize/detach/reconnect/exact
Stop software path. Closed/error stream bridges reject subsequent control or
replay; active CLOSE first obtains positive attachment cleanup proof and leaves
the workspace alive. An unconfirmed cleanup retains the writer reservation.

The existing real tmux adapter is still Claude-only and rejects Codex before
any tmux I/O. Current command argv values are prototype contracts, not proof of
the final qualified bootstrap/vendor invocation. Mac tests and Linux CI validate
software behavior; actual host/CLI qualification remains separate.
