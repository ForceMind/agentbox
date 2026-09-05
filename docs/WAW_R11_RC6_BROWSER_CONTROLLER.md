# R11 rc6 browser controller safety foundation

状态：controller 安全基础 `ea0ac84` 已完成独立 Sol 复审、定向/全量 Web 验证和
PR #80 的 20/20 exact-head CI；真实 terminal surface 与 `WorkspacePage` 组合仍待
实现。
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

## 仍待组合的页面边界

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
