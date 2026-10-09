# U1 keyboard focus qualification

## Scope and baseline

Base `120b12310628745248fe40586915f1f4b20f37ae` / tree
`4a5941660273fa66f33ea1ccf158e87b7f86dfbe` is PR167 merged main. Live read-back
on 2026-10-09 confirmed all six exact-main workflows succeeded. Historical
PR167-pending text is retained below newer state records; it is not live status.

This bounded U1 check follows the existing
[design acceptance](../../docs/project/KEBUI_UI_DESIGN.md#10-设计与实现验收) and
[review gaps](REVIEW.md). It covers only the native Agent/scope and exact Stop
dialogs, the new workspace focus after scope confirmation, and the equivalent
control after a same-page theme render. Production U2/API/Runtime is unchanged.

The fixture explicitly seeds synthetic draft/message/approval/admitted state.
Every tested activation, select change, dismissal and focus traversal uses real
Playwright browser keyboard events, whose `isTrusted` values are recorded. No
`locator.focus()`, `locator.press()` or JavaScript focus is used by the test.
Read-only DOM evaluation observes active elements and operation state.

Two representative configurations are used: 1280px Chinese/light and 390px
English/dark. Each dialog checks two complete Tab and Shift+Tab cycles, then
Escape and Cancel twice without a fixture reset. A browser-UI Tab slot is
accepted only when `activeElement` is BODY, `document.hasFocus()` is false, and
exactly one more real Tab/Shift+Tab returns to the expected dialog control;
focused BODY or any background control still fails. Cancellation must close the
dialog, restore the exact connected opener and preserve all synthetic state;
Stop target identity must remain unchanged and pending confirmation cleared.

Scope confirmation must focus the newly connected visible `#main`, after which
Tab reaches a workspace control. Theme switching must retain the equivalent
theme control and operation state. This is not a full-page focus redesign.

## Evidence stages

Test-only head `bdac5c593d9313cbeb61f56e38b3c6d51ce81189` / tree
`bb93ff9478feff0aa9c8263be3ee7fa5229d5f3a` first added the keyboard script and
existing CI step only. No product source was changed before actual browser
evidence. Its E2E run is
[37949393261](https://github.com/ForceMind/agentbox/actions/runs/37949393261).

Local Chromium could not start because `socket()` returned EPERM, before any
page opened. Local syntax/diff checks, 11 existing DOM regressions, 504 DOM
combinations, six native-zoom helper unit tests and 875 relative document links
passed. These are not browser or pixel qualifications. Hosted browser findings
and any strictly necessary source repair are recorded below when observed.

## Limits

No screen-reader, full accessibility audit, physical client, mobile soft
keyboard/safe-area, real Agent/CLI/host, secret handling, U3, release, deployment
or DNS qualification is implied. Screenshot existence does not establish pixel
review; actual reviewed originals are listed separately. The final combined
head requires all existing CI regressions and six exact-head terminal workflow
results. Draft PR168 remains unmerged until the parent coordinator completes its
normal review and merge/read-back procedure.

## First actual browser result and bounded repair

Chromium 151.0.7922.34 on
[design job113883917136](https://github.com/ForceMind/agentbox/actions/runs/37949393261/job/113883917136)
completed the original three journeys, 120 core geometries, 21 large-font
screens and eight long-text checks before the new keyboard step failed.
Native 200% steps were skipped after that failure, not passed.

The unmodified product reproducibly left `activeElement` at BODY after scope
confirmation and theme switching, in both configurations. The necessary repair
is two focus calls only: focus the new `#main` immediately after confirmed scope
navigation, and focus the new equivalent theme button after its render. No
generic render/navigation focus manager or custom native-dialog trap is added.

The initial script also failed at the native dialogs' end-of-cycle BODY slot.
It did not record `document.hasFocus()`, so these four observations do not prove
background controls were reachable and are not claimed as product bugs. The
follow-up adds that observation and requires immediate keyboard return to the
expected modal control, while preserving the original RED artifact. Native
dismissal, pending Stop, target guards and all operation state code remain intact.

Original artifact
[11624814474](https://github.com/ForceMind/agentbox/actions/runs/37949393261/artifacts/11624814474)
is 8,434,260 bytes, downloaded and SHA256 verified:
`b54b7d501166a04b0f60bb0b28d12d59814e4f3b5483e256dfc04aa0f6276b48`.
Its report records head bdac5c, PR merge checkout
`fb15e26d86ad39b48dd85060a6d01ba21e3f83de`, all eight initial failures,
zero page errors and zero external requests. Original JSON is retained in
`evidence/keyboard-focus-red.json`. Product app/HTML SHA256 matches the base.
New browser result and final combined exact-head CI remain pending.

## Calibrated product RED, before source changes

Test-only head `d7c387559935ce90ede678375114aa582af26c5d` / tree
`842f08bc9932f18c20e6744e58bf0ac77d837e37` still has byte-identical base app/HTML.
Its [design job113885975941](https://github.com/ForceMind/agentbox/actions/runs/37949991195/job/113885975941)
proves all four dialog cases pass: 16 openings/dismissals total, every complete
forward/backward control cycle, Escape/Cancel twice each per dialog/configuration,
exact connected opener return and complete state/target preservation. It records
64 browser-UI slots, each unfocused document/BODY with native modal still open,
and immediate expected keyboard re-entry; zero background-control focus events.
Native dialog logic needs no product change.

Only the four scope-confirm/theme cases remain RED, each with
`document.hasFocus() === true` and `activeElement === document.body`. This
separates actual render-induced loss from browser-UI traversal.
[Artifact11625756907](https://github.com/ForceMind/agentbox/actions/runs/37949991195/artifacts/11625756907)
is 8,443,815 bytes; downloaded ZIP SHA256
`d6a5acfcfc91b9bb548ce65b59dbc73795c170774df3b3276ee563f1f04bbced`.
Full report is retained as `evidence/keyboard-focus-calibrated-red.json`.
The two-line source repair was applied only after this result. The final script
also strengthens viewport intersection for opener/theme/workspace focus, without
weakening prior state or focus assertions.

Independent review verified the first artifact hashes and merge-checkout tree,
the test-only calibration diff, and the distinction between browser chrome and
main-document controls. See [W3C native dialog technique](https://www.w3.org/WAI/WCAG22/Techniques/html/H102)
and [WHATWG dialog discussion](https://github.com/whatwg/html/issues/8339).
The implementer actually opened four first-run originals: desktop/mobile
scope-confirm and desktop/mobile theme after-render. These show the rendered
page, while DOM/event evidence establishes focus. This does not imply every
original or unrelated page was visually re-reviewed. Final candidate browser
results, independent final review and exact-head CI remain pending.

## 修复源码实际 GREEN 与独立像素资格（2026-10-09 16:04 UTC）

修复 head `09b0e86b5923dad3e444c0a9f358ddf50bab17ee` / tree
`73e592fa8f6afe054fd0b68c7ef125f1eaf88474` 的
[design job113903147573](https://github.com/ForceMind/agentbox/actions/runs/37954997708/job/113903147573)
首轮全部成功。PR merge checkout `cbee01eb36d78b839058a2d9206b837ac0eb6415`
与 source 同 tree，parents 为 main120b123 与 source09b0e86，已实际 fetch/read-back。

8项键盘案例全过；16次dialog开关、64个严格browser-UI槽、0底层focusin、
567个可信keydown和32个可信click。取消后原opener与完整state/target均保持；
确认范围后 MAIN 获焦，下一Tab到工作区new按钮；主题按钮重绘后仍获焦。
这些目标均connected、documentFocused、layout-visible且与viewport相交。
0 page errors/外部请求。既有三旅程、120核心几何、21页大字体、8长文本、
48组真实原生200%也全部通过；新键盘证据不扩大为全页/读屏/设备资格。

[Artifact11627937508](https://github.com/ForceMind/agentbox/actions/runs/37954997708/artifacts/11627937508)
共242PNG，26,638,554 bytes；实际下载并经独审核SHA256
`8a1d051fc807cfd64fbb74b70d3addf3153684f09f06e7555465f44dd1a0cc81`。
JSON的app.js/index.html/验收script哈希与上述source逐一一致。

独立审阅者实际逐张打开全部8张keyboard原图：两配置各自的scope-open、
stop-open、scope-confirm-after、theme-after。所查modal标题/精确目标/取消按钮
可读，焦点轮廓清楚，没有关键遮挡或新增布局问题。其余234张本次未重新像素
审查，不能冒称全242张已看。实施者另自查两配置scope-confirm/theme共4张。
独立结论为此有界source/事件/8图 PASS，无阻断。

本次最后仅更新资格记录与CURRENT_STATE，不改产品、测试或workflow。source
在16:04时五套workflow成功，普通e2e仍运行；最终文档组合head必须独立取得
六套准确CI终态，最终结果记录于[PR168](https://github.com/ForceMind/agentbox/pull/168)。
不把source设计job成功冒称最终组合head或合并后main成功；保持Draft由父任务
协调正常merge/read-back，无U3、真实host、release、部署或DNS操作。
