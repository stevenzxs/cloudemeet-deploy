const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
test('client workflow is manual, pinned, least privilege and signature gated', () => {
  const text = fs.readFileSync(path.join(__dirname, '../../../.github/workflows/build-clients.yml'), 'utf8');
  assert.match(text, /workflow_dispatch:/);
  assert.doesNotMatch(text, /pull_request:|contents: write/);
  assert.match(text, /979a058769a085d0e63e68e6019d5753ed14f96b/);
  assert.match(text, /5d9d14d19b55aa618b3610d1a865e3d77485d46f/);
  assert.match(text, /ANDROID_KEYSTORE_BASE64/);
  for (const key of ['WINDOWS_PFX_BASE64', 'WINDOWS_PFX_PASSWORD', 'CERTIFICATES_READ_TOKEN']) assert.match(text, new RegExp(key));
  assert.match(text, /unsigned fallback prohibited/);
  assert.match(text, /repository: stevenzxs\/cloudmeet-certificates/);
  const policy = JSON.parse(fs.readFileSync(path.join(__dirname, '../../../config/signing-policy.json'), 'utf8'));
  assert.match(text, new RegExp(`ref: ${policy.commit}`));
  assert.match(text, /build-clients.cjs --target/);
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
