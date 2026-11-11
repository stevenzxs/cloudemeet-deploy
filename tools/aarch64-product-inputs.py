"""Verify immutable Actions deployment materials before any image import."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def verify(root, records):
    root = Path(root).resolve()
    for name, expected in records.items():
        path = root / name
        if (path.is_symlink() or not path.is_file() or root not in path.resolve().parents
                or any(p.is_symlink() for p in path.parents if p != root)
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError('Deployment input mismatch: ' + name)


if __name__ == '__main__':
    root = Path(sys.argv[1]).resolve()
    expected = sys.argv[2]
    actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD']).decode().strip()
    if actual != expected:
        raise SystemExit('Deployment commit mismatch')
    records = json.loads((root / 'tools/product-inputs.json').read_text())
    verify(root, records)
    print(json.dumps({'deployment_commit': actual, 'verified_files': records}, indent=2))
