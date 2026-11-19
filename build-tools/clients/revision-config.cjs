// Consume the canonical Python contract rather than implementing a second ledger.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

function loadAssignment(file, root, target, env = process.env) {
  if (!file || !env.GITHUB_SHA || !env.GITHUB_RUN_ID || !env.GITHUB_RUN_ATTEMPT) throw Error('Bound Actions version assignment required');
  const result = spawnSync('python', ['-B', path.join(root, 'deploy/build-tools/revision_versions.py'),
    '--record', file, '--policy', path.join(root, 'deploy/config/version-policy.json'),
    '--sha', env.GITHUB_SHA, '--run-id', env.GITHUB_RUN_ID, '--attempt', env.GITHUB_RUN_ATTEMPT,
    '--scope', target === 'all' ? 'electron' : target], { encoding: 'utf8' });
  if (result.status !== 0) throw Error('Version allocation validation failed; review policy/history/Run binding');
  const record = JSON.parse(result.stdout);
  if (target === 'all' && !record.request.scope.includes('android')) throw Error('Client scope mismatch');
  const sources = JSON.parse(fs.readFileSync(path.join(root, 'deploy/build-tools/sources.json'), 'utf8'));
  for (const [name, identity] of Object.entries(sources.clients)) {
    if (record.request.sources[name] !== identity.commit) throw Error('Client source allocation mismatch');
    const actual = spawnSync('git', ['-C', path.join(root, name === 'electron' ? 'jitsi-meet-electron' : 'jm'), 'rev-parse', 'HEAD'], { encoding: 'utf8' });
    if (actual.status !== 0 || actual.stdout.trim() !== identity.commit) throw Error('Client checkout differs from allocation');
  }
  return record;
}

function forgeWrapper(project, assignment) {
  const v = assignment.versions;
  return `const path = require('node:path');
const root = ${JSON.stringify(project)};
const config = require(path.join(root, 'forge.config.js'));
config.packagerConfig = { ...config.packagerConfig, appVersion: ${JSON.stringify(v.msi_version)}, buildVersion: ${JSON.stringify(v.pe_version)} };
config.packagerConfig.ignore = [...config.packagerConfig.ignore, /^\\/cloudmeet\\.forge\\.cjs$/];
config.makers = config.makers.map(m => m.name === '@electron-forge/maker-wix' ? { ...m, config: { ...m.config, version: ${JSON.stringify(v.msi_version)} } } : m);
config.hooks.postMake = async (_config, results) => require(path.join(root, 'scripts/unified-msi.cjs')).buildUnifiedMsi(results, ${JSON.stringify(v.msi_version)}, await require(path.join(root, 'scripts/build-openvpn-bundle.cjs')).verifyPayload());
module.exports = config;
`;
}
module.exports = { loadAssignment, forgeWrapper };
