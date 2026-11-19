// probe-join.js — 经 /cm/meeting/<room> 完整用户路径入会(填昵称+点加入), 观察应用层稳定性
// 用法: node probe-join.js
// 环境变量:
//   TARGET     实例入口, 默认 https://10.1.2.28:8443
//   ROOM       房间号, 默认随机9位
//   NICK       昵称, 默认 probe-bot
//   DURATION   观察秒数, 默认 90
//   CHROME_PATH 浏览器可执行文件路径(可选)
// 判定: Jitsi iframe 成功嵌入且全程稳定不消失 => PASS
const { chromium } = require('playwright-core');
const { findChrome } = require('./chrome-path');

const TARGET = process.env.TARGET || 'https://10.1.2.28:8443';
const ROOM = process.env.ROOM || String(Math.floor(100000000 + Math.random() * 900000000));
const NICK = process.env.NICK || 'probe-bot';
const DURATION = parseInt(process.env.DURATION || '90', 10);

(async () => {
  const browser = await chromium.launch({
    executablePath: findChrome(),
    headless: true,
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--mute-audio', '--ignore-certificate-errors'],
  });
  const context = await browser.newContext({ ignoreHTTPSErrors: true, permissions: ['camera', 'microphone'] });
  const page = await context.newPage();

  const events = [];
  page.on('framedetached', (f) => events.push(`iframe DETACHED: ${f.url().slice(0, 120)}`));
  page.on('pageerror', (e) => events.push(`pageerror: ${String(e).slice(0, 200)}`));
  page.on('response', (res) => {
    if (res.status() >= 400 && !/\.(png|css|woff)/.test(res.url())) {
      events.push(`HTTP ${res.status()} ${res.request().method()} ${res.url().slice(0, 140)}`);
    }
  });

  const meetingUrl = `${TARGET}/cm/meeting/${ROOM}`;
  console.log(`open ${meetingUrl}`);
  await page.goto(meetingUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(6000);

  const nick = await page.$('input[placeholder*="昵称"]');
  if (nick) { await nick.fill(NICK); console.log('nickname filled'); }
  const btn = await page.$('button:has-text("加入会议")');
  if (btn) { await btn.click(); console.log('clicked join'); }

  let iframeSeen = false;
  const start = Date.now();
  while ((Date.now() - start) / 1000 < DURATION) {
    await page.waitForTimeout(15000);
    const t = Math.round((Date.now() - start) / 1000);
    const frames = await page.evaluate(() => Array.from(document.querySelectorAll('iframe')).map(f => f.src));
    const jitsiFrame = frames.find(u => u.includes(`/${ROOM}?`) || u.includes(`/${ROOM}#`));
    if (jitsiFrame) iframeSeen = true;
    console.log(`[t=${t}s] jitsi iframe: ${jitsiFrame ? 'present' : 'MISSING'}`);
  }
  await browser.close();

  if (events.length) {
    console.log('--- events ---');
    events.forEach(e => console.log(' ', e));
  }
  const pass = iframeSeen && !events.some(e => e.startsWith('iframe DETACHED'));
  console.log(pass ? 'VERDICT: PASS (app join flow embeds Jitsi and stays stable)' : 'VERDICT: FAIL (join flow stuck or iframe dropped)');
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
