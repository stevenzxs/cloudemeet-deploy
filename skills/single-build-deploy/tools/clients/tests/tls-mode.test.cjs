const test = require('node:test');
const assert = require('node:assert/strict');
const { parseConfig } = require('../core.cjs');
const { readCa, androidTrust } = require('../ca-config.cjs');
const base = 'SITE_DOMAIN=meet.example.com\nSITE_SCHEME=https\nSITE_PORT=443\nCLIENT_VERSION=1.0.21\n';
test('explicit public mode rejects private anchors, IP and nonstandard port', () => {
  const config = parseConfig(base + 'TLS_MODE=caddy-public-acme\n');
  assert.equal(config.tlsMode, 'caddy-public-acme');
  assert.equal(readCa(config, 'unused'), null);
  for (const text of [base+'TLS_MODE=unknown',base+'TLS_MODE=caddy-public-acme\nCLIENT_CA_FILE=ca.crt',
    base.replace('meet.example.com','118.193.36.35')+'TLS_MODE=caddy-public-acme',
    base.replace('PORT=443','PORT=8443')+'TLS_MODE=caddy-public-acme',base+'TLS_MODE=private-ca']) {
    assert.throws(() => parseConfig(text));
  }
});
test('public Android policy replaces target private anchors with system trust only', () => {
  const xml='<network-security-config><domain-config><domain>meet.example.com</domain><trust-anchors><certificates src="@raw/cloudmeet_client_ca" /></trust-anchors></domain-config></network-security-config>';
  const result=androidTrust(xml,'meet.example.com','caddy-public-acme');
  assert.match(result, /src="system"/);
  assert.doesNotMatch(result, /cloudmeet_client_ca/);
  assert.match(result, /cleartextTrafficPermitted="false"/);
});
