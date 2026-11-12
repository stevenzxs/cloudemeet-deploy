#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { parseConfig, versionCode, withLock, withFiles, findWix } = require('./core.cjs');
const { readCa, androidTrust } = require('./ca-config.cjs');
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
    else if (['--target', '--env-file'].includes(flag)) {
      const value = args.shift();
      if (!value || value.startsWith('--')) throw Error(`Missing value for ${flag}`);
      result[{ '--target': 'target', '--env-file': 'file' }[flag]] = value;
    } else throw Error(`Unknown argument: ${flag}`);
  }
  if (!['all', 'electron', 'android'].includes(result.target)) throw Error('Invalid target');
  if (fs.realpathSync(result.file) !== fs.realpathSync(canonical)) throw Error('Only deploy/config/client.env is allowed');
  return result;
}

function run(exe, args, cwd, env, logfile) {
  const fd = fs.openSync(logfile, 'a');
  try {
    const result = spawnSync(exe, args, { cwd, env, stdio: ['ignore', fd, fd], windowsHide: true });
    if (result.error || result.status !== 0) throw Error(`Build step failed (${path.basename(exe)}); see ${logfile}`);
  } finally { fs.closeSync(fd); }
}

function preflight(options, config) {
  const blockers = [];
  let androidCode;
  let ca;
  try { ca = readCa(config, canonical); } catch (error) { blockers.push(`Invalid CLIENT_CA_FILE: ${error.message}`); }
  const exists = (file, label) => { if (!fs.existsSync(file)) blockers.push(`Missing ${label}`); };
  if (process.platform !== 'win32') blockers.push('Windows host required by this restored builder');
  if (fs.existsSync(lock)) blockers.push('Active build lock exists; do not delete without investigation');
  if (options.target !== 'electron') {
    try { androidCode = versionCode(config.version); }
    catch (error) { blockers.push(error.message); }
    exists(path.join(root, 'jm/android/gradlew.bat'), 'Gradle wrapper');
    exists(path.join(root, 'jm/node_modules/react-native/package.json'), 'Android Node dependencies');
    exists(path.join(root, 'jm/android/keystores/release.keystore.properties'), 'Android release signing configuration');
    const java = process.env.JAVA_HOME && path.join(process.env.JAVA_HOME, 'bin/java.exe');
    if (!java || !fs.existsSync(java)) blockers.push('JAVA_HOME must point to an installed JDK');
    const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT;
    if (!sdk || !fs.existsSync(path.join(sdk, 'platform-tools'))) blockers.push('ANDROID_HOME/ANDROID_SDK_ROOT with installed SDK required');
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
      'MSI may be unsigned without configured PFX; actual signing must be inspected before delivery.'
    ] };
}

function androidTasks() {
  // Gradle 8 task-scoped --rerun: rerun packaging, not all compilation dependencies.
  return [':app:packageRelease', '--rerun', ':app:assembleRelease'];
}

function collect(source, destination, extension, started) {
  const results = [];
  const walk = dir => {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isSymbolicLink()) throw Error('Artifact links are not allowed');
      if (entry.isDirectory()) walk(file);
      else if (entry.name.endsWith(extension) && fs.statSync(file).mtimeMs >= started) {
        const relative = path.relative(source, file); const output = path.join(destination, relative);
        fs.mkdirSync(path.dirname(output), { recursive: true }); fs.copyFileSync(file, output);
        results.push({ file: path.relative(path.dirname(destination), output), bytes: fs.statSync(output).size,
          sha256: crypto.createHash('sha256').update(fs.readFileSync(output)).digest('hex') });
      }
    }
  };
  walk(source);
  if (!results.length) throw Error(`No fresh ${extension} artifacts were produced`);
  return results;
}

