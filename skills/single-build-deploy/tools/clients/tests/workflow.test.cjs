const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const WORKFLOW = path.join(__dirname, '../../../../../.github/workflows/build-single.yml');
test('single patch workflow keeps Android signing but removes Windows signing credentials', () => {
  const text = fs.readFileSync(WORKFLOW, 'utf8');
  assert.match(text, /workflow_dispatch:/);
  assert.doesNotMatch(text, /pull_request:/);
  assert.doesNotMatch(text, /revision-allocation\.yml/, 'patch flow never allocates a joint revision');
  assert.match(text, /ANDROID_KEYSTORE_BASE64/);
  for (const key of ['WINDOWS_PFX_BASE64', 'WINDOWS_PFX_PASSWORD', 'CERTIFICATES_READ_TOKEN', 'SIGNTOOL_PATH']) assert.doesNotMatch(text, new RegExp(key));
  assert.match(text, /debug fallback prohibited/);
  const policy = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../config/signing-policy.json'), 'utf8'));
  assert.match(policy.android_certificate_der_sha256, /^[0-9a-f]{64}$/);
  assert.equal((text.match(/deploy\/skills\/single-build-deploy\/tools\/clients\/build-clients\.cjs --target/g) || []).length, 2, 'Mutually exclusive branches each invoke the skill-owned builder once');
  assert.match(text, /maven-route\.py --audit client-network-audit\/maven-route\.jsonl --gradle-command -- node/);
  assert.match(text, /--version-record patch-assignment\.json/);
  assert.match(text, /Client build or package verification failed/);
  assert.match(text, /runs-on: \$\{\{ inputs\.target == 'android' && 'ubuntu-24\.04' \|\| 'windows-2022' \}\}/);
  assert.match(text, /Build and verify packages\s*\n\s*timeout-minutes: 35/);
  assert.match(text, /client-ca\.crt/);
  assert.match(text, /27\.1\.12297006/);
  assert.match(text, /java-version: '17'/);
  assert.match(text, /cache: gradle/);
  assert.match(text, /jm\/android\/gradle\/wrapper\/gradle-wrapper\.properties/);
  assert.match(text, /Gradle dependency cache restored: \$hit/);
  assert.ok(text.indexOf('path: jm') < text.indexOf('Set up Java and restore Gradle dependency cache'),
    'Android source must be checked out before the dependency cache is calculated');
  assert.match(text, /name: Retain audit and sanitized build diagnostics even on failure\s+if: always\(\)/);
  assert.match(text, /path: client-network-audit\//);
  assert.doesNotMatch(text, /path:.*(?:cloudmeet-clients-|electron\.log|android\.log)/);
  for (const line of text.split('\n').filter(x => x.includes('uses:') && !x.includes('uses: ./.github/workflows/'))) {
    assert.match(line, /@[0-9a-f]{40}\s*$/);
  }
});
test('single patch client checkout derives from the sources lock with a three-way assertion', () => {
  const text = fs.readFileSync(WORKFLOW, 'utf8');
  const sources = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../sources.json'), 'utf8'));
  assert.equal(sources.clients.android.repository, 'https://github.com/stevenzxs/jm.git');
  for (const target of ['electron', 'android']) {
    assert.match(sources.clients[target].commit, /^[0-9a-f]{40}$/);
  }
  assert.match(text, /Read pinned client source commit from the reviewed sources lock/);
  assert.match(text, /Assert checkout, sources lock and patch record agree/);
  assert.match(text, /sources\.clients\.\$\(\$env:CLIENT_TARGET\)\.commit/);
  // The patch flow must not hardcode a client commit: only action pins use 40-hex.
  const withoutUses = text.split('\n').filter(line => !line.includes('uses:')).join('\n');
  assert.doesNotMatch(withoutUses, /ref: [0-9a-f]{40}/);
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
