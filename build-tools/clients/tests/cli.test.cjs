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
test('failed child retains sanitized diagnostics and reports the actual exit code', () => {
  const { run } = require('../build-clients.cjs');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-diagnostics-'));
  const env = { ...process.env, WINDOWS_PFX_PASSWORD: 'fixture-private-password',
    WINDOWS_PFX_BASE64: Buffer.from('fixture-private-pfx').toString('base64'),
    CLOUDMEET_AUDIT_DIR: path.join(dir, 'audit') };
  try {
    const source = `console.error('Forge fixture compiler error');
      console.error(process.env.WINDOWS_PFX_PASSWORD);
      console.error(process.env.WINDOWS_PFX_BASE64);
      console.error('password=unregistered-secret'); process.exit(7);`;
    assert.throws(() => run(process.execPath, ['-e', source], dir, env, path.join(dir, 'electron.log')),
      error => /exit=7/.test(error.message) && /Forge fixture compiler error/.test(error.message)
        && !error.message.includes('fixture-private') && !error.message.includes('unregistered-secret'));
    const report = fs.readFileSync(path.join(env.CLOUDMEET_AUDIT_DIR, 'build-electron.log'), 'utf8');
    assert.match(report, /Forge fixture compiler error/);
    for (const secret of [env.WINDOWS_PFX_PASSWORD, env.WINDOWS_PFX_BASE64, 'unregistered-secret']) {
      assert.ok(!report.includes(secret));
    }
    assert.match(fs.readFileSync(path.join(dir, 'electron.log'), 'utf8'), /fixture-private-password/);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
test('spawn errors remain distinct from a nonzero compiler exit', () => {
  const { run } = require('../build-clients.cjs');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-spawn-'));
  try {
    assert.throws(() => run(path.join(dir, 'missing-executable'), [], dir, {}, path.join(dir, 'android.log')),
      /spawn=ENOENT/);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
test('diagnostic sanitizer excludes private-key blocks and credential-bearing lines', () => {
  const { sanitizeBuildLog } = require('../build-clients.cjs');
  const text = sanitizeBuildLog('error compiler\n-----BEGIN PRIVATE KEY-----\nprivate bytes\n-----END PRIVATE KEY-----\nAuthorization: Bearer value\nsigntool /p hidden-value\n', {});
  assert.match(text, /error compiler/);
  for (const secret of ['private bytes', 'Bearer value', 'hidden-value']) assert.ok(!text.includes(secret));
});
test('candidate creation tolerates a missing temporary parent directory', () => {
  const { createCandidate } = require('../build-clients.cjs');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-parent-'));
  try {
    const base = path.join(dir, 'missing', 'opencode');
    const candidate = createCandidate(base);
    assert.equal(path.dirname(candidate), base);
    assert.ok(fs.statSync(candidate).isDirectory());
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
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
