const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { deliver } = require('../delivery.cjs');
test('delivery requires package checks and refuses overwrite', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-delivery-'));
  try {
    const candidate = path.join(tmp, 'candidate'); fs.mkdirSync(candidate); fs.writeFileSync(path.join(candidate, 'client.msi'), 'fixture');
    const artifact = { file: 'client.msi', platform: 'windows', architecture: 'x64', architectures: ['x64'], sha256: crypto.createHash('sha256').update('fixture').digest('hex') };
    const manifest = { version: '1.0.20', origin: 'https://example.test', candidate, artifacts: [artifact] };
    const root = path.join(tmp, 'release');
    assert.throws(() => deliver(manifest, root), /checks incomplete/);
    assert.equal(fs.existsSync(root), false);
    artifact.checks = Object.fromEntries(['version','architecture','origin','ca','signature'].map(n => [n, { passed: true, detail: n }]));
    const result = deliver(manifest, root);
    assert.equal(fs.readFileSync(result[0].file, 'utf8'), 'fixture');
    assert.ok(fs.existsSync(path.join(result[0].directory, 'SHA256SUMS')));
    assert.throws(() => deliver(manifest, root), /existing/);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});
