const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const file = path.join(__dirname, '../patches/web/host-control-custom-config.js');
function run(config) {
  const context = { config };
  const code = fs.readFileSync(file, 'utf8');
  vm.runInNewContext(code, context);
  vm.runInNewContext(code, context);
  return config;
}
test('disabled deployment never advertises transfer', () => {
  assert.equal(run({}).customParticipantMenuButtons, undefined);
});
test('enabled persistent config adds once and preserves unrelated actions', () => {
  const config = run({ cloudmeetHostTransferEnabled: true,
    customParticipantMenuButtons: [{ id: 'other' }] });
  assert.deepEqual(Array.from(config.customParticipantMenuButtons, b => b.id), ['other', 'cloudmeet-transfer-host']);
});
test('truthy strings do not enable the feature', () => {
  assert.equal(run({ cloudmeetHostTransferEnabled: 'true' }).customParticipantMenuButtons, undefined);
});
