const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const fs = require("fs");
const path = require("path");
const assert = require("assert");
(async () => {
  const out = path.join(__dirname, "evidence");
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
    headless: true,
  });
  const page = await browser.newPage();
  let network = [];
  let errors = [];
  page.on("request", (r) => {
    if (!r.url().startsWith("file:")) network.push(r.url());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  const url = "file://" + path.join(__dirname, "index.html");
  const results = [];
  const check = (s) => results.push(s);
  const act = async (s) => {
    await page.locator(`[data-action="${s}"]`).first().click();
  };
  await page.goto(url);
  await act("new");
  await page.selectOption("#agent-choice", "Claude Code");
  await act("create-work");
  await page.fill("#draft", "Synthetic keyboard and IME request");
  await page.locator("#draft").dispatchEvent("compositionstart");
  await page.locator("#draft").press("Control+Enter");
  assert.equal(await page.evaluate(() => state.phase), "idle");
  await page.locator("#draft").dispatchEvent("compositionend");
  const beforeNewline = await page.locator("#draft").inputValue();
  await page.locator("#draft").press("End");
  await page.locator("#draft").press("Enter");
  assert.equal(await page.locator("#draft").inputValue(), beforeNewline + "\n");
  assert.equal(await page.evaluate(() => state.phase), "idle");
  await page.locator("#draft").dispatchEvent("keydown", {
    key: "Enter",
    metaKey: true,
    isComposing: true,
  });
  assert.equal(await page.evaluate(() => state.requestCount), 0);
  await page.locator("#draft").press("Control+Enter");
  assert.equal(await page.evaluate(() => state.phase), "accepted");
  const acceptedId = await page.evaluate(() => state.requestId);
  await page.evaluate(() => send());
  assert.equal(await page.evaluate(() => state.phase), "accepted");
  assert.equal(await page.evaluate(() => state.requestId), acceptedId);
  assert.equal(await page.evaluate(() => state.requestCount), 1);
  assert.equal(await page.evaluate(() => state.acceptedCount), 1);
  assert.equal(await page.evaluate(() => state.sendAttempts), 1);
  await act("advance");
  await act("advance");
  await act("go:results");
  assert.equal(await page.locator("#diff").count(), 0);
  await act("read-result");
  assert.equal(await page.locator("#diff").count(), 1);
  await act("back-work");
  assert.equal(await page.evaluate(() => state.phase), "succeeded");
  check(
    "A success: explicit Project/Agent, IME does not send, Enter newline, Ctrl+Enter accept, advance twice, gated body, return",
  );
  await page.selectOption("#scenario", "failure");
  const beforeFailedRequest = await page.evaluate(() => state.requestCount);
  await page.fill("#draft", "Retry synthetic request");
  await page.locator("#composer button[type=submit]").click();
  assert.equal(await page.evaluate(() => state.phase), "failed");
  assert.equal(
    await page.evaluate(() => state.message),
    "Retry synthetic request",
  );
  assert.equal(
    await page.evaluate(() => state.requestCount),
    beforeFailedRequest + 1,
  );
  const failedId = await page.evaluate(() => state.requestId);
  assert.notEqual(failedId, acceptedId);
  await act("retry");
  assert.equal(await page.evaluate(() => state.requestId), failedId);
  assert.equal(await page.evaluate(() => state.phase), "accepted");
  await act("disconnect");
  assert.equal(await page.evaluate(() => state.route), "recovery");
  assert.equal(await page.evaluate(() => state.phase), "unknown");
  check(
    "A failure/interruption: failed request explicitly retried; disconnect does not create success",
  );
  await page.selectOption("#scenario", "success");
  await page.goto(url + "#approval");
  await act("approve");
  assert.equal(await page.evaluate(() => state.approval), "approved");
  assert(await page.locator("[data-action=approve]").isDisabled());
  await act("approval-continue");
  assert.equal(await page.evaluate(() => state.phase), "accepted");
  await page.goto(url + "#approval");
  await page.selectOption("#scenario", "failure");
  await act("approve");
  assert.equal(await page.evaluate(() => state.approval), "unknown");
  await act("read-approval");
  assert.equal(await page.evaluate(() => state.approval), "expired");
  const expiredRevision = await page.evaluate(() => state.revision);
  await act("fresh-approval");
  assert.equal(await page.evaluate(() => state.revision), expiredRevision + 1);
  await act("reject");
  assert.equal(await page.evaluate(() => state.approval), "rejected");
  await page.selectOption("#scenario", "interrupted");
  await act("approve");
  assert.equal(await page.evaluate(() => state.approval), "unknown");
  check(
    "B success/failure/interruption: revision-bound approval, explicit read-only recovery, expiry, fresh revision, rejection",
  );
  await page.goto(url + "#recovery");
  await page.selectOption("#scenario", "failure");
  await act("recover");
  assert.equal(await page.evaluate(() => state.recovered), false);
  await page.selectOption("#scenario", "interrupted");
  await act("recover");
  assert.equal(await page.evaluate(() => state.recovered), true);
  await act("stop-dialog");
  assert(await page.locator("#dialog").isVisible());
  await act("close");
  assert.equal(await page.evaluate(() => state.stopped), false);
  await act("stop-dialog");
  await act("stop-confirm");
  assert.equal(await page.evaluate(() => state.stopped), true);
  await act("detach");
  assert.equal(await page.evaluate(() => state.stopped), true);
  check(
    "C failure/interruption/success: no replay, target reverification, cancel stop, exact synthetic stop readback, detach distinct",
  );
  await page.goto(url + "#work");
  await page.selectOption("#scenario", "success");
  await page.fill("#draft", "<img src=x onerror=alert(1)>");
  await page.locator("#composer button[type=submit]").click();
  assert.equal(await page.locator("img").count(), 0);
  await act("new");
  await act("create-work");
  assert.equal(await page.evaluate(() => state.message), "");
  assert.equal(await page.evaluate(() => state.admitted), false);
  check("User text inert; new scope clears message/body/approval");
  await page.selectOption("#scenario", "failure");
  assert(await page.locator('[data-action="retry"]').isDisabled());
  await page.fill("#draft", "Failure needs an actual request");
  await page.locator("#composer button[type=submit]").click();
  assert.equal(await page.locator('[data-action="retry"]').isDisabled(), false);
  await act("retry");
  await act("new");
  await act("create-work");
  await page.selectOption("#scenario", "success");
  await page.fill("#draft", "Synthetic Command shortcut");
  await page.locator("#draft").press("Meta+Enter");
  assert.equal(await page.evaluate(() => state.acceptedCount), 1);
  check(
    "Enter inserts newline; composing Meta event cannot send; Meta+Enter sends; fresh failure has disabled retry",
  );

  // Regressions discovered by independent review. Events are explicitly injected;
  // this verifies browser lifecycle handlers, not physical background/OS behavior.
  await page.goto(url + "#recovery");
  await page.selectOption("#scenario", "success");
  await act("recover");
  await act("detach");
  assert.equal(await page.evaluate(() => state.stopped), false);
  assert.equal(await page.evaluate(() => state.phase), "running");
  await page.goto(url + "#recovery");
  await act("stop-dialog");
  await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  assert.equal(await page.evaluate(() => state.recovered), false);
  assert(await page.locator('[data-action="stop-dialog"]').isDisabled());
  assert.equal(await page.locator("#dialog").isVisible(), false);
  await act("recover");
  await act("stop-dialog");
  await page.evaluate(() => {
    window.oldStopButton = document.querySelector(
      '[data-action="stop-confirm"]',
    );
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  assert.equal(await page.locator("#dialog").isVisible(), false);
  await page.evaluate(() => {
    delete document.hidden;
  });
  await act("recover");
  await page.evaluate(() => {
    document.getElementById("dialog").append(window.oldStopButton);
    window.oldStopButton.click();
  });
  assert.equal(await page.evaluate(() => state.stopped), false);
  await act("stop-dialog");
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#dialog").isVisible(), false);
  await act("stop-dialog");
  await act("stop-confirm");
  await act("recover");
  assert.equal(await page.evaluate(() => state.stopped), true);
  assert.equal(await page.evaluate(() => state.phase), "interrupted");
  await page.goto(url + "#agents");
  await page.evaluate(() => {
    state.draft = "preserved synthetic draft";
    state.admitted = true;
    state.approval = "approved";
  });
  const beforePicker = await page.evaluate(() => JSON.stringify(state));
  await act("choose:Claude Code");
  await act("close");
  assert.equal(await page.evaluate(() => JSON.stringify(state)), beforePicker);
  await act("choose:Claude Code");
  await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => JSON.stringify(state)), beforePicker);
  await act("choose:Claude Code");
  await act("create-work");
  assert.equal(await page.evaluate(() => state.agent), "Claude Code");
  assert.equal(await page.evaluate(() => state.admitted), false);
  assert.equal(await page.evaluate(() => state.approval), "pending");
  assert.equal(await page.evaluate(() => state.message), "");
  assert.equal(await page.evaluate(() => state.requestId), "");
  assert.equal(await page.evaluate(() => state.recovered), false);
  assert.equal(await page.evaluate(() => state.stopped), false);
  const beforeSkip = await page.evaluate(() => ({
    hash: location.hash,
    draft: state.draft,
  }));
  await page.locator(".skip").focus();
  await page.keyboard.press("Enter");
  assert.equal(await page.evaluate(() => document.activeElement.id), "main");
  assert.equal(await page.evaluate(() => location.hash), beforeSkip.hash);
  assert.equal(await page.evaluate(() => state.draft), beforeSkip.draft);
  assert.equal(await page.evaluate(() => state.route), "work");
  check(
    "Reviewed regressions: offline/hidden stale Stop, stopped readback, Agent cancel/Escape, committed scope clearing, keyboard skip without route mutation",
  );
  await page.evaluate(() => toast("Synthetic dismissible notice"));
  await act("dismiss-toast");
  assert.equal(await page.locator("#live").textContent(), "");
  await page.evaluate(() => toast("Synthetic expiring notice"));
  await page.waitForFunction(
    () => document.getElementById("live").textContent === "",
  );
  await page.evaluate(() => toast("Synthetic old-route notice"));
  await page.goto(url + "#catalog");
  const screens = await page.evaluate(() => Object.keys(titles));
  for (const screen of screens) {
    await page.goto(url + "#" + screen);
    await page.waitForFunction((r) => state.route === r, screen);
    assert(await page.locator("h1").count());
  }
  check(`All ${screens.length} catalog screens open`);
  let geometries = 0;
  for (const width of [360, 390, 768, 1024, 1440])
    for (const lang of ["zh", "en"])
      for (const theme of ["light", "dark"])
        for (const screen of [
          "home",
          "work",
          "approval",
          "results",
          "agents",
          "recovery",
        ]) {
          await page.setViewportSize({
            width,
            height: width < 768 ? 844 : 1000,
          });
          await page.evaluate(
            ({ lang, theme, screen }) => {
              resetScope();
              state.project = "Meadow";
              state.agent = "Codex";
              state.message = "请改善合成项目的空状态，并补充可访问性测试。";
              state.requestId = "demo-capture-request-01";
              state.requestCount = 1;
              state.acceptedCount = 1;
              state.sendAttempts = 1;
              state.lang = lang;
              state.scenario = "success";
              state.route = screen;
              state.phase =
                screen === "work"
                  ? "running"
                  : screen === "results"
                    ? "succeeded"
                    : screen === "recovery"
                      ? "unknown"
                      : "idle";
              state.online = screen !== "recovery";
              state.admitted = screen === "results";
              state.approval = "pending";
              state.recovered = false;
              state.stopped = false;
              document.documentElement.dataset.theme = theme;
              render();
            },
            { lang, theme, screen },
          );
          assert.equal(await page.locator("#live").textContent(), "");
          const geometry = await page.evaluate(() => ({
            scroll: document.documentElement.scrollWidth,
            width: innerWidth,
          }));
          assert(
            geometry.scroll <= geometry.width,
            JSON.stringify({ width, lang, theme, screen, geometry }),
          );
          geometries++;
          if ([390, 1440].includes(width) && lang === "zh") {
            await page.screenshot({
              path: path.join(out, `${screen}-${width}-${theme}.png`),
              fullPage: true,
            });
          }
        }
  check(
    `${geometries} core-screen geometry cases: 360/390/768/1024/1440 × zh/en × light/dark × 6`,
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(url + "#settings");
  await act("large");
  for (const screen of screens) {
    await page.goto(url + "#" + screen);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    );
    assert(!overflow, `Large text overflow: ${screen}`);
  }
  check(
    `Large-text mode: ${screens.length} screens at 390px without horizontal page overflow`,
  );
  await page.goto(url + "#work");
  await page.evaluate(() => (state.draft = "same-scope draft"));
  await page.evaluate(() => render());
  await act("go:workspace");
  await page.goBack();
  assert.equal(await page.locator("#draft").inputValue(), "same-scope draft");
  await page.goForward();
  await page.waitForFunction(() => state.route === "workspace");
  assert.equal(await page.evaluate(() => state.draft), "same-scope draft");
  check("Hash Back/Forward preserves same-scope draft");
  assert.equal(network.length, 0);
  assert.equal(errors.length, 0);
  check("Zero non-file requests and zero browser page errors");
  fs.writeFileSync(
    path.join(out, "verification.json"),
    JSON.stringify(
      {
        date: new Date().toISOString(),
        browser: await browser.version(),
        checks: results,
        geometries,
        screenshots: 24,
        network,
        errors,
      },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({ checks: results, geometries, network, errors }, null, 2),
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
