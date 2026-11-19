// probe-candidates.js — 抓取 JVB 下发的 ICE 候选，检测“只通告容器内网地址”类故障
// 用法: node probe-candidates.js
// 环境变量:
//   TARGET     实例入口, 默认 https://10.1.2.28:8443
//   ROOM       房间名, 默认 probe-cand-<时间戳>
//   CHROME_PATH 浏览器可执行文件路径(可选, 自动探测 playwright 缓存)
// 判定: 候选中出现 TARGET 主机地址 => PASS; 仅出现不可达内网地址 => FAIL
const { chromium } = require('playwright-core');
const { findChrome } = require('./chrome-path');

const TARGET = process.env.TARGET || 'https://10.1.2.28:8443';
const ROOM = process.env.ROOM || ('probe-cand-' + Date.now());
const targetHost = new URL(TARGET).hostname;

async function join(browser, name, found) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, permissions: ['camera', 'microphone'] });
  const page = await context.newPage();
  page.on('websocket', (ws) => {
    ws.on('framereceived', (data) => {
      const p = typeof data.payload === 'string' ? data.payload : '';
      if (!p.includes('candidate')) return;
      (p.match(/<candidate[^>]*\/?>(?:<\/candidate>)?/g) || []).forEach(m => {
        const attrs = {};
        ['protocol', 'ip', 'port', 'type', 'rel-addr'].forEach(k => {
          const mm = m.match(new RegExp(k + "='([^']*)'")) || m.match(new RegExp(k + '="([^"]*)"'));
          if (mm) attrs[k] = mm[1];
        });
        if (attrs.ip) found.add(JSON.stringify(attrs));
      });
    });
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
  const found = new Set();
  const a = await join(browser, 'cand-A', found);
  await a.waitForTimeout(6000);
  const b = await join(browser, 'cand-B', found);
  await b.waitForTimeout(25000);
  await browser.close();

  const candidates = [...found].map(s => JSON.parse(s));
  console.log(`TARGET=${TARGET} ROOM=${ROOM}`);
  console.log('=== JVB remote candidates ===');
  candidates.forEach(c => console.log(' ', JSON.stringify(c)));
  const hit = candidates.filter(c => c.ip === targetHost);
  if (hit.length > 0) {
    console.log(`VERDICT: PASS (${hit.length} candidate(s) advertise reachable host ${targetHost})`);
    process.exit(0);
  }
  console.log(`VERDICT: FAIL (no candidate matches ${targetHost}; JVB likely advertises an unreachable container/private address — check JVB_ADVERTISE_IPS / MEDIA_HOST)`);
  process.exit(1);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
