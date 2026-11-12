const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');

function findWix(env = process.env) {
  const pathKey = Object.keys(env).find(key => key.toLowerCase() === 'path');
  const candidates = [
    ...(env.WIX ? [path.join(env.WIX, 'bin'), env.WIX] : []),
    ...(env[pathKey] || '').split(path.delimiter).filter(Boolean).map(dir => dir.replace(/^"|"$/g, '')),
    ...['v3.14', 'v3.11'].map(version => path.join(env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', `WiX Toolset ${version}`, 'bin'))
  ];
  return candidates.find(dir => ['candle.exe', 'light.exe'].every(tool => {
    try { return fs.statSync(path.join(dir, tool)).isFile(); } catch { return false; }
  })) || null;
}

function parseConfig(text) {
  const keys = ['SITE_DOMAIN', 'SITE_SCHEME', 'SITE_PORT', 'CLIENT_VERSION'];
  const values = {};
  for (const line of text.replace(/^\uFEFF/, '').split(/\r?\n/)) {
    if (!line.trim() || line.trim().startsWith('#')) continue;
    const match = line.match(/^\s*([A-Z_]+)\s*=\s*([^#]*?)\s*(?:#.*)?$/);
    if (!match || ![...keys, 'CLIENT_CA_FILE'].includes(match[1]) || Object.hasOwn(values, match[1])) throw Error('Unknown or duplicate client configuration');
    values[match[1]] = match[2];
  }
  if (keys.some(key => !values[key])) throw Error('Missing client configuration');
  const host = values.SITE_DOMAIN;
  const dns = host.length <= 253 && /^(?:[a-z\d](?:[a-z\d-]{0,61}[a-z\d])?\.)+[a-z]{2,63}$/i.test(host);
  if (net.isIP(host) !== 4 && !dns) throw Error('SITE_DOMAIN must be a DNS name or IPv4 address');
  if (!['https', 'http'].includes(values.SITE_SCHEME)) throw Error('Invalid SITE_SCHEME');
  if (!/^\d+$/.test(values.SITE_PORT) || +values.SITE_PORT < 1 || +values.SITE_PORT > 65535) throw Error('Invalid SITE_PORT');
  const version = values.CLIENT_VERSION;
  if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)) throw Error('CLIENT_VERSION must be numeric major.minor.patch');
  const parts = version.split('.').map(Number);
  if (parts[0] > 255 || parts[1] > 255 || parts[2] > 65535) throw Error('CLIENT_VERSION exceeds MSI limits');
  const origin = `${values.SITE_SCHEME}://${host}:${+values.SITE_PORT}`;
  return { values, origin, desktopUrl: `${origin}/cm/desktop`, version };
}

function versionCode(version) {
  if (!/^(0|[1-9]\d*)\.[0-9]\.(0|[1-9]\d?)$/.test(version)) {
    throw Error('Android version requires major.minor.patch with minor 0..9 and patch 0..99');
  }
  const [major, minor, patch] = version.split('.').map(Number);
  const value = major * 1000 + minor * 100 + patch;
  if (!Number.isSafeInteger(value) || value < 1 || value > 2100000000) throw Error('Invalid Android versionCode');
  return value;
}

async function withLock(file, callback) {
  const descriptor = fs.openSync(file, 'wx');
  try {
    fs.writeFileSync(descriptor, JSON.stringify({ pid: process.pid, started: new Date().toISOString() }));
    return await callback();
  } finally { fs.closeSync(descriptor); fs.unlinkSync(file); }
}

async function withFiles(changes, callback) {
  const originals = [];
  try {
    for (const [file, content] of changes) {
      originals.push([file, fs.existsSync(file) ? fs.readFileSync(file) : null]);
      fs.writeFileSync(file, content);
    }
    return await callback();
  } finally {
    for (const [file, bytes] of originals.reverse()) {
      if (bytes === null) { if (fs.existsSync(file)) fs.unlinkSync(file); }
      else fs.writeFileSync(file, bytes);
    }
  }
}

module.exports = { parseConfig, versionCode, withLock, withFiles, findWix };
