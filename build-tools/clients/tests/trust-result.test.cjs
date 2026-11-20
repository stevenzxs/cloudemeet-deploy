const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
test('Windows verification returns authoritative identity from inside certificate tool trust scope', () => {
  const policy = {commit:'a'.repeat(40),windows_identity:'identity.json'};
  const expected = 'b'.repeat(64);
  const calls=[];
  let output = 'tool verification output\nCLOUDMEET_VERIFIED:'+JSON.stringify({status:'Valid',signer:expected,timestamp:true})+'\n';
  const sandbox={module:{exports:{}},__dirname:path.resolve(__dirname,'..'),process:{env:{SIGNTOOL_PATH:'tool'}},require(name){
    if(name==='node:path') return path;
    if(name==='node:fs') return {existsSync:()=>true,readFileSync:p=>JSON.stringify(p.endsWith('signing-policy.json')?policy:{certificate_der_sha256:expected})};
    if(name==='node:child_process') return {spawnSync(exe,args){calls.push({exe,args});if(exe==='git')return {status:0,stdout:args.includes('rev-parse')?policy.commit:''};return {status:0,stdout:output};}};
    throw Error(name);
  }};
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
});
