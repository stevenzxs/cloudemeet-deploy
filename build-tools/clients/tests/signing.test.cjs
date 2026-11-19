const test = require('node:test');
const assert = require('node:assert/strict');
const verify = require('../verify-package.cjs');
const approved = '6c8897672e567b6be645bbe4435c2fc9fa85663cf7cc9ed8de46364eebb7e815';
test('APK requires the unique approved signer, not merely Verifies', () => {
  const valid = `Verifies\nSigner #1 certificate SHA-256 digest: ${approved}\n`;
  assert.equal(verify.validateAndroidSigner(valid, approved), approved);
  for (const text of ['Verifies', valid.replace(approved, '0'.repeat(64)), valid + `Signer #2 certificate SHA-256 digest: ${approved}\n`]) {
    assert.throws(() => verify.validateAndroidSigner(text, approved), /signer/i);
  }
});
test('Windows requires valid timestamped signatures from the approved identity', () => {
  const valid = { status: 'Valid', signer: approved, timestamp: true };
  assert.equal(verify.validateWindowsSigner(valid, approved), approved);
  for (const bad of [{ ...valid, status: 'NotSigned' }, { ...valid, signer: '0'.repeat(64) }, { ...valid, timestamp: false }]) {
    assert.throws(() => verify.validateWindowsSigner(bad, approved), /signature/i);
  }
  assert.throws(() => verify.validateWindowsSigner(valid, null), /identity/i);
});
