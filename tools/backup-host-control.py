#!/usr/bin/env python3
"""Consistent local backup and idle gate before optional host-control rollout."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess


def backup(root, project):
    root = Path(root).resolve()
    stats = json.loads(subprocess.check_output(['docker', 'exec', project+'-jicofo-1',
                       'curl', '-fsS', 'http://127.0.0.1:8888/stats']))
    if stats.get('conferences') != 0 or stats.get('participants') != 0:
        raise RuntimeError('active or unknown meeting state: refuse rollout')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = root/'backups'/('host-control-'+stamp)
    out.mkdir(parents=True, mode=0o700)
    out.chmod(0o700)
    for name in ['.env','jitsi.env','Caddyfile','docker-compose.yml','registry.yaml','jitsi-base.yaml']:
        shutil.copy2(root/name, out/name)
    for name in ['data/jitsi/prosody/config','data/jitsi/prosody/prosody-plugins-custom','data/jitsi/web']:
        if (root/name).exists():
            shutil.copytree(root/name, out/name)
    source = root/'data/api/jitsi-meet-api.sqlite.db'
    if not source.is_file():
        raise RuntimeError('database location mismatch: no valid backup')
    with sqlite3.connect('file:'+str(source)+'?mode=ro', uri=True) as src, sqlite3.connect(out/'api.sqlite.db') as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('backup integrity check failed')
    rows = subprocess.check_output(['docker','ps','-q'], text=True).split()
    state = []
    for cid in rows:
        info = json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
        state.append({k:info[k] for k in ['Id','Name','Image'] } | {'StartedAt':info['State']['StartedAt']})
    (out/'containers.json').write_text(json.dumps(state,indent=2))
    (out/'idle-stats.json').write_text(json.dumps(stats,indent=2))
    print('Backup verified: '+str(out))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--project',required=True)
    args=parser.parse_args()
    backup(args.root,args.project)
