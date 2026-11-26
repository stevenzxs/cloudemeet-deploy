#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawn, spawnSync } = require('node:child_process');
const { parseConfig, versionCode, withLock, withFiles, findWix } = require('./core.cjs');
const { readCa, androidTrust } = require('./ca-config.cjs');
const { auditGenerated, auditPackages, writeAudit, inventorySources } = require('./network-audit.cjs');
const root = path.resolve(__dirname, '../../..');
const canonical = path.join(root, 'deploy/config/client.env');
const lock = path.join(__dirname, '.client-build.lock');

function argumentsFor(args) {
  const result = { target: 'all', file: canonical, check: false };
  const seen = new Set();
  while (args.length) {
    const flag = args.shift();
    if (seen.has(flag)) throw Error(`Duplicate argument: ${flag}`);
    seen.add(flag);
    if (flag === '--check') result.check = true;
    else if (['--target', '--env-file', '--version-record'].includes(flag)) {
      const value = args.shift();
      if (!value || value.startsWith('--')) throw Error(`Missing value for ${flag}`);
      result[{ '--target': 'target', '--env-file': 'file', '--version-record': 'versionRecord' }[flag]] = value;
    } else throw Error(`Unknown argument: ${flag}`);
  }
  if (!['all', 'electron', 'android'].includes(result.target)) throw Error('Invalid target');
  if (fs.realpathSync(result.file) !== fs.realpathSync(canonical)) throw Error('Only deploy/config/client.env is allowed');
  return result;
}

function sanitizeBuildLog(text, env) {
  text = text.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '');
  text = text.replace(/-----BEGIN ([A-Z ]*PRIVATE KEY)-----[\s\S]*?(?:-----END \1-----|$)/g, '[REDACTED PRIVATE KEY]');
  const secrets = Object.entries(env).filter(([name, value]) => value && /PASSWORD|PASSPHRASE|TOKEN|SECRET|KEYSTORE|PFX|CREDENTIAL|AUTHORIZATION/i.test(name))
    .flatMap(([, value]) => [String(value), encodeURIComponent(value), JSON.stringify(String(value)).slice(1, -1)])
    .sort((a, b) => b.length - a.length);
  for (const value of secrets) text = text.split(value).join('[REDACTED]');
  const value = `(?:"[^"\\r\\n]*"|'[^'\\r\\n]*'|[^\\s;,&]+)`;
  return text.replace(new RegExp(`(\\b(?:[\\w.-]*(?:password|passphrase|token|secret)|authorization)["']?\\s*[:=]\\s*(?:Bearer\\s+|Basic\\s+)?|\\bBearer\\s+|\\/p\\s+)${value}`, 'gi'),
    '$1[REDACTED]');
}

