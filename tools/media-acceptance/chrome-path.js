// chrome-path.js — 定位本机 Chromium 可执行文件
const fs = require('fs');
const path = require('path');

function findChrome() {
  if (process.env.CHROME_PATH && fs.existsSync(process.env.CHROME_PATH)) return process.env.CHROME_PATH;
  const base = path.join(process.env.LOCALAPPDATA || '', 'ms-playwright');
  const candidates = [];
  try {
    for (const dir of fs.readdirSync(base).filter(d => d.startsWith('chromium-')).sort().reverse()) {
      candidates.push(path.join(base, dir, 'chrome-win64', 'chrome.exe'));
      candidates.push(path.join(base, dir, 'chrome-win', 'chrome.exe'));
    }
  } catch (_) {}
  candidates.push(
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'
  );
  for (const c of candidates) if (fs.existsSync(c)) return c;
  throw new Error('Chromium not found; set CHROME_PATH');
}

module.exports = { findChrome };
