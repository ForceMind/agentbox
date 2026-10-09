// Bounded U1 keyboard evidence. Fixture setup is injected; every tested action
// uses browser keyboard input. No locator.focus(), locator.press(), or JS focus.
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createHash } = require("node:crypto");
const { execFileSync } = require("node:child_process");
const out = path.join(__dirname, "evidence");
const report = {
  checkout: execFileSync("git", ["rev-parse", "HEAD"], { cwd: __dirname, encoding: "utf8" }).trim(),
  head: process.env.KEBUI_HEAD_SHA || null,
  scope: "Synthetic U1 Chromium keyboard only: scope and exact Stop dialogs, repeated Escape/Cancel, scope-confirm navigation, same-page theme render. Not screen reader, OS/IME, real device, or production qualification.",
  hashes: Object.fromEntries(["app.js", "index.html", "verify-keyboard-focus.cjs"].map(name => [name, createHash("sha256").update(fs.readFileSync(path.join(__dirname, name))).digest("hex")])),
  cases: [], errors: [], externalRequests: [],
};
fs.mkdirSync(out, { recursive: true });

async function snapshot(page) {
  return page.evaluate(() => ({ state: JSON.stringify(state), target: stopTarget(), pendingStop }));
}
async function focusInfo(page) {
  return page.evaluate(() => {
    const el = document.activeElement;
    const r = el.getBoundingClientRect();
    return { documentFocused: document.hasFocus(), nativeModal: document.getElementById("dialog").matches(":modal") && document.getElementById("dialog").open, tag: el.tagName, id: el.id, action: el.dataset.action || null,
      connected: el.isConnected, visible: !!(r.width && r.height) && getComputedStyle(el).visibility !== "hidden",
      inDialog: !!el.closest("#dialog"), inMain: !!el.closest("#main"),
      rect: { x: r.x, y: r.y, width: r.width, height: r.height },
    };
  });
}
async function tabTo(page, selector, key = "Tab") {
  assert.equal(await page.locator(selector).count(), 1, `unique keyboard target: ${selector}`);
  for (let i = 0; i < 80; i++) {
    if (await page.evaluate(s => document.activeElement.matches(s), selector)) return;
    await page.keyboard.press(key);
  }
  throw new Error(`Keyboard could not reach ${selector}`);
}
async function activate(page, selector) {
  await tabTo(page, selector);
  await page.keyboard.press("Enter");
}
async function cycleDialog(page, selectors, item) {
  // Verify the native initial focus, both wrapping boundaries and all controls.
  assert(await page.evaluate(s => document.activeElement.matches(s), selectors[0]), "dialog initial focus");
  item.cycles = [];
  item.browserFocusSlots = [];
  for (const key of ["Tab", "Shift+Tab"]) {
    for (let i = 1; i <= selectors.length * 2; i++) {
      await page.keyboard.press(key);
      const index = key === "Tab" ? i % selectors.length : (selectors.length - i % selectors.length) % selectors.length;
      let actual = await focusInfo(page);
      if (!actual.inDialog) {
        // Chromium may give browser UI one tab stop between the dialog ends.
        // BODY is not accepted as page focus: the document must be unfocused,
        // and exactly one more real key must return to the expected modal control.
        const outside = actual;
        await page.keyboard.press(key);
        actual = await focusInfo(page);
        item.browserFocusSlots.push({ key, outside, returned: actual });
        assert(key === "Tab" ? index === 0 : index === selectors.length - 1, "browser UI slot is only allowed at modal ends");
        assert(outside.nativeModal, "dialog must still be native modal");
        assert.equal(outside.tag, "BODY", "background controls must remain unreachable");
        assert.equal(outside.documentFocused, false, "BODY must not retain document focus");
      }
      item.cycles.push({ key, expected: selectors[index], actual });
      assert(actual.documentFocused && actual.inDialog && actual.connected && actual.visible, "Tab escaped the visible native dialog");
      assert(await page.evaluate(s => document.activeElement.matches(s), selectors[index]), `native ${key} order: ${selectors[index]}`);
    }
  }
}
async function closedAtOpener(page, before, item) {
  await page.waitForFunction(() => !document.getElementById("dialog").open);
  item.after = await snapshot(page);
  item.focusAfter = await focusInfo(page);
  assert.deepEqual(item.after, before, "cancellation must preserve scope/draft/approval/request/stop and clear pending Stop");
  assert(await page.evaluate(() => document.activeElement === window.keyboardOpener && window.keyboardOpener.isConnected), "dismissal must return to the exact connected opener");
  assert(item.focusAfter.documentFocused && item.focusAfter.visible, "returned opener must have visible document focus");
}

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
  report.browser = browser.version();
  try {
    // Two representative configurations cover both languages, themes and widths;
    // this is deliberately not a new full page or device matrix.
    for (const config of [{ width: 1280, lang: "zh", theme: "light" }, { width: 390, lang: "en", theme: "dark" }]) {
      for (const kind of ["scope-dismiss", "stop-dismiss", "scope-confirm", "theme"]) {
        const label = `${config.width}-${config.lang}-${config.theme}-${kind}`;
        const item = { label, outcome: "pending" };
        report.cases.push(item);
        const page = await browser.newPage({ viewport: { width: config.width, height: 900 } });
        page.on("pageerror", e => report.errors.push({ label, error: e.message }));
        page.on("request", r => { if (!r.url().startsWith("file:")) report.externalRequests.push(r.url()); });
        try {
          await page.goto("file://" + path.join(__dirname, "index.html"));
          await page.evaluate(({ lang, theme, kind }) => {
            state.lang = lang;
            state.route = kind === "stop-dismiss" ? "recovery" : "agents";
            state.draft = "Preserve this synthetic draft";
            state.message = "Synthetic existing message";
            state.approval = "approved";
            state.admitted = true;
            document.documentElement.dataset.theme = theme;
            render();
            window.keyboardEvents = [];
            window.focusEvents = [];
            document.addEventListener("focusin", e => window.focusEvents.push({ tag: e.target.tagName, id: e.target.id, action: e.target.dataset.action || null, modalBackground: document.getElementById("dialog").open && document.getElementById("dialog").matches(":modal") && !e.target.closest("#dialog") }));
            document.addEventListener("keydown", e => window.keyboardEvents.push({ type: "keydown", key: e.key, trusted: e.isTrusted }));
            document.addEventListener("click", e => window.keyboardEvents.push({ type: "click", action: e.target.closest("[data-action]")?.dataset.action || null, trusted: e.isTrusted }));
          }, { ...config, kind });
          if (kind.endsWith("dismiss")) {
            const stop = kind === "stop-dismiss";
            if (stop) await activate(page, '[data-action="recover"]');
            const opener = stop ? '[data-action="stop-dialog"]' : '[data-action="choose:Claude Code"]';
            const controls = stop ? ['[data-action="stop-confirm"]', '[data-action="close"]'] : ['#project-choice', '#agent-choice', '[data-action="create-work"]', '[data-action="close"]'];
            item.rounds = [];
            // Escape and Cancel each repeated, without resetting the page/state.
            for (const method of ["Escape", "Cancel", "Escape", "Cancel"]) {
              await tabTo(page, opener);
              await page.evaluate(() => { window.keyboardOpener = document.activeElement; });
              const before = await snapshot(page);
              assert.equal(before.pendingStop, null);
              const round = { method, before };
              item.rounds.push(round);
              await page.keyboard.press("Enter");
              assert(await page.locator("#dialog").isVisible());
              if (stop) assert.equal(await page.evaluate(() => pendingStop), before.target);
              await cycleDialog(page, controls, round);
              if (!stop) {
                // Mutate both uncommitted choices through the real keyboard.
                await page.keyboard.press("ArrowDown");
                await page.keyboard.press("Tab");
                await page.keyboard.press("ArrowUp");
                assert.equal(await page.locator("#project-choice").inputValue(), "Observatory");
                assert.equal(await page.locator("#agent-choice").inputValue(), "Codex");
              }
              if (item.rounds.length === 1) await page.screenshot({ path: path.join(out, `keyboard-${label}-open.png`) });
              if (method === "Escape") await page.keyboard.press("Escape");
              else await activate(page, '[data-action="close"]');
              await closedAtOpener(page, before, round);
            }
          } else if (kind === "scope-confirm") {
            await activate(page, '[data-action="choose:Claude Code"]');
            await activate(page, '[data-action="create-work"]');
            await page.waitForFunction(() => state.route === "work" && !document.getElementById("dialog").open);
            item.after = await snapshot(page);
            item.focusAfter = await focusInfo(page);
            await page.screenshot({ path: path.join(out, `keyboard-${label}-after.png`) });
            assert.equal(item.focusAfter.id, "main", "scope confirmation must focus the newly connected #main");
            assert(item.focusAfter.documentFocused && item.focusAfter.connected && item.focusAfter.visible && !item.focusAfter.inDialog);
            assert(item.focusAfter.rect.y < 900 && item.focusAfter.rect.y + item.focusAfter.rect.height > 0, "main must intersect the viewport");
            assert.equal(await page.evaluate(() => state.agent), "Claude Code");
            assert.equal(await page.evaluate(() => state.approval), "pending");
            assert.equal(await page.evaluate(() => state.admitted), false);
            assert.equal(await page.evaluate(() => state.stopped), false);
            assert.equal(await page.evaluate(() => state.message), "");
            assert.equal(await page.evaluate(() => state.requestId), "");
            assert.equal(await page.evaluate(() => state.draft), await page.evaluate(() => seed()));
            await page.keyboard.press("Tab");
            item.nextTab = await focusInfo(page);
            assert(item.nextTab.documentFocused && item.nextTab.inMain && item.nextTab.connected && item.nextTab.visible, "Tab after confirmation must reach workspace controls");
          } else {
            await tabTo(page, '[data-action="theme"]');
            const before = await snapshot(page);
            const theme = await page.evaluate(() => document.documentElement.dataset.theme);
            await page.keyboard.press("Enter");
            item.focusAfter = await focusInfo(page);
            item.after = await snapshot(page);
            await page.screenshot({ path: path.join(out, `keyboard-${label}-after.png`) });
            assert.notEqual(await page.evaluate(() => document.documentElement.dataset.theme), theme);
            assert.deepEqual(item.after, before, "theme render must preserve operation state");
            assert.equal(item.focusAfter.action, "theme", "theme render must retain the equivalent control focus");
            assert(item.focusAfter.documentFocused && item.focusAfter.connected && item.focusAfter.visible);
            await page.keyboard.press("Tab");
            assert.equal((await focusInfo(page)).action, "language");
          }
          item.outcome = "passed";
        } catch (error) {
          item.outcome = "failed";
          item.error = error.message;
          item.failureFocus = await focusInfo(page);
          await page.screenshot({ path: path.join(out, `keyboard-${label}-failure.png`) });
        } finally {
          item.input = await page.evaluate(() => window.keyboardEvents || []);
          item.focusEvents = await page.evaluate(() => window.focusEvents || []);
          assert(item.focusEvents.every(e => !e.modalBackground), `${label}: native modal must never focus a background control`);
          assert(item.input.length > 0 && item.input.every(e => e.trusted), `${label}: all tested input must be trusted browser keyboard/click events`);
          await page.close();
        }
      }
    }
    assert.equal(report.errors.length, 0, "no page errors");
    assert.equal(report.externalRequests.length, 0, "no external requests");
    assert(report.cases.every(item => item.outcome === "passed"), "keyboard qualification has failed cases");
  } finally {
    fs.writeFileSync(path.join(out, "keyboard-focus-verification.json"), JSON.stringify(report, null, 2) + "\n");
    console.log(JSON.stringify(report.cases.map(({ label, outcome, error }) => ({ label, outcome, error }))));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
