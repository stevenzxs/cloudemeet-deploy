"""Strict public deployment configuration; never execute dotenv as shell code."""
import argparse
import ipaddress
import os
import hashlib
import json
from pathlib import Path
import re
import shlex


ORIGIN_CONFIG = '''// Managed same-origin signaling; no external host is embedded.
config.bosh = '/http-bind';
config.websocket = (window.location.protocol === 'https:' ? 'wss://' : 'ws://')
    + window.location.host + '/xmpp-websocket';
'''


def install_origin_config(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Refusing symlink for browser configuration')
    if path.exists():
        if path.read_text(encoding='utf-8') != ORIGIN_CONFIG:
            raise ValueError('Existing custom-config.js preserved; explicit merge is required')
        return
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(ORIGIN_CONFIG)
    path.chmod(0o644)


def read_env(path):
    values = {}
    for number, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in values:
            raise ValueError('Invalid or duplicate configuration key at line %s' % number)
        values[key] = value
    return values


def load_target(path):
    values = read_env(path)
    expected = {'SITE_SCHEME', 'HTTPS_PORT', 'HTTP_PORT', 'MEDIA_PORT', 'MEDIA_HOST'}
    if set(values) != expected:
        raise ValueError('target.env must contain exactly: ' + ', '.join(sorted(expected)))
    media_host = values['MEDIA_HOST']
    if media_host:
        media_host = str(ipaddress.IPv4Address(media_host))
    if values['SITE_SCHEME'] != 'https':
        raise ValueError('This baseline requires HTTPS')
    for key in ('HTTPS_PORT', 'HTTP_PORT', 'MEDIA_PORT'):
        if not values[key].isdigit() or not 1 <= int(values[key]) <= 65535:
            raise ValueError('Invalid port: ' + key)
        values[key] = str(int(values[key]))
    if values['HTTPS_PORT'] == values['HTTP_PORT']:
        raise ValueError('HTTP and HTTPS TCP ports must differ')
    # This identity is for the local fallback certificate, never a browser redirect.
    values.update(SITE_HOST='cloudmeet.internal', PUBLIC_URL='https://cloudmeet.internal',
                  JVB_ADVERTISE_IPS=media_host, JVB_PORT=values['MEDIA_PORT'])
    return values


def resolve_target(root, external=None):
    """Resolve one explicit instance file without modifying immutable package bytes."""
    root = Path(root).resolve()
    external = external or os.environ.get('CLOUDMEET_TARGET_ENV')
    if external:
        path = Path(external)
        if not path.is_absolute() or path.is_symlink():
            raise ValueError('Instance target must be an absolute non-symlink path')
        path = path.resolve()
        if path == root or root in path.parents:
            raise ValueError('Instance target must be outside immutable package')
        values=load_target(path)
    else:
        values=load_target(root/'target.env')
    expected=os.environ.get('CLOUDMEET_TARGET_SHA256')
    if expected and fingerprint(values)!=expected:
        raise ValueError('Instance target changed after preflight')
    return values


def fingerprint(values):
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode('utf-8')).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('file')
    args = parser.parse_args()
    for key, value in load_target(args.file).items():
        print('export %s=%s' % (key, shlex.quote(value)))
