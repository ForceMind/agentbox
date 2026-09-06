# R11 rc6 browser controller safety foundation

状态：controller 安全基础 `ea0ac84` 与 bounded renderer `f4d868e` 已分别完成独立
Sol 复审和 PR #80 的 20/20 exact-head CI。当前分支的 page-composition 实现已完成
本地验证和独立复审；本次实现自身仍待提交、exact-head CI、normal merge 与 read-back。
本文不表示浏览器终端、rc6、R11 或真实 trust-provider 资格已经完成。

## 目的

`WAWBrowserController` 是一个 attachment 的唯一流 owner。它只在 ticket、独立
trust、same-origin binary WebSocket、local canary 和 `ADMITTED` 全部完成后进入
`CONNECTED`。页面不能把 lifecycle metadata 当作 terminal admission，也不能绕过
controller 直接把 INPUT、RESIZE、Detach 或 Stop 发往 Control Plane。

## 已冻结的安全规则

- 每次 Detach、fence 或页面生命周期事件都会销毁 terminal model、清空 surface
  owner 的 cursor，并使下一次连接发送 `resume_cursor: null`。当前版本不实现把
  model 与 cursor 原子转移到 reconnect 的 positive-cursor replay。
- `ADMITTED.output_cursor` 只是 Runtime 选择的 fresh-redraw baseline bound；它不
  是已渲染 cursor。只有 `OUTPUT` 解密后被 terminal renderer 成功完成，controller
  才更新 `outputCursor`。
- 只允许 fresh redraw 的精确 `GAP { from_cursor: "0", to_cursor: "0",
  reason: "baseline_redraw" }` marker；任何其他 GAP 立即清模并 fence。
- 每一次 wire publication（包括 INPUT、RESIZE 和 heartbeat）都在 `socket.send`
  前重新核对 controller epoch、页面 selection/auth context 和 trust lease。任一
  失效先 fence，不依赖 React effect 或 Abort listener 的调度时机。
- `write_uncertain` 和除 `INPUT_RATE_LIMITED` 外的 rejected INPUT ACK 都在 resolve
  outcome 前同步 fence socket、crypto、terminal 和后续 INPUT/RESIZE。controller
  从不自动重发任何 input。
- Detach/Stop 需要重复 `projectId`、`workspaceId`、`agentType`、`generation` 与当前
  page control context。Stop 先取得 exact Detach `ATTACH_PTY_CLOSED` proof，再发
  generation-bound Stop；context/page lifecycle 在任一 await 点失效时不发送下一
  个 mutation，也不接受迟到 receipt 复活 UI。只有 exact `state: STOPPED` receipt
  可以进入本地 `STOPPED`。

## 页面组合边界

- 生产 terminal renderer 必须显式创建 `TerminalScheduler` render task，用
  `textContent` 与 closed CSS classes 写入受控 surface；禁止默认 no-op renderer，
  禁止把 terminal plaintext、ticket、key、raw frame 写入 React persistence、URL、
  browser storage、日志或 analytics。
- 通用 artifact 的 `WAW_TRUST_EXTENSION_ID` 仍为 `null`。没有已签名 enrollment
  时 Connect 必须显示 provider unavailable，不能注入 synthetic trust provider。
  这项真实 extension/trustd 资格继续属于 R12。
- 页面 hook 负责 selection/auth/route/page lifecycle 的 `AbortController`，并将
  已确定的 `Locale` 传给 copy。它不能再读取 `navigator.language` 或
  `navigator.languages`；全站只有 i18n bootstrap 的 `navigator.languages[0]`
  可以决定 `zh-CN` 或 English。

## Page-composition implementation checkpoint（待 exact-head CI）

`useWAWBrowserAttachment` 是 `WorkspacePage` 唯一的 browser attachment owner。
它保留 controller、trust 和 concrete DOM surface 的可验证边界，页面本身没有
ticket、key、plaintext frame 或 generic runtime command authority。

- Connect/Reconnect 仅在 document 可见、固定高度 viewport 与 terminal surface 已就绪、
  Runtime 为 `RUNNING`、且受管 Chromium provider 明确可用时才会创建 provider 或请求
  ticket。通用构建的 extension ID 为 `null` 时路径保持 disabled，不打开 port、不发 ticket。
- runtime identity 分为三层：仅 `RUNNING` 可取新 ticket；`RUNNING` 与
  `NEEDS_INTERACTION` 可维持现有 stream；`RUNNING`、`NEEDS_INTERACTION`、
  `TRUST_REQUIRED`、`LOGIN_REQUIRED` 均可保留已准入 attachment 的 exact control
  identity。后两种状态同步围栏 stream，却不允许以 direct HTTP Stop 跳过 Detach proof。
- `pagehide`、`document` 的 `freeze`、visibility hidden、surface replacement、auth/
  Project/runtime identity 改变和 unmount 都同步清 terminal DOM、未提交 input DOM 与流
  lease。页面恢复只显示已围栏状态；它不会恢复旧 stream。控制操作使用独立的 fresh
  page-control lease，因此同一身份在前台确认 Stop 时仍按
  `Detach(ATTACH_PTY_CLOSED) -> Stop` 执行；`detachConfirmed` 为 false 不能显示
  `STOP_CONFIRMED`，也不能 fallback 到 direct Stop。
