"""Strict public deployment configuration; never execute dotenv as shell code."""
import argparse
import ipaddress
from pathlib import Path
import re
import shlex


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
    expected = {'SERVER_HOST', 'SITE_SCHEME', 'HTTPS_PORT', 'HTTP_PORT', 'MEDIA_PORT'}
    if set(values) != expected:
        raise ValueError('target.env must contain exactly: ' + ', '.join(sorted(expected)))
    host = str(ipaddress.IPv4Address(values['SERVER_HOST']))
    if values['SITE_SCHEME'] != 'https':
        raise ValueError('This baseline requires HTTPS')
    for key in ('HTTPS_PORT', 'HTTP_PORT', 'MEDIA_PORT'):
        if not values[key].isdigit() or not 1 <= int(values[key]) <= 65535:
            raise ValueError('Invalid port: ' + key)
        values[key] = str(int(values[key]))
    if values['HTTPS_PORT'] == values['HTTP_PORT']:
        raise ValueError('HTTP and HTTPS TCP ports must differ')
    values.update(SITE_HOST=host, PUBLIC_URL='https://' + host + ':' + values['HTTPS_PORT'],
                  JVB_ADVERTISE_IPS=host, JVB_PORT=values['MEDIA_PORT'])
    return values


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('file')
    args = parser.parse_args()
    for key, value in load_target(args.file).items():
        print('export %s=%s' % (key, shlex.quote(value)))
