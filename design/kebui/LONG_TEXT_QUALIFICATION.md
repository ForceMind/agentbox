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

Current qualification: NOT RUN. Syntax checks do not qualify browser geometry.
The first exact-head CI run must preserve a failure rather than assume wrapping
already works. No production code, transport, backend or scope contract changed.
This is not physical-device, keyboard-IME, all-page long-text, all-page zoom or
production integration qualification. No real credentials or private content.
