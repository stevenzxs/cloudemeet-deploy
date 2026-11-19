// Invocation adapter only. Signing implementation/identities belong to the certificate repository.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '../../..');
const policy = JSON.parse(fs.readFileSync(path.join(root, 'deploy/config/signing-policy.json'), 'utf8'));
const certificateRoot = path.join(root, 'cloudmeet-certificates');
function windowsIdentity() {
  const sha = spawnSync('git', ['-C', certificateRoot, 'rev-parse', 'HEAD'], { encoding: 'utf8' });
  if (sha.status !== 0 || sha.stdout.trim() !== policy.commit) throw Error('Reviewed certificate tool checkout required');
  const dirty = spawnSync('git', ['-C', certificateRoot, 'status', '--porcelain', '--untracked-files=all'], { encoding: 'utf8' });
  if (dirty.status !== 0 || dirty.stdout.trim()) throw Error('Certificate tool checkout must be clean');
  const file = path.join(certificateRoot, policy.windows_identity);
  if (!fs.existsSync(file)) throw Error('Approved Windows public identity missing: windows/public/identity.json in certificate repository');
  const identity = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!/^[0-9a-f]{64}$/.test(identity.certificate_der_sha256 || '')) throw Error('Approved Windows identity fingerprint required');
  return { file, fingerprint: identity.certificate_der_sha256 };
}
function invoke(script, file) {
  const identity = windowsIdentity();
  if (!process.env.SIGNTOOL_PATH || !fs.existsSync(process.env.SIGNTOOL_PATH)) throw Error('Verified Windows SignTool required');
  const args = ['-NoProfile', '-File', path.join(certificateRoot, 'windows', script),
    '-Path', file, '-Identity', identity.file, '-SignTool', process.env.SIGNTOOL_PATH];
  if (script === 'sign-package.ps1') args.push('-TimestampUrl', policy.timestamp_url);
  const result = spawnSync('powershell.exe', args, { stdio: 'inherit', windowsHide: true });
  if (result.error || result.status !== 0) throw Error('Approved Windows signing/verification failed');
}
function sign(file) { invoke('sign-package.ps1', file); }
function verify(file) { invoke('verify-signature.ps1', file); }
module.exports = { policy, windowsIdentity, sign, verify };
