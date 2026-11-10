#!/usr/bin/env python3
"""Migrate the candidate overlay away from /run bind-mount parent ownership."""
import argparse
import json
import os
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--root',required=True)
a=p.parse_args()
root=Path(a.root)
path=root/'host-control/compose.json'
data=json.loads(path.read_text())
service=data['services']['prosody']
service['volumes']=[v.replace('/run/prosody/config/conf.d/zz-', '/config/conf.d/zz-') for v in service['volumes']]
config=root/'data/jitsi/prosody/config/conf.d'
config.mkdir(exist_ok=True)
os.chown(config,1000,1000)
path.write_text(json.dumps(data,indent=2)+'\n')
print('Candidate mount corrected; persistent /config copied by official startup')
