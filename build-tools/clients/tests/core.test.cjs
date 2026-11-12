const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const corePath = path.join(__dirname, '../core.cjs');
const config = 'SITE_DOMAIN=47.96.221.94\nSITE_SCHEME=https\nSITE_PORT=8443\nCLIENT_VERSION=1.0.19\n';
test('core module exists', () => assert.ok(fs.existsSync(corePath), 'unified builder core is missing'));
const load = () => require(corePath);
test('optional public CA configuration is accepted without accepting unknown keys', () => {
  assert.equal(load().parseConfig(config + 'CLIENT_CA_FILE=../cert/ca.crt\n').values.CLIENT_CA_FILE, '../cert/ca.crt');
});
test('WiX discovery accepts portable PATH and WIX directories', () => {
  const { findWix } = load();
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-wix-test-'));
  try {
    fs.writeFileSync(path.join(dir, 'candle.exe'), '');
    assert.equal(findWix({ PATH: dir }), null);
    fs.writeFileSync(path.join(dir, 'light.exe'), '');
    assert.equal(findWix({ PATH: dir }), dir);
    assert.equal(findWix({ WIX: dir }), dir);
    fs.mkdirSync(path.join(dir, 'bin'));
    fs.renameSync(path.join(dir, 'candle.exe'), path.join(dir, 'bin/candle.exe'));
    fs.renameSync(path.join(dir, 'light.exe'), path.join(dir, 'bin/light.exe'));
    assert.equal(findWix({ WIX: dir }), path.join(dir, 'bin'));
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
test('strict config uses explicit version and full outer origin', () => {
  assert.equal(load().parseConfig(config).origin, 'https://47.96.221.94:8443');
  assert.equal(load().parseConfig(config).version, '1.0.19');
});
test('rejects missing, duplicate, extra and invalid fields', () => {
  const { parseConfig } = load();
  for (const text of [config.replace('CLIENT_VERSION=1.0.19', ''), config + 'SITE_PORT=443\n',
    config + 'SECRET=x\n', config.replace('47.96.221.94', '999.2.3.4'),
    config.replace('1.0.19', '1.0.19-rc1'), config.replace('1.0.19', '256.0.0'),
    config.replace('8443', '65536')]) assert.throws(() => parseConfig(text));
});
test('Android code is derived only from configured version using fixed decimal slots', () => {
  const { versionCode } = load();
  assert.equal(versionCode('1.0.19'), 1019);
  assert.equal(versionCode('1.1.0'), 1100);
  assert.equal(versionCode('2.0.0'), 2000);
  assert.equal(versionCode('1.0.19'), versionCode('1.0.19'));
  for (const version of ['1.10.0', '1.0.100', '0.0.0', '1.0.19-rc1', '01.0.19']) {
    assert.throws(() => versionCode(version));
  }
});
test('lock is exclusive and temporary source bytes restored after failure', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-builder-test-'));
  const file = path.join(dir, 'source'); fs.writeFileSync(file, 'original\r\n');
  const lock = path.join(dir, 'lock');
  try {
    await assert.rejects(load().withLock(lock, async () => {
      await assert.rejects(load().withLock(lock, async () => {}));
      await load().withFiles([[file, 'temporary']], async () => { throw Error('build failed'); });
    }), /build failed/);
    assert.equal(fs.readFileSync(file, 'utf8'), 'original\r\n');
    assert.equal(fs.existsSync(lock), false);
    const fresh = path.join(dir, 'new');
    await load().withFiles([[fresh, 'new']], async () => {});
    assert.equal(fs.existsSync(fresh), false);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
