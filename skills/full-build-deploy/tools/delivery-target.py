#!/usr/bin/env python3
"""Origin-only public configuration derivation. Never dispatch, allocate or deploy."""
import argparse
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import socket
from urllib.parse import urlsplit


def usable_ipv4(value):
    ip = ipaddress.IPv4Address(value)
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_link_local or ip.is_reserved:
        raise ValueError('Usable target IPv4 required')
    return str(ip)


def derive(origin, root, resolved=None, target_ipv4=None):
    u = urlsplit(origin)
    if (u.scheme != 'https' or not u.hostname or u.username is not None or u.password is not None
            or u.path not in ('', '/') or u.query or u.fragment or any(c.isspace() for c in origin)):
        raise ValueError('Complete HTTPS origin only; no credentials/path/query/fragment')
    host = u.hostname
    port = 443 if u.port is None else u.port
    if not 1 <= port <= 65535:
        raise ValueError('Invalid port')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host) or '..' in host:
            raise ValueError('Invalid domain')
        addresses = {usable_ipv4(v) for v in resolved or []}
        if len(addresses) != 1 or target_ipv4 is None or usable_ipv4(target_ipv4) not in addresses:
            raise ValueError('Domain requires unique current A record and independently verified same-server IPv4')
        media = next(iter(addresses))
    else:
        media = usable_ipv4(host)
        if target_ipv4 and usable_ipv4(target_ipv4) != media:
            raise ValueError('Origin and target identity mismatch')
    root = Path(root)
    spec = importlib.util.spec_from_file_location('target', root/'config/target.py')
    target = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(target)
    values = target.read_env(root/'config/target.env')
    values.update(SITE_SCHEME='https', HTTPS_PORT=str(port), MEDIA_HOST=media)
    target.validate_target(values)
    skill_root = Path(__file__).resolve().parents[1]
    baseline = json.loads((skill_root/'config/version-policy.json').read_text(encoding='utf-8'))['client_baseline']
    return {'origin': f'https://{host}' + (f':{port}' if port != 443 else ''),
            'client': {'SITE_SCHEME': 'https', 'SITE_DOMAIN': host, 'SITE_PORT': str(port), 'CLIENT_VERSION': baseline},
            'target': values}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--origin', required=True)
    p.add_argument('--verified-target-ipv4', help='From current target identity evidence, not user re-entry')
    p.add_argument('--target-env', type=Path, help='Create external instance file, refuses overwrite/package paths')
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    u = urlsplit(args.origin)
    try:
        ipaddress.ip_address(u.hostname or '')
        addresses = None
    except ValueError:
        addresses = [v[4][0] for v in socket.getaddrinfo(u.hostname, None, socket.AF_INET, socket.SOCK_STREAM)]
    result = derive(args.origin, root, addresses, args.verified_target_ipv4)
    if args.target_env:
        out = args.target_env.resolve()
        if out.is_relative_to(root):
            raise ValueError('Instance target.env must be outside configuration/package tree')
        with out.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(''.join(f'{k}={v}\n' for k, v in result['target'].items()))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
