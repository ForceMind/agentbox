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
  const config = readConfig(process.env);
  const out = path.join(__dirname, "evidence");
  fs.mkdirSync(out, { recursive: true });
  const html = path.join(__dirname, "index.html");
  const report = {
    method: "headed Chromium; Xvfb; native X11 Ctrl+0/Ctrl+=; no emulation",
    scope: `six-core / native window ${config.width}x1000 / ${config.lang} / ${config.theme}`,
    config,
    wheelMode: "native detented wheel; centeringIntent is not actual displacement; actual scroll and wheel events are recorded",
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
  const runXdo = (timeout, args) => {
    assert(timeout > 0, "native window discovery budget exhausted");
    report.keyboard.push(args);
    return execFileSync("xdotool", args, {
      encoding: "utf8",
      timeout,
    }).trim();
  };
  const xdo = (...args) => runXdo(10000, args);
  const xdoProbe = (remaining, ...args) => runXdo(Math.floor(remaining()), args);
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
    if (name !== "failure") await page.waitForFunction(() =>
      !window.__zoomScrolls.document.pending &&
      (!document.getElementById("dialog").open || !window.__zoomScrolls.dialog.pending));

    const presentation = await page.evaluate(() => ({ language: state.lang, htmlLanguage: document.documentElement.lang, theme: document.documentElement.dataset.theme }));
    assert.deepEqual(presentation, { language: config.lang, htmlLanguage: config.lang === "zh" ? "zh-CN" : "en", theme: config.theme }, "actual rendered language/theme must match the case");
    const filename = `zoom-${config.key}-native-${name}.png`;
    const destination = path.join(out, filename);
    execFileSync("import", ["-window", "root", destination], { timeout: 10000 });
    const png = fs.readFileSync(destination);
    assert.equal(png.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
    const width = png.readUInt32BE(16);
    const height = png.readUInt32BE(20);
    assert.equal(width, 1600, "capture must retain the full isolated Xvfb root");
    assert.equal(height, 1200);
    report.screenshots.push(filename);
    report.nativeImages.push({ filename, width, height, metrics: await metrics(),
      view: await page.evaluate(() => ({
        scrollX, scrollY, route: state.route, phase: state.phase,
        language: state.lang, htmlLanguage: document.documentElement.lang, theme: document.documentElement.dataset.theme,
        admitted: state.admitted, recovered: state.recovered, stopped: state.stopped,
        approval: state.approval, dialogOpen: document.getElementById("dialog").open,
        dialogScroll: document.getElementById("dialog").scrollTop,
      })) });
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
      const settled = await waitForStableGeometry((timeout) => locator.evaluate((el) => {
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
          documentScroll: scrollY,
          pending: window.__zoomScrolls.document.pending ||
            Boolean(dialog?.open && window.__zoomScrolls.dialog.pending),
        };
      }, undefined, { timeout }));
      const geom = settled.geometry;
      current.geometryWaits.push({ label, observations: settled.observations, elapsedMs: settled.elapsedMs, scroll: geom.scroll });
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
      // Use one native X11 wheel notch at the independently calibrated pointer.
      // No CDP coordinate scaling or synthetic DOM event dispatch is involved.
      const pointer = await nativeMove(x, y, `wheel:${label}`);
      await page.evaluate(() => { window.__zoomWheel = null; });
      const beforeEnd = await page.evaluate((key) => window.__zoomScrolls[key].end, geom.scroller);
      xdo("click", "--clearmodifiers", delta > 0 ? "5" : "4");
      await page.waitForFunction(() => window.__zoomWheel !== null);
      const actualWheel = await page.evaluate(() => window.__zoomWheel);
      assert(actualWheel.trusted && actualWheel.deltaMode === 0, "trusted pixel wheel event required");
      assert(Math.abs(actualWheel.x - x) <= 1 && Math.abs(actualWheel.y - y) <= 1,
        "wheel event coordinates must match calibrated pointer");
      assert(Math.sign(actualWheel.deltaY) === Math.sign(delta), "wheel direction");
      await page.waitForFunction(({ key, beforeEnd }) =>
        window.__zoomScrolls[key].end > beforeEnd && !window.__zoomScrolls[key].pending,
        { key: geom.scroller, beforeEnd });
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
          centeringIntent: delta,
          pointer,
          actualWheel,
          scrollEndObserved: true,
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
      args: [`--window-size=${config.width},1000`, "--window-position=0,0"],
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
      window.__zoomScrolls = {
        document: { pending: false, scroll: 0, end: 0, trusted: true },
        dialog: { pending: false, scroll: 0, end: 0, trusted: true },
      };
      const scrolling = (kind, event) => {
        const key = event.target === document ? "document" : event.target.id === "dialog" ? "dialog" : null;
        if (!key) return;
        const record = window.__zoomScrolls[key];
        record[kind]++;
        record.pending = kind === "scroll";
        record.trusted = record.trusted && event.isTrusted;
      };
      document.addEventListener("scroll", (e) => scrolling("scroll", e), { capture: true, passive: true });
      document.addEventListener("scrollend", (e) => scrolling("end", e), { capture: true, passive: true });
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
    assert(await page.evaluate(() => "onscrollend" in document), "native scrollend support is required");
    await page.evaluate(({ lang, theme }) => { state.lang = lang; document.documentElement.dataset.theme = theme; render(); }, config);
    await page.bringToFront();
    const title = await page.title();
    report.windowDiscovery = [];
    windowId = await waitForNativeWindow((remaining) => {
      let windows;
      try {
        windows = xdoProbe(remaining, "search", "--onlyvisible", "--class", "chromium").split(/\s+/).filter(Boolean);
      } catch (error) {
        if (error.status === 1) return [];
        throw error;
      }
      return windows.map((id) => ({ id, title: xdoProbe(remaining, "getwindowname", id) }));
    }, title, report.windowDiscovery);
    xdo("windowfocus", "--sync", windowId);
    xdo("key", "--clearmodifiers", "ctrl+0");
    await tick();
    const base = await metrics();
    const nativeGeometry = Object.fromEntries(xdo("getwindowgeometry", "--shell", windowId)
      .split("\n").map((line) => line.split("=")).map(([key, value]) => [key, Number(value)]));
    assert.equal(nativeGeometry.WIDTH, config.width, "actual native window width matches requested case");
    assert.equal(nativeGeometry.HEIGHT, 1000, "actual native window height");
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
    assert.equal((await metrics()).width, config.width / 2, "200% layout width matches this native window case");
    await shot("calibration-200");
    // Preserve one API comparison separately; it is not native pixel qualification.
    await page.screenshot({ path: path.join(out, `zoom-${config.key}-api-comparison-200.png`), fullPage: false });
    report.screenshots.push(`zoom-${config.key}-api-comparison-200.png`);
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
      current = { route, targets: [], wheels: [], geometryWaits: [], status: "running" };
      report.screens.push(current);
      await page.evaluate(({ route, lang, theme }) => {
        resetScope();
        state.lang = lang;
        state.scenario = "success";
        state.route = route;
        state.project = "Meadow";
        state.agent = "Codex";
        state.message = lang === "zh" ? "请改善合成项目的空状态，并补充可访问性测试。" : "Improve the synthetic project empty state and add accessibility tests.";
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
        document.documentElement.dataset.theme = theme;
        render();
      }, { route, lang: config.lang, theme: config.theme });
      xdo("key", "--clearmodifiers", "ctrl+Home");
      await page.waitForFunction(() => scrollY === 0 && !window.__zoomScrolls.document.pending);
      await tick();
      assertZoom(base, await metrics());
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${route}: page overflow`,
      );
      await shot(`${route}-entry`);
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
        assert.equal(await page.evaluate(() => state.phase), "running");
        await reveal(page.locator("#main .card h2"), "cancel retains running readback");
        await shot("recovery-cancel-running");
        await reveal(page.locator("#main .card .facts"), "cancel retains exact target");
        await shot("recovery-cancel-target");
        await click("stop-dialog");
        await reveal(button("stop-confirm"), "exact Stop confirmation");
        await shot("recovery-stop-button");
        await click("stop-confirm");
        assert.equal(await page.evaluate(() => state.stopped), true);
        await reveal(page.locator("#main .card h2"), "Stop readback");
        await shot("recovery-readback-heading");
        await reveal(page.locator("#main .card .facts"), "stopped exact-target readback");
        await shot("recovery-readback-target");
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
      current.scrollEvents = await page.evaluate(() => window.__zoomScrolls);
      assert(Object.values(current.scrollEvents).every((events) => events.trusted), "native scroll lifecycle events");
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
      report.failureInput = await page.evaluate(() => ({ pointer: window.__zoomPointer, wheel: window.__zoomWheel, click: window.__zoomClick, scroll: window.__zoomScrolls })).catch(() => null);
      await shot("failure").catch(() => {});
    }
    throw error;
  } finally {
    fs.writeFileSync(
      path.join(out, `browser-zoom-${config.key}.json`),
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

function readConfig(env) {
  const width = env.KEBUI_ZOOM_WIDTH || "1440";
  const lang = env.KEBUI_ZOOM_LANG || "zh";
  const theme = env.KEBUI_ZOOM_THEME || "light";
  assert(["1440", "780"].includes(width), "bounded native window width");
  assert(["zh", "en"].includes(lang), "bounded UI language");
  assert(["light", "dark"].includes(theme), "bounded UI theme");
  return { width: Number(width), lang, theme, key: `${width}-${lang}-${theme}` };
}

async function waitForNativeWindow(observe, expectedTitle, trace, {
  now = () => performance.now(),
  pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  timeoutMs = 10000,
} = {}) {
  const start = now();
  const remaining = () => timeoutMs - (now() - start);
  while (true) {
    assert(remaining() > 0, "synthetic Chromium window title did not become ready");
    const windows = await observe(remaining);
    const matches = windows.filter((window) => window.title.includes(expectedTitle));
    trace.push({ elapsedMs: now() - start, expectedTitle, windows, matches: matches.map((window) => window.id) });
    assert(now() - start <= timeoutMs, "synthetic Chromium window title did not become ready");
    assert(matches.length <= 1, "ambiguous synthetic Chromium windows");
    if (matches.length === 1) return matches[0].id;
    assert(now() - start < timeoutMs, "synthetic Chromium window title did not become ready");
    await pause(Math.min(50, remaining()));
  }
}

async function waitForStableGeometry(observe, {
  now = () => performance.now(),
  pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  timeoutMs = 10000,
} = {}) {
  const start = now();
  let previous;
  let observations = 0;
  while (true) {
    const remaining = timeoutMs - (now() - start);
    assert(remaining > 0, `scroll geometry did not settle: ${JSON.stringify({ observations, previous })}`);
    const geometry = await observe(Math.max(1, Math.floor(remaining)));
    observations++;
    const elapsedMs = now() - start;
    assert(elapsedMs <= timeoutMs, `scroll geometry did not settle: ${JSON.stringify({ observations, geometry })}`);
    if (!geometry.pending && previous && !previous.pending &&
        JSON.stringify(geometry) === JSON.stringify(previous)) {
      return { geometry, observations, elapsedMs };
    }
    previous = geometry;
    await pause(Math.min(32, timeoutMs - (now() - start)));
  }
}

module.exports = { assertZoom, wheelDelta, nativePoint, readConfig, waitForNativeWindow, waitForStableGeometry };
if (require.main === module)
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
