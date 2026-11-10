#!/usr/bin/env python3
"""Stage an immutable business Web directory override; never changes images/data."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import tarfile


def stage(root, archive, expected):
    root, archive = Path(root), Path(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise RuntimeError('archive digest mismatch')
    output = root/'host-control/web-candidate'
    if output.exists():
        raise RuntimeError('candidate already exists')
    with tarfile.open(archive) as source:
        members = source.getmembers()
        if any(m.issym() or m.islnk() or not (m.isfile() or m.isdir())
               or Path(m.name).is_absolute() or '..' in Path(m.name).parts for m in members):
            raise RuntimeError('unsafe archive')
        output.mkdir()
        for member in members:
            target = output/member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as data, target.open('wb') as destination:
                    shutil.copyfileobj(data, destination)
    if not (output/'index.html').is_file():
        raise RuntimeError('missing entrypoint')
    overlay = {'services': {'app-web': {'volumes': [str(output)+':/usr/share/nginx/html/cm:ro']}}}
    (root/'host-control/web-compose.json').write_text(json.dumps(overlay,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['root','archive','sha256']: p.add_argument('--'+name,required=True)
    a=p.parse_args();stage(a.root,a.archive,a.sha256)
