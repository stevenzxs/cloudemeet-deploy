#!/usr/bin/env python3
"""Repair an existing paired transfer/reclaim deployment; check-only by default."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def output(*args):
    return subprocess.check_output(args, stderr=subprocess.PIPE).decode()


def updated_config(text):
    if len(re.findall(r'(?m)^\s*host_transfer_enabled\s*=\s*true\s*;', text)) != 1:
        raise ValueError('Exactly one enabled host transfer setting required')
    values = {'host_reclaim_enabled': 'true',
              'host_reclaim_url': '"https://gateway:9443/internal/host-role/v1/reclaim"'}
    for key, value in values.items():
        pattern = r'(?m)^[ \t]*'+key+r'\s*=[^\n]*$'
        matches = re.findall(pattern, text)
        if len(matches) > 1:
            raise ValueError('Duplicate setting: '+key)
        line = key+' = '+value+';'
        text = re.sub(pattern, lambda _: line, text) if matches else text.rstrip()+'\n'+line+'\n'
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prosody', required=True)
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-idle', action='store_true', help='Administrator confirms no active meetings')
    args = parser.parse_args()
    if args.apply and not args.confirm_idle:
        parser.error('Prosody restart interrupts XMPP; --confirm-idle required for --apply')
    p, g = [json.loads(output('docker', 'inspect', name))[0] for name in (args.prosody, args.gateway)]
    project = p['Config']['Labels']['com.docker.compose.project']
    if project != g['Config']['Labels']['com.docker.compose.project'] or not project:
        raise ValueError('Containers must belong to the same Compose project')
    if p['Config']['Labels']['com.docker.compose.service'] != 'prosody' or g['Config']['Labels']['com.docker.compose.service'] != 'gateway':
        raise ValueError('Unexpected container service identity')
    root = Path(p['Config']['Labels']['com.docker.compose.project.working_dir']).resolve()
    target = '/config/conf.d/zz-cloudmeet-host-control.cfg.lua'
    matches = []
    for mount in p['Mounts']:
        dest = mount['Destination'].rstrip('/')
        if mount['Type'] == 'bind' and (target == dest or target.startswith(dest+'/')):
            matches.append((len(dest), Path(mount['Source'])/target[len(dest):].lstrip('/')))
    if not matches:
        raise ValueError('Persistent bind-mounted configuration required')
    config = max(matches, key=lambda item: item[0])[1]
    if config.is_symlink() or not config.is_file() or root not in config.resolve().parents:
        raise ValueError('Configuration must be a regular file inside the actual project')
    original = config.read_text()
    if output('docker', 'exec', args.prosody, 'cat', target) != original:
        raise ValueError('Host/container configuration differs')
    candidate = updated_config(original)
    for setting in ['host_role_check_secret', 'host_role_check_url', 'host_transfer_url',
                    'host_transfer_complete_url', 'host_transfer_claim_url', 'host_transfer_status_url',
                    'host_transfer_rebind_url', 'host_transfer_participant_domain']:
        if not re.search(r'(?m)^\s*'+setting+r'\s*=', original):
            raise ValueError('Missing prerequisite: '+setting)
    plugin = output('docker', 'exec', args.prosody, 'cat', '/prosody-plugins-custom/mod_muc_host_transfer.lua')
    if 'host_reclaim_enabled' not in plugin or ':reclaim' not in plugin:
        raise ValueError('Loaded plugin file lacks reclaim implementation')
    runtime = json.loads(output('docker', 'exec', args.gateway, 'curl', '-fsS', 'http://127.0.0.1:2019/config/'))
    servers = runtime['apps']['http']['servers'].values()
    internal = [s for s in servers if s['listen'] == [':9443']]
    if len(internal) != 1 or '/internal/host-role/v1/reclaim' not in json.dumps(internal):
        raise ValueError('Internal gateway reclaim route missing')
    # Probe without credentials or mutations: API must recognize route and deny authentication.
    status = output('docker', 'exec', '-i', args.gateway, 'curl', '-sS', '--max-time', '10',
                    '-o', '/dev/null', '-w', '%{http_code}', '-X', 'POST',
                    '-H', 'Content-Type: application/json', '--data', '{}',
                    'http://api:9000/mapi/internal/host-role/v1/reclaim')
    if status not in ('401', '403'):
        raise ValueError('Reclaim API must deny unauthenticated probe with 401/403, received '+status)
    subprocess.run(['docker', 'exec', args.prosody, 'prosodyctl', 'check', 'config'],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    print('Preflight passed. Target:', config, 'Prosody:', args.prosody)
    if not args.apply:
        print('CHECK ONLY: no configuration changes or restart. Use --apply --confirm-idle.')
        return
    if candidate == original:
        print('Already configured; no changes or restart. Functional acceptance still required.')
        return
    os.umask(0o077)
    backup = config.with_name(config.name+'.reclaim-backup-'+datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ'))
    shutil.copy2(config, backup)
    try:
        # Preserve bind-mounted inode and ownership.
        config.write_text(candidate)
        subprocess.run(['docker', 'exec', args.prosody, 'prosodyctl', 'check', 'config'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        subprocess.run(['docker', 'restart', args.prosody], check=True)
        if output('docker', 'inspect', '--format', '{{.State.Running}}', args.prosody).strip() != 'true':
            raise ValueError('Prosody not running after restart')
    except Exception:
        config.write_text(original)
        subprocess.run(['docker', 'restart', args.prosody], check=False)
        raise
    print('Configuration applied; backup:', backup)
    print('Restart completed, NOT functional acceptance. Verify transfer, creator reclaim, revocation and credential confirmation.')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit('Command failed; sensitive output suppressed. Inspect service locally. If changes began, inspect rollback result.')
