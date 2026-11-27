const test = require('node:test');
const assert = require('node:assert/strict');
const { parseConfig, versionCode } = require('../core.cjs');
const config = 'SITE_DOMAIN=example.com\nSITE_SCHEME=https\nSITE_PORT=8443\nCLIENT_VERSION=1.0.21\n';
test('allocated display version is distinct from all platform fields', () => {
  const versions = { revision: 100, client_version: '1.0.21+r100', android_code: 1022000,
    msi_version: '1.0.1210', pe_version: '1.0.1210.0', version_formula: 2 };
  const parsed = parseConfig(config, { versions });
  assert.equal(parsed.version, '1.0.21+r100');
  assert.equal(parsed.msiVersion, '1.0.1210');
  assert.equal(parsed.peVersion, '1.0.1210.0');
  assert.equal(versionCode(parsed.version), 1022000);
  assert.throws(() => parseConfig(config, { versions: { ...versions, android_code: 1021 } }));
  assert.throws(() => parseConfig(config.replace('1.0.21', '1.0.22'), { versions }));
});
test('patch assignment occupies the band between joint revisions', () => {
  const versions = { revision: 45, patch: 1, client_version: '1.0.21+r45-patch.1',
    android_code: 1021451, msi_version: '1.0.661', pe_version: '1.0.661.0', version_formula: 2 };
  const parsed = parseConfig(config, { versions });
  assert.equal(parsed.version, '1.0.21+r45-patch.1');
  assert.equal(parsed.msiVersion, '1.0.661');
  assert.equal(versionCode(parsed.version), 1021451);
  assert.throws(() => parseConfig(config, { versions: { ...versions, android_code: 102145 } }));
  assert.throws(() => parseConfig(config, { versions: { ...versions, patch: 0 } }));
  assert.throws(() => parseConfig(config, { versions: { ...versions, patch: 10 } }));
  assert.throws(() => parseConfig(config, { versions: { ...versions, msi_version: '1.0.660' } }));
});
test('revision client code refuses zero, leading zeros and overflow', () => {
  assert.equal(versionCode('1.0.21+r1'), 1021010);
  assert.equal(versionCode('1.0.21+r10'), 1021100);
  for (const s of ['1.0.21+r0', '1.0.21+r01', '1.0.21+r300000000']) assert.throws(() => versionCode(s));
});
test('Forge adapter retires vendor payload verification and excludes build adapter from the shipped app', () => {
  const vm = require('node:vm');
  const { forgeWrapper } = require('../revision-config.cjs');
  const hook = () => {};
  const native = { hooks: { preMake: hook, postMake: hook }, packagerConfig: { ignore: [/native/] }, makers: [] };
  const sandbox = { module: { exports: {} }, require: file => file === 'node:path' ? require(file) : native };
  vm.runInNewContext(forgeWrapper('C:/source', { versions: { msi_version: '1.0.22', pe_version: '1.0.22.0' } }), sandbox);
  const config = sandbox.module.exports;
  // OpenVPN removed from the package (user 2026-11-20): preMake vendor check is a no-op, not the native hook.
  assert.notEqual(config.hooks.preMake, hook);
  assert.equal(typeof config.hooks.preMake, 'function');
  assert.equal(config.packagerConfig.appVersion, '1.0.22');
  assert.equal(config.packagerConfig.buildVersion, '1.0.22.0');
  assert.ok(config.packagerConfig.ignore.some(rule => rule.test('/forge.config.cloudmeet-base.cjs')));
});
test('Forge removes Windows signing hooks and returns maker-wix MSI unchanged', async () => {
  const vm = require('node:vm');
  const { forgeWrapper } = require('../revision-config.cjs');
  const calls = [];
  const config = { hooks: { postPackage: async () => calls.push('native') }, packagerConfig: { ignore: [], windowsSign: { forbidden: true } }, makers: [] };
  const results = [{ artifacts: ['C:/final.msi'] }];
  const required = [];
  const sandbox = { module: { exports: {} }, require: file => {
    required.push(file.replaceAll('\\', '/'));
    if (file === 'node:path') return require(file);
    if (file.endsWith('signing.cjs')) return { sign: file => calls.push(file.replaceAll('\\', '/')) };
    if (file.endsWith('forge.config.cloudmeet-base.cjs')) return config;
    if (file.endsWith('unified-msi.cjs') || file.endsWith('build-openvpn-bundle.cjs')) throw Error('OpenVPN assembly must not be invoked');
    throw Error(file);
  } };
  vm.runInNewContext(forgeWrapper('C:/source', { versions: { msi_version: '1.0.22', pe_version: '1.0.22.0' } }), sandbox);
  // electron-forge 7 resolves forge.config.js before the package.json config.forge
  // path string; the adapter must load the preserved base config, never itself.
  assert.ok(required.some(file => file.endsWith('/forge.config.cloudmeet-base.cjs')));
  assert.ok(!required.some(file => file.endsWith('/forge.config.js')));
  assert.equal(config.hooks.postPackage, undefined);
  const output = await config.hooks.postMake({}, results);
  assert.equal(config.packagerConfig.windowsSign, undefined);
  assert.deepEqual(calls, []);
  assert.ok(!required.some(file => file.endsWith('/signing.cjs')));
  assert.equal(output, results);
});
test('Forge pins the actual WiX ProductVersion after its four-field conversion', async () => {
  const vm = require('node:vm');
  const { forgeWrapper } = require('../revision-config.cjs');
  let calls = 0;
  const native = { hooks: {}, packagerConfig: { ignore: [] }, makers: [
    { name: '@electron-forge/maker-wix', config: { beforeCreate: async creator => {
      calls++; creator.windowsCompliantVersion = '9.9.9.9';
    } } },
    { name: '@electron-forge/maker-zip', config: { untouched: true } },
  ] };
  const otherMaker = native.makers[1];
  const sandbox = { module: { exports: {} }, require: file => file === 'node:path' ? require(file) : native };
  vm.runInNewContext(forgeWrapper('C:/source', { versions: {
    msi_version: '1.0.33', pe_version: '1.0.33.0', client_version: '1.0.21+r12',
  } }), sandbox);
  const maker = sandbox.module.exports.makers[0];
  const creator = { semanticVersion: maker.config.version, windowsCompliantVersion: '1.0.33.0' };
  await maker.config.beforeCreate(creator);
  assert.equal(calls, 1);
  assert.equal(creator.windowsCompliantVersion, '1.0.33');
  assert.equal(creator.semanticVersion, '1.0.33');
  assert.equal(native.makers[1], otherMaker);
});
test('Forge supplies the WiX version hook when the source has no beforeCreate', async () => {
  const vm = require('node:vm');
  const { forgeWrapper } = require('../revision-config.cjs');
  const native = { hooks: {}, packagerConfig: { ignore: [] }, makers: [
    { name: '@electron-forge/maker-wix', config: {} },
  ] };
  const sandbox = { module: { exports: {} }, require: file => file === 'node:path' ? require(file) : native };
  vm.runInNewContext(forgeWrapper('C:/source', { versions: {
    msi_version: '1.0.65535', pe_version: '1.0.65535.0',
  } }), sandbox);
  const creator = { windowsCompliantVersion: '1.0.65535.0' };
  await sandbox.module.exports.makers[0].config.beforeCreate(creator);
  assert.equal(creator.windowsCompliantVersion, '1.0.65535');
});
