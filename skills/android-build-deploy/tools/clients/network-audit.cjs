const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

function inventorySources(project, paths) {
  const endpoints = [], inputs = {};
  const walk = file => {
    if (!fs.existsSync(file) || fs.lstatSync(file).isSymbolicLink()) return;
    if (fs.statSync(file).isDirectory()) {
      if (/^(node_modules|build|out|test|tests|__tests__|\.git)$/.test(path.basename(file))) return;
      for (const name of fs.readdirSync(file)) walk(path.join(file, name));
      return;
    }
    if (!/\.(js|ts|tsx|json|xml|java|kt|env|gradle)$/.test(file) || /lock\.json$/.test(file)) return;
    const bytes = fs.readFileSync(file);
    const relative = path.relative(project, file).replaceAll('\\', '/');
    inputs[relative] = hash(bytes);
    bytes.toString('utf8').split(/\r?\n/).forEach((line, index) => {
      for (const match of line.matchAll(/(?:https?|wss?):\/\/[^\s"'<>`\\]+/g)) {
        try {
          const url = new URL(match[0]);
          endpoints.push({ source: `${relative}:${index + 1}`, value: `${url.protocol}//${url.host}${url.pathname}`,
            status: 'review-required', reason: 'Source literal; effective generated settings checked separately' });
        } catch { /* dynamic URL fragments are not parsed as literal endpoints */ }
      }
    });
  };
  paths.forEach(p => walk(path.join(project, p)));
  return { endpoints, inputSha256: inputs, limitation: 'Source literals are inventory, not proof of runtime selection. User profile/managed overrides require target-side verification.' };
}

function auditGenerated(target, config, input) {
  const warnings = [];
  if (target === 'electron') {
    const actual = {};
    for (const line of input.deployment.trim().split(/\r?\n/)) {
      const match = /^(SITE_DOMAIN|SITE_SCHEME|SITE_PORT)=(.+)$/.exec(line);
      if (!match) throw Error('Generated Electron configuration invalid');
      if (Object.hasOwn(actual, match[1])) {
        if (actual[match[1]] !== match[2]) throw Error(`Generated Electron configuration conflicts: ${match[1]}`);
        warnings.push(`Equivalent duplicate Electron key: ${match[1]}`);
      }
      actual[match[1]] = match[2];
    }
    if (['SITE_DOMAIN', 'SITE_SCHEME', 'SITE_PORT'].some(k => actual[k] !== config.values[k])
        || input.trust.origin !== config.origin) throw Error('Generated Electron origin mismatch');
  } else {
    if (input.deployment.origin !== config.origin) throw Error('Generated Android origin mismatch');
    if (!input.restrictions.includes(`android:key="SERVER_URL" android:defaultValue="${config.origin}"`)) {
      throw Error('Generated Android managed origin mismatch');
    }
    if (input.trust && (!input.trust.includes(`<domain includeSubdomains="false">${config.values.SITE_DOMAIN}</domain>`)
        || !input.trust.includes(config.tlsMode === 'caddy-public-acme' ? 'src="system"' : '@raw/cloudmeet_client_ca'))) throw Error('Generated Android trust scope mismatch');
  }
  return { phase: 'generated', status: 'pass', target, warnings, parameters: [
      ...Object.entries(config.values).filter(([k]) => ['SITE_DOMAIN', 'SITE_SCHEME', 'SITE_PORT'].includes(k))
      .map(([name, value]) => ({ name, value, source: 'batch-origin-contract', consumer: target })),
    ...Object.entries({ origin: config.origin, desktopUrl: config.desktopUrl,
      api: `${config.origin}/mapi/`, bosh: `${config.origin}/http-bind`,
      websocket: `${config.origin.replace(/^http/, 'ws')}/xmpp-websocket` })
      .map(([name, value]) => ({ name, value, source: 'derived from batch-origin-contract', consumer: target }))
  ], unverified: ['endpoint TLS connectivity', 'installation', 'meeting media'] };
}

function auditPackages(manifest) {
  const common = ['origin', 'ca', 'architecture', 'version'];
  if (!manifest.artifacts.length || manifest.artifacts.some(a => {
    const required = a.platform === 'windows' ? common : [...common, 'signature'];
    const signing = a.checks?.signing;
    return required.some(k => a.checks?.[k]?.passed !== true)
      || (a.platform === 'windows' && (a.checks.signature !== undefined
        || signing?.required !== false || signing?.status !== 'unsigned'
        || typeof signing.detail !== 'string' || !signing.detail.startsWith('UNSIGNED EXE/MSI;')));
  })) {
    throw Error('Post-package network audit incomplete');
  }
  return { phase: 'final-packages', status: 'pass', origin: manifest.origin,
    artifacts: manifest.artifacts.map(a => ({ file: a.file, sha256: a.sha256, checks: a.checks })),
    unverified: ['endpoint TLS connectivity', 'installation', 'meeting media'] };
}

function writeAudit(directory, name, report, workspace, configFile = path.join(__dirname, '../../config/client.env'), originContract = null) {
  const git = cwd => {
    const r = spawnSync('git', ['-C', cwd, 'rev-parse', 'HEAD'], { encoding: 'utf8' });
    return r.status === 0 ? r.stdout.trim() : 'unavailable';
  };
  const config = configFile;
  report = { schema: 1, createdAt: new Date().toISOString(),
    configSha: git(path.join(workspace, 'deploy')),
    sources: { electron: git(path.join(workspace, 'jitsi-meet-electron')), android: git(path.join(workspace, 'jm')) },
    clientEnvSha256: fs.existsSync(config) ? hash(fs.readFileSync(config)) : 'unavailable',
    ...(originContract ? { originContract } : {}),
    runId: process.env.GITHUB_RUN_ID || null, attempt: process.env.GITHUB_RUN_ATTEMPT || null, ...report };
  fs.mkdirSync(directory, { recursive: true });
  const json = JSON.stringify(report, null, 2) + '\n';
  fs.writeFileSync(path.join(directory, name + '.json'), json);
  fs.writeFileSync(path.join(directory, name + '.md'), `# Client network audit: ${name}\n\nJSON SHA256: ${hash(json)}\n\n\`\`\`json\n${json}\`\`\`\n`);
  return report;
}
function stageReports(source, destination) {
  for (const name of fs.readdirSync(source).filter(n => /^network-.*\.(json|md)$/.test(n))) {
    const from = path.join(source, name), to = path.join(destination, name);
    if (!fs.lstatSync(from).isFile()) throw Error('Audit report must be a regular file');
    fs.copyFileSync(from, to, fs.constants.COPYFILE_EXCL);
    if (hash(fs.readFileSync(from)) !== hash(fs.readFileSync(to))) throw Error('Audit staging digest mismatch');
  }
}
module.exports = { auditGenerated, auditPackages, writeAudit, inventorySources, stageReports };
