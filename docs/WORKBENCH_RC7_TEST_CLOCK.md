# Bounded rc7 lifecycle test-clock correction

## 2026-10-05 #145 / #146 已闭环：统一视图与主干质量复核通过

#145 已交付正式 Changes 页有界统一diff（hunk、旧/新补丁坐标、增删文本、
完整原文fallback、键盘与手机wrap）。最终feature head
`63da1b1539ed68186b249e905e8b14c568ce1673` 六套首次CI与独立六图pixel
PASS；首轮巨大留白的失败证据保留，最终滚动区域定位修正已验。

#145 merge `c93ed22a57b2667d8f6b13fdb3fd3720001e72f2` 的旧rc7 lifecycle
单测导致Frontend失败，其余五套通过。后继test-only #146 不改产品5ms预算、
测试timeout、断言或UI；历史成因仍为强支持推断，原失败未抹除。最终head
`1c4d5c30d62531eebb219e1afea82a11059175bb` 六套首次workflow全SUCCESS。

#146 于2026-10-05T16:21:56Z正常合并。最新main
`a1cab129f18ede5b982b6ab53d037c51771b4dea`，parents为上述c93ed22与
1c4d5c3；tree `26f245acde25737aa9c8ef47e408ad9c56a8006a` 与head完全一致。
新exact-main六套首次workflow均SUCCESS（23成功/3预期skip）：
[Frontend](https://github.com/ForceMind/agentbox/actions/runs/37340266309)
1554 Web+6 extension、原rc7三项110ms通过；
[Backend](https://github.com/ForceMind/agentbox/actions/runs/37340266512)
三版本各5284 passed/88 skipped与14项native process；
[E2E](https://github.com/ForceMind/agentbox/actions/runs/37340266503)
224 passed/30 prescribed skipped/0failed/0flaky，包括64项formal native
桌面/手机，224还含16项pureNode检查。

main artifact11359310257 ZIP摘要已实际校验为
`818a8d6b7441f77a8aa6580f2dd65658975b411c28a29a3c56b93733ba746ba4`。
未声称重复main图像素审查：production UI/native fixture/E2E与已独立pixel-PASS
的63da1b1未改。最终feature图artifact11355935840摘要为
`73d1faf08c60a7b1e973a32c562801eab98b16e2a64d2fe888aa62f029347186`。

本有界卡到此停止，下一功能仅建议、未启动；不称整个S02/WS08完成。
默认未配置仍unavailable；无生产key/pin、host/installer激活、真实账号或发布。
下方所有pending与失败描述是当时快照，不覆盖本节最新闭环事实。


Base: main `c93ed22a57b2667d8f6b13fdb3fd3720001e72f2`, tree
`44630157273d4eea963d5738ed930eb257b7847e`. PR #145's final head had six
successful first-attempt workflows and independent six-image pixel PASS. The
merge tree equals that head. This is a separate test-only CI-closure follow-on,
not another Changes feature, WAW product change or new authority.

## Observed main failure

[Frontend run 37334720162](https://github.com/ForceMind/agentbox/actions/runs/37334720162),
job 111846470320, failed in the unchanged
`wawBrowserLifecycle.rc7.test.ts` socket error/backpressure case: 5000ms timeout
plus one unhandled `PROTOCOL_INVALID` rejection. Web totals were 1553 passed and
1 failed. The other five exact-main workflows succeeded. No blind rerun was
used to erase this result, and no successful PR-head run substitutes for main.

The fixture already controls the controller scheduler with `WAWRc7FakeClock`,
but wire decoding still read real `performance.now()`. `decodeWireFrame` keeps
its strict 5ms nonopaque validation budget. Adjacent `wawWire.test.ts` and
`wawBrowserController.test.ts` already freeze that clock for deterministic
unit tests. The lifecycle test exercises fencing/cleanup/backpressure, not
wall-clock performance qualification.

## Controlled evidence and limits of inference

An isolated archive of exact main reproduced the same failure fingerprint by
changing only the first controller-inbound decoder readings from 0 to 6 ms:
5000 ms timeout plus unhandled `PROTOCOL_INVALID`. With a frozen clock the original
three lifecycle cases passed in 52 ms.

A second same-condition experiment injected a real pause into the first
controller-inbound `TextDecoder.decode`. The old test observed 8.022 ms and
reproduced the timeout/rejection. With the same 8.026 ms pause and only the unit
clock frozen, the affected case passed in 51 ms. No product decoder, deadline,
test timeout or behavioral assertion changed. These are controlled local
observations, not a claim that the historical CI pause duration was recorded.
CI did not log internal timer readings: its cause remains a strongly supported
inference. Diagnostic code/logs are retained with the task evidence and are not
installed into the product or regular tests.

The three-microtask `settle()` helper was also inspected. A fixture may inject
the next frame before outbound publication appears in a synchronous metadata
probe, but controller continuations precede queued inbound handling. The normal
baseline passed. That observation did not prove a separate historical race and
was not used to justify unrelated changes or rejection suppression.

## Exact minimal change and retained negative coverage

Only the lifecycle test imports `beforeEach` and stubs `performance.now()` to 0
per case, with the existing `afterEach(restoreAllMocks)` restoring it. Product
files, strict 5 ms decoder budget, 5000 ms test timeout, fixture action ordering and
all assertions are unchanged. The controller fake clock and scheduler remain
independent, including its 60000 ms backpressure cleanup advance. The global
performance spy also freezes TerminalScheduler elapsed readings inside these
fixtures; these three cases do not claim renderer timing qualification. The
separate wire and renderer deadline suites remain unchanged.

`wawWire.test.ts` retains the separate `checks a bounded validation deadline and
fails without hop allocation` case: it supplies 0 then 6 to the real decoder and
directly requires `WireError`. The same unchanged test separately checks closed
state and no hop allocation for invalid sequences after restoring the timer.
Freezing ordinary lifecycle fixtures therefore does not remove deadline-rejection coverage.
The diagnosis candidate's adjacent five-file suite passed 317 tests, including
that negative case. Independent review and full new exact-head/main gates are
still required for this new branch; old green tests cannot close it.

No production key/pin, credentials, listener/host activation, release or deploy
is included. The original unified view and raw fallback remain unchanged.
