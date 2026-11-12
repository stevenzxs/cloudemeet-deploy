"""First installation only: target-generated secrets and CA, no data replacement."""
import importlib.util
import json
import os
from pathlib import Path
import secrets


def main():
    root = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('verifier', root / 'install.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    verifier.verify_checksums(root)
    verifier.require_ready(json.loads((root / 'candidate.json').read_text()))
    if any((root / name).exists() or (root / name).is_symlink() for name in ['.env', 'data']):
        raise ValueError('First installation refuses existing secrets or data')
    if (root/'target.env').is_file():
        target_spec = importlib.util.spec_from_file_location('target_config', root/'target.py')
        target = importlib.util.module_from_spec(target_spec)
        target_spec.loader.exec_module(target)
        target.load_target(root/'target.env')
        text = ''
    else:
        text = (root / 'server.env.example').read_text()
    for key in ['JWT_APP_SECRET', 'JICOFO_AUTH_PASSWORD', 'JVB_AUTH_PASSWORD']:
        text += key + '=' + secrets.token_hex(32) + '\n'
    fd = os.open(str(root / '.env'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
    print('Fresh secrets generated. Gateway will generate a new target CA; never export its private key.')


if __name__ == '__main__':
    main()
