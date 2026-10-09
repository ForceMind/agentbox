# U1 long-text qualification

This bounded check closes the explicit 360/390px long Chinese/English message,
Project name and error-copy item in `docs/project/KEBUI_UI_DESIGN.md`, section 5.
It does not repeat or replace PR166's native 200% evidence.

Baseline main: `fdef24785d9a2ca04c5bbe9b05224bbd52e40a22`.
The final PR166 main has six successful workflows; the older main failure in
CURRENT_STATE is historical, not the current remote status.

`verify-long-text.cjs` uses eight viewport/language/theme combinations. Project
state and long error text are explicitly injected synthetic fixtures; the long
message is filled and submitted through the real prototype composer. It checks
exact message/draft retention, untruncated horizontal text geometry, reachable
Retry and disconnect actions and request identity preservation. It records
full-page failure/recovery screenshots, errors, requests and source commit.

First browser result: RED on source head `d7242af`, PR merge checkout `7e4119f`.
Chromium 151 passed the two 360px Chinese themes, then the 312-character English
Project fixture widened the 360px page to 2790px. The full message and error
wrapped, but the context title, timeline and composer label did not. Original
artifact `11614898786`, SHA256
`bf9d59d93b85b65d6adab79540318a611199cf6b4c12860ef057626a6a5e3104`,
contains raw geometry and the actual overflowing screenshot. Parent inspection
confirmed the horizontal overflow; this is not a claim that all images were reviewed.

The follow-up adds inherited emergency text wrapping in the main content and
allows row text containers to shrink. It does not truncate names or hide overflow.
Its exact-head browser/CI result remains pending. Syntax checks do not qualify browser geometry.
The first exact-head CI run must preserve a failure rather than assume wrapping
already works. No production code, transport, backend or scope contract changed.
This is not physical-device, keyboard-IME, all-page long-text, all-page zoom or
production integration qualification. No real credentials or private content.
