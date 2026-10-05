/** Isolated UI-study check. No API, Runtime, accounts, or credentials. */
import { createRequire } from 'node:module';
const { chromium } = createRequire(new URL('../../apps/web/package.json', import.meta.url))('@playwright/test');
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root = path.dirname(fileURLToPath(import.meta.url));
const output = path.join(root, 'screenshots');
await mkdir(output, { recursive: true });
const html = await readFile(path.join(root, 'index.html'));
const server = createServer((req, res) => { res.writeHead(200, {'Content-Type':'text/html; charset=utf-8'}); res.end(html); });
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}/`;
let browser;
const results = [], errors = [], requests = [];
try {
  browser = await chromium.launch(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {});
  const page = await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
  page.on('pageerror', e=>errors.push(e.message));
  page.on('request', req=>requests.push(req.url()));
  for (const route of ['overview','workspace']) {
    await page.goto(`${url}#${route}`);
    await page.screenshot({path:path.join(output,`desktop-${route}.png`),fullPage:true});
  }
  const routes = ['overview','attention','projects','project','workspace','changes','files','artifacts','approval','agents','settings','onboarding','system','map'];
  for(const width of [1440,1024,768,390,360]) {
    await page.setViewportSize({width,height:width<800?844:1000});
    for(const route of routes) {
      await page.goto(`${url}#${route}`);
      await page.getByRole('heading',{level:1}).waitFor();
      const size=await page.evaluate(()=>({doc:document.documentElement.scrollWidth,view:innerWidth}));
      assert(size.doc<=size.view+1,`Horizontal page overflow: ${route} at ${width}, ${JSON.stringify(size)}`);
      results.push({check:'route-and-overflow',route,width,pass:true});
    }
  }
  await page.setViewportSize({width:1440,height:1000});
  for(const route of ['overview','workspace','changes','project','approval','settings','onboarding']){
    await page.goto(`${url}#${route}`);
    await page.screenshot({path:path.join(output,`desktop-${route}.png`),fullPage:true});
  }
  await page.goto(`${url}#workspace`);
  await page.getByRole('button',{name:'切换深色',exact:true}).click();
  await page.screenshot({path:path.join(output,'desktop-workspace-dark.png'),fullPage:true});
  await page.getByRole('button',{name:'停止',exact:true}).click();
  assert(await page.locator('dialog').evaluate(el=>el.open));
  await page.keyboard.press('Escape');
  assert(!await page.locator('dialog').evaluate(el=>el.open));
  assert.equal(await page.evaluate(()=>document.activeElement.textContent.trim()),'停止');
  results.push({check:'stop-dialog-escape-focus-return',pass:true});
  await page.keyboard.press('Control+k');
  await page.locator('#command-input').fill('设置');
  await page.keyboard.press('Enter');
  await page.waitForURL('**/#settings');
  await page.goBack();
  await page.waitForURL('**/#workspace');
  results.push({check:'command-search-and-browser-back',pass:true});
  await page.getByLabel('补充下一步要求（仅设计演示）').fill('Long text '.repeat(100)+'<img src=x onerror=alert(1)>');
  await page.getByLabel('发送示例消息').click();
  assert.equal(await page.locator('.message.user').last().locator('img').count(),0);
  results.push({check:'long-input-inert-text',pass:true});
  await page.goto(`${url}#projects`);
  await page.getByRole('textbox',{name:'搜索项目',exact:true}).fill('not-present');
  assert.equal(await page.locator('[data-project-name]:visible').count(),0);
  await page.getByRole('textbox',{name:'搜索项目',exact:true}).fill('AgentBox');
  assert.equal(await page.locator('[data-project-name]:visible').count(),1);
  results.push({check:'project-search',pass:true});
  await page.getByRole('button',{name:'添加项目',exact:true}).click();
  await page.getByRole('button',{name:'取消',exact:true}).click();
  assert(!await page.locator('dialog').evaluate(el=>el.open));
  results.push({check:'new-project-cancel',pass:true});
  for(const state of ['loading','empty','error','permission','stale']){
    await page.goto(`${url}#overview`);
    await page.getByLabel('切换示例数据状态').selectOption(state);
    assert.equal(await page.locator('.work-row').count(),0);
    assert.equal(await page.locator('[data-project-name]').count(),0);
    if(state==='stale')await page.screenshot({path:path.join(output,'desktop-stale.png'),fullPage:true});
    results.push({check:'state-clears-sample-rows',state,pass:true});
  }
  await page.goto(`${url}#changes`);
  await page.getByRole('button',{name:'统一视图',exact:true}).click();
  assert(await page.locator('.diff').innerText().then(t=>t.includes('diff --git')));
  await page.getByRole('button',{name:'完整原文',exact:true}).click();
  assert.equal(await page.locator('.code-row').count(),18);
  results.push({check:'unified-raw-roundtrip',pass:true});
  await page.setViewportSize({width:390,height:844});
  await page.goto(`${url}#overview`);
  await page.reload();
  for(const route of ['overview','workspace','changes','approval','onboarding']){
    await page.goto(`${url}#${route}`);
    await page.screenshot({path:path.join(output,`phone-${route}.png`),fullPage:true});
    if(route==='workspace'){
      await page.getByRole('button',{name:'查看变化 / 文件',exact:true}).click();
      assert(await page.locator('.inspection').isVisible());
      assert(!await page.locator('.conversation').isVisible());
      await page.screenshot({path:path.join(output,'phone-workspace-inspection.png'),fullPage:true});
      await page.getByRole('button',{name:'返回对话',exact:true}).click();
      assert(await page.locator('.conversation').isVisible());
      results.push({check:'mobile-pane-switch',pass:true});
      await page.getByLabel('补充下一步要求（仅设计演示）').focus();
      await page.setViewportSize({width:390,height:500});
      assert(await page.getByLabel('发送示例消息').isVisible());
      await page.screenshot({path:path.join(output,'phone-keyboard-viewport.png'),fullPage:true});
      await page.setViewportSize({width:390,height:844});
      results.push({check:'reduced-mobile-viewport-composer',pass:true,note:'Viewport simulation, not a real software keyboard'});
    }
  }
  await page.getByRole('button',{name:'打开导航',exact:true}).click();
  assert(await page.locator('.main').evaluate(el=>el.inert));
  await page.keyboard.press('Escape');
  assert(!await page.locator('.main').evaluate(el=>el.inert));
  assert.equal(await page.evaluate(()=>document.activeElement.getAttribute('aria-label')),'打开导航');
  results.push({check:'mobile-drawer-escape-and-focus',pass:true});
  assert.equal(errors.length,0,JSON.stringify(errors));
  assert(requests.every(u=>u.startsWith(url)),'Unexpected external request');
  const report={prototype:true,baseline:'a1cab129f18ede5b982b6ab53d037c51771b4dea',checks:results.length,results,errors,externalRequests:requests.filter(u=>!u.startsWith(url)),notes:['No production app or backend exercised','No real host, credentials, API, CLI or authority claims','Screenshots use synthetic design content','Chinese-only prototype; English adaptation remains a migration requirement']};
  await writeFile(path.join(root,'verification.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({pass:true,checks:results.length,errors:errors.length}));
} finally { await browser?.close();server.close(); }
