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
  assert.equal(report.versionCode, 1019);
  assert.equal(report.deliveryRoot, path.resolve(__dirname, '../../../release/clients'));
  assert.ok(!report.blockers.some(text => text.includes('lastVersionCode')));
  assert.ok(report.warnings.some(text => text.includes('NOT verified')));
  assert.deepEqual(fs.existsSync(state) ? fs.readFileSync(state) : null, before);
});