async function run(exe, args, cwd, env, logfile, output = process.stderr) {
  const logEnv = { ...env };
  // Android passwords live in the provisioned properties file, not the build
  // environment. Mask their exact values without printing or forwarding them.
  const props = path.join(cwd, 'keystores/release.keystore.properties');
  if (fs.existsSync(props)) {
    for (const [index, match] of [...fs.readFileSync(props, 'utf8').matchAll(/^\s*(?:storePassword|keyPassword)\s*=\s*(.+?)\s*$/gm)].entries()) {
      logEnv[`SIGNING_PASSWORD_${index}`] = match[1];
    }
  }
  const fd = fs.openSync(logfile, 'a');
  let diagnostic = '';
  const auditFile = env.CLOUDMEET_AUDIT_DIR && path.join(env.CLOUDMEET_AUDIT_DIR, `build-${path.basename(logfile)}`);
  if (auditFile) fs.mkdirSync(env.CLOUDMEET_AUDIT_DIR, { recursive: true });
  const retain = text => {
    diagnostic = (diagnostic + text).slice(-65536);
    if (auditFile) fs.appendFileSync(auditFile, text);
    // Prefix child output so it cannot be interpreted as Actions commands.
    output.write(`[client-build] ${text}`);
  };
  // Buffer split credentials until the line is complete, then stream immediately.
  // Flush the final unterminated line on close as well.
  const finishStreams = [];
  const consumeStream = () => {
    let pending = '', privateKey = false, oversized = false;
    const flush = () => {
      if (oversized) { retain('[REDACTED oversized line]\n'); oversized = false; }
      else {
        if (/-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(pending)) privateKey = true;
        retain(privateKey ? '[REDACTED PRIVATE KEY]\n' : sanitizeBuildLog(pending, logEnv) + '\n');
        if (/-----END [A-Z ]*PRIVATE KEY-----/.test(pending)) privateKey = false;
      }
      pending = '';
    };
    finishStreams.push(() => { if (pending || oversized) flush(); });
    return chunk => {
      fs.writeSync(fd, chunk);
      for (const part of chunk.split(/([\r\n])/)) {
        if (part === '\n' || part === '\r') { if (pending || oversized) flush(); }
        else if (!oversized) {
          pending += part;
          if (pending.length > 1048576) { pending = ''; oversized = true; }
        }
      }
    };
  };
  let result;
  try {
    result = await new Promise(resolve => {
      const child = spawn(exe, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
      let error;
      child.on('error', value => { error = value; });
      child.stdout.setEncoding('utf8').on('data', consumeStream());
      child.stderr.setEncoding('utf8').on('data', consumeStream());
      child.on('close', (status, signal) => {
        for (const finish of finishStreams) finish();
        resolve({ error, status, signal });
      });
    });
  } finally { fs.closeSync(fd); }
  if (result.error || result.status !== 0) {
    // Raw logs remain protected in the candidate. Never upload that directory,
    // command arguments, or the child environment (which can contain signing material).
    const reason = result.error ? `spawn=${result.error.code || 'unknown'}` : `exit=${result.status}, signal=${result.signal || 'none'}`;
    const tail = diagnostic.split('\n').slice(-30).join('\n').slice(-8192);
    throw Error(`Build step failed (${path.basename(exe)}; ${reason}); protected log: ${logfile}\nSanitized build output:\n${tail}`);
  }
}

function androidKeystorePolicyBlockers(java) {
  const dir = path.join(root, 'jm/android/keystores');
  const propsFile = path.join(dir, 'release.keystore.properties');
  const keystore = path.join(dir, 'release.keystore');
  if (!fs.existsSync(propsFile) || !fs.existsSync(keystore)) return [];
  if (!java) return [];
  const props = {};
  try {
    for (const line of fs.readFileSync(propsFile, 'utf8').split(/\r?\n/)) {
      if (!line.trim() || line.trim().startsWith('#')) continue;
      const key = line.split('=')[0].trim();
      props[key] = line.slice(line.indexOf('=') + 1).trim();
    }
  } catch { return ['Android signing properties unreadable; re-provision signing secrets']; }
  if (!props.storePassword || !props.keyAlias) return ['Android signing properties incomplete; re-provision signing secrets'];
  const keytool = path.join(path.dirname(java), process.platform === 'win32' ? 'keytool.exe' : 'keytool');
  const result = spawnSync(keytool, ['-list', '-v', '-keystore', keystore,
    '-storepass', props.storePassword, '-alias', props.keyAlias],
    { encoding: 'utf8', windowsHide: true, timeout: 60000 });
  const match = /SHA-?256:\s*([0-9a-f:]+)/i.exec(result.stdout || '');
  if (result.status !== 0 || !match) return ['Android keystore certificate fingerprint could not be established; re-provision signing secrets via certificate repository android/provision-secrets.py'];
  const actual = match[1].replaceAll(':', '').toLowerCase();
  const expected = require('./signing.cjs').policy.android_certificate_der_sha256;
  if (actual !== expected) return [`CI Android keystore certificate ${actual} does not match approved signing policy ${expected}; re-provision ANDROID_KEYSTORE secrets via certificate repository android/provision-secrets.py`];
  return [];
}

function preflight(options, config) {
  const blockers = [];
  if (!config.assignment) blockers.push('Version allocation missing: diagnostic baseline only; release builds disabled');
  let androidCode;
  let ca;
  try { ca = readCa(config, canonical); } catch (error) { blockers.push(`Invalid CLIENT_CA_FILE: ${error.message}`); }
  const exists = (file, label) => { if (!fs.existsSync(file)) blockers.push(`Missing ${label}`); };
  if (process.platform !== 'win32' && options.target !== 'android') blockers.push('Windows host required for Electron packaging');
  if (fs.existsSync(lock)) blockers.push('Active build lock exists; do not delete without investigation');
  if (options.target !== 'electron') {
    try { androidCode = versionCode(config.version); }
    catch (error) { blockers.push(error.message); }
    exists(path.join(root, 'jm/android', process.platform === 'win32' ? 'gradlew.bat' : 'gradlew'), 'Gradle wrapper');
    exists(path.join(root, 'jm/node_modules/react-native/package.json'), 'Android Node dependencies');
    exists(path.join(root, 'jm/android/keystores/release.keystore.properties'), 'Android release signing configuration');
    const java = process.env.JAVA_HOME && path.join(process.env.JAVA_HOME, 'bin', process.platform === 'win32' ? 'java.exe' : 'java');
    if (!java || !fs.existsSync(java)) blockers.push('JAVA_HOME must point to an installed JDK');
    const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT;
    if (!sdk || !fs.existsSync(path.join(sdk, 'platform-tools'))) blockers.push('ANDROID_HOME/ANDROID_SDK_ROOT with installed SDK required');
    blockers.push(...androidKeystorePolicyBlockers(java));
  }
  if (options.target !== 'android') {
    exists(path.join(root, 'jitsi-meet-electron/node_modules/@electron-forge/cli/dist/electron-forge.js'), 'Electron Forge dependencies');
    if (!findWix()) blockers.push('Missing WiX v3 candle.exe/light.exe: configure WIX or PATH');
  }
  return { origin: config.origin, desktopUrl: config.desktopUrl, version: config.version,
    target: options.target, deliveryRoot: path.join(root, 'deploy/release/clients'),
    ca: ca ? { file: ca.file, sha256: ca.sha256, validTo: ca.validTo } : null,
    ...(androidCode === undefined ? {} : { versionCode: androidCode }), blockers, warnings: [
      'Version-derived Android code may be lower than old time-based APK codes; in-place upgrade is NOT guaranteed.',
      'Configured CA is scoped to the deployment host; actual endpoint TLS compatibility is NOT verified.',
      'Preflight is not compilation, artifact signature verification or installation acceptance.',
      'Windows EXE/MSI delivery is unsigned; unknown-publisher or SmartScreen warnings are possible. Android retains approved release signing.'
    ] };
}

function androidTasks() {
  // Gradle 8 task-scoped --rerun: rerun packaging, not all compilation dependencies.
  return [':app:packageRelease', '--rerun', ':app:assembleRelease'];
}

function elapsedMs(started) {
  return Number((process.hrtime.bigint() - started) / 1000000n);
}

function androidLayout(abis) {
  const actual = [...new Set(abis)].sort();
  const supported = ['armeabi-v7a', 'arm64-v8a', 'x86_64'];
  if (!actual.length || actual.some(abi => !supported.includes(abi))) throw Error('Unsupported or missing APK ABI (x86 is excluded)');
  return { platform: 'android', architectures: actual, architecture: actual.length === 1 ? actual[0] : 'universal' };
}

function inspectApk(file) {
  const script = 'import json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); print(json.dumps(sorted({n.split("/")[1] for n in z.namelist() if n.startswith("lib/") and n.endswith(".so") and len(n.split("/"))==3})))';
  const python = process.platform === 'win32' ? 'python' : 'python3';
  const result = spawnSync(python, ['-B', '-c', script, file], { encoding: 'utf8', windowsHide: true });
  if (result.error || result.status !== 0) throw Error('Python 3 with zipfile is required to inspect APK ABIs');
  return androidLayout(JSON.parse(result.stdout));
}

function collect(source, destination, extension, started, layoutFor) {
  const results = [];
  const walk = dir => {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isSymbolicLink()) throw Error('Artifact links are not allowed');
      if (entry.isDirectory()) walk(file);
      else if (entry.name.endsWith(extension) && fs.statSync(file).mtimeMs >= started) {
        const layout = layoutFor ? layoutFor(file) : null;
        const relative = path.relative(source, file);
        const output = layout ? path.join(destination, layout.platform, layout.architecture, relative) : path.join(destination, relative);
        fs.mkdirSync(path.dirname(output), { recursive: true }); fs.copyFileSync(file, output);
        results.push({ file: path.relative(layout ? destination : path.dirname(destination), output),
          ...(layout ? { ...layout, deliveryDirectory: path.posix.join(layout.platform, layout.architecture, '<batch>') } : {}), bytes: fs.statSync(output).size,
          sha256: crypto.createHash('sha256').update(fs.readFileSync(output)).digest('hex') });
      }
    }
  };
  walk(source);
  if (!results.length) throw Error(`No fresh ${extension} artifacts were produced`);
  return results;
}

