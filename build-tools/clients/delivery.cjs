const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

function deliver(manifest, root) {
  const required = ['version', 'architecture', 'origin', 'ca', 'signature'];
  // Validate the entire batch before creating any release directory.
  for (const artifact of manifest.artifacts) {
    const checks = artifact.checks;
    if (!checks || required.some(name => checks[name]?.passed !== true)) {
      throw Error(`Package checks incomplete: ${artifact.file}; required: ${required.join(', ')}`);
    }
    if (hash(path.join(manifest.candidate, artifact.file)) !== artifact.sha256) throw Error('Candidate digest changed');
    if (!['windows', 'android'].includes(artifact.platform)
        || !(artifact.platform === 'windows' ? ['x64', 'arm64']
          : ['armeabi-v7a', 'arm64-v8a', 'x86_64', 'universal']).includes(artifact.architecture)) {
      throw Error('Invalid client delivery platform/architecture');
    }
  }
  if (!manifest.artifacts.length) throw Error('No client artifacts');
  const batch = `${manifest.version}-${path.basename(manifest.candidate)}`;
  const destinations = manifest.artifacts.map(a => path.join(root, a.platform, a.architecture, batch));
  if (destinations.some(p => fs.existsSync(p))) throw Error('Refusing existing delivery batch');
  return manifest.artifacts.map((artifact, index) => {
    const destination = destinations[index];
    fs.mkdirSync(destination, { recursive: true });
    const file = path.basename(artifact.file);
    fs.copyFileSync(path.join(manifest.candidate, artifact.file), path.join(destination, file));
    if (hash(path.join(destination, file)) !== artifact.sha256) throw Error('Delivery digest mismatch');
    const evidence = { ...manifest, artifacts: [{ ...artifact, file }], status: 'packaged-delivered',
      acceptance: 'Package checks only; installation, endpoint TLS and meeting/media acceptance not performed.' };
    fs.writeFileSync(path.join(destination, 'build-evidence.json'), JSON.stringify(evidence, null, 2) + '\n');
    fs.writeFileSync(path.join(destination, 'README.txt'), `CloudMeet ${manifest.version}\nOrigin: ${manifest.origin}\n`
      + `Architectures: ${artifact.architectures.join(', ')}\nSignature: ${artifact.checks.signature.detail}\n`
      + evidence.acceptance + '\n');
    const sums = fs.readdirSync(destination).sort().map(name => `${hash(path.join(destination, name))}  ${name}\n`).join('');
    fs.writeFileSync(path.join(destination, 'SHA256SUMS'), sums);
    return { directory: destination, file: path.join(destination, file), sha256: artifact.sha256,
      checksumManifestSha256: hash(path.join(destination, 'SHA256SUMS')) };
  });
}

module.exports = { deliver };
