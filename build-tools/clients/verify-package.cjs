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

function inspectWindowsShortcuts(file, run = ps) {
  const rows = JSON.parse(run(`[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$ErrorActionPreference = 'Stop'
$i = New-Object -ComObject WindowsInstaller.Installer
$d = $i.OpenDatabase(${quote(file)}, 0)
$v = $d.OpenView('SELECT Shortcut, Directory_, Name, Target FROM Shortcut')
$v.Execute()
$rows = @()
while ($r = $v.Fetch()) {
  $rows += [PSCustomObject]@{ id=$r.StringData(1); directory=$r.StringData(2); name=$r.StringData(3); target=$r.StringData(4) }
}
ConvertTo-Json -InputObject @($rows) -Compress`));
  const expected = [['MyDesktopShortcut', 'DesktopFolder'],
    ['ApplicationStartMenuShortcut', 'ApplicationProgramsFolder']];
  if (!Array.isArray(rows) || rows.length !== expected.length || expected.some(([id, directory]) => {
    const matches = rows.filter(row => row.id === id);
    const row = matches[0];
    return matches.length !== 1 || row.directory !== directory || typeof row.name !== 'string'
      || row.name.split('|').at(-1) !== '云会议'
      || row.target !== '[APPLICATIONROOTDIRECTORY]cloudmeet.exe';
  })) throw Error('MSI desktop/start menu shortcut name or target mismatch');
  return rows;
}