async function build(options, config, report) {
  console.error('[client-stage] Compile and package (includes product signing hooks)');
  return withLock(lock, async () => {
    const candidate = createCandidate();
    require('./network-audit.cjs').stageReports(options.auditDir, candidate);
    if (!config.assignment) throw Error('Allocated version required; legacy versions are diagnostic-only');
    const manifest = { ...report, tls_mode: config.tlsMode, versionAssignment: config.assignment, status: 'building', candidate, started: new Date().toISOString(), artifacts: [], phaseTimings: [] };
    const save = () => fs.writeFileSync(path.join(candidate, 'build.json'), JSON.stringify(manifest, null, 2) + '\n');
    const timed = async (name, action, artifact) => {
      const started = process.hrtime.bigint();
      const timing = { phase: name, ...(artifact ? { artifact: path.basename(artifact) } : {}), status: 'running' };
      manifest.phaseTimings.push(timing);
      console.error(`[client-timing] ${name} started`);
      save();
      try {
        const result = await action();
        timing.status = 'success';
        return result;
      } catch (error) {
        timing.status = 'failed';
        throw error;
      } finally {
        timing.durationMs = elapsedMs(started);
        console.error(`[client-timing] ${name} ${timing.status} ${timing.durationMs}ms`);
        save();
      }
    };
    const recordNetwork = (name, data) => {
      writeAudit(candidate, name, data, root);
      if (process.env.CLOUDMEET_AUDIT_DIR) writeAudit(process.env.CLOUDMEET_AUDIT_DIR, name, data, root);
    };
    const env = { ...process.env, CLOUDMEET_BUILD_MODE: 'release' };
    // Only the reviewed certificate-repository tools may consume Windows secrets.
    delete env.CLOUDMEET_CODESIGN_PFX;
    delete env.CLOUDMEET_CODESIGN_PASSWORD;
    for (const key of ['SITE_DOMAIN', 'SITE_SCHEME', 'SITE_PORT', 'CLIENT_VERSION', 'CLIENT_CA_FILE', 'CLOUDMEET_ENV_FILE']) delete env[key];
    try {
      const ca = readCa(config, canonical);
      if ((ca?.sha256 || null) !== (report.ca?.sha256 || null)) throw Error('CA changed after preflight');
      if (options.target !== 'electron') {
        manifest.versionCode = versionCode(config.version);
      }
      save();
      if (options.target !== 'android') {
        const project = path.join(root, 'jitsi-meet-electron');
        const metadata = path.join(project, 'package.json');
        const pkg = JSON.parse(fs.readFileSync(metadata, 'utf8')); pkg.version = config.version;
        const started = Date.now();
        // electron-forge 7 prefers an existing forge.config.js over the package.json
        // config.forge path string, so the adapter must occupy forge.config.js itself;
        // the source config is preserved beside it as forge.config.cloudmeet-base.cjs
        // (both are restored/removed by withFiles after the build).
        const nativeForge = path.join(project, 'forge.config.js');
        const changes = [[metadata, JSON.stringify(pkg, null, 2) + '\n'],
          [path.join(project, 'cloudmeet-version.json'), JSON.stringify(config.assignment, null, 2) + '\n'],
          [path.join(project, 'forge.config.cloudmeet-base.cjs'), fs.readFileSync(nativeForge, 'utf8')],
          [nativeForge, require('./revision-config.cjs').forgeWrapper(project, config.assignment)],
           [path.join(project, 'deployment.env'), Object.entries(config.values).filter(([key]) => !['CLIENT_VERSION', 'CLIENT_CA_FILE', 'TLS_MODE'].includes(key)).map(([key, value]) => `${key}=${value}`).join('\n') + '\n'],
          [path.join(project, 'client-trust.json'), JSON.stringify({ origin: config.origin, caFile: ca ? 'client-ca.crt' : null }) + '\n']];
        if (ca) changes.push([path.join(project, 'client-ca.crt'), ca.pem]);
        await withFiles(changes, async () => {
          recordNetwork('network-electron-generated', auditGenerated('electron', config, {
            deployment: fs.readFileSync(path.join(project, 'deployment.env'), 'utf8'),
            trust: JSON.parse(fs.readFileSync(path.join(project, 'client-trust.json'), 'utf8'))
          }));
          const wix = findWix();
          if (!wix) throw Error('WiX tools disappeared after preflight');
          const pathKey = Object.keys(env).find(key => key.toLowerCase() === 'path') || 'PATH';
          // Existing project hooks interpret WIX as an installation root with bin/.
          // Use the resolved PATH instead, also supporting portable WiX directories.
          const buildEnv = { ...env, [pathKey]: `${wix}${path.delimiter}${env[pathKey] || ''}` };
          delete buildEnv.WIX;
          await run(process.execPath, [path.join(project, 'node_modules/@electron-forge/cli/dist/electron-forge.js'), 'make', '--platform=win32', '--arch=x64'], project,
            buildEnv, path.join(candidate, 'electron.log'));
          manifest.artifacts.push(...collect(path.join(project, 'out/make/wix/x64'), candidate, '.msi', started,
            () => ({ platform: 'windows', architecture: 'x64', architectures: ['x64'] })));
        });
      }
      if (options.target !== 'electron') {
        const project = path.join(root, 'jm');
        const restrictions = path.join(project, 'android/app/src/main/res/xml/app_restrictions.xml');
        const xml = fs.readFileSync(restrictions, 'utf8');
        if (!xml.includes('android:key="SERVER_URL"') || xml.includes('android:defaultValue=')) throw Error('Unexpected Android restrictions layout; refusing overwrite');
        const started = Date.now();
        const changes = [[path.join(project, 'react/features/cloudmeet/deployment.json'), JSON.stringify({ origin: config.origin }, null, 4) + '\n'],
          [path.join(project, 'android/app/src/main/assets/cloudmeet-version.json'), JSON.stringify(config.assignment, null, 2) + '\n'],
          [restrictions, xml.replace('android:key="SERVER_URL"', `android:key="SERVER_URL" android:defaultValue="${config.origin}"`)]];
        const gradle = path.join(project, 'android/app/build.gradle');
        const gradleText = fs.readFileSync(gradle, 'utf8');
        const filters = "abiFilters 'armeabi-v7a', 'arm64-v8a', 'x86', 'x86_64'";
        if (!gradleText.includes(filters)) throw Error('Unexpected Android ABI filters; refusing implicit architecture change');
        changes.push([gradle, gradleText.replace(filters, "abiFilters 'armeabi-v7a', 'arm64-v8a', 'x86_64'")]);
        if (ca || config.tlsMode === 'caddy-public-acme') {
          const trust = path.join(project, 'android/app/src/main/res/xml/network_security_config.xml');
          changes.push([trust, androidTrust(fs.readFileSync(trust, 'utf8'), config.values.SITE_DOMAIN, config.tlsMode)]);
          if (ca) changes.push([path.join(project, 'android/app/src/main/res/raw/cloudmeet_client_ca.crt'), ca.pem]);
        }
        await withFiles(changes, async () => {
          recordNetwork('network-android-generated', auditGenerated('android', config, {
            deployment: JSON.parse(fs.readFileSync(path.join(project, 'react/features/cloudmeet/deployment.json'), 'utf8')),
            restrictions: fs.readFileSync(restrictions, 'utf8'),
            trust: (ca || config.tlsMode === 'caddy-public-acme') ? fs.readFileSync(path.join(project, 'android/app/src/main/res/xml/network_security_config.xml'), 'utf8') : null
          }));
          const gradleArgs = [...androidTasks(), `-PappVersion=${config.version}`, `-PcloudmeetVersionCode=${manifest.versionCode}`, '--no-daemon', '--build-cache'];
          if (process.env.CLOUDMEET_GRADLE_INIT) gradleArgs.push('--init-script', process.env.CLOUDMEET_GRADLE_INIT);
          // Bound repository downloads so a degraded Maven egress fails fast
          // and retries instead of stalling the build for tens of minutes.
          const gradleEnv = { ...env, GRADLE_OPTS: `${env.GRADLE_OPTS || ''} -Dorg.gradle.internal.http.connectionTimeout=60000 -Dorg.gradle.internal.http.socketTimeout=60000`.trim() };
          if (process.platform === 'win32') {
            await timed('android-gradle-build', () => run(process.env.ComSpec || 'cmd.exe', ['/d', '/c', 'gradlew.bat', ...gradleArgs], path.join(project, 'android'), gradleEnv, path.join(candidate, 'android.log')));
          } else {
            const wrapper = path.join(project, 'android', 'gradlew');
            fs.chmodSync(wrapper, 0o755);
            await timed('android-gradle-build', () => run(wrapper, gradleArgs, path.join(project, 'android'), gradleEnv, path.join(candidate, 'android.log')));
          }
          manifest.artifacts.push(...collect(path.join(project, 'android/app/build/outputs/apk/release'), candidate, '.apk', started, inspectApk));
        });
      }
      console.error('[client-stage] Verify final packages');
      manifest.status = 'checking-packages'; save();
      for (const artifact of manifest.artifacts) {
        const scratch = fs.mkdtempSync(path.join(candidate, 'inspection-'));
        artifact.checks = await timed(options.target === 'android' ? 'android-package-verification' : 'client-package-verification', () => require('./verify-package.cjs').verifyPackage(
          path.join(candidate, artifact.file), artifact, config, ca, root, scratch), artifact.file);
      }
      manifest.networkAudit = writeAudit(candidate, 'network-final-packages', auditPackages(manifest), root);
      recordNetwork('network-final-packages', manifest.networkAudit);
      console.error('[client-stage] Deliver verified packages');
      manifest.deliveries = await timed(options.target === 'android' ? 'android-delivery' : 'client-delivery',
        () => require('./delivery.cjs').deliver(manifest, report.deliveryRoot));
      manifest.status = 'packaged-delivered';
      manifest.acceptance = 'Package checks and delivery completed; installation, endpoint TLS and media acceptance not performed.';
      save(); console.log(JSON.stringify(manifest, null, 2));
    } catch (error) {
      recordNetwork('network-failure', { status: 'fail', phase: manifest.status,
        message: 'Build/package audit interrupted; inspect protected build logs. No acceptance claimed.' });
      manifest.status = 'failed'; manifest.error = error.message; save(); throw error;
    }
  });
}

