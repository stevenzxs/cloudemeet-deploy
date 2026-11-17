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
      ? matchesCa(asar.extractFile(asarFile, 'client-ca.crt'), ca) : trust.caFile === null), ca?.sha256 || 'system trust');
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
    const scan = JSON.parse(command('python', ['-B', '-c',
      'import zipfile,json,sys; z=zipfile.ZipFile(sys.argv[1]); o=sys.argv[2].encode(); h=sys.argv[3].encode(); r={"origin":[],"domain":[]}\n'
      + 'for n in z.namelist():\n'
      + '    if not n.endswith(".xml") or n=="AndroidManifest.xml": continue\n'
      + '    d=z.read(n)\n'
      + '    if b"SERVER_URL" in d and o in d: r["origin"].append(n)\n'
      + '    if h in d and b"trust-anchors" in d: r["domain"].append(n)\n'
      + 'print(json.dumps(r))', file, config.origin, config.values.SITE_DOMAIN]));
    const readXml = name => {
      const raw = command('python', ['-B', '-c',
        'import zipfile,sys; sys.stdout.buffer.write(zipfile.ZipFile(sys.argv[1]).read(sys.argv[2]))', file, name]);
      // apkanalyzer omits element text (e.g. <domain> values); raw member bytes keep the AXML string pool.
      try { return command(analyzer, ['resources', 'xml', '--file', name, file]) + '\n' + raw; }
      catch { return raw; }
    };
    let origin = false; let domain = false;
    for (const name of scan.origin) { const xml = readXml(name); if (xml.includes('SERVER_URL') && xml.includes(config.origin)) { origin = true; break; } }
    for (const name of scan.domain) { const xml = readXml(name); if (xml.includes(config.values.SITE_DOMAIN) && xml.includes('trust-anchors')) { domain = true; break; } }
    check('origin', origin, 'Packaged managed SERVER_URL');
    const caFound = !ca || command('python', ['-B', '-c',
      'import zipfile,hashlib,sys,base64,re; z=zipfile.ZipFile(sys.argv[1]); want=sys.argv[2]; ok=False\n'
      + 'for n in z.namelist():\n'
      + '    i=z.getinfo(n)\n'
      + '    if n.endswith("/") or i.file_size>=65536: continue\n'
      + '    d=z.read(n)\n'
      + '    m=re.search(rb"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----", d, re.S)\n'
      + '    try: der=base64.b64decode(re.sub(rb"\\s", b"", m.group(1))) if m else d\n'
      + '    except Exception: continue\n'
      + '    if hashlib.sha256(der).hexdigest()==want: ok=True; break\n'
      + 'print(ok)', file, ca?.sha256 || '']).trim() === 'True';
    check('ca', caFound && (!ca || domain), ca?.sha256 || 'system trust');
  }
  return checks;
}
module.exports = { verifyPackage };
