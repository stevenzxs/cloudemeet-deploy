const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
test('MSI workflow routes to MSI-owned allocation and builder', () => {
  const text = fs.readFileSync(path.join(__dirname, '../../../../../.github/workflows/build-msi.yml'), 'utf8');
  assert.match(text, /workflow_dispatch:/);
  assert.doesNotMatch(text, /pull_request:/);
  const jobs = text.split('\njobs:\n')[1];
  assert.match(jobs, /version:\n    permissions:\n      contents: write\n    uses: .\/\.github\/workflows\/allocate-msi-revision.yml/);
  assert.ok((text.match(/contents: write/g) || []).length >= 1);
  assert.doesNotMatch(jobs.slice(jobs.indexOf('\n  build:')).split('\n  publish:')[0], /contents: write/);
  assert.match(text, /deploy\/skills\/msi-build-deploy\/tools\/clients\/build-clients\.cjs --target electron/);
  assert.match(text, /Build and verify packages/);
  for (const line of text.split('\n').filter(x => x.includes('uses:') && !x.includes('uses: ./.github/workflows/'))) {
    assert.match(line, /@[0-9a-f]{40}\s*$/);
  }
});
test('MSI checkout matches its source lock', () => {
  const root = path.join(__dirname, '../../../../../');
  const text = fs.readFileSync(path.join(root, '.github/workflows/build-msi.yml'), 'utf8');
  const sources = JSON.parse(fs.readFileSync(path.join(root, 'skills/msi-build-deploy/sources.json'), 'utf8'));
  assert.equal(sources.clients.electron.repository, 'https://github.com/stevenzxs/jitsi-meet-electron.git');
  for (const source of [sources.clients.electron]) {
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