function createCandidate(base = process.env.LOCALAPPDATA
  ? path.join(process.env.LOCALAPPDATA, 'Temp/opencode') : os.tmpdir()) {
  fs.mkdirSync(base, { recursive: true });
  return fs.mkdtempSync(path.join(base, 'cloudmeet-clients-'));
}

async function main() {
  console.error('[client-stage] Preflight');
  const options = argumentsFor(process.argv.slice(2));
  const auditDir = process.env.CLOUDMEET_AUDIT_DIR || path.join(createCandidate(), 'audit');
  options.auditDir = auditDir;
  let config;
  try {
    const assignment = options.versionRecord ? require('./revision-config.cjs').loadAssignment(options.versionRecord, root, options.target) : null;
    if (!options.check && !assignment) throw Error('Version record required');
    config = parseConfig(fs.readFileSync(canonical, 'utf8'), assignment);
  }
  catch {
    writeAudit(auditDir, 'network-client-preflight', { phase: 'preflight', status: 'fail',
      blockers: ['Invalid canonical client configuration; input values not echoed.'] }, root);
    throw Error('Client configuration audit failed');
  }
  const report = preflight(options, config);
  for (const target of (options.target === 'all' ? ['electron', 'android'] : [options.target])) {
    const project = path.join(root, target === 'electron' ? 'jitsi-meet-electron' : 'jm');
    writeAudit(auditDir, `network-${target}-source-inventory`, inventorySources(project,
      target === 'electron' ? ['src', 'deployment.env', 'client-trust.json', 'forge.config.js']
        : ['react/features/cloudmeet', 'android/app/src/main', 'android/app/build.gradle']), root);
  }
  writeAudit(auditDir, 'network-client-preflight', { phase: 'preflight', status: report.blockers.length ? 'fail' : 'pass',
    origin: config.origin, desktopUrl: config.desktopUrl, version: config.version,
    parameters: ['SITE_DOMAIN', 'SITE_SCHEME', 'SITE_PORT'].map(name => ({ name, value: config.values[name], source: 'config/client.env' })),
    ca: report.ca, blockers: report.blockers, unverified: report.warnings }, root);
  console.log(JSON.stringify(report, null, 2));
  if (report.blockers.length) { process.exitCode = 1; return; }
  if (!options.check) await build(options, config, report);
}
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
module.exports = { argumentsFor, preflight, collect, androidTasks, androidLayout, createCandidate, run, sanitizeBuildLog };
