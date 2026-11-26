const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { parseConfig } = require('../core.cjs');
const { auditGenerated, auditPackages, inventorySources } = require('../network-audit.cjs');
const config = parseConfig('SITE_DOMAIN=10.1.2.28\nSITE_SCHEME=https\nSITE_PORT=8443\nCLIENT_VERSION=1.0.21\n');
const fs = require('node:fs');

test('Android compiled references and renamed members resolve through resource table', () => {
  const inspect = require('../verify-package.cjs').inspectAndroidResources;
  const tree = host => `E: network-security-config (line=1)
  E: domain-config (line=2)
    E: domain (line=3)
      A: includeSubdomains=(type 0x12)0x0
      C: "${host}"
    E: trust-anchors (line=4)
      E: certificates (line=5)
        A: src=@0x7f110000`;
  let compiledTree = tree('10.1.2.28');
  const run = (exe, args) => {
    if (args[0] === 'dump' && args[1] === 'xmltree') {
      assert.equal(exe, 'aapt');
      assert.deepEqual(args, ['dump', 'xmltree', 'fixture.apk', 'res/A.xml']);
      return compiledTree;
    }
    if (args[0] === 'dump') return 'spec resource 0x7f150000 pkg:xml/app_restrictions: flags=0\nspec resource 0x7f150006 pkg:xml/network_security_config: flags=0\nspec resource 0x7f110000 pkg:raw/cloudmeet_client_ca: flags=0';
    if (args[0] === 'manifest') return '<application xmlns:android="http://schemas.android.com/apk/res/android" android:networkSecurityConfig="@ref/0x7f150006"><meta-data android:name="android.content.APP_RESTRICTIONS" android:resource="@ref/0x7f150000"/></application>';
    if (args[1] === 'value') return ({app_restrictions:'res/Kt.xml',network_security_config:'res/A.xml',cloudmeet_client_ca:'res/C.crt'})[args[args.indexOf('--name')+1]];
    if (args.includes('res/Kt.xml')) return `<restrictions xmlns:android="http://schemas.android.com/apk/res/android"><restriction android:key="SERVER_URL" android:defaultValue="${config.origin}"/></restrictions>`;
    // Real apkanalyzer output loses binary XML character data, not just refs.
    if (args.includes('res/A.xml')) return '<network-security-config><domain-config><domain includeSubdomains="false"/><trust-anchors><certificates src="@ref/0x7f110000"/></trust-anchors></domain-config></network-security-config>';
    throw Error('Unexpected resource command');
  };
  assert.equal(inspect('fixture.apk','analyzer','aapt',config,true,run), 'res/C.crt');
  compiledTree = tree('other.example');
  assert.throws(() => inspect('fixture.apk','analyzer','aapt',config,true,run), /matched 0/);
  compiledTree = tree('10.1.2.28').replace('    E: trust-anchors', '      E: trust-anchors');
  assert.throws(() => inspect('fixture.apk','analyzer','aapt',config,true,run), /structure mismatch/);
  compiledTree = tree('10.1.2.28').replace('C: "10.1.2.28"', 'C: not-a-quoted-string');
  assert.throws(() => inspect('fixture.apk','analyzer','aapt',config,true,run), /character data/);
  compiledTree = '';
  assert.throws(() => inspect('fixture.apk','analyzer','aapt',config,true,run), /structure mismatch/);
  compiledTree = tree('10.1.2.28').replace('    E: domain (line=3)', '    E: other (line=3)');
  assert.throws(() => inspect('fixture.apk','analyzer','aapt',config,true,run), /structure mismatch/);
});

