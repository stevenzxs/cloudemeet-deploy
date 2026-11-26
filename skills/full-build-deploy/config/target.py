"""Strict public deployment configuration; never execute dotenv as shell code."""
import argparse
import ipaddress
import os
import hashlib
import json
from pathlib import Path
import re
import shlex
import urllib.parse


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
    return validate_target(read_env(path))


def validate_target(values):
    values = dict(values)
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


def apply_origin_contract(values, contract):
    """Bind service-facing public URL/host/HTTPS port to the approved batch origin."""
    values = dict(values)
    required = {'origin', 'scheme', 'host', 'port', 'addresses'}
    if not isinstance(contract, dict) or not required <= set(contract):
        raise ValueError('Complete approved origin contract required')
    try:
        parsed = urllib.parse.urlsplit(contract['origin'])
        parsed_port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid approved origin contract') from exc
    if (parsed.scheme != contract['scheme'] or parsed.hostname != contract['host']
            or parsed_port != contract['port'] or parsed.scheme != 'https'
            or parsed.username or parsed.password or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        raise ValueError('Origin contract fields disagree or unsupported server scheme')
    if not isinstance(contract['addresses'], list) or not contract['addresses']:
        raise ValueError('Resolved origin address evidence required')
    try:
        addresses = {str(ipaddress.ip_address(value)) for value in contract['addresses']}
    except ValueError as exc:
        raise ValueError('Invalid origin address evidence') from exc
    host = contract['host']
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and addresses != {str(literal)}:
        raise ValueError('Literal origin differs from resolved address evidence')
    if not 1 <= int(contract['port']) <= 65535:
        raise ValueError('Invalid origin port')
    values.update(SITE_SCHEME='https', HTTPS_PORT=str(contract['port']),
                  SITE_HOST=host, PUBLIC_URL=contract['origin'])
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
    contract_file=root/'provenance/origin-contract.json'
    if contract_file.is_file():
        contract=json.loads(contract_file.read_text(encoding='utf-8'))
        values=apply_origin_contract(values,contract)
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
