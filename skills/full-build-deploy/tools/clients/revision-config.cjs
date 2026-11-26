// Consume the canonical Python contract rather than implementing a second ledger.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

function loadAssignment(file, root, target, env = process.env) {
  if (!file || !env.GITHUB_SHA || !env.GITHUB_RUN_ID || !env.GITHUB_RUN_ATTEMPT) throw Error('Bound Actions version assignment required');
  const record = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!record.request || !record.versions) throw Error('Invalid version assignment');
  if (record.request.configuration_sha !== env.GITHUB_SHA || record.request.run_id !== env.GITHUB_RUN_ID) {
    throw Error('Version assignment does not match this run');
  }
  if (target === 'all' && !record.request.scope.includes('android')) throw Error('Client scope mismatch');
  const skillRoot = path.resolve(__dirname, '..', '..');
  const sources = JSON.parse(fs.readFileSync(path.join(skillRoot, 'sources.json'), 'utf8'));
  for (const [name, identity] of Object.entries(sources.clients)) {
    if (record.request.sources[name] !== identity.commit) throw Error('Client source allocation mismatch');
    const actual = spawnSync('git', ['-C', path.join(root, name === 'electron' ? 'jitsi-meet-electron' : 'jm'), 'rev-parse', 'HEAD'], { encoding: 'utf8' });
    if (actual.status !== 0 || actual.stdout.trim() !== identity.commit) throw Error('Client checkout differs from allocation');
  }
  return record;
}

function forgeWrapper(project, assignment) {
  const v = assignment.versions;
  // electron-forge 7 resolves forge.config.{js,...} BEFORE the package.json
  // config.forge path string (forge docs: a path string is used only when no
  // forge.config.* file exists). The build therefore writes the original
  // source config to forge.config.cloudmeet-base.cjs and places this wrapper
  // at forge.config.js, which forge is guaranteed to pick up.
  return `const path = require('node:path');
const root = ${JSON.stringify(project)};
const config = require(path.join(root, 'forge.config.cloudmeet-base.cjs'));
// Approved unsigned Windows delivery: never load or call signing tools.
delete config.packagerConfig.windowsSign;
delete config.hooks.postPackage;
config.packagerConfig = { ...config.packagerConfig, appVersion: ${JSON.stringify(v.msi_version)}, buildVersion: ${JSON.stringify(v.pe_version)} };
config.packagerConfig.ignore = [...config.packagerConfig.ignore, /^\\/forge\\.config\\.cloudmeet-base\\.cjs$/];
// User approved 2026-11-20: OpenVPN is removed from the package; the vendor
// payload verification and unified MSI assembly are retired. The reviewed
// maker-wix MSI is delivered unsigned and becomes the final artifact.
config.hooks.preMake = async () => {};
config.makers = config.makers.map(m => {
  if (m.name !== '@electron-forge/maker-wix') return m;
  const beforeCreate = m.config?.beforeCreate;
  return { ...m, config: { ...m.config, version: ${JSON.stringify(v.msi_version)},
    beforeCreate: async function (creator) {
      if (beforeCreate) await beforeCreate.call(this, creator);
      // electron-wix-msi appends .0 even to a three-field version. Pin the
      // allocated MSI ProductVersion before create(), not by editing a built MSI
      // or relaxing the final strict version check. PE buildVersion stays separate.
      creator.windowsCompliantVersion = ${JSON.stringify(v.msi_version)};
    },
  } };
});
config.hooks.postMake = async (_config, results) => results;
module.exports = config;
`;
}
module.exports = { loadAssignment, forgeWrapper };
