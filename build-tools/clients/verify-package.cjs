const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { matchesCa } = require('./ca-config.cjs');
function command(exe, args) {
  let verbatim = false;
  if (exe.endsWith('.bat')) { args = ['/d', '/s', '/c', '"' + [exe, ...args].map(v => '"' + v.replaceAll('"', '') + '"').join(' ') + '"']; exe = process.env.ComSpec || 'cmd.exe'; verbatim = true; }
  const result = spawnSync(exe, args, { encoding: 'utf8', windowsHide: true, maxBuffer: 64 * 1024 * 1024, windowsVerbatimArguments: verbatim });
  if (result.error || result.status !== 0) throw Error(`Package inspection failed: ${exe}: ${result.stderr || result.error}`);
  return result.stdout;
}
const ps = script => command('powershell.exe', ['-NoProfile', '-Command', script]);
const PY = process.platform === 'win32' ? 'python' : 'python3';
const sdkTool = (dir, base) => path.join(dir, process.platform === 'win32'
  ? (base === 'aapt' ? 'aapt.exe' : `${base}.bat`) : base);
const quote = value => "'" + value.replaceAll("'", "''") + "'";

function validateAndroidSigner(output, expected) {
  const signers = [...output.matchAll(/^Signer #\d+ certificate SHA-256 digest:\s*([0-9a-f:]+)\s*$/gim)]
    .map(m => m[1].replaceAll(':', '').toLowerCase());
  if (!output.includes('Verifies')) throw Error('Android package signature does not verify');
  if (signers.length !== 1) throw Error(`Expected exactly one APK signer certificate, apksigner reported ${signers.length}`);
  if (!/^[0-9a-f]{64}$/.test(expected || '')) throw Error('Approved Android identity fingerprint required');
  if (signers[0] !== expected) throw Error(`Approved Android signer mismatch: APK signer ${signers[0]} != policy ${expected}`);
  return signers[0];
}
function validateWindowsSigner(value, expected) {
  if (!/^[0-9a-f]{64}$/.test(expected || '')) throw Error('Approved Windows identity required');
  if (value.status !== 'Valid' || value.signer !== expected || value.timestamp !== true) throw Error('Approved timestamped Windows signature required');
  return expected;
}

function inspectAndroidResources(file, analyzer, aapt, config, requireCa, run = command) {
  const table = run(aapt, ['dump', 'resources', file]);
  const ids = new Map();
  for (const m of table.matchAll(/spec resource (0x[0-9a-f]+) [^\s:]+:([^\s:]+):/gi)) ids.set(m[1].toLowerCase(), '@' + m[2]);
  const normalize = xml => xml.replace(/@ref\/(0x[0-9a-f]+)/gi, (all, id) => ids.get(id.toLowerCase()) || all);
  const member = (type, name) => {
    const value = run(analyzer, ['resources', 'value', '--config', 'default', '--name', name, '--type', type, file]).trim();
    if (!/^res\/[a-zA-Z0-9_./-]+$/.test(value) || value.split('/').includes('..')) throw Error('Unsafe Android resource member');
    return value;
  };
  const xml = name => normalize(run(analyzer, ['resources', 'xml', '--file', member('xml', name), file]));
  validateAndroidResources(normalize(run(analyzer, ['manifest', 'print', file])),
    xml('app_restrictions'), requireCa ? xml('network_security_config') : '', config, requireCa);
  return requireCa ? member('raw', 'cloudmeet_client_ca') : null;
}

function validateAndroidResources(manifest, restrictions, trust, config, requireCa) {
  const script = `import sys,json,xml.etree.ElementTree as E
d=json.loads(sys.argv[1]); ns='{http://schemas.android.com/apk/res/android}'
m=E.fromstring(d['manifest']); app=m if m.tag=='application' else m.find('application')
assert app is not None
assert any(x.get(ns+'name')=='android.content.APP_RESTRICTIONS' and x.get(ns+'resource')=='@xml/app_restrictions' for x in app.findall('meta-data'))
r=E.fromstring(d['restrictions'])
matches=[x for x in r.iter('restriction') if x.get(ns+'key')=='SERVER_URL']
assert len(matches)==1 and matches[0].get(ns+'defaultValue')==d['origin']
if d['requireCa']:
 assert app.get(ns+'networkSecurityConfig')=='@xml/network_security_config'
 t=E.fromstring(d['trust'])
 rules=[x for x in t.iter('domain-config') if any((v.text or '').strip()==d['host'] and v.get('includeSubdomains','false')=='false' for v in x.findall('domain'))]
 assert len(rules)==1
 assert any(x.get('src')=='@raw/cloudmeet_client_ca' for x in rules[0].findall('./trust-anchors/certificates'))
print('verified')`;
  const result = command(PY, ['-B', '-c', script, JSON.stringify({ manifest, restrictions, trust,
    origin: config.origin, host: config.values.SITE_DOMAIN, requireCa })]);
  if (result.trim() !== 'verified') throw Error('Android resource reference validation failed');
  return true;
}

function verifyPackage(file, artifact, config, ca, workspace, scratch) {
  const checks = {};
  const check = (name, ok, detail) => {
    if (!ok) throw Error(`Package ${name} check failed: ${file}`);
    checks[name] = { passed: true, detail };
  };
  if (artifact.platform === 'windows') {
    const version = ps(`$i=New-Object -ComObject WindowsInstaller.Installer; $d=$i.OpenDatabase(${quote(file)},0); $v=$d.OpenView('SELECT Value FROM Property WHERE Property = ''ProductVersion'''); $v.Execute(); $r=$v.Fetch(); $r.StringData(1)`).trim();
    check('version', Boolean(config.assignment) && version === config.msiVersion, version);
    const out = path.join(scratch, 'msi-payload');
    command('msiexec.exe', ['/a', file, '/qn', `TARGETDIR=${out}`]);
    const files = [];
    const walk = dir => { for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name); if (e.isDirectory()) walk(p); else files.push(p);
    } }; walk(out);
    const asarFile = files.find(p => path.basename(p) === 'app.asar');
    if (!asarFile) throw Error('MSI app.asar missing');
    const asar = require(path.join(workspace, 'jitsi-meet-electron/node_modules/@electron/asar'));
    const metadata = JSON.parse(asar.extractFile(asarFile, 'package.json').toString());
    const assignment = JSON.parse(asar.extractFile(asarFile, 'cloudmeet-version.json').toString());
    check('displayVersion', metadata.version === config.version
      && JSON.stringify(assignment) === JSON.stringify(config.assignment), config.version);
    const env = asar.extractFile(asarFile, 'deployment.env').toString();
    const trust = JSON.parse(asar.extractFile(asarFile, 'client-trust.json').toString());
    require('./network-audit.cjs').auditGenerated('electron', config, { deployment: env, trust });
    check('origin', true, config.origin);
    check('ca', trust.origin === config.origin && (ca
      ? matchesCa(asar.extractFile(asarFile, 'client-ca.crt'), ca) : trust.caFile === null), ca?.sha256 || 'system trust');
    const exe = files.find(p => /cloudmeet\.exe$/i.test(p));
    if (!exe) throw Error('MSI main executable missing');
    const peVersion = ps(`(Get-Item -LiteralPath ${quote(exe)}).VersionInfo.FileVersion`).trim();
    check('peVersion', peVersion === config.peVersion, peVersion);
    const bytes = fs.readFileSync(exe); const offset = bytes.readUInt32LE(0x3c);
    check('architecture', bytes.readUInt16LE(offset + 4) === 0x8664 && artifact.architecture === 'x64', 'PE AMD64');
    const signing = require('./signing.cjs');
    const identity = signing.windowsIdentity();
    const signatures = [file, exe].map(p => {
      signing.verify(p); // SignTool verifies all signatures and RFC3161 timestamp.
      const value = JSON.parse(ps(`$s=Get-AuthenticodeSignature -LiteralPath ${quote(p)}; $h=[Security.Cryptography.SHA256]::Create(); try { $fingerprint=([BitConverter]::ToString($h.ComputeHash($s.SignerCertificate.RawData))).Replace('-','').ToLowerInvariant() } finally { $h.Dispose() }; @{status=$s.Status.ToString();signer=$fingerprint;timestamp=($null -ne $s.TimeStamperCertificate)} | ConvertTo-Json -Compress`));
      validateWindowsSigner(value, identity.fingerprint);
      return { file: path.basename(p), ...value };
    });
    check('signature', true, JSON.stringify(signatures));
  } else {
    const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT;
    const tools = fs.readdirSync(path.join(sdk, 'build-tools')).sort((a,b) => a.localeCompare(b, undefined, { numeric: true })).reverse()
      .map(n => path.join(sdk, 'build-tools', n)).find(p => fs.existsSync(sdkTool(p, 'apksigner')));
    const badging = command(sdkTool(tools, 'aapt'), ['dump', 'badging', file]);
    check('version', badging.includes(`versionName='${config.version}'`) && badging.includes(`versionCode='${require('./core.cjs').versionCode(config.version)}'`), config.version);
    const allocation = command(PY, ['-B', '-c',
      'import zipfile,sys; print(zipfile.ZipFile(sys.argv[1]).read("assets/cloudmeet-version.json").decode())', file]);
    check('versionAssignment', Boolean(config.assignment)
      && JSON.stringify(JSON.parse(allocation)) === JSON.stringify(config.assignment), config.version);
    const native = /native-code: (.*)/.exec(badging);
    const abis = native ? [...native[1].matchAll(/'([^']+)'/g)].map(m => m[1]).sort() : [];
    check('architecture', JSON.stringify(abis) === JSON.stringify([...artifact.architectures].sort()) && !abis.includes('x86'), abis.join(','));
    const signature = command(sdkTool(tools, 'apksigner'), ['verify', '--verbose', '--print-certs', file]);
    check('signature', true, validateAndroidSigner(signature, require('./signing.cjs').policy.android_certificate_der_sha256));
    const analyzer = sdkTool(path.join(sdk, 'cmdline-tools/latest/bin'), 'apkanalyzer');
    const caMember = inspectAndroidResources(file, analyzer, sdkTool(tools, 'aapt'), config, Boolean(ca));
    check('origin', true, 'Manifest-selected managed SERVER_URL; runtime/profile overrides not verified');
    const caFound = !ca || command(PY, ['-B', '-c',
      'import zipfile,hashlib,sys,base64,re; z=zipfile.ZipFile(sys.argv[1]); want=sys.argv[2]; ok=False\n'
      + 'for n in [sys.argv[3]]:\n'
      + '    i=z.getinfo(n)\n'
      + '    if n.endswith("/") or i.file_size>=65536: continue\n'
      + '    d=z.read(n)\n'
      + '    m=re.search(rb"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----", d, re.S)\n'
      + '    try: der=base64.b64decode(re.sub(rb"\\s", b"", m.group(1))) if m else d\n'
      + '    except Exception: continue\n'
      + '    if hashlib.sha256(der).hexdigest()==want: ok=True; break\n'
      + 'print(ok)', file, ca?.sha256 || '', caMember || '']).trim() === 'True';
    check('ca', caFound, ca?.sha256 || 'system trust');
  }
  return checks;
}
module.exports = { verifyPackage, validateAndroidResources, inspectAndroidResources, validateAndroidSigner, validateWindowsSigner };
