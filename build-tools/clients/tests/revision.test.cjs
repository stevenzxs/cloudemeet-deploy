const test = require('node:test');
const assert = require('node:assert/strict');
const { parseConfig, versionCode } = require('../core.cjs');
const config = 'SITE_DOMAIN=example.com\nSITE_SCHEME=https\nSITE_PORT=8443\nCLIENT_VERSION=1.0.21\n';
test('allocated display version is distinct from all platform fields', () => {
  const versions = { revision: 100, client_version: '1.0.21+r100', android_code: 1021100,
    msi_version: '1.0.121', pe_version: '1.0.121.0' };
  const parsed = parseConfig(config, { versions });
  assert.equal(parsed.version, '1.0.21+r100');
  assert.equal(parsed.msiVersion, '1.0.121');
  assert.equal(parsed.peVersion, '1.0.121.0');
  assert.equal(versionCode(parsed.version), 1021100);
  assert.throws(() => parseConfig(config, { versions: { ...versions, android_code: 1021 } }));
  assert.throws(() => parseConfig(config.replace('1.0.21', '1.0.22'), { versions }));
});
test('revision client code refuses zero, leading zeros and overflow', () => {
  assert.equal(versionCode('1.0.21+r1'), 10211);
  assert.equal(versionCode('1.0.21+r10'), 102110);
  for (const s of ['1.0.21+r0', '1.0.21+r01', '1.0.21+r1000000']) assert.throws(() => versionCode(s));
});
test('Forge adapter preserves native hooks while excluding build adapter from the shipped app', () => {
  const vm = require('node:vm');
  const { forgeWrapper } = require('../revision-config.cjs');
  const hook = () => {};
  const native = { hooks: { preMake: hook, postMake: hook }, packagerConfig: { ignore: [/native/] }, makers: [] };
  const sandbox = { module: { exports: {} }, require: file => file === 'node:path' ? require(file) : native };
  vm.runInNewContext(forgeWrapper('C:/source', { versions: { msi_version: '1.0.22', pe_version: '1.0.22.0' } }), sandbox);
  const config = sandbox.module.exports;
  assert.equal(config.hooks.preMake, hook);
  assert.equal(config.packagerConfig.appVersion, '1.0.22');
  assert.equal(config.packagerConfig.buildVersion, '1.0.22.0');
  assert.ok(config.packagerConfig.ignore.some(rule => rule.test('/cloudmeet.forge.cjs')));
});
test('Forge signs main executable before unified MSI and then signs final MSI', async () => {
  const vm = require('node:vm');
  const { forgeWrapper } = require('../revision-config.cjs');
  const calls = [];
  const config = { hooks: { postPackage: async () => calls.push('native') }, packagerConfig: { ignore: [], windowsSign: { forbidden: true } }, makers: [] };
  const results = [{ artifacts: ['C:/final.msi'] }];
  const sandbox = { module: { exports: {} }, require: file => {
    if (file === 'node:path') return require(file);
    if (file.endsWith('signing.cjs')) return { sign: file => calls.push(file.replaceAll('\\', '/')) };
    if (file.endsWith('forge.config.js')) return config;
    if (file.endsWith('unified-msi.cjs')) return { buildUnifiedMsi: async () => { calls.push('assemble'); return results; } };
    if (file.endsWith('build-openvpn-bundle.cjs')) return { verifyPayload: async () => 'vendor' };
    throw Error(file);
  } };
  vm.runInNewContext(forgeWrapper('C:/source', { versions: { msi_version: '1.0.22', pe_version: '1.0.22.0' } }), sandbox);
  await config.hooks.postPackage({}, { outputPaths: ['C:/app'] });
  await config.hooks.postMake({}, results);
  assert.equal(config.packagerConfig.windowsSign, undefined);
  assert.deepEqual(calls, ['native', 'C:/app/cloudmeet.exe', 'assemble', 'C:/final.msi']);
});
