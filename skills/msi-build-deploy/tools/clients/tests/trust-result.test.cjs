const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
test('retained legacy Windows verification adapter stays strict but is not used by current package checks', () => {
  const policy = {commit:'a'.repeat(40),windows_identity:'identity.json'};
  const expected = 'b'.repeat(64);
  const calls=[];
  let output = 'tool verification output\nCLOUDMEET_VERIFIED:'+JSON.stringify({status:'Valid',signer:expected,timestamp:true})+'\n';
  const sandbox={module:{exports:{}},__dirname:path.resolve(__dirname,'..'),process:{env:{SIGNTOOL_PATH:'tool'}},require(name){
    if(name==='node:path') return path;
     if(name==='node:fs') return {existsSync:()=>true,readFileSync:p=>JSON.stringify(p.endsWith('signing-policy.json')?policy:{certificate_der_sha256:expected})};
    if(name==='node:child_process') return {spawnSync(exe,args){calls.push({exe,args});if(exe==='git')return {status:0,stdout:args.includes('rev-parse')?policy.commit:''};return {status:0,stdout:output};}};
    throw Error(name);
  },path,skillRoot:path.resolve(__dirname,'../../..')};
  vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../signing.cjs'),'utf8'),sandbox);
  const result=sandbox.module.exports.verify('candidate.msi');
  assert.equal(result?.signer,expected);
  assert.equal(result.status,'Valid');
  assert.ok(calls.some(c=>c.args.includes('-Command')));
  for (const bad of ['', 'CLOUDMEET_VERIFIED:{}\n',
    'CLOUDMEET_VERIFIED:'+JSON.stringify({status:'Valid',signer:'0'.repeat(64),timestamp:true})+'\n',
    'CLOUDMEET_VERIFIED:'+JSON.stringify({status:'Valid',signer:expected,timestamp:false})+'\n', output+output]) {
    output = bad;
    assert.throws(()=>sandbox.module.exports.verify('candidate.msi'));
  }
  const verifier = fs.readFileSync(path.resolve(__dirname,'../verify-package.cjs'),'utf8');
  assert.doesNotMatch(verifier, /Get-AuthenticodeSignature/);
  assert.doesNotMatch(verifier, /signing\.verify|windowsIdentity/);
  assert.match(verifier, /required: false, status: 'unsigned'/);
});
test('Windows final inspection keeps content gates without loading any signing tool', () => {
  const config = { assignment: { versions: {} }, msiVersion: '1.0.33', peVersion: '1.0.33.0',
    version: '1.0.21+r12', origin: 'https://example.test:8443' };
  const pe = Buffer.alloc(256); pe.writeUInt32LE(64, 0x3c); pe.writeUInt16LE(0x8664, 68);
  let originValid = true;
  let shortcutName = '?????;
  const sandbox = { module: { exports: {} }, process: { platform: 'win32', env: {} }, require(name) {
    if (name === 'node:path') return path;
    if (name === 'node:fs') return { readdirSync: () => ['app.asar','cloudmeet.exe'].map(name => ({name,isDirectory:()=>false})), readFileSync: () => pe };
    if (name === 'node:child_process') return { spawnSync(exe,args) {
      if (exe === 'msiexec.exe') return {status:0,stdout:''};
      const script = args.at(-1);
      assert.equal(exe, 'powershell.exe');
      if (script.includes('ProductVersion')) return {status:0,stdout:config.msiVersion};
      if (script.includes('FileVersion')) return {status:0,stdout:config.peVersion};
      if (script.includes('FROM Shortcut')) return {status:0,stdout:JSON.stringify([
        {id:'MyDesktopShortcut',directory:'DesktopFolder',name:shortcutName,target:'[APPLICATIONROOTDIRECTORY]cloudmeet.exe'},
        {id:'ApplicationStartMenuShortcut',directory:'ApplicationProgramsFolder',name:shortcutName,target:'[APPLICATIONROOTDIRECTORY]cloudmeet.exe'},
      ])};
      throw Error('Unexpected Windows command');
    } };
    if (name === './ca-config.cjs') return {};
    if (name === './network-audit.cjs') return {auditGenerated:()=>{if (!originValid) throw Error('origin mismatch'); return {warnings:[]};}};
    if (name.replaceAll('\\','/').endsWith('@electron/asar')) return {extractFile:(_file,member)=>Buffer.from({
      'package.json':JSON.stringify({version:config.version}),
      'cloudmeet-version.json':JSON.stringify(config.assignment),
      'deployment.env':'fixture', 'client-trust.json':JSON.stringify({origin:config.origin,caFile:null})
    }[member])};
    throw Error('Unexpected dependency (signing must not load): '+name);
  } };
  vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../verify-package.cjs'),'utf8'), sandbox);
  const verify = () => sandbox.module.exports.verifyPackage('client.msi',{platform:'windows',architecture:'x64'},config,null,'workspace','scratch');
  const checks = verify();
  for (const key of ['version','displayVersion','peVersion','architecture','origin','ca','shortcuts']) assert.equal(checks[key].passed,true);
  assert.equal(checks.signature,undefined);
  assert.equal(checks.signing.status,'unsigned');
  shortcutName = 'CloudMeet';
  assert.throws(verify,/shortcut/i);
  shortcutName = '?????;
  originValid = false;
  assert.throws(verify,/origin mismatch/);
});