- view size 只由固定高度 `.workspace-terminal-frame` 的 `ResizeObserver` 得出。可用
  content box 扣除 16px 四边 padding 后按 8px × 20px cell clamp 到 8–240 columns 和
  1–200 rows。renderer 的普通、wide 和 sparse-gap cell 都只用 closed CSS classes；
  plaintext 仍只进入 `textContent`，不使用动态 style 或 HTML parsing。
- 输入框在 submit 时只发送 `value + "\r"`（空行即 `"\r"`），处理 IME，按含 CR 的
  UTF-8 长度限制为 16 KiB，并在 controller 同步接管后立即清零临时字节数组。ACK pending
  禁用第二次 input；React state 只保留 outcome state/reason code，从不保留 input 文本。
- action errors 绑定 auth、selection 与 attachment identity；scope 变化后的旧 request
  或旧 callback 无法在新页面显示 error。Runtime status error 和 terminal outcome 都用
  本地化文本配合 technical code，绝不显示 server prose。

同一 checkpoint 也补齐了 API/relay 的 current binding read-back：WebSocket admission、
active INPUT 和 OUTPUT publication 从 claims 的 exact binding primary key 读取并要求
`CURRENT`。Runtime Start 已返回可运行状态后如 Project/binding 漂移，API 先持久化
generation/binding/host-bound Stop intent，再执行 shielded exact Stop；只有正向回执才
写 `STOPPED`，不确定结果保持 `UNKNOWN/reconciliation_required`。

本地证据：Web `vitest run` 为 28 files、983 passed；`tsc -b --pretty false`、ESLint、
Prettier 和 `git diff --check` 均通过。受管本机 API/relay matrix
`test_waw_workspace_api.py test_waw_relay.py` 为 117 passed；完整 `pnpm e2e` 为
64 passed（58.6s），覆盖桌面/移动、`zh-CN`/English、overflow、focus 和 exact Stop。
独立 Sol 最终复审为 P0=0、P1=0。以上不替代本 checkpoint 的 exact-head CI，也不构成
真实 CRX/trustd、CLI/PTY 或 host qualification 证据。

## 本地验证

- `vitest run src/features/workspace/wawBrowserController.test.ts`：28 passed；三个
  并发独立进程均为 28/28。fixture 固定其 `performance.now()`，避免触及 wire 层
  既有 5 ms fail-closed budget；生产 budget 未改变。
- 串行完整 Web `vitest run`：26 files、947 passed。一次与 build 并行时，既有
  `terminalScheduler` 高计算用例超过 Vitest 的 5 秒单测上限；单独和串行重跑均
  通过，未把该并行超时记为成功。
- `tsc -b --pretty false`、targeted ESLint、Prettier、Vite production build 与
  `git diff --check`：通过。
- 覆盖 local canary/ADMITTED gate、fresh-redraw marker 与其反例、deferred/rejected
  renderer、render-gated cursor、新 ticket/attachment/socket/crypto/terminal 的完整
  reconnect、terminal input rejection/write uncertainty、final send、deferred input、
  heartbeat/scheduled resize、stale control context、Detach/Stop lifecycle/Abort、
  每个 receipt identity field 和 exact Stop receipt。
- PR #80 exact head `ea0ac844c1f2e52fc8cdc51a0ec7d90645094338`：20/20 checks
  terminal `SUCCESS`，包含 native、E2E、four installer jobs、frontend/security,
  release candidate 和 Backend Python 3.11/3.12/3.13。

Controller safety 的独立 Sol review 最终结论为 P0/P1/P2 均无。下一步是 page hook
和双语 `WorkspacePage` 接线，并运行 Web/E2E acceptance matrix。

## Bounded DOM renderer checkpoint

Commit `f4d868e` adds the production-only renderer factory used by the next
page-composition slice. It gives `TerminalScheduler` an explicit render task;
the task builds a full projection in a `DocumentFragment` and replaces the
surface only after the whole render succeeds. Terminal plaintext is copied only
through text nodes/`textContent`; the class set is closed. Cancel/fence clears
the old surface before external callback reentrancy can install another owner,
with a verified `textContent` fallback when `replaceChildren()` fails.

Renderer tests cover render/cancel/fence DOM cleanup, persistent DOM exceptions,
reentrant fence callbacks, bounded multi-turn rendering and a cancelled late
render task. The renderer suite has 11 cases; full Web validation is 958 passed.
The existing cross-frame UTF-8 reservation test retains all assertions and uses
a 10-second per-test deadline to tolerate observed Mac parallel-worker pressure;
isolated execution remains below five seconds. Final exact head
`48850bab3a7822d22114dd46b14ba4362f004f32` completed PR #80's 20/20 CI. This
checkpoint does not attach the renderer to `WorkspacePage` yet.
