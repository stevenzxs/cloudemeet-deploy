const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { inspectWindowsShortcuts } = require('../verify-package.cjs');
const { forgeWrapper } = require('../revision-config.cjs');

test('active Forge adapter retains Chinese shortcut label and stable identity', async () => {
  const native = { hooks: {}, packagerConfig: { ignore: [] }, makers: [
    { name: '@electron-forge/maker-wix', config: {
      name: 'CloudMeet', exe: 'cloudmeet', manufacturer: 'CloudMeet', shortcutName: '云会议',
      beforeCreate: async creator => { creator.wixTemplate = '<Product Codepage="936"><Package SummaryCodepage="936"/>'; },
    } },
  ] };
  const sandbox = { module: { exports: {} }, require: id => id === 'node:path' ? require(id) : native };
  vm.runInNewContext(forgeWrapper('C:/source', { versions: {
    msi_version: '1.0.36', pe_version: '1.0.36.0',
  } }), sandbox);
  const config = sandbox.module.exports.makers[0].config;
  assert.equal(config.shortcutName, '云会议');
  assert.equal(config.name, 'CloudMeet');
  assert.equal(config.exe, 'cloudmeet');
  assert.equal(config.manufacturer, 'CloudMeet');
  const creator = {};
  await config.beforeCreate(creator);
  assert.match(creator.wixTemplate, /Codepage="936"/);
  assert.equal(creator.windowsCompliantVersion, '1.0.36');
});

const shortcuts = () => [
  { id: 'MyDesktopShortcut', directory: 'DesktopFolder', name: 'CLOUDM~1|云会议', target: '[APPLICATIONROOTDIRECTORY]cloudmeet.exe' },
  { id: 'ApplicationStartMenuShortcut', directory: 'ApplicationProgramsFolder', name: '云会议', target: '[APPLICATIONROOTDIRECTORY]cloudmeet.exe' },
];

test('final MSI inspection reads Shortcut table and accepts Chinese desktop/start menu labels', () => {
  let script;
  const rows = inspectWindowsShortcuts("C:/candidate's/client.msi", value => {
    script = value;
    return JSON.stringify(shortcuts());
  });
  assert.match(script, /SELECT .* FROM Shortcut/);
  assert.match(script, /candidate''s/);
  assert.match(script, /OutputEncoding/);
  assert.equal(rows.length, 2);
});

test('final MSI inspection rejects English labels, missing/duplicate rows and wrong targets', () => {
  assert.equal(typeof inspectWindowsShortcuts, 'function');
  for (const index of [0, 1]) {
    const rows = shortcuts(); rows[index].name = 'CloudMeet';
    assert.throws(() => inspectWindowsShortcuts('client.msi', () => JSON.stringify(rows)), /shortcut/i);
  }
  const wrongTarget = shortcuts(); wrongTarget[0].target = '[APPLICATIONROOTDIRECTORY]other.exe';
  for (const rows of [[], shortcuts().slice(0, 1), [...shortcuts(), shortcuts()[0]], wrongTarget]) {
    assert.throws(() => inspectWindowsShortcuts('client.msi', () => JSON.stringify(rows)), /shortcut/i);
  }
});

test('Windows Installer COM reads Unicode shortcuts from a database-only fixture', {
  skip: process.platform !== 'win32',
}, () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const path = require('node:path');
  const { spawnSync } = require('node:child_process');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cm-shortcut-db-'));
  const file = path.join(dir, 'fixture.msi');
  const q = value => "'" + value.replaceAll("'", "''") + "'";
  try {
    // Only a test database: no payload, installer execution, or product build.
    const sql = 'CREATE TABLE `Shortcut` (`Shortcut` CHAR(72) NOT NULL, `Directory_` CHAR(72), `Name` CHAR(128), `Target` CHAR(255) PRIMARY KEY `Shortcut`)';
    const script = `$ErrorActionPreference='Stop'
$i=New-Object -ComObject WindowsInstaller.Installer
$d=$i.OpenDatabase(${q(file)},3)
$d.OpenView(${q(sql)}).Execute()
${shortcuts().map(row => `$d.OpenView(${q('INSERT INTO `Shortcut` (`Shortcut`, `Directory_`, `Name`, `Target`) VALUES (' + [row.id,row.directory,row.name,row.target].map(q).join(',') + ')')}).Execute()`).join('\n')}
$d.Commit()`;
    const result = spawnSync('powershell.exe', ['-NoProfile', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr || result.error?.message);
    const rows = inspectWindowsShortcuts(file);
    assert.deepEqual(rows.map(row => row.name.split('|').at(-1)), ['云会议', '云会议']);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
