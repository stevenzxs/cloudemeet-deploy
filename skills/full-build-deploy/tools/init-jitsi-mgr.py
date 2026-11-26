#!/usr/bin/env python3
"""First-install jitsi-mgr secrets; no network, overwrite, or secret logging."""
import os
from pathlib import Path
import secrets
import subprocess

DEPLOY_ROOT = Path(__file__).resolve().parent.parent
JITSI_MGR_DATA = DEPLOY_ROOT / 'data/jitsi-mgr'
KEYS_DIR = JITSI_MGR_DATA / 'keys'


def create_directories():
    JITSI_MGR_DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    KEYS_DIR.mkdir(mode=0o700)


def generate_jwt_keys():
    private = KEYS_DIR / 'jwt-private.pem'
    public = KEYS_DIR / 'jwt-public.pem'
    if private.exists() or public.exists():
        raise ValueError('First installation refuses existing jitsi-mgr keys')
    fd = os.open(str(private), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    # PKCS#8, not PKCS#1: JwtTokenProvider consumes PKCS8EncodedKeySpec.
    subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
                    'rsa_keygen_bits:2048', '-out', str(private)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['openssl', 'pkey', '-in', str(private), '-pubout',
                    '-out', str(public)], check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    public.chmod(0o644)
    return True


def generate_db_password():
    env = DEPLOY_ROOT / '.env'
    text = env.read_text() if env.exists() else ''
    if any(line.startswith('JITSI_MGR_DB_PASSWORD=') for line in text.splitlines()):
        raise ValueError('First installation refuses existing jitsi-mgr password')
    fd = os.open(str(env), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write('\nJITSI_MGR_DB_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
    return True


def main():
    create_directories()
    generate_jwt_keys()
    generate_db_password()
    print('jitsi-mgr target secrets initialized; private material remains on target.')


if __name__ == '__main__':
    main()