function validateAndroidSigner(output, expected) {
  // apksigner <= 36 prints "Signer #1 certificate SHA-256 digest:"; build-tools
  // 37 prints scheme-prefixed "V2 Signer: certificate SHA-256 digest:". Tolerate
  // both, uppercase/colon variants and SHA256/SHA-256 spellings.
  const signers = [...output.matchAll(/^(?:V\d+(?:\.\d+)? Signer:|Signer #\d+) certificate SHA-?256 digest:\s*([0-9a-fA-F:]+)\s*$/gim)]
    .map(m => m[1].replaceAll(':', '').toLowerCase());
  if (!output.includes('Verifies')) throw Error('Android package signature does not verify');
  if (signers.length !== 1) throw Error(`Expected exactly one APK signer certificate, apksigner reported ${signers.length}; output excerpt: ${JSON.stringify(output.replace(/[A-Za-z0-9+/=]{48,}/g, '<b64>').slice(0, 500))}`);
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
  const inspectTrust = requireCa || config.tlsMode === 'caddy-public-acme';
  const trustMember = inspectTrust ? member('xml', 'network_security_config') : null;
  const xml = name => normalize(run(analyzer, ['resources', 'xml', '--file', member('xml', name), file]));
  validateAndroidResources(normalize(run(analyzer, ['manifest', 'print', file])),
    xml('app_restrictions'), inspectTrust ? xml('network_security_config') : '', config, inspectTrust,
    inspectTrust ? run(aapt, ['dump', 'xmltree', file, trustMember]) : null);
  return requireCa ? member('raw', 'cloudmeet_client_ca') : null;
}

function validateAndroidResources(manifest, restrictions, trust, config, requireCa, trustTree = null) {
  const script = `import sys,json,re,xml.etree.ElementTree as E
d=json.loads(sys.argv[1]); ns='{http://schemas.android.com/apk/res/android}'
anchor='system' if d['publicTrust'] else '@raw/cloudmeet_client_ca'
m=E.fromstring(d['manifest']); app=m if m.tag=='application' else m.find('application')
assert app is not None
assert any(x.get(ns+'name')=='android.content.APP_RESTRICTIONS' and x.get(ns+'resource')=='@xml/app_restrictions' for x in app.findall('meta-data'))
r=E.fromstring(d['restrictions'])
matches=[x for x in r.iter('restriction') if x.get(ns+'key')=='SERVER_URL']
assert len(matches)==1 and matches[0].get(ns+'defaultValue')==d['origin']
if d['requireCa']:
  assert app.get(ns+'networkSecurityConfig')=='@xml/network_security_config'
  t=E.fromstring(d['trust'])
  if d['trustTree'] is not None:
   # apkanalyzer preserves attributes but drops binary XML character data.
   # Pair every element/parent with aapt's tree of the SAME compiled member.
   nodes=list(t.iter()); parents={c:p for p in t.iter() for c in p}
   stack=[]; count=0; texts={}
   for line in d['trustTree'].splitlines():
    element=re.fullmatch(r'( *)E: ([\\w.-]+) \\(line=\\d+\\)\\s*',line)
    if element:
     depth=len(element[1])
     while stack and stack[-1][0]>=depth: stack.pop()
     if count>=len(nodes): raise ValueError('Android XML structure mismatch')
     node=nodes[count]; count+=1
     parent=stack[-1][1] if stack else None
     if node.tag!=element[2] or parents.get(node) is not parent: raise ValueError('Android XML structure mismatch')
     stack.append((depth,node))
    elif re.match(r'\\s*[CT]:',line):
     text=re.fullmatch(r'( *)C: (".*")\\s*',line)
     if not text or not stack or len(text[1])<=stack[-1][0]: raise ValueError('Unsupported Android XML character data')
     try: value=json.loads(text[2])
     except ValueError: raise ValueError('Unsupported Android XML character data')
     node=stack[-1][1]; texts[node]=texts.get(node,'')+value
   if count!=len(nodes): raise ValueError('Android XML structure mismatch')
   for node in nodes:
    value=texts.get(node,'')
    if (node.text or '').strip() and (node.text or '').strip()!=value.strip(): raise ValueError('Android XML character data mismatch')
    node.text=value
  rules=[x for x in t.iter('domain-config') if any((v.text or '').strip()==d['host'] for v in x.findall('domain'))]
  if not rules: raise ValueError('Android CA scope: matched 0 rules for '+d['host'])
  for rule in rules:
   if any(v.get('includeSubdomains','false')!='false' for v in rule.findall('domain') if (v.text or '').strip()==d['host']): raise ValueError('Android CA scope includes subdomains')
   if not any(x.get('src')==anchor for x in rule.findall('./trust-anchors/certificates')): raise ValueError('Android CA anchor missing')
   if d['publicTrust'] and (rule not in list(t) or rule.get('cleartextTrafficPermitted')!='false' or len(rule.findall('domain'))!=1 or len(rule.findall('trust-anchors'))!=1 or len(rule.findall('./trust-anchors/certificates'))!=1 or rule.find('./trust-anchors/certificates').attrib!={'src':'system'} or any(c.tag not in ('domain','trust-anchors') for c in rule)): raise ValueError('Public TLS requires explicit host and system anchors only')
  if len(rules)>1:
   def canonical(node):
    return (node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),tuple(sorted(canonical(c) for c in node)))
   parents={c:p for p in t.iter() for c in p}
   for rule in rules:
    if parents.get(rule) is not t or rule.get('cleartextTrafficPermitted') is None: raise ValueError('Duplicate Android rules require explicit non-inherited security settings')
    if rule.get('cleartextTrafficPermitted')!='false': raise ValueError('Duplicate Android rules have conflicting cleartext settings')
    if any((v.text or '').strip()!=d['host'] or v.get('includeSubdomains','false')!='false' for v in rule.findall('domain')): raise ValueError('Duplicate Android rules broaden host scope')
    anchors=rule.findall('trust-anchors')
    if len(anchors)!=1 or not list(anchors[0]) or any(c.tag!='certificates' or c.attrib!={'src':anchor} for c in anchors[0]): raise ValueError('Duplicate Android rules have conflicting trust anchors')
    if any(c.tag not in ('domain','trust-anchors') for c in rule): raise ValueError('Duplicate Android rules contain unsupported inherited or security settings')
   if any(canonical(rule)!=canonical(rules[0]) for rule in rules[1:]): raise ValueError('Duplicate Android CA rules have conflicting settings')
   print('Equivalent duplicate Android CA rules: '+str(len(rules)))
print('verified')`;
  const result = command(PY, ['-B', '-c', script, JSON.stringify({ manifest, restrictions, trust,
    origin: config.origin, host: config.values.SITE_DOMAIN, requireCa, trustTree, publicTrust: config.tlsMode === 'caddy-public-acme' })]);
  const lines = result.trim().split(/\r?\n/);
  if (lines.pop() !== 'verified') throw Error('Android resource reference validation failed');
  for (const warning of lines) console.warn(warning);
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
    check('shortcuts', true, inspectWindowsShortcuts(file));
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
    const audit = require('./network-audit.cjs').auditGenerated('electron', config, { deployment: env, trust });
    for (const warning of audit.warnings) console.warn(warning);
    check('origin', true, JSON.stringify({ origin: config.origin, warnings: audit.warnings }));
    check('ca', trust.origin === config.origin && (ca
      ? matchesCa(asar.extractFile(asarFile, 'client-ca.crt'), ca) : trust.caFile === null), ca?.sha256 || 'system trust');
    const exe = files.find(p => /cloudmeet\.exe$/i.test(p));
    if (!exe) throw Error('MSI main executable missing');
    const peVersion = ps(`(Get-Item -LiteralPath ${quote(exe)}).VersionInfo.FileVersion`).trim();
    check('peVersion', peVersion === config.peVersion, peVersion);
    const bytes = fs.readFileSync(exe); const offset = bytes.readUInt32LE(0x3c);
    check('architecture', bytes.readUInt16LE(offset + 4) === 0x8664 && artifact.architecture === 'x64', 'PE AMD64');
    // Unsigned is the approved policy, NOT a successful signature check.
    checks.signing = { required: false, status: 'unsigned',
      detail: 'UNSIGNED EXE/MSI; Windows may show unknown-publisher or SmartScreen warnings.' };
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
    const signRun = spawnSync(sdkTool(tools, 'apksigner'), ['verify', '--verbose', '--print-certs', file],
      { encoding: 'utf8', windowsHide: true, maxBuffer: 64 * 1024 * 1024 });
    if (signRun.error || signRun.status !== 0) throw Error(`Package inspection failed: apksigner: ${signRun.stderr || signRun.error}`);
    // Some apksigner builds print the certificate block on stderr; parse both streams.
    const signature = `${signRun.stdout || ''}\n${signRun.stderr || ''}`;
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
module.exports = { verifyPackage, inspectWindowsShortcuts, validateAndroidResources, inspectAndroidResources, validateAndroidSigner, validateWindowsSigner };
