// Optional browser QA: npm install playwright, then node scripts/check_browser_input.cjs.
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { chromium } = require(process.env.NEO_PLAYWRIGHT_PACKAGE || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.resolve(__dirname, '../tests/fixtures/browser_input.html')).href);
    await page.locator('#single').click();
    assert.equal(await page.locator('#singles').textContent(), '1');
    await page.locator('#double').dblclick();
    assert.equal(await page.locator('#doubles').textContent(), '1');
    await page.locator('#right').click({ button: 'right' });
    assert.equal(await page.locator('#rights').textContent(), '1');
    await page.locator('#scrollbox').hover();
    await page.mouse.wheel(0, 500);
    await page.waitForFunction(() => document.getElementById('scrollbox').scrollTop > 0);
    assert.ok((await page.locator('#wheel').textContent()).includes('down'));
    fs.mkdirSync(path.resolve(__dirname, '../tmp'), { recursive: true });
    await page.screenshot({ path: path.resolve(__dirname, '../tmp/browser-practice.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log('PASS: single click, double click, right click, wheel scrolling; no JavaScript errors.');
    await page.locator('#reset').click();
    assert.equal(await page.locator('#singles').textContent(), '0');
    assert.equal(await page.locator('#doubles').textContent(), '0');
    assert.equal(await page.locator('#rights').textContent(), '0');

    // Production classifier + controller -> browser events. This deliberately
    // does not use PyAutoGUI: all inputs stay inside this isolated browser.
    const root = path.resolve(__dirname, '..');
    const python = process.env.NEO_PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    async function gesture(name, selector) {
      const target = page.locator(selector);
      await target.scrollIntoViewIfNeeded();
      const box = await target.boundingBox();
      const result = spawnSync(python, ['-m', 'scripts.browser_gesture_scenarios'], {
        cwd: root, encoding: 'utf8',
        input: JSON.stringify({ name, target: [box.x+box.width/2,box.y+box.height/2], viewport: [1280,1000] }),
      });
      assert.equal(result.status, 0, result.stderr);
      const commands = JSON.parse(result.stdout);
      for (const command of commands) {
        const [x,y,count,button] = command.arguments;
        if (command.kind === 'move') await page.mouse.move(x,y);
        else if (command.kind === 'click') {
          if (count === 2) await page.mouse.dblclick(x,y,{button,delay:100});
          else await page.mouse.click(x,y,{button});
        } else if (command.kind === 'scroll') await page.mouse.wheel(0,-x*120);
        else if (command.kind === 'key' && x === 'playpause') await page.keyboard.press('MediaPlayPause');
        else if (command.kind === 'hotkey' && ['alt','command'].includes(x)) {
          await page.keyboard.press((x === 'alt' ? 'Alt' : 'Meta')+'+'+(y === 'left' ? 'ArrowLeft' : 'ArrowRight'));
        }
        else throw new Error('Unexpected command: '+JSON.stringify(command));
      }
      return commands;
    }
    const single = await gesture('single','#single');
    assert.equal(single.filter(c=>c.kind==='click').length,1);
    assert.ok(!single.some(c=>['key','scroll','hotkey'].includes(c.kind)));
    assert.equal(await page.locator('#singles').textContent(),'1');
    // A small target catches transition drift that the large practice cards
    // could hide. It exists only in this isolated automated test page.
    await page.evaluate(()=>{
      const target=document.createElement('button');
      target.id='tremor-target'; target.textContent='0';
      target.style.cssText='position:fixed;left:620px;top:400px;width:14px;height:14px;min-height:0;padding:0;border:0;z-index:100';
      target.addEventListener('click',()=>target.textContent=String(Number(target.textContent)+1));
      document.body.append(target);
    });
    await gesture('single_shake','#tremor-target');
    assert.equal(await page.locator('#tremor-target').textContent(),'1');
    await page.locator('#tremor-target').evaluate(el=>el.remove());
    console.log('PASS: a brief pre-click hand displacement still clicks the 14-pixel browser target exactly once.');
    await gesture('double','#double');
    assert.equal(await page.locator('#doubles').textContent(),'1');
    await gesture('right','#right');
    assert.equal(await page.locator('#rights').textContent(),'1');
    const previousScroll = await page.locator('#scrollbox').evaluate(el=>el.scrollTop);
    await gesture('scroll','#scrollbox');
    await page.waitForFunction(before=>document.getElementById('scrollbox').scrollTop>before,previousScroll);
    await gesture('playback','#playback');
    assert.ok((await page.locator('#playback').textContent()).includes('paused'));
    assert.ok((await page.locator('#playback').textContent()).endsWith('1'));
    assert.deepEqual(errors,[]);
    await page.screenshot({path:path.resolve(root,'tmp/browser-gesture-results.png'),fullPage:true});
    console.log('PASS: production gesture sequences reach browser targets: two-finger single click, explicit double/right click, palm-gated scroll, one playback command. Synthetic hands + browser input; no webcam/OS injection.');
    // Browser toolbar shortcuts are not dispatched by Playwright's page-level
    // keyboard API. Exercise the actual OS executor only when explicitly asked.
    if (process.argv.includes('--desktop-history')) {
      const desktop = await chromium.launch({channel:'chrome',headless:false});
      try {
        const tab = await desktop.newPage();
        const first = page.url();
        const second = new URL('history_next.html?step=2',first).href;
        const third = new URL('history_next.html?step=3',first).href;
        await tab.goto(first); await tab.goto(second); await tab.goto(third);
        async function nativeHistory(name,expectedURL) {
          const token='NEO-HISTORY-CHECK-'+require('node:crypto').randomUUID();
          const currentURL=tab.url();
          assert.ok([first,second,third].includes(currentURL));
          await tab.evaluate(value=>document.title=value,token);
          await tab.bringToFront();
          const generated=spawnSync(python,['-m','scripts.browser_gesture_scenarios'],{
            cwd:root,encoding:'utf8',input:JSON.stringify({name,target:[640,500],viewport:[1280,1000]})});
          assert.equal(generated.status,0,generated.stderr);
          const actions=JSON.parse(generated.stdout).filter(c=>c.kind!=='move');
          assert.equal(actions.length,1);
          assert.equal(actions[0].description,'browser '+name);
          assert.equal(tab.url(),currentURL);
          const sent=spawnSync(python,['-m','scripts.desktop_history_input'],{
            cwd:root,encoding:'utf8',input:JSON.stringify({title_token:token,command:actions[0]})});
          assert.equal(sent.status,0,sent.stderr);
          await tab.waitForURL(expectedURL,{timeout:5000});
        }
        await nativeHistory('back',second);
        await nativeHistory('back',first);
        await nativeHistory('forward',second);
        await nativeHistory('forward',third);
        console.log('PASS: real PyAutoGUI Back twice / Forward twice reached the exact Chrome history entries.');
      } finally { await desktop.close(); }
    } else console.log('SKIP: OS browser history delivery (opt in with --desktop-history on Windows).');
    if (process.argv.includes('--desktop-scroll')) {
      const desktop=await chromium.launch({channel:'chrome',headless:false});
      try {
        const tab=await desktop.newPage();
        const token='NEO-SCROLL-CHECK-'+require('node:crypto').randomUUID();
        await tab.goto('about:blank');
        await tab.setContent('<title>'+token+'</title><body style="height:6000px;background:linear-gradient(#e9f7ff,#467f90)"><h1>NEO isolated wheel delivery check</h1></body>');
        await tab.bringToFront();
        await tab.evaluate(()=>{
          window.wheelEvents=[];
          addEventListener('wheel',e=>wheelEvents.push({delta:e.deltaY,mode:e.deltaMode}),{passive:true});
        });
        const reference=spawnSync(python,['-m','scripts.desktop_scroll_input'],{
          cwd:root,encoding:'utf8',input:JSON.stringify({title_token:token,delta:-1,raw_reference:true})});
        assert.equal(reference.status,0,reference.stderr);
        await tab.waitForFunction(()=>wheelEvents.length>0);
        const rawDelta=await tab.evaluate(()=>wheelEvents[0].delta);
        for (const delta of [-1,1]) {
          const before=await tab.evaluate(()=>scrollY);
          await tab.evaluate(()=>wheelEvents=[]);
          const sent=spawnSync(python,['-m','scripts.desktop_scroll_input'],{
            cwd:root,encoding:'utf8',input:JSON.stringify({title_token:token,delta})});
          assert.equal(sent.status,0,sent.stderr);
          await tab.waitForFunction(({before,delta})=>delta<0?scrollY>before:scrollY<before,{before,delta},{timeout:5000});
          await tab.waitForFunction(()=>wheelEvents.length>0);
          const event=await tab.evaluate(()=>wheelEvents[0]);
          assert.equal(Math.sign(event.delta),-delta);
          assert.ok(Math.abs(event.delta/rawDelta)>100,'Native notch must exceed the old raw-unit pulse by approximately 120x');
          console.log(`PASS: native wheel delta ${event.delta}; old one-unit delta ${rawDelta}.`);
        }
        console.log('PASS: actual Windows native wheel input scrolls Chrome down and up with full-notch deltas.');
      } finally { await desktop.close(); }
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
