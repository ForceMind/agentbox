// Bounded U1 evidence: native Chromium browser zoom, not CSS/pinch/DPR emulation.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { execFileSync } = require("node:child_process");
const { pathToFileURL } = require("node:url");

function assertZoom(base, zoom) {
  assert.equal(base.dpr, 1, "100% baseline must use native DPR 1");
  assert.equal(zoom.dpr, 2, "native page zoom must report DPR 2");
  assert.equal(zoom.scale, 1, "pinch zoom is not browser zoom");
  assert.equal(base.scale, 1);
  assert.equal(zoom.outerWidth, base.outerWidth, "window width changed");
  assert.equal(zoom.outerHeight, base.outerHeight, "window height changed");
  assert(Math.abs(base.width - zoom.width * 2) <= 2, "layout width must halve");
  assert(
    Math.abs(base.height - zoom.height * 2) <= 2,
    "layout height must halve",
  );
  assert.equal(
    zoom.bodyFont,
    base.bodyFont,
    "CSS font size must stay unchanged",
  );
  assert.equal(zoom.bodyZoom, base.bodyZoom, "CSS zoom must stay unchanged");
  assert.equal(zoom.bodyTransform, "none", "CSS transform is not browser zoom");
  assert.equal(zoom.large, false, "large mode is not browser zoom");
}

