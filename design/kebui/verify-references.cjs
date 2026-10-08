// Static, offline board verification. No upstream website is opened by this test.
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const requests = [];
    const errors = [];
    page.on("request", (r) => {
      if (!r.url().startsWith("file:")) requests.push(r.url());
    });
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(
      pathToFileURL(path.join(__dirname, "reference-board.html")).href,
    );
    assert.equal(await page.title(), "Kebui · Evidence-led reference board");
    assert.equal(await page.locator("article[data-reference]").count(), 6);
    assert.equal(await page.locator("img,iframe,script,form").count(), 0);
    const names = await page
      .locator("article[data-reference]")
      .evaluateAll((els) => els.map((el) => el.dataset.reference));
    assert.deepEqual(names, [
      "Cindy",
      "Paseo",
      "HAPI",
      "CloudCLI",
      "Yep Anywhere",
      "Kebui",
    ]);
    const out = path.join(__dirname, "evidence");
    fs.mkdirSync(out, { recursive: true });
    for (const width of [360, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: width < 768 ? 844 : 1000 });
      for (const card of await page.locator("article").all())
        assert(await card.isVisible());
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `overflow ${width}`,
      );
      if ([390, 1440].includes(width))
        await page.screenshot({
          path: path.join(out, `reference-board-${width}.png`),
          fullPage: true,
        });
    }
    await page
      .getByRole("link", { name: "完整来源、哈希与观察矩阵 →" })
      .focus();
    assert.equal(
      await page.evaluate(() => document.activeElement.getAttribute("href")),
      "PUBLIC_VISUAL_EVIDENCE.md",
    );
    assert.deepEqual(requests, []);
    assert.deepEqual(errors, []);
    const report = {
      date: new Date().toISOString(),
      browser: await browser.version(),
      source: process.env.GITHUB_SHA || "local",
      cards: names,
      widths: [360, 390, 768, 1024, 1440],
      screenshots: 2,
      requests,
      errors,
    };
    fs.writeFileSync(
      path.join(out, "reference-verification.json"),
      JSON.stringify(report, null, 2),
    );
    console.log(JSON.stringify(report, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
