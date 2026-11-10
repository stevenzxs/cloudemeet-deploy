#!/usr/bin/env python3
"""Explicit opt-in after compatible installed clients pass their prerequisite gates.

Only updates the candidate server config; no restart. Requires idle stats and
the verified backup. Invoke explicitly; preparation never calls this tool.
"""
import argparse
import json
from pathlib import Path
import subprocess


def enable(root, project):
    root = Path(root)
    stats = json.loads(subprocess.check_output(['docker','exec',project+'-jicofo-1',
        'curl','-fsS','http://127.0.0.1:8888/stats']))
    if stats.get('conferences') != 0 or stats.get('participants') != 0:
        raise RuntimeError('idle gate failed')
    if not list((root/'backups').glob('host-control-*/api.sqlite.db')):
        raise RuntimeError('verified backup required')
    config = root/'host-control/zz-cloudmeet-host-control.cfg.lua'
    text = config.read_text()
    for name in ['host_transfer_enabled','host_reclaim_enabled']:
        if text.count(name+' = false;') != 1:
            raise RuntimeError('unexpected feature config: '+name)
    if 'host_transfer_admin_recovery_enabled = false;' not in text:
        raise RuntimeError('administrator recovery must stay disabled')
    # Preserve inode: Docker's read-only file bind sees this exact source inode.
    with config.open('w') as output:
        output.write(text.replace('host_transfer_enabled = false;', 'host_transfer_enabled = true;')
            .replace('host_reclaim_enabled = false;', 'host_reclaim_enabled = true;'))
    print('Feature config enabled, pending explicit Prosody restart; no services changed')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True)
    p.add_argument('--project',required=True)
    a=p.parse_args();enable(a.root,a.project)
