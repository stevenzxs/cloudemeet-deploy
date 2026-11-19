const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
test('client workflow is manual, pinned, least privilege and signature gated', () => {
  const text = fs.readFileSync(path.join(__dirname, '../../../.github/workflows/build-clients.yml'), 'utf8');
  assert.match(text, /workflow_dispatch:/);
  assert.doesNotMatch(text, /pull_request:|contents: write/);
  assert.match(text, /979a058769a085d0e63e68e6019d5753ed14f96b/);
  assert.match(text, /bee7389737ac93b28b2987861166a744c361beb8/);
  assert.match(text, /ANDROID_KEYSTORE_BASE64/);
  assert.match(text, /build-clients.cjs --target/);
  assert.match(text, /client-ca.crt/);
  assert.match(text, /27.1.12297006/);
  assert.match(text, /java-version: '17'/);
  for (const line of text.split('\n').filter(x => x.includes('uses:') && !x.includes('uses: ./.github/workflows/'))) {
    assert.match(line, /@[0-9a-f]{40}\s*$/);
  }
});
