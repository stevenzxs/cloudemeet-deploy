const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { argumentsFor, collect, androidTasks } = require('../build-clients.cjs');
test('client toolchain root resolves to the workspace above deploy checkout', () => {
  const root = path.resolve(__dirname, '../../../../../..');
  assert.equal(path.basename(path.join(root, 'deploy')), 'deploy');
  assert.ok(fs.existsSync(path.join(root, 'jm/android/gradlew')));
  assert.ok(fs.existsSync(path.join(root, 'jitsi-meet-electron/package.json')));
});
test('Android always repackages APK while retaining dependency compilation cache', () => {
  assert.deepEqual(androidTasks(), [':app:packageRelease', '--rerun', ':app:assembleRelease']);
});
test('Android phase timing uses a monotonic clock and records verification and delivery', () => {
  const source = fs.readFileSync(path.join(__dirname, '../build-clients.cjs'), 'utf8');
  for (const marker of ['android-gradle-build', 'android-package-verification', 'android-delivery']) {
    assert.ok(source.includes(marker), `Missing phase timing ${marker}`);
  }
  assert.match(source, /process\.hrtime\.bigint\(\)/);
  assert.match(source, /finally\s*\{\s*timing\.durationMs = elapsedMs\(started\);[\s\S]{0,100}save\(\)/);
});
test('Android Gradle invocation enables build cache and preserves forced APK packaging', () => {
  const source = fs.readFileSync(path.join(__dirname, '../build-clients.cjs'), 'utf8');
  assert.deepEqual(androidTasks(), [':app:packageRelease', '--rerun', ':app:assembleRelease']);
  assert.match(source, /'--no-daemon', '--build-cache'/);
});
const { parseConfig } = require('../core.cjs');
test('failed child retains sanitized diagnostics and reports the actual exit code', async () => {
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
    await assert.rejects(run(process.execPath, ['-e', source], dir, env, path.join(dir, 'electron.log')),
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
test('spawn errors remain distinct from a nonzero compiler exit', async () => {
  const { run } = require('../build-clients.cjs');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-spawn-'));
  try {
    await assert.rejects(run(path.join(dir, 'missing-executable'), [], dir, {}, path.join(dir, 'android.log')),
      /spawn=ENOENT/);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
test('diagnostics are retained before a running child exits without partial credential leakage', async () => {
  const { run } = require('../build-clients.cjs');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-live-'));
  const audit = path.join(dir, 'audit');
  const promise = run(process.execPath, ['-e', "console.log('phase-start');process.stdout.write('fixture-secret');setTimeout(()=>process.exit(0),1800)"],
    dir, { ...process.env, CLOUDMEET_AUDIT_DIR: audit, WINDOWS_PFX_PASSWORD: 'fixture-secret-value' }, path.join(dir, 'electron.log'));
  try {
    await new Promise(resolve => setTimeout(resolve, 1000));
    const report = fs.readFileSync(path.join(audit, 'build-electron.log'), 'utf8');
    assert.match(report, /phase-start/);
    assert.ok(!report.includes('fixture-secret'));
  } finally { await promise; fs.rmSync(dir, { recursive: true, force: true }); }
});
test('diagnostic sanitizer excludes private-key blocks and credential-bearing lines', () => {
  const { sanitizeBuildLog } = require('../build-clients.cjs');
  const text = sanitizeBuildLog('error compiler\n-----BEGIN PRIVATE KEY-----\nprivate bytes\n-----END PRIVATE KEY-----\nAuthorization: Bearer value\nsigntool /p hidden-value\n', {});
  assert.match(text, /error compiler/);
  for (const secret of ['private bytes', 'Bearer value', 'hidden-value']) assert.ok(!text.includes(secret));
});
test('sanitizer preserves signing diagnostics and redacts values rather than whole lines', () => {
  const { sanitizeBuildLog } = require('../build-clients.cjs');
  const text = sanitizeBuildLog('signing password validation failed: missing password\n'
    + 'tokenizer compiled; token count=42\nAuthorization: Bearer hidden-auth; compiler failed\n'
    + 'password="hidden with spaces"; task failed\nsigntool /p hidden-pass /v compiler-error\n'
    + 'known=fixture-secret; download failed\n', { BUILD_TOKEN: 'fixture-secret' });
  for (const message of ['signing password validation failed: missing password', 'tokenizer compiled; token count=42',
    'compiler failed', 'task failed', '/v compiler-error', 'download failed']) assert.ok(text.includes(message), message);
  for (const secret of ['hidden-auth', 'hidden with spaces', 'hidden-pass', 'fixture-secret']) assert.ok(!text.includes(secret));
});
for (const target of ['android', 'electron']) test(`${target} streams both outputs before exit and retains full audit including EOF`, async () => {
  const { run } = require('../build-clients.cjs');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-stream-'));
  const release = path.join(dir, 'release');
  const audit = path.join(dir, 'audit');
  fs.mkdirSync(path.join(dir, 'keystores'));
  fs.writeFileSync(path.join(dir, 'keystores/release.keystore.properties'), 'storePassword=fixture-store-value\nkeyPassword=fixture-key-value\n');
  let output = '', resolveLive;
  const live = new Promise(resolve => { resolveLive = resolve; });
  const sink = { write(text) { output += text; if (output.includes('stderr-progress')) resolveLive(); } };
  const source = `const fs=require('node:fs'); console.log('stdout-progress'); console.error('stderr-progress');
    process.stdout.write('fixture-');
    const timer=setInterval(()=>{if(!fs.existsSync(${JSON.stringify(release)}))return;
      clearInterval(timer);process.stdout.write('secret-value\\n');
      console.log('-----BEGIN PRIVATE KEY-----');console.log('private-fixture');console.log('-----END PRIVATE KEY-----');
      console.log('fixture-store-value fixture-key-value');
      process.stdout.write('download-progress\\r');console.log('::error::fixture-not-an-annotation');
      console.log('x'.repeat(70000));process.stdout.write('last-line-without-newline');},20);
    setTimeout(()=>process.exit(9),4000).unref();`;
  const promise = run(process.execPath, ['-e', source], dir,
    { ...process.env, CLOUDMEET_AUDIT_DIR: audit, BUILD_TOKEN: 'fixture-secret-value' }, path.join(dir, `${target}.log`), sink);
  try {
    await Promise.race([live, new Promise((_, reject) => setTimeout(() => reject(Error('no live build output')), 2000))]);
    assert.ok(!fs.existsSync(release));
    assert.match(output, /stdout-progress/);
  } finally {
    fs.writeFileSync(release, 'continue');
    await promise;
    try {
      const report = fs.readFileSync(path.join(audit, `build-${target}.log`), 'utf8');
      for (const text of [output, report]) {
        assert.match(text, /stdout-progress/); assert.match(text, /stderr-progress/);
        assert.match(text, /last-line-without-newline/); assert.ok(text.length > 70000);
        assert.ok(!text.includes('fixture-secret-value')); assert.ok(!text.includes('private-fixture'));
        assert.ok(!text.includes('fixture-store-value')); assert.ok(!text.includes('fixture-key-value'));
        assert.match(text, /download-progress/);
      }
      assert.ok(!output.split('\n').some(line => line.startsWith('::error::')));
    } finally { fs.rmSync(dir, { recursive: true, force: true }); }
  }
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
test('arguments accept explicit per-batch configuration and reject ambiguity', () => {
  const tempEnv = path.resolve(os.tmpdir(), `client-${process.pid}.env`);
  const envArgument = path.resolve(tempEnv);
  fs.writeFileSync(tempEnv, 'SITE_DOMAIN=47.96.221.94\nSITE_SCHEME=https\nSITE_PORT=8443\nCLIENT_VERSION=1.0.21\nTLS_MODE=private-ca\nCLIENT_CA_FILE=client-ca.crt\n');
  assert.equal(argumentsFor(['--target', 'electron', '--check']).target, 'electron');
  assert.equal(argumentsFor(['--env-file', envArgument]).file, envArgument);
  const contract = path.resolve(__dirname, 'origin.json');
  fs.writeFileSync(contract, '{}');
  assert.equal(argumentsFor(['--env-file', envArgument, '--origin-contract', contract, '--check']).originContract, contract);
  for (const args of [['--target'], ['--target', 'ios'], ['--wat'], ['--check', '--check'], ['--origin-contract', 'relative.json']]) {
    assert.throws(() => argumentsFor(args));
  }
  assert.throws(() => argumentsFor(['--env-file', 'relative.env']));
  fs.rmSync(contract, { force: true });
  fs.rmSync(tempEnv, { force: true });
});
test('skill revision configuration avoids legacy validators and checkout binding', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../revision-config.cjs'), 'utf8');
  assert.doesNotMatch(source, /revision_versions\.py/);
  assert.doesNotMatch(source, /version-policy\.json/);
  assert.doesNotMatch(source, /sources\.json/);
  assert.doesNotMatch(source, /Client checkout differs from allocation/);
  assert.doesNotMatch(source, /deploy\/build-tools|deploy\/config/);
});
test('skill-local client config contains no fixed endpoint or fixed TLS approval', () => {
  const config = fs.readFileSync(path.resolve(__dirname, '../../../config/client.env'), 'utf8');
  assert.doesNotMatch(config, /^SITE_(DOMAIN|SCHEME|PORT)=/m);
  assert.doesNotMatch(config, /^TLS_MODE=/m);
  assert.match(config, /^CLIENT_VERSION=/m);
  assert.match(config, /^CLIENT_CA_FILE=/m);
});
test('skill signing adapter reads its skill-owned signing policy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../signing.cjs'), 'utf8');
  assert.match(source, /config\/signing-policy\.json/);
  assert.doesNotMatch(source, /deploy\/config/);
});
test('workflow client contract keeps canonical DNS evidence and batch env in provenance', () => {
  const workflow = fs.readFileSync(path.resolve(__dirname, '../../../../../.github/workflows/build-single.yml'), 'utf8');
  assert.match(workflow, /needs\.version\.outputs\.origin_contract/);
  assert.match(workflow, /--origin-contract/);
  assert.match(workflow, /--env-file/);
});
test('workflow rejects mismatch between batch environment and origin evidence before build', () => {
  const cli = path.resolve(__dirname, '../build-clients.cjs');
  const envFile = path.join(os.tmpdir(), `client-origin-${process.pid}.env`);
  const originFile = path.join(os.tmpdir(), `origin-contract-${process.pid}.json`);
  const record = path.join(os.tmpdir(), `version-${process.pid}.json`);
  const childEnv = { ...process.env, GITHUB_SHA: 'a'.repeat(40), GITHUB_RUN_ID: '1', GITHUB_RUN_ATTEMPT: '1' };
  fs.writeFileSync(envFile, 'SITE_DOMAIN=47.96.221.94\nSITE_SCHEME=https\nSITE_PORT=8443\nCLIENT_VERSION=1.0.21\nTLS_MODE=private-ca\nCLIENT_CA_FILE=client-ca.crt\n');
  fs.writeFileSync(originFile, JSON.stringify({ origin: 'https://different.example:8443', scheme: 'https', host: 'different.example', port: 8443, tls_mode: 'private-ca', addresses: ['192.0.2.10'] }));
  fs.writeFileSync(record, '{}');
  try {
    const result = spawnSync(process.execPath, [cli, '--target', 'electron', '--env-file', envFile,
      '--origin-contract', originFile, '--version-record', record], { encoding: 'utf8', env: childEnv });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /Batch client configuration differs from normalized origin contract/);
  } finally { for (const file of [envFile, originFile, record]) fs.rmSync(file, { force: true }); }
});
test('workflow accepts an explicit default HTTPS port when normalized origin omits it', () => {
  const cli = path.resolve(__dirname, '../build-clients.cjs');
  const envFile = path.join(os.tmpdir(), `client-default-port-${process.pid}.env`);
  const originFile = path.join(os.tmpdir(), `origin-default-port-${process.pid}.json`);
  const record = path.join(os.tmpdir(), `version-default-port-${process.pid}.json`);
  const childEnv = { ...process.env, GITHUB_SHA: 'a'.repeat(40), GITHUB_RUN_ID: '1', GITHUB_RUN_ATTEMPT: '1' };
  fs.writeFileSync(envFile, 'SITE_DOMAIN=cloudmeet.example.com\nSITE_SCHEME=https\nSITE_PORT=443\nCLIENT_VERSION=1.0.21\nTLS_MODE=caddy-public-acme\n');
  fs.writeFileSync(originFile, JSON.stringify({ origin: 'https://cloudmeet.example.com:443', scheme: 'https', host: 'cloudmeet.example.com', port: 443, tls_mode: 'caddy-public-acme', addresses: ['192.0.2.10'] }));
  fs.writeFileSync(record, JSON.stringify({ request: { scope: ['electron'], sources: { electron: 'b'.repeat(40), android: 'c'.repeat(40) } }, versions: { revision: 1, client_version: '1.0.21+r1', android_code: 10211, msi_version: '1.0.22', pe_version: '1.0.22.0' } }));
  try {
    const result = spawnSync(process.execPath, [cli, '--target', 'electron', '--env-file', envFile,
      '--origin-contract', originFile, '--version-record', record], { encoding: 'utf8', env: childEnv });
    assert.equal(result.status, 1);
    assert.doesNotMatch(result.stderr, /Batch client configuration differs from normalized origin contract/);
  } finally { for (const file of [envFile, originFile, record]) fs.rmSync(file, { force: true }); }
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
  const configPath = path.resolve(os.tmpdir(), `client-check-${process.pid}.env`);
  fs.mkdirSync(path.dirname(configPath), { recursive: true });
  fs.writeFileSync(configPath, 'SITE_DOMAIN=47.96.221.94\nSITE_SCHEME=https\nSITE_PORT=8443\nCLIENT_VERSION=1.0.21\nTLS_MODE=private-ca\nCLIENT_CA_FILE=client-ca.crt\n');
  const before = fs.existsSync(state) ? fs.readFileSync(state) : null;
  const result = spawnSync(process.execPath, [cli, '--target', 'all', '--check', '--env-file', configPath], {
    encoding: 'utf8', env: { ...process.env, SITE_DOMAIN: 'wrong.invalid', CLIENT_VERSION: '9.9.9' }
  });
  const report = JSON.parse(result.stdout);
  const config = parseConfig(fs.readFileSync(configPath, 'utf8'));
  assert.equal(report.version, config.version); assert.equal(report.origin, config.origin);
  assert.equal(report.versionCode, require('../core.cjs').versionCode(config.version));
  assert.equal(report.deliveryRoot, path.resolve(__dirname, '../../../../../../deploy/release/clients'));
  assert.ok(!report.blockers.some(text => text.includes('lastVersionCode')));
  assert.ok(report.warnings.some(text => text.includes('NOT verified')));
  assert.deepEqual(fs.existsSync(state) ? fs.readFileSync(state) : null, before);
  fs.rmSync(configPath, { force: true });
});
