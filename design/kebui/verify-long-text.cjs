// Bounded U1 synthetic content pressure; not real-device or 200% qualification.
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

(async () => {
  const out = path.join(__dirname, 'evidence');
  fs.mkdirSync(out, { recursive: true });
  const report = { source: execFileSync('git', ['rev-parse', 'HEAD'], {cwd: __dirname, encoding:'utf8'}).trim(), scope: 'Synthetic long text at 360/390 CSS pixels, Chinese/English, light/dark. Project state and error text are explicit injected fixtures; message submission and retry use actual UI.', cases: [], errors: [], externalRequests: [] };
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {}) });
  report.browser = browser.version();
  try {
    for (const width of [360,390]) for (const lang of ['zh','en']) for (const theme of ['light','dark']) {
      const page = await browser.newPage({ viewport: {width,height:844} });
      page.on('pageerror', e => report.errors.push(String(e)));
      page.on('request', r => {if (!r.url().startsWith('file:')) report.externalRequests.push(r.url());});
      const label = `${width}-${lang}-${theme}`;
      await page.goto('file://' + path.join(__dirname, 'index.html'));
      const project = (lang === 'zh' ? '跨区域个人研究项目与长名称边界' : 'CrossRegionResearchProjectWithoutSpaces').repeat(8);
      const message = (lang === 'zh' ? '这是合成长消息，检查完整换行与操作可达性。' : 'Synthetic long message checks wrapping and reachable actions. ').repeat(60) + ' END_MESSAGE';
      const error = (lang === 'zh' ? '合成长错误说明：请保留请求并人工重试，不自动发送。' : 'Synthetic long error: retain the request and retry explicitly, never resend automatically. ').repeat(20) + ' END_ERROR';
      await page.evaluate(({lang,theme,project}) => {state.lang=lang;state.project=project;state.route='work';state.scenario='failure';document.documentElement.dataset.theme=theme;render();}, {lang,theme,project});
      await page.locator('#draft').fill(message);
      await page.locator('#composer button[type=submit]').click();
      assert.equal(await page.evaluate(()=>state.phase),'failed');
      const id = await page.evaluate(()=>state.requestId);
      await page.locator('.banner.error p').evaluate((el,text)=>{el.textContent=text;},error);
      assert.equal(await page.locator('.message.user p').textContent(),message);
      assert.equal(await page.locator('#draft').inputValue(),message);
      const geometry = await page.evaluate(() => {
        const selectors=['.message.user p','.banner.error p','#composer label','.timeline li p','.grid > section > .row strong'];
        const targets=selectors.flatMap(s=>[...document.querySelectorAll(s)].map(el=>{
          const r=el.getBoundingClientRect(), style=getComputedStyle(el), range=document.createRange();range.selectNodeContents(el);
          const lines=[...range.getClientRects()].filter(x=>x.width>0&&x.height>0);
          return {selector:s,textLength:el.textContent.length,left:r.left,right:r.right,scrollWidth:el.scrollWidth,clientWidth:el.clientWidth,overflowX:style.overflowX,lines:lines.length,inlineWithinViewport:lines.every(x=>x.left>=-1&&x.right<=innerWidth+1)};
        }));
        return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,targets};
      });
      await page.screenshot({path:path.join(out,`long-text-${label}-failed.png`),fullPage:true});
      report.cases.push({label,projectLength:project.length,messageLength:message.length,errorLength:error.length,geometry,outcome:'pending'});
      assert(geometry.documentWidth<=width+1,`${label}: document horizontal overflow ${geometry.documentWidth}`);
      assert(geometry.targets.length>=5,`${label}: missing long-text targets`);
      for(const target of geometry.targets) assert(target.inlineWithinViewport && !['hidden','clip'].includes(target.overflowX),`${label}: clipped or overflowing ${target.selector}`);
      await page.locator('[data-action="retry"]').click();
      assert.equal(await page.evaluate(()=>state.phase),'accepted');
      assert.equal(await page.evaluate(()=>state.requestId),id);
      await page.locator('[data-action="disconnect"]').click();
      assert.equal(await page.evaluate(()=>state.phase),'unknown');
      assert.equal(await page.evaluate(()=>state.requestId),id);
      await page.screenshot({path:path.join(out,`long-text-${label}-recovery.png`),fullPage:true});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${label}: recovery horizontal overflow`);
      report.cases.at(-1).outcome='passed';
      await page.close();
    }
    assert.equal(report.errors.length,0);assert.equal(report.externalRequests.length,0);
  } finally {
    fs.writeFileSync(path.join(out,'long-text-verification.json'),JSON.stringify(report,null,2)+'\n');
    await browser.close();
  }
  console.log(JSON.stringify({cases:report.cases.length,errors:report.errors,externalRequests:report.externalRequests}));
})().catch(e=>{console.error(e);process.exitCode=1;});