async function main() {
  const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
  const out = path.join(__dirname, "evidence");
  fs.mkdirSync(out, { recursive: true });
  const html = path.join(__dirname, "index.html");
  const report = {
    method: "headed Chromium; Xvfb; native X11 Ctrl+0/Ctrl+=; no emulation",
    scope: "six-core baseline / one native window / zh / light",
    date: new Date().toISOString(),
    source: process.env.GITHUB_SHA || "local",
    headSource: process.env.KEBUI_HEAD_SHA || "local",
    checkoutTree: execFileSync("git", ["rev-parse", "HEAD^{tree}"], { encoding: "utf8" }).trim(),
    htmlSHA256: crypto
      .createHash("sha256")
      .update(fs.readFileSync(html))
      .digest("hex"),
    status: "running",
    keyboard: [],
    calibration: [],
    screens: [],
    screenshots: [],
    nativeImages: [],
    pointers: [],
    clicks: [],
    requests: [],
    errors: [],
  };
  let browser;
  let page;
  let windowId;
  let chromeInsets;
  const xdo = (...args) => {
    report.keyboard.push(args);
    return execFileSync("xdotool", args, {
      encoding: "utf8",
      timeout: 10000,
    }).trim();
  };
  const metrics = () =>
    page.evaluate(() => ({
      dpr: devicePixelRatio,
      scale: visualViewport.scale,
      width: innerWidth,
      height: innerHeight,
      outerWidth,
      outerHeight,
      bodyFont: getComputedStyle(document.body).fontSize,
      bodyZoom: getComputedStyle(document.body).zoom,
      bodyTransform: getComputedStyle(document.body).transform,
      large: document.body.classList.contains("large"),
    }));
  const shot = async (name) => {
    const filename = `zoom-native-${name}.png`;
    const destination = path.join(out, filename);
    execFileSync("import", ["-window", "root", destination], { timeout: 10000 });
    const png = fs.readFileSync(destination);
    assert.equal(png.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
    const width = png.readUInt32BE(16);
    const height = png.readUInt32BE(20);
    assert.equal(width, 1600, "capture must retain the full isolated Xvfb root");
    assert.equal(height, 1200);
    report.screenshots.push(filename);
    report.nativeImages.push({ filename, width, height, metrics: await metrics() });
  };
  const tick = () =>
    page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );
  let current;
  async function nativeMove(x, y, label) {
    const m = await metrics();
    const point = nativePoint(x, y, m.dpr, chromeInsets);
    await page.evaluate(() => { window.__zoomPointer = null; });
    // Move out first so even repeated targets yield a fresh trusted event.
    xdo("mousemove", "--window", windowId, "0", "0");
    xdo("mousemove", "--window", windowId, String(point.x), String(point.y));
    await page.waitForFunction(({ x, y }) => window.__zoomPointer &&
      Math.abs(window.__zoomPointer.x - x) <= 1 && Math.abs(window.__zoomPointer.y - y) <= 1, { x, y });
    const actual = await page.evaluate(() => window.__zoomPointer);
    assert(actual.trusted, `${label}: native pointer must be trusted`);
    assert(Math.abs(actual.x - x) <= 1 && Math.abs(actual.y - y) <= 1,
      `${label}: native/CSS coordinates disagree ${JSON.stringify({ x, y, point, actual })}`);
    report.pointers.push({ label, intended: { x, y }, native: point, actual });
    return actual;
  }
  // Wheel the real document or open dialog. Never use DOM scrollIntoView or force clicks.
  async function reveal(locator, label) {
    assert.equal(await locator.count(), 1, `${label}: unique target`);
    for (let attempt = 0; attempt < 32; attempt++) {
      const geom = await locator.evaluate((el) => {
        const r = el.getBoundingClientRect();
        const dialog = el.closest("dialog");
        const clip = dialog
          ? dialog.getBoundingClientRect()
          : { top: 0, bottom: innerHeight, left: 0, right: innerWidth };
        return {
          x: r.x,
          y: r.y,
          width: r.width,
          height: r.height,
          top: Math.max(0, clip.top + 2),
          bottom: Math.min(innerHeight, clip.bottom - 2),
          left: Math.max(0, clip.left + 2),
          right: Math.min(innerWidth, clip.right - 2),
          scroll: dialog ? dialog.scrollTop : scrollY,
          scroller: dialog ? "dialog" : "document",
        };
      });
      assert(geom.width > 0 && geom.height > 0, `${label}: nonempty bounds`);
      const fits = geom.y >= geom.top && geom.y + geom.height <= geom.bottom;
      if (fits) {
        const overflow = await locator.evaluate((el) => {
          const root = document.documentElement;
          const dialog = el.closest("dialog");
          return {
            page: root.scrollWidth - root.clientWidth,
            target: el.scrollWidth - el.clientWidth,
            dialog: dialog ? dialog.scrollWidth - dialog.clientWidth : 0,
          };
        });
        assert(
          overflow.page <= 1 && overflow.target <= 1 && overflow.dialog <= 1,
          `${label}: horizontal content overflow ${JSON.stringify(overflow)}`,
        );
        assert(
          geom.x >= 0 && geom.x + geom.width <= (await metrics()).width + 1,
          `${label}: horizontal clipping`,
        );
        const hit = await locator.evaluate((el) => {
          const r = el.getBoundingClientRect();
          const points = [0.2, 0.5, 0.8].flatMap((x) =>
            [0.2, 0.5, 0.8].map((y) => [r.x + r.width * x, r.y + r.height * y]),
          );
          // Mid-edge samples catch thin overlays without treating rounded corners as clipping.
          points.push(
            [r.x + 1, r.y + r.height / 2],
            [r.right - 1, r.y + r.height / 2],
            [r.x + r.width / 2, r.y + 1],
            [r.x + r.width / 2, r.bottom - 1],
          );
          return points.every(([x, y]) => {
            const at = document.elementFromPoint(x, y);
            return at === el || el.contains(at);
          });
        });
        assert(hit, `${label}: target obscured`);
        current.targets.push({ label, geometry: geom, unobscured: true });
        return locator;
      }
      assert(
        geom.height <= geom.bottom - geom.top,
        `${label}: target taller than scroll viewport`,
      );
      const delta = wheelDelta(geom);
      const x = (geom.left + geom.right) / 2;
      const y = (geom.top + geom.bottom) / 2;
      // Calibrate the CDP wheel position against a fresh trusted DOM pointer event.
      // Native browser zoom uses device-independent input coordinates here.
      await page.evaluate(() => { window.__zoomPointer = null; window.__zoomWheel = null; });
      await page.mouse.move(0, 0);
      const scale = (await metrics()).dpr;
      await page.mouse.move(x * scale, y * scale);
      await page.waitForFunction(({ x, y }) => window.__zoomPointer &&
        Math.abs(window.__zoomPointer.x - x) <= 1 && Math.abs(window.__zoomPointer.y - y) <= 1, { x, y });
      const pointer = await page.evaluate(() => window.__zoomPointer);
      assert(pointer.trusted && Math.abs(pointer.x - x) <= 1 && Math.abs(pointer.y - y) <= 1,
        "wheel pointer coordinate calibration failed");
      await page.mouse.wheel(0, delta * scale);
      await page.waitForFunction(() => window.__zoomWheel !== null);
      const actualWheel = await page.evaluate(() => window.__zoomWheel);
      assert(actualWheel.trusted && actualWheel.deltaMode === 0, "trusted pixel wheel event required");
      assert(Math.abs(actualWheel.x - x) <= 1 && Math.abs(actualWheel.y - y) <= 1,
        "wheel event coordinates must match calibrated pointer");
      assert(Math.sign(actualWheel.deltaY) === Math.sign(delta), "wheel direction");
      await tick();
      const after = await locator.evaluate(
        (el) => el.closest("dialog")?.scrollTop ?? scrollY,
      );
      if (after !== geom.scroll)
        current.wheels.push({
          target: label,
          scroller: geom.scroller,
          before: geom.scroll,
          after,
          delta,
          pointer,
          actualWheel,
        });
    }
    assert.fail(`${label}: wheel could not reach target`);
  }
  const button = (action) =>
    page.locator(`[data-action="${action}"]`).filter({ visible: true });
  async function click(action) {
    const target = await reveal(button(action), action);
    assert(await target.isEnabled(), `${action}: enabled`);
    const rect = await target.evaluate((el) => {
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height };
    });
    const apiBox = await target.boundingBox();
    const x = rect.x + rect.width / 2;
    const y = rect.y + rect.height / 2;
    const pointer = await nativeMove(x, y, action);
    assert.equal(pointer.action, action, "native pointer must hit the intended button");
    await page.evaluate(() => { window.__zoomClick = null; });
    xdo("click", "--clearmodifiers", "1");
    await page.waitForFunction(() => window.__zoomClick !== null);
    const actual = await page.evaluate(() => window.__zoomClick);
    assert(actual.trusted, "native click must be trusted");
    assert.equal(actual.action, action, "native click must reach the intended action");
    assert(Math.abs(actual.x - x) <= 1 && Math.abs(actual.y - y) <= 1, "native click coordinates");
    report.clicks.push({ action, rect, apiBox, pointer, actual });
  }
  async function facts(locator, label) {
    const fields = locator.locator("dt, dd");
    assert((await fields.count()) > 0, `${label}: contains fields`);
    for (let i = 0; i < (await fields.count()); i++) {
      await reveal(fields.nth(i), `${label} field ${i + 1}`);
    }
  }
  try {
    assert(
      process.env.DISPLAY,
      "Use the existing CI's xvfb-run for headed Chromium",
    );
    browser = await chromium.launch({
      headless: false,
      args: ["--window-size=1440,1000", "--window-position=0,0"],
    });
    report.browser = await browser.version();
    const context = await browser.newContext({ viewport: null });
    page = await context.newPage();
    page.setDefaultTimeout(10000);
    page.on("request", (r) => {
      if (!r.url().startsWith("file:")) report.requests.push(r.url());
    });
    page.on("pageerror", (e) => report.errors.push(e.message));
    await page.addInitScript(() => {
      const snapshot = (event) => ({
        x: event.clientX, y: event.clientY, trusted: event.isTrusted,
        action: event.target.closest?.("button")?.dataset.action || null,
        tag: event.target.tagName,
        deltaX: event.deltaX, deltaY: event.deltaY, deltaMode: event.deltaMode,
      });
      document.addEventListener("mousemove", (e) => { window.__zoomPointer = snapshot(e); }, { capture: true, passive: true });
      document.addEventListener("wheel", (e) => { window.__zoomWheel = snapshot(e); }, { capture: true, passive: true });
      document.addEventListener("click", (e) => { window.__zoomClick = snapshot(e); }, { capture: true, passive: true });
    });
    await page.goto(pathToFileURL(html).href);
    await page.bringToFront();
    const title = await page.title();
    const windows = xdo("search", "--onlyvisible", "--class", "chromium")
      .split(/\s+/)
      .filter(Boolean);
    const matches = windows.filter((id) =>
      xdo("getwindowname", id).includes(title),
    );
    assert.equal(matches.length, 1, "exactly one synthetic Chromium window");
    windowId = matches[0];
    xdo("windowfocus", "--sync", windowId);
    xdo("key", "--clearmodifiers", "ctrl+0");
    await tick();
    const base = await metrics();
    const nativeGeometry = Object.fromEntries(xdo("getwindowgeometry", "--shell", windowId)
      .split("\n").map((line) => line.split("=")).map(([key, value]) => [key, Number(value)]));
    assert.equal(nativeGeometry.WIDTH, base.outerWidth);
    assert.equal(nativeGeometry.HEIGHT, base.outerHeight);
    assert.equal(base.width, nativeGeometry.WIDTH, "unframed Xvfb content width");
    chromeInsets = { left: 0, top: nativeGeometry.HEIGHT - base.height };
    assert(chromeInsets.top > 0 && chromeInsets.top < 200, "bounded native browser chrome");
    report.nativeWindow = { ...nativeGeometry, chromeInsets };
    report.calibration.push({ percent: 100, ...base });
    await shot("calibration-100");
    let previous = base.dpr;
    for (const percent of [110, 125, 150, 175, 200]) {
      xdo("key", "--clearmodifiers", "ctrl+equal");
      await page.waitForFunction((old) => devicePixelRatio > old, previous);
      const observed = await metrics();
      report.calibration.push({ percent, ...observed });
      assert(
        Math.abs(observed.dpr - percent / 100) < 0.02,
        `native zoom step ${percent}`,
      );
      previous = observed.dpr;
    }
    assertZoom(base, await metrics());
    await shot("calibration-200");
    // Preserve one API comparison separately; it is not native pixel qualification.
    await page.screenshot({ path: path.join(out, "zoom-api-comparison-200.png"), fullPage: false });
    report.screenshots.push("zoom-api-comparison-200.png");
    assertZoom(base, await metrics());
    await shot("after-api-comparison-200");
    // Close only the native zoom bubble; no site dialog is open yet.
    xdo("key", "--clearmodifiers", "Escape");
    for (const route of [
      "home",
      "work",
      "approval",
      "results",
      "agents",
      "recovery",
    ]) {
      current = { route, targets: [], wheels: [], status: "running" };
      report.screens.push(current);
      await page.evaluate((route) => {
        resetScope();
        state.lang = "zh";
        state.scenario = "success";
        state.route = route;
        state.project = "Meadow";
        state.agent = "Codex";
        state.message = "请改善合成项目的空状态，并补充可访问性测试。";
        state.requestId = "demo-zoom-request-01";
        state.requestCount = 1;
        state.acceptedCount = 1;
        state.sendAttempts = 1;
        state.phase =
          route === "work"
            ? "running"
            : route === "results"
              ? "succeeded"
              : route === "recovery"
                ? "unknown"
                : "idle";
        state.online = route !== "recovery";
        state.admitted = false;
        document.documentElement.dataset.theme = "light";
        render();
      }, route);
      await page.keyboard.press("Control+Home");
      await tick();
      assertZoom(base, await metrics());
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${route}: page overflow`,
      );
      await shot(`${route}-top`);
      if (route === "home") {
        await reveal(page.locator("#main .notice"), "home explanatory body");
        await shot("home-body");
        await click("new");
        await click("close");
        assert.equal(await page.locator("#dialog").isVisible(), false);
      } else if (route === "work") {
        await reveal(page.locator(".message.user p"), "synthetic request body");
        await shot("work-body");
        await reveal(page.locator("#composer"), "composer");
        await shot("work-composer");
        await click("advance");
        assert.equal(await page.evaluate(() => state.phase), "succeeded");
        await click("go:results");
        await click("back-work");
        assert.equal(await page.evaluate(() => state.route), "work");
      } else if (route === "approval") {
        await facts(
          page.locator("#main .facts"),
          "approval scope and consequences",
        );
        await shot("approval-scope");
        await reveal(button("reject"), "reject alternative");
        await click("approve");
        assert.equal(await page.evaluate(() => state.approval), "approved");
        await reveal(button("approval-continue"), "approval readback action");
        await shot("approval-readback");
      } else if (route === "results") {
        assert.equal(await page.locator("#diff").count(), 0);
        await click("read-result");
        await reveal(page.locator("#diff"), "explicitly read synthetic body");
        assert(
          (await page.locator("#diff").textContent()).includes(
            "Create project",
          ),
        );
        await shot("results-body");
        await click("diff-raw");
        await reveal(page.locator("#diff"), "raw body");
        await shot("results-raw");
        await click("back-work");
        assert.equal(await page.evaluate(() => state.route), "work");
      } else if (route === "agents") {
        await facts(
          page.locator("#main .facts").nth(1),
          "Claude environment qualification",
        );
        await shot("agents-environment");
        await click("choose:Claude Code");
        await click("close");
        assert.equal(await page.evaluate(() => state.agent), "Codex");
      } else {
        assert(await button("stop-dialog").isDisabled());
        await click("recover");
        assert.equal(await page.evaluate(() => state.recovered), true);
        await click("stop-dialog");
        await facts(page.locator("#dialog .facts"), "exact Stop scope");
        await shot("recovery-stop-scope");
        await click("close");
        assert.equal(await page.evaluate(() => state.stopped), false);
        await click("stop-dialog");
        await reveal(button("stop-confirm"), "exact Stop confirmation");
        await shot("recovery-stop-button");
        await click("stop-confirm");
        assert.equal(await page.evaluate(() => state.stopped), true);
        await reveal(page.locator("#main .card h2"), "Stop readback");
        await shot("recovery-readback");
      }
      assert(
        current.wheels.length > 0,
        `${route}: actual wheel scrolling required`,
      );
      assertZoom(base, await metrics());
      assert(
        await page.evaluate(
          () =>
            document.documentElement.scrollWidth <=
            document.documentElement.clientWidth + 1,
        ),
        `${route}: final-state page overflow`,
      );
      current.status = "passed";
    }
    assert.deepEqual(report.requests, []);
    assert.deepEqual(report.errors, []);
    report.status = "passed";
  } catch (error) {
    report.status = "failed";
    if (current && current.status === "running") current.status = "failed";
    report.failure = String(error.stack || error);
    if (page && !page.isClosed()) {
      report.failureMetrics = await metrics().catch(() => null);
      await shot("failure").catch(() => {});
    }
    throw error;
  } finally {
    fs.writeFileSync(
      path.join(out, "browser-zoom-verification.json"),
      JSON.stringify(report, null, 2) + "\n",
    );
    console.log(JSON.stringify(report, null, 2));
    if (browser) await browser.close();
  }
}

function wheelDelta(geometry) {
  return Math.max(
    -240,
    Math.min(
      240,
      geometry.y + geometry.height / 2 - (geometry.top + geometry.bottom) / 2,
    ),
  );
}

function nativePoint(x, y, dpr, insets) {
  assert(Number.isFinite(x) && Number.isFinite(y) && dpr > 0);
  return { x: Math.round(insets.left + x * dpr), y: Math.round(insets.top + y * dpr) };
}

module.exports = { assertZoom, wheelDelta, nativePoint };
if (require.main === module)
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
