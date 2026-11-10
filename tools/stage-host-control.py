#!/usr/bin/env python3
"""Stage verified plugin/internal Caddy config only. Does not restart services."""
import argparse
import hashlib
from pathlib import Path
import shutil


def stage(root, plugin):
    root, plugin = Path(root), Path(plugin)
    expected = '91779945f43d4f7d7ad2cabe32f04503fb62d29ddaf410e74cfc87209b1b201c'
    if hashlib.sha256(plugin.read_bytes()).hexdigest() != expected:
        raise RuntimeError('plugin source digest mismatch')
    if not list((root/'backups').glob('host-control-*/api.sqlite.db')):
        raise RuntimeError('verified backup required')
    caddy = root/'Caddyfile'
    current = caddy.read_text()
    if 'gateway:9443' in current:
        raise RuntimeError('internal listener already staged; inspect, do not append again')
    for directory in [root/'patches/prosody', root/'data/jitsi/prosody/prosody-plugins-custom']:
        target = directory/'mod_muc_host_transfer.lua'
        if target.exists():
            raise RuntimeError('existing plugin requires explicit diff review')
        shutil.copy2(plugin, target)
        target.chmod(0o644)
    caddy.write_text(current+'\n'+(root/'host-control/gateway-internal.caddy').read_text())
    print('Staged plugin and internal listener; services unchanged')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True)
    p.add_argument('--plugin',required=True)
    a=p.parse_args()
    stage(a.root,a.plugin)