test('all batch audit phases are staged without changing bytes', () => {
  const os = require('node:os');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-stage-'));
  try {
    const src = path.join(dir, 'audit'), dst = path.join(dir, 'candidate');
    fs.mkdirSync(src); fs.mkdirSync(dst);
    for (const phase of ['client-preflight', 'android-source-inventory']) {
      for (const ext of ['json', 'md']) fs.writeFileSync(path.join(src, `network-${phase}.${ext}`), phase);
    }
    require('../network-audit.cjs').stageReports(src, dst);
    assert.deepEqual(fs.readdirSync(dst).sort(), fs.readdirSync(src).sort());
    for (const name of fs.readdirSync(src)) assert.deepEqual(fs.readFileSync(path.join(src, name)), fs.readFileSync(path.join(dst, name)));
  } finally { fs.rmSync(dir, { recursive: true }); }
});

test('generated Electron config must exactly match all origin fields', () => {
  assert.throws(() => auditGenerated('electron', config, {
    deployment: 'SITE_DOMAIN=10.1.2.28\nSITE_SCHEME=https\nSITE_PORT=8443\nSITE_PORT=443\n',
    trust: { origin: config.origin, caFile: null }
  }), /configuration/);
});
test('equivalent Electron duplicate keys are accepted with an audit warning', () => {
  const report = auditGenerated('electron', config, {
    deployment: 'SITE_DOMAIN=10.1.2.28\nSITE_SCHEME=https\nSITE_PORT=8443\nSITE_PORT=8443\n',
    trust: { origin: config.origin, caFile: null }
  });
  assert.match(report.warnings.join(' '), /SITE_PORT/);
  assert.throws(() => auditGenerated('electron', config, {
    deployment: 'SITE_DOMAIN=10.1.2.28\nSITE_SCHEME=https\nSITE_PORT=8443\nSITE_PORT=443\n',
    trust: { origin: config.origin, caFile: null }
  }), /conflicts: SITE_PORT/);
});
test('equivalent Android rules pass but missing, inherited or conflicting duplicates fail', () => {
  const validate = require('../verify-package.cjs').validateAndroidResources;
  const manifest = '<application xmlns:android="http://schemas.android.com/apk/res/android" android:networkSecurityConfig="@xml/network_security_config"><meta-data android:name="android.content.APP_RESTRICTIONS" android:resource="@xml/app_restrictions" /></application>';
  const restrictions = `<restrictions xmlns:android="http://schemas.android.com/apk/res/android"><restriction android:key="SERVER_URL" android:defaultValue="${config.origin}" /></restrictions>`;
  const rule = '<domain-config cleartextTrafficPermitted="false"><domain includeSubdomains="false">10.1.2.28</domain><trust-anchors><certificates src="@raw/cloudmeet_client_ca" /></trust-anchors></domain-config>';
  const xml = body => `<network-security-config>${body}</network-security-config>`;
  assert.equal(validate(manifest, restrictions, xml(rule + rule), config, true), true);
  assert.throws(() => validate(manifest, restrictions, xml(''), config, true), /matched 0/);
  assert.throws(() => validate(manifest, restrictions, xml(rule + rule.replace('cleartextTrafficPermitted="false"', 'cleartextTrafficPermitted="true"')), config, true), /conflicting/);
  assert.throws(() => validate(manifest, restrictions, xml(rule + rule.replace(' cleartextTrafficPermitted="false"', '')), config, true), /explicit/);
  assert.throws(() => validate(manifest, restrictions, xml(rule + rule.replace('includeSubdomains="false"', 'includeSubdomains="true"')), config, true), /subdomains/);
  assert.throws(() => validate(manifest, restrictions, xml(rule + rule.replace('</trust-anchors>', '<certificates src="system" /></trust-anchors>')), config, true), /trust anchors/);
  assert.throws(() => validate(manifest, restrictions, xml(rule + rule.replace('</domain>', '</domain><domain>other.example</domain>')), config, true), /host scope/);
  assert.throws(() => validate(manifest, restrictions, xml(rule + '<domain-config>'+rule+'</domain-config>'), config, true), /explicit/);
});
test('generated Android deployment and restrictions cannot diverge', () => {
  assert.throws(() => auditGenerated('android', config, {
    deployment: { origin: 'https://old.example.org:8443' },
    restrictions: `android:key="SERVER_URL" android:defaultValue="${config.origin}"`
  }), /origin/);
});
test('valid generated configs produce auditable derived endpoints', () => {
  const r = auditGenerated('electron', config, {
    deployment: 'SITE_DOMAIN=10.1.2.28\nSITE_SCHEME=https\nSITE_PORT=8443\n',
    trust: { origin: config.origin, caFile: null }
  });
  assert.equal(r.parameters.find(p => p.name === 'desktopUrl').value, config.desktopUrl);
  assert.equal(r.status, 'pass');
});
test('audit reports batch-origin as the source rather than fixed repository config', () => {
  const report = auditGenerated('electron', config, { deployment: 'SITE_DOMAIN=10.1.2.28\nSITE_SCHEME=https\nSITE_PORT=8443\n', trust: { origin: config.origin } });
  assert.ok(report.parameters.filter(p => ['SITE_DOMAIN', 'SITE_SCHEME', 'SITE_PORT'].includes(p.name)).every(p => p.source === 'batch-origin-contract'));
});
test('written audit hashes the passed batch env and embeds origin address evidence', () => {
  const os = require('node:os');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'network-audit-contract-'));
  try {
    const batchEnv = path.join(dir, 'batch.env');
    fs.writeFileSync(batchEnv, 'SITE_DOMAIN=10.1.2.28\nSITE_SCHEME=https\nSITE_PORT=8443\n');
    const originContract = { origin: config.origin, addresses: ['10.1.2.28'] };
    const report = require('../network-audit.cjs').writeAudit(dir, 'batch', { status: 'pass' }, dir, batchEnv, originContract);
    assert.equal(report.clientEnvSha256.length, 64);
    assert.deepEqual(report.originContract, originContract);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
test('client audit records normalized address and TLS provenance', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../build-clients.cjs'), 'utf8');
  assert.match(source, /options\.file, report\.originContract/);
  assert.match(source, /report\.originContract = originContract/);
});
test('post-package audit refuses incomplete package checks', () => {
  assert.throws(() => auditPackages({ artifacts: [{ checks: { origin: { passed: true } } }] }), /incomplete/);
});
test('Android packaged XML references must select the checked restrictions and scoped CA', () => {
  const validate = require('../verify-package.cjs').validateAndroidResources;
  const manifest = '<application xmlns:android="http://schemas.android.com/apk/res/android" android:networkSecurityConfig="@xml/network_security_config"><meta-data android:name="android.content.APP_RESTRICTIONS" android:resource="@xml/app_restrictions" /></application>';
  const restrictions = `<restrictions xmlns:android="http://schemas.android.com/apk/res/android"><restriction android:key="SERVER_URL" android:defaultValue="${config.origin}" /></restrictions>`;
  const trust = `<network-security-config><domain-config><domain includeSubdomains="false">10.1.2.28</domain><trust-anchors><certificates src="@raw/cloudmeet_client_ca" /></trust-anchors></domain-config></network-security-config>`;
  assert.equal(validate(manifest, restrictions, trust, config, true), true);
  assert.throws(() => validate(manifest.replace('@xml/network_security_config', '@xml/unused'), restrictions, trust, config, true));
  assert.throws(() => validate(manifest, restrictions, trust.replace('@raw/cloudmeet_client_ca', '@raw/other'), config, true));
  assert.throws(() => validate(manifest, restrictions, trust.replace('10.1.2.28', 'old.invalid'), config, true));
});
test('source inventory records endpoints without URL credentials', () => {
  const os = require('node:os');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'network-inventory-'));
  try {
    fs.mkdirSync(path.join(dir, 'src'));
    fs.writeFileSync(path.join(dir, 'src/main.js'), 'const api="https://user:DO_NOT_LOG@example.org:9443/api?token=DO_NOT_LOG";');
    const report = inventorySources(dir, ['src']);
    assert.equal(report.endpoints.length, 1);
    assert.ok(!JSON.stringify(report).includes('DO_NOT_LOG'));
    assert.equal(report.endpoints[0].value, 'https://example.org:9443/api');
  } finally { fs.rmSync(dir, { recursive: true }); }
});