async function build(options, config, report) {
  return withLock(lock, async () => {
    const candidate = fs.mkdtempSync(path.join(process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, 'Temp/opencode') : os.tmpdir(), 'cloudmeet-clients-'));
    const manifest = { ...report, status: 'building', candidate, started: new Date().toISOString(), artifacts: [] };
    const save = () => fs.writeFileSync(path.join(candidate, 'build.json'), JSON.stringify(manifest, null, 2) + '\n');
    const env = { ...process.env, CLOUDMEET_BUILD_MODE: 'release' };
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
        const changes = [[metadata, JSON.stringify(pkg, null, 2) + '\n'],
          [path.join(project, 'deployment.env'), Object.entries(config.values).filter(([key]) => !['CLIENT_VERSION', 'CLIENT_CA_FILE'].includes(key)).map(([key, value]) => `${key}=${value}`).join('\n') + '\n'],
          [path.join(project, 'client-trust.json'), JSON.stringify({ origin: config.origin, caFile: ca ? 'client-ca.crt' : null }) + '\n']];
        if (ca) changes.push([path.join(project, 'client-ca.crt'), ca.pem]);
        await withFiles(changes, async () => {
          const wix = findWix();
          if (!wix) throw Error('WiX tools disappeared after preflight');
          const pathKey = Object.keys(env).find(key => key.toLowerCase() === 'path') || 'PATH';
          // Existing project hooks interpret WIX as an installation root with bin/.
          // Use the resolved PATH instead, also supporting portable WiX directories.
          const buildEnv = { ...env, [pathKey]: `${wix}${path.delimiter}${env[pathKey] || ''}` };
          delete buildEnv.WIX;
          run(process.execPath, [path.join(project, 'node_modules/@electron-forge/cli/dist/electron-forge.js'), 'make', '--platform=win32', '--arch=x64'], project,
            buildEnv, path.join(candidate, 'electron.log'));
          manifest.artifacts.push(...collect(path.join(project, 'out/make/unified/x64'), path.join(candidate, 'electron'), '.msi', started));
        });
      }
      if (options.target !== 'electron') {
        const project = path.join(root, 'jm');
        const restrictions = path.join(project, 'android/app/src/main/res/xml/app_restrictions.xml');
        const xml = fs.readFileSync(restrictions, 'utf8');
        if (!xml.includes('android:key="SERVER_URL"') || xml.includes('android:defaultValue=')) throw Error('Unexpected Android restrictions layout; refusing overwrite');
        const started = Date.now();
        const changes = [[path.join(project, 'react/features/cloudmeet/deployment.json'), JSON.stringify({ origin: config.origin }, null, 4) + '\n'],
          [restrictions, xml.replace('android:key="SERVER_URL"', `android:key="SERVER_URL" android:defaultValue="${config.origin}"`)]];
        if (ca) {
          const trust = path.join(project, 'android/app/src/main/res/xml/network_security_config.xml');
          changes.push([trust, androidTrust(fs.readFileSync(trust, 'utf8'), config.values.SITE_DOMAIN)],
            [path.join(project, 'android/app/src/main/res/raw/cloudmeet_client_ca.crt'), ca.pem]);
        }
        await withFiles(changes, async () => {
          run(process.env.ComSpec || 'cmd.exe', ['/d', '/c', 'gradlew.bat', ...androidTasks(), `-PappVersion=${config.version}`, `-PcloudmeetVersionCode=${manifest.versionCode}`, '--no-daemon'], path.join(project, 'android'), env, path.join(candidate, 'android.log'));
          manifest.artifacts.push(...collect(path.join(project, 'android/app/build/outputs/apk/release'), path.join(candidate, 'android'), '.apk', started));
        });
      }
      manifest.status = 'compiled-candidate-unverified';
      manifest.acceptance = 'Not promoted: inspect actual versions, embedded origin, ABI, signatures and certificate trust before delivery.';
      save(); console.log(JSON.stringify(manifest, null, 2));
    } catch (error) { manifest.status = 'failed'; manifest.error = error.message; save(); throw error; }
  });
}

async function main() {
  const options = argumentsFor(process.argv.slice(2));
  const config = parseConfig(fs.readFileSync(canonical, 'utf8'));
  const report = preflight(options, config);
  console.log(JSON.stringify(report, null, 2));
  if (report.blockers.length) { process.exitCode = 1; return; }
  if (!options.check) await build(options, config, report);
}
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
module.exports = { argumentsFor, preflight, collect, androidTasks };
