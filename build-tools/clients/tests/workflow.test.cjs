const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
test('client workflow keeps Android signing but removes Windows signing credentials', () => {
  const text = fs.readFileSync(path.join(__dirname, '../../../.github/workflows/build-clients.yml'), 'utf8');
  assert.match(text, /workflow_dispatch:/);
  assert.doesNotMatch(text, /pull_request:|contents: write/);
  assert.match(text, /5d9d14d19b55aa618b3610d1a865e3d77485d46f/);
  assert.match(text, /ANDROID_KEYSTORE_BASE64/);
  for (const key of ['WINDOWS_PFX_BASE64', 'WINDOWS_PFX_PASSWORD', 'CERTIFICATES_READ_TOKEN', 'SIGNTOOL_PATH']) assert.doesNotMatch(text, new RegExp(key));
  assert.match(text, /debug fallback prohibited/);
  const policy = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../config/signing-policy.json'), 'utf8'));
  assert.match(policy.android_certificate_der_sha256, /^[0-9a-f]{64}$/);
  assert.match(text, /build-clients.cjs --target/);
  assert.equal((text.match(/node deploy\/build-tools\/clients\/build-clients\.cjs --target/g) || []).length, 1);
  assert.doesNotMatch(text, /--version-record version-assignment\.json --check/);
  assert.match(text, /Client build or package verification failed/);
  assert.match(text, /runs-on: \$\{\{ matrix\.target == 'android' && 'ubuntu-24\.04' \|\| 'windows-2022' \}\}/);
  assert.match(text, /Build and verify packages\s*\n\s*#[^\n]*\n\s*#[^\n]*\n\s*timeout-minutes: 35/);
  assert.doesNotMatch(text, /GNU find missing/);
  assert.match(text, /client-ca.crt/);
  assert.match(text, /27.1.12297006/);
  assert.match(text, /java-version: '17'/);
  assert.match(text, /name: Retain audit and sanitized build diagnostics even on failure\s+if: always\(\)/);
  assert.match(text, /path: client-network-audit\//);
  assert.doesNotMatch(text, /path:.*(?:cloudmeet-clients-|electron\.log|android\.log)/);
  for (const line of text.split('\n').filter(x => x.includes('uses:') && !x.includes('uses: ./.github/workflows/'))) {
    assert.match(line, /@[0-9a-f]{40}\s*$/);
  }
});
test('client checkouts match source locks and Android pins the reviewed main fix', () => {
  const root = path.join(__dirname, '../../..');
  const text = fs.readFileSync(path.join(root, '.github/workflows/build-clients.yml'), 'utf8');
  const sources = JSON.parse(fs.readFileSync(path.join(root, 'build-tools/sources.json'), 'utf8'));
  assert.equal(sources.clients.android.repository, 'https://github.com/stevenzxs/jm.git');
  assert.equal(sources.clients.android.commit, 'a4012af4a20c257b327af1c9bd34d654ec6642e9');
  for (const source of Object.values(sources.clients)) {
    const repository = source.repository.replace('https://github.com/', '').replace(/\.git$/, '');
    const checkout = text.split('\n').filter(line => !line.trimStart().startsWith('#')).join('\n')
      .split(/\n\s*- uses: /).find(step => step.includes(`repository: ${repository}\n`));
    assert.ok(checkout, `Missing checkout for ${repository}`);
    const ref = checkout.match(/^\s+ref: (\S+)\s*$/m)?.[1];
    assert.match(ref || '', /^[0-9a-f]{40}$/, 'Source checkout must use a full SHA, not a floating branch');
    assert.equal(ref, source.commit, `Workflow/source lock mismatch for ${repository}`);
  }
});
test('normal client build retains mandatory preflight before compilation and reports stages', () => {
  const text = fs.readFileSync(path.join(__dirname, '../build-clients.cjs'), 'utf8');
  assert.ok(text.indexOf('const report = preflight(options, config)') < text.indexOf('if (!options.check) await build'));
  assert.match(text, /if \(report\.blockers\.length\) \{ process\.exitCode = 1; return; \}/);
  assert.doesNotMatch(text, /windowsIdentity|WINDOWS_PFX|SIGNTOOL_PATH/);
  for (const stage of ['Preflight', 'Compile and package', 'Verify final packages', 'Deliver verified packages']) {
    assert.ok(text.includes(`[client-stage] ${stage}`));
  }
});
