const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { argumentsFor, collect, androidTasks } = require('../build-clients.cjs');
test('Android always repackages APK while retaining dependency compilation cache', () => {
  assert.deepEqual(androidTasks(), [':app:packageRelease', '--rerun', ':app:assembleRelease']);
});
const { parseConfig } = require('../core.cjs');
test('Android directories reflect actual ABI sets and exclude x86', () => {
  const { androidLayout } = require('../build-clients.cjs');
  assert.equal(androidLayout(['arm64-v8a']).architecture, 'arm64-v8a');
  assert.deepEqual(androidLayout(['x86_64', 'arm64-v8a', 'arm64-v8a']).architectures, ['arm64-v8a', 'x86_64']);
  assert.equal(androidLayout(['armeabi-v7a', 'arm64-v8a']).architecture, 'universal');
  assert.throws(() => androidLayout(['x86']));
  assert.throws(() => androidLayout([]));
});
test('platform layout creates only the architecture actually collected', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-layout-'));
  try {
    const src = path.join(dir, 'src'); fs.mkdirSync(src); fs.writeFileSync(path.join(src, 'client.msi'), 'fixture');
    const dst = path.join(dir, 'candidate');
    const result = collect(src, dst, '.msi', 0, () => ({ platform: 'windows', architecture: 'x64', architectures: ['x64'] }));
    assert.equal(result[0].file, path.join('windows', 'x64', 'client.msi'));
    assert.equal(result[0].deliveryDirectory, 'windows/x64/<batch>');
    assert.equal(fs.existsSync(path.join(dst, 'windows', 'arm64')), false);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
test('arguments enforce the canonical configuration and reject ambiguity', () => {
  assert.equal(argumentsFor(['--target', 'electron', '--check']).target, 'electron');
  for (const args of [['--target'], ['--target', 'ios'], ['--wat'], ['--check', '--check'], ['--env-file', __filename]]) {
    assert.throws(() => argumentsFor(args));
  }
});
test('artifact collection rejects stale outputs and keeps separate subdirectories', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-artifacts-test-'));
  try {
    const src = path.join(dir, 'src'); const dst = path.join(dir, 'dst'); fs.mkdirSync(src);
    const old = path.join(src, 'old.apk'); fs.writeFileSync(old, 'stale'); fs.utimesSync(old, 1, 1);
    assert.throws(() => collect(src, dst, '.apk', Date.now() - 10000), /No fresh/);
    fs.mkdirSync(path.join(src, 'arm64')); fs.writeFileSync(path.join(src, 'arm64/new.apk'), 'fresh');
    const outputs = collect(src, dst, '.apk', Date.now() - 10000);
    assert.equal(outputs.length, 1); assert.equal(outputs[0].sha256.length, 64);
    assert.equal(fs.readFileSync(path.join(dst, 'arm64/new.apk'), 'utf8'), 'fresh');
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
test('check ignores endpoint/version environment overrides and never creates build state', () => {
  const cli = path.resolve(__dirname, '../build-clients.cjs');
  const state = path.resolve(__dirname, '../release-version.json');
  const before = fs.existsSync(state) ? fs.readFileSync(state) : null;
  const result = spawnSync(process.execPath, [cli, '--target', 'all', '--check'], {
    encoding: 'utf8', env: { ...process.env, SITE_DOMAIN: 'wrong.invalid', CLIENT_VERSION: '9.9.9' }
  });
  const report = JSON.parse(result.stdout);
  const config = parseConfig(fs.readFileSync(path.resolve(__dirname, '../../../config/client.env'), 'utf8'));
  assert.equal(report.version, config.version); assert.equal(report.origin, config.origin);
  assert.equal(report.versionCode, require('../core.cjs').versionCode(config.version));
  assert.equal(report.deliveryRoot, path.resolve(__dirname, '../../../release/clients'));
  assert.ok(!report.blockers.some(text => text.includes('lastVersionCode')));
  assert.ok(report.warnings.some(text => text.includes('NOT verified')));
  assert.deepEqual(fs.existsSync(state) ? fs.readFileSync(state) : null, before);
});
