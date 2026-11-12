const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { readCa, androidTrust } = require('../ca-config.cjs');
test('CA is optional but configured missing files fail closed', () => {
  assert.equal(readCa({ values: {} }, __filename), null);
  assert.throws(() => readCa({ origin: 'https://example.org', values: { CLIENT_CA_FILE: 'missing-ca.crt' } }, __filename));
  assert.throws(() => readCa({ origin: 'http://example.org', values: { CLIENT_CA_FILE: 'ca.crt' } }, __filename), /HTTPS/);
});
test('Android host-specific trust preserves unrelated domain settings', () => {
  const input = '<network-security-config><domain-config><domain>47.96.221.94</domain><domain>other.example</domain><trust-anchors><certificates src="system" /></trust-anchors></domain-config></network-security-config>';
  const xml = androidTrust(input, '47.96.221.94');
  assert.equal((xml.match(/47\.96\.221\.94/g) || []).length, 1);
  assert.ok(xml.includes('other.example'));
  assert.ok(xml.includes('@raw/cloudmeet_client_ca'));
  assert.equal(androidTrust(xml, '47.96.221.94'), xml);
});
