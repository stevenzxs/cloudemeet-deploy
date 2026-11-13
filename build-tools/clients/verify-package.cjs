const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const crypto = require('node:crypto');
const sha = data => crypto.createHash('sha256').update(data).digest('hex');
function command(exe, args) {
  if (exe.endsWith('.bat')) { args = ['/d', '/s', '/c', '"' + [exe, ...args].map(v => '"' + v.replaceAll('"', '') + '"').join(' ') + '"']; exe = process.env.ComSpec || 'cmd.exe'; }
  const result = spawnSync(exe, args, { encoding: 'utf8', windowsHide: true, maxBuffer: 64 * 1024 * 1024 });
  if (result.error || result.status !== 0) throw Error(`Package inspection failed: ${exe}: ${result.stderr || result.error}`);
  return result.stdout;
}
function ps(script) { return command('powershell.exe', ['-NoProfile', '-Command', script]); }
const quote = value => "'" + value.replaceAll("'", "''") + "'";

function verifyPackage(file, artifact, config, ca, workspace, scratch) {
  const checks = {};
  const check = (name, ok, detail) => {
    if (!ok) throw Error(`Package ${name} check failed: ${file}`);
    checks[name] = { passed: true, detail };
  };
  if (artifact.platform === 'windows') {
    const version = ps(`$i=New-Object -ComObject WindowsInstaller.Installer; $d=$i.OpenDatabase(${quote(file)},0); $v=$d.OpenView('SELECT Value FROM Property WHERE Property = ''ProductVersion'''); $v.Execute(); $r=$v.Fetch(); $r.StringData(1)`).trim();
    check('version', version === config.version, version);
    const out = path.join(scratch, 'msi-payload');
    command('msiexec.exe', ['/a', file, '/qn', `TARGETDIR=${out}`]);
    const files = [];
    const walk = dir => { for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name); if (e.isDirectory()) walk(p); else files.push(p);
    } }; walk(out);
    const asarFile = files.find(p => path.basename(p) === 'app.asar');
    if (!asarFile) throw Error('MSI app.asar missing');
    const asar = require(path.join(workspace, 'jitsi-meet-electron/node_modules/@electron/asar'));
    const env = asar.extractFile(asarFile, 'deployment.env').toString();
    check('origin', env.includes(`SITE_DOMAIN=${config.values.SITE_DOMAIN}\n`)
      && env.includes(`SITE_SCHEME=${config.values.SITE_SCHEME}\n`)
      && env.includes(`SITE_PORT=${config.values.SITE_PORT}\n`), config.origin);
    const trust = JSON.parse(asar.extractFile(asarFile, 'client-trust.json').toString());
    check('ca', trust.origin === config.origin && (ca
      ? sha(asar.extractFile(asarFile, 'client-ca.crt')) === ca.sha256 : trust.caFile === null), ca?.sha256 || 'system trust');
    const exe = files.find(p => /cloudmeet\.exe$/i.test(p));
    if (!exe) throw Error('MSI main executable missing');
    const bytes = fs.readFileSync(exe); const offset = bytes.readUInt32LE(0x3c);
    check('architecture', bytes.readUInt16LE(offset + 4) === 0x8664 && artifact.architecture === 'x64', 'PE AMD64');
    const signatures = [file, exe].map(p => ({ file: path.basename(p), status: ps(`(Get-AuthenticodeSignature ${quote(p)}).Status`).trim() }));
    check('signature', signatures.every(s => ['Valid', 'NotSigned'].includes(s.status)), JSON.stringify(signatures));
  } else {
    const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT;
    const tools = fs.readdirSync(path.join(sdk, 'build-tools')).sort((a,b) => a.localeCompare(b, undefined, { numeric: true })).reverse()
      .map(n => path.join(sdk, 'build-tools', n)).find(p => fs.existsSync(path.join(p, 'apksigner.bat')));
    const badging = command(path.join(tools, 'aapt.exe'), ['dump', 'badging', file]);
    check('version', badging.includes(`versionName='${config.version}'`) && badging.includes(`versionCode='${require('./core.cjs').versionCode(config.version)}'`), config.version);
    const native = /native-code: (.*)/.exec(badging);
    const abis = native ? [...native[1].matchAll(/'([^']+)'/g)].map(m => m[1]).sort() : [];
    check('architecture', JSON.stringify(abis) === JSON.stringify([...artifact.architectures].sort()) && !abis.includes('x86'), abis.join(','));
    const signature = command(path.join(tools, 'apksigner.bat'), ['verify', '--verbose', '--print-certs', file]);
    check('signature', signature.includes('Verifies'), signature);
    const analyzer = path.join(sdk, 'cmdline-tools/latest/bin/apkanalyzer.bat');
    const listing = command(analyzer, ['files', 'list', file]).split(/\r?\n/).map(s => s.trim().replace(/^\//, ''));
    let origin = false; let domain = false;
    for (const name of listing.filter(n => n.endsWith('.xml') && n !== 'AndroidManifest.xml')) {
      const xml = command(analyzer, ['resources', 'xml', '--file', name, file]);
      if (xml.includes('SERVER_URL') && xml.includes(config.origin)) origin = true;
      if (xml.includes(config.values.SITE_DOMAIN) && xml.includes('trust-anchors')) domain = true;
      if (origin && domain) break;
    }
    check('origin', origin, 'Packaged managed SERVER_URL');
    const caFound = !ca || command('python', ['-B', '-c',
      'import zipfile,hashlib,sys; z=zipfile.ZipFile(sys.argv[1]); print(any(hashlib.sha256(z.read(n)).hexdigest()==sys.argv[2] for n in z.namelist() if not n.endswith("/") and z.getinfo(n).file_size<65536))', file, ca.sha256]).trim() === 'True';
    check('ca', caFound && (!ca || domain), ca?.sha256 || 'system trust');
  }
  return checks;
}
module.exports = { verifyPackage };
