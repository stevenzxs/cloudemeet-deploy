#!/usr/bin/env python3
"""Probe internal strict TLS and auth without printing credentials or bodies."""
import argparse
import json
from pathlib import Path
import subprocess


def probe(root, network, image):
    root=Path(root)
    secret=(root/'host-control/api.env').read_text().strip().split('=',1)[1]
    def request(value):
        config = 'silent\nshow-error\ncacert = "/ca.crt"\noutput = "/dev/null"\nwrite-out = "%{http_code}"\n'
        config += 'header = "Content-Type: application/json"\n'
        if value is not None:
            config += 'header = "X-Role-Check-Secret: '+value+'"\n'
        config += 'data = "'+json.dumps({'roomName':'123456789'}).replace('"','\\"')+'"\n'
        config += 'url = "https://gateway:9443/internal/host-role/v1/status"\n'
        return subprocess.check_output(['docker','run','--rm','-i','--network',network,
            '--entrypoint','curl','-v',str(root/'host-control/ca.crt')+':/ca.crt:ro',image,
            '--config','-'],input=config,text=True).strip()
    # Unknown rooms return business conflict409 after authentication; no test
    # authority is created merely to obtain200.
    for name,value,expected in [('missing',None,{'403'}),('wrong','invalid-test-secret',{'403'}),('valid',secret,{'200','409'})]:
        status=request(value)
        print(name+' internal authentication: '+status)
        if status not in expected:
            raise RuntimeError('internal authentication probe failed: '+name)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['root','network','image']: p.add_argument('--'+name,required=True)
    a=p.parse_args();probe(a.root,a.network,a.image)
