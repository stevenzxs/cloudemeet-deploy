// probe-media.js — 双人假设备入会，实测 JVB 媒体连通性与会议稳定性
// 用法: node probe-media.js
// 环境变量:
//   TARGET     实例入口, 默认 https://10.1.2.28:8443
//   ROOM       房间名, 默认 probe-media-<时间戳>
//   DURATION   观察秒数, 默认 120
//   CHROME_PATH 浏览器可执行文件路径(可选)
// 判定: 两端 ICE connected 且全程无 iceFailed/强制刷新 => PASS; 否则 FAIL
const { chromium } = require('playwright-core');
const { findChrome } = require('./chrome-path');

const TARGET = process.env.TARGET || 'https://10.1.2.28:8443';
const ROOM = process.env.ROOM || ('probe-media-' + Date.now());
const DURATION = parseInt(process.env.DURATION || '120', 10);

const state = {
  iceConnected: { A: false, B: false },
  iceFailed: 0,
  reloads: 0,
  errors: [],
};

async function join(browser, name) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, permissions: ['camera', 'microphone'] });
  const page = await context.newPage();
  page.on('console', (msg) => {
    const t = msg.text();
    if (/ICE connected JVB/.test(t)) state.iceConnected[name === 'probe-A' ? 'A' : 'B'] = true;
    if (/conference\.iceFailed|force reloading the conference/i.test(t)) {
      state.iceFailed++;
      state.errors.push(`[${name}] ${t.slice(0, 200)}`);
    }
    if (/ICE disconnected JVB/.test(t)) {
      state.errors.push(`[${name}] ${t.slice(0, 160)}`);
    }
  });
  page.on('pageerror', (e) => {
    if (/iceFailed|conference/i.test(String(e))) state.errors.push(`[${name}][pageerror] ${String(e).slice(0, 200)}`);
  });
  const url = `${TARGET}/${ROOM}#config.prejoinConfig.enabled=false&config.startWithAudioMuted=false&config.startWithVideoMuted=false&userInfo.displayName=%22${name}%22`;
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
  return page;
}

(async () => {
  const browser = await chromium.launch({
    executablePath: findChrome(),
    headless: true,
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--mute-audio', '--ignore-certificate-errors'],
  });
  const a = await join(browser, 'probe-A');
  await a.waitForTimeout(6000);
  const b = await join(browser, 'probe-B');

  const start = Date.now();
  let lastUrl = { A: null, B: null };
  while ((Date.now() - start) / 1000 < DURATION) {
    await new Promise(r => setTimeout(r, 15000));
    const t = Math.round((Date.now() - start) / 1000);
    for (const [key, p] of [['A', a], ['B', b]]) {
      try {
        const st = await p.evaluate(() => ({
          url: location.href,
          joined: window.APP && APP.conference ? APP.conference.isJoined() : false,
          members: window.APP && APP.conference ? APP.conference.membersCount : 0,
        }));
        if (lastUrl[key] && lastUrl[key] !== st.url) state.reloads++;
        lastUrl[key] = st.url;
        console.log(`[t=${t}s] ${key}: joined=${st.joined} members=${st.members} ice=${state.iceConnected[key]}`);
      } catch (e) { console.log(`[t=${t}s] ${key}: eval error ${e.message}`); }
    }
  }
  await browser.close();

  console.log('=== summary ===');
  console.log(`ICE connected: A=${state.iceConnected.A} B=${state.iceConnected.B}`);
  console.log(`iceFailed events: ${state.iceFailed}, page reloads: ${state.reloads}`);
  if (state.errors.length) {
    console.log('--- notable events ---');
    [...new Set(state.errors)].slice(0, 20).forEach(e => console.log(' ', e));
  }
  const pass = state.iceConnected.A && state.iceConnected.B && state.iceFailed === 0 && state.reloads === 0;
  console.log(pass ? 'VERDICT: PASS (media path to JVB healthy, conference stable)' : 'VERDICT: FAIL (media path broken or conference unstable — check JVB advertise/UDP reachability)');
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
