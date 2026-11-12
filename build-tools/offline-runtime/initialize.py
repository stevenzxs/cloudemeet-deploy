"""First installation only: target-generated secrets and CA, no data replacement."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess


def initialize_host_control(root):
    """Generate private internal TLS material on the installation target only."""
    out = root/'data/host-control'
    out.mkdir(parents=True, mode=0o755)
    def openssl(*args):
        subprocess.run(['openssl', *args], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    openssl('req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-days', '3650',
            '-subj', '/CN=CloudMeet Internal CA', '-keyout', str(out/'ca.key'), '-out', str(out/'ca.crt'))
    openssl('req', '-newkey', 'rsa:3072', '-nodes', '-subj', '/CN=gateway',
            '-keyout', str(out/'gateway.key'), '-out', str(out/'gateway.csr'))
    (out/'cert.ext').write_text('subjectAltName=DNS:gateway\nextendedKeyUsage=serverAuth\n')
    openssl('x509', '-req', '-in', str(out/'gateway.csr'), '-CA', str(out/'ca.crt'),
            '-CAkey', str(out/'ca.key'), '-CAcreateserial', '-days', '365',
            '-extfile', str(out/'cert.ext'), '-out', str(out/'gateway.crt'))
    for path in out.iterdir():
        path.chmod(0o644 if path.suffix == '.crt' else 0o600)


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
    subprocess.run(['openssl', 'version'], check=True, stdout=subprocess.DEVNULL)
    for key in ['JWT_APP_SECRET', 'JICOFO_AUTH_PASSWORD', 'JVB_AUTH_PASSWORD', 'JITSI_ROLE_CHECK_SECRET']:
        text += key + '=' + secrets.token_hex(32) + '\n'
    fd = os.open(str(root / '.env'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
    initialize_host_control(root)
    print('Fresh secrets generated. Gateway will generate a new target CA; never export its private key.')


if __name__ == '__main__':
    main()
