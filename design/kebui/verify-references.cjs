// Static, offline board verification. No upstream website is opened by this test.
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
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
    assert.equal(await page.locator("article[data-reference]").count(), 7);
    assert.equal(await page.locator("img,iframe,script,form").count(), 0);
    const names = await page
      .locator("article[data-reference]")
      .evaluateAll((els) => els.map((el) => el.dataset.reference));
    assert.deepEqual(names, [
      "Cromma",
      "Cindy",
      "Paseo",
      "HAPI",
      "CloudCLI",
      "Yep Anywhere",
      "Kebui",
    ]);
    const cromma = page.locator('article[data-reference="Cromma"]');
    const crommaText = await cromma.innerText();
    for (const text of [
      "仅据原作者文字记录",
      "未重新查看原图",
      "全部 · 未读 · AI · 朋友 · 群组",
      "搜索 · 新建",
      "示例会话 A",
      "示例会话 B",
      "Project A · Codex · 执行中",
      "Project B · Claude Code · 待确认",
      "未读不等于待确认",
      "不采用",
      "纯合成示意",
      "私人头像和消息",
    ])
      assert(crommaText.includes(text), `Cromma content missing: ${text}`);
    assert.equal(await cromma.locator(".schematic").count(), 2);
    assert.equal(await cromma.locator("button,input,[role=button]").count(), 0);
    assert.equal(
      await cromma
        .getByRole("link", { name: "查看既有文字来源 →" })
        .getAttribute("href"),
      "../../docs/project/KEBUI_UI_DESIGN.md",
    );
    const out = path.join(__dirname, "evidence");
    fs.mkdirSync(out, { recursive: true });
    for (const width of [360, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: width < 768 ? 844 : 1000 });
      assert(
        await cromma.evaluate((card) => {
          const rect = card.getBoundingClientRect();
          const range = document.createRange();
          const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
          let node;
          while ((node = walker.nextNode())) {
            if (!node.textContent.trim()) continue;
            range.selectNodeContents(node);
            const panel = node.parentElement.closest(".schematic");
            const boxes = panel
              ? [rect, panel.getBoundingClientRect()]
              : [rect];
            for (const line of range.getClientRects())
              for (const box of boxes)
                if (
                  line.left < box.left ||
                  line.right > box.right ||
                  line.top < box.top ||
                  line.bottom > box.bottom
                )
                  return false;
          }
          return true;
        }),
        `Cromma text bounds ${width}`,
      );
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
      boardSha256: createHash("sha256")
        .update(fs.readFileSync(path.join(__dirname, "reference-board.html")))
        .digest("hex"),
      cards: names,
      cromma: {
        provenance: "existing-author-text-only",
        source: "docs/project/KEBUI_UI_DESIGN.md R1 (2026-10-07)",
        originalImageReviewed: false,
        syntheticPanels: 2,
        contentAndTextBounds: "passed",
      },
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
