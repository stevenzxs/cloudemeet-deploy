#!/usr/bin/env python3
"""Offline network-input inventory and fail-closed target/Compose checks. No probes."""
import argparse
import datetime
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

SERVICES = ['gateway', 'app-web', 'api', 'web', 'prosody', 'jicofo', 'jvb']
NETWORK = re.compile(r'(?:^|_)(?:IP|IPS|HOST|HOSTS|PORT|PORTS|URL|URLS|ADDRESS|DOMAIN|BIND|SERVER|SERVERS)(?:_|$)')
SECRET = re.compile(r'PASSWORD|SECRET|TOKEN|CREDENTIAL|PRIVATE|BINDPW', re.I)


def load_module(file):
    spec = importlib.util.spec_from_file_location('network_target', file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit(root, mode='generic', target=None, rendered=None):
    root = Path(root)
    config = root/'config' if (root/'config/target.env').exists() else root
    target_module = load_module(config/'target.py')
    values = target_module.read_env(config/'target.env')
    values.update(target or {})
    public = target_module.read_env(config/'jitsi.env')
    parameters, errors, inputs = [], [], {}
    if target is not None:
        inputs['effective-target-values'] = hashlib.sha256(
            json.dumps(target, sort_keys=True).encode('utf-8')).hexdigest()

    def add(name, value, source, service='shared', status='pass', consumer=None):
        if SECRET.search(name):
            return
        value = str(value)
        if '://' in value:
            try:
                u = urlsplit(value)
                if u.username or u.password or u.query or u.fragment:
                    errors.append('Credential-bearing URL rejected: '+name)
                    value = '[redacted URL]'
            except ValueError:
                errors.append('Malformed URL: '+name)
                value = '[invalid URL]'
        parameters.append(dict(name=name, value=value, source=source, service=service,
                               status=status, consumer=consumer or source))

    # Inventory every declared network environment variable and interpolation, even
    # optional upstream switches. Values absent from the explicit input are not
    # inherited from the calling shell and are never reported as validated.
    files = [config/'target.env', config/'jitsi.env', config/'jitsi-base.yaml',
             config/'docker-compose.yml', config/'Caddyfile',
             root/'build-tools/package.sh', root/'build-tools/templates/nginx.conf',
             root/'build-tools/offline-runtime/start.py']
    for file in files:
        if not file.is_file():
            continue
        data = file.read_bytes()
        relative = file.relative_to(root).as_posix()
        inputs[relative] = hashlib.sha256(data).hexdigest()
        service = 'shared'
        for number, line in enumerate(data.decode('utf-8').splitlines(), 1):
            if line.lstrip().startswith('#'):
                continue
            match = re.match(r'^\s{2,4}([a-z][a-z-]*):\s*$', line)
            if match and match[1] in SERVICES:
                service = match[1]
            names = set(re.findall(r'\b[A-Z][A-Z0-9_]+\b', line))
            for name in sorted(names):
                if NETWORK.search(name) and not SECRET.search(name):
                    value = values.get(name, public.get(name, ''))
                    literal = re.search(r"['\"]"+re.escape(name)+r"['\"]\s*:\s*['\"]([^'\"]*)['\"]", line)
                    default = re.search(r'\$\{'+re.escape(name)+r':-([^}]*)\}', line)
                    if not value and literal:
                        value = literal[1]
                    if not value and default:
                        value = default[1]
                    add(name, value, relative+':'+str(number), service,
                        'configured' if value else 'optional-or-derived')
                    if name.endswith('_PORT') and value and '${' not in value and (
                            not value.isdigit() or not 1 <= int(value) <= 65535):
                        errors.append('Invalid configured port: '+name)
            # Fixed routes/listeners matter as much as env parameters. Do not dump
            # arbitrary source lines (which can contain credentials).
            for endpoint in re.findall(r'(?:https?|wss?)://[a-zA-Z0-9_.:-]+(?:/[a-zA-Z0-9_./-]*)?', line):
                add('FIXED_ENDPOINT', endpoint, relative+':'+str(number), service)
            for endpoint in re.findall(r'(?:reverse_proxy|listen|server|proxy_pass)\s+([a-zA-Z0-9_.:/$-]+)', line):
                add('LISTENER_OR_UPSTREAM', endpoint, relative+':'+str(number), service)

    for name in ('HTTP_PORT', 'HTTPS_PORT', 'MEDIA_PORT'):
        value = values.get(name, '')
        if not re.fullmatch(r'[0-9]+', value) or not 1 <= int(value) <= 65535:
            errors.append('Invalid port: '+name)
        add(name, value, 'target.env', 'gateway' if name != 'MEDIA_PORT' else 'jvb')
    if values.get('HTTP_PORT') == values.get('HTTPS_PORT'):
        errors.append('HTTP/HTTPS TCP port collision')
    if values.get('SITE_SCHEME') != 'https':
        errors.append('Server baseline requires HTTPS')
    host = values.get('MEDIA_HOST', '')
    status = 'pass'
    if not host:
        status = 'deferred'
        if mode == 'target':
            errors.append('MEDIA_HOST required before target startup; discovery is not evidence')
    else:
        try:
            ip = ipaddress.IPv4Address(host)
            if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_link_local or ip.is_reserved:
                raise ValueError()
        except ValueError:
            errors.append('MEDIA_HOST must be a usable client-reachable IPv4 (reachability untested)')
            status = 'fail'
    add('MEDIA_HOST', host, 'target.env', 'jvb', status, 'target.py -> JVB_ADVERTISE_IPS')
    add('JVB_ADVERTISE_IPS', host, 'derived:MEDIA_HOST', 'jvb', status, 'Compose jvb.environment')
    add('JVB_PORT', values.get('MEDIA_PORT', ''), 'derived:MEDIA_PORT', 'jvb')

    if rendered is not None:
        configs = rendered.get('services', {})
        if set(configs) != set(SERVICES):
            errors.append('Rendered Compose must contain exactly seven services')
        for service, settings in configs.items():
            if service in ('gateway', 'jvb'):
                expected = ({(values['HTTPS_PORT'], '443', 'tcp'),
                             (values['HTTP_PORT'], '80', 'tcp')} if service == 'gateway'
                            else {(values['MEDIA_PORT'], values['MEDIA_PORT'], 'udp')})
                ports = settings.get('ports', [])
                actual = [(str(p.get('published')), str(p.get('target')), p.get('protocol', 'tcp'))
                          for p in ports if isinstance(p, dict)]
                if len(actual) != len(expected) or set(actual) != expected:
                    errors.append('Required published ports mismatch: '+service)
            environment = settings.get('environment', {})
            if isinstance(environment, list):
                environment = dict(item.partition('=')[::2] for item in environment)
            for key, value in environment.items():
                if NETWORK.search(key) and not SECRET.search(key):
                    add(key, value or '', 'rendered Compose environment', service)
                    if key.endswith('_PORT') and value and (not str(value).isdigit() or not 1 <= int(value) <= 65535):
                        errors.append('Invalid rendered port: '+service+'.'+key)
            for port in settings.get('ports', []):
                if not isinstance(port, dict):
                    errors.append('Compose ports must be normalized JSON objects')
                    continue
                add('PUBLISHED_PORT', json.dumps({k: port.get(k) for k in
                    ('host_ip', 'published', 'target', 'protocol')}), 'rendered Compose ports', service)
                if service in ('gateway','jvb') and port.get('host_ip') not in (None,'','0.0.0.0','::'):
                    errors.append('Direct-entry published binding must be wildcard: '+service)
                if service not in ('gateway', 'jvb') and port.get('host_ip') not in ('127.0.0.1', '::1'):
                    errors.append('Internal service exposed: '+service)
                if service == 'gateway' and str(port.get('target')) not in ('80', '443'):
                    errors.append('Internal gateway listener must not be published')
                if service == 'jvb' and (str(port.get('published')) != values['MEDIA_PORT']
                        or str(port.get('target')) != values['MEDIA_PORT'] or port.get('protocol', 'tcp') != 'udp'):
                    errors.append('JVB media port/protocol mismatch')
            if service == 'jvb':
                if str(environment.get('JVB_ADVERTISE_IPS', '')) != host:
                    errors.append('MEDIA_HOST / JVB_ADVERTISE_IPS mismatch')
                if str(environment.get('JVB_PORT', '')) != values['MEDIA_PORT']:
                    errors.append('MEDIA_PORT / JVB_PORT mismatch')
        for key in ('PUBLIC_URL', 'XMPP_DOMAIN', 'XMPP_AUTH_DOMAIN', 'XMPP_MUC_DOMAIN', 'XMPP_PORT'):
            seen = {str(c.get('environment', {}).get(key)) for c in configs.values()
                    if isinstance(c.get('environment'), dict) and c['environment'].get(key) is not None}
            if len(seen) > 1:
                errors.append('Cross-service mismatch: '+key)

    def git(*args):
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else 'unavailable'

    source_file = root/'build-tools/sources.json'
    return dict(schema=1, phase='rendered' if rendered is not None else 'preflight',
                mode=mode, services=SERVICES, created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                config_sha=git('rev-parse', 'HEAD'), dirty=bool(git('status', '--porcelain', '--untracked-files=no')),
                run_id=os.environ.get('GITHUB_RUN_ID'), attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
                batch=os.environ.get('BATCH'), sources=json.loads(source_file.read_text()) if source_file.exists() else {},
                input_sha256=inputs, parameters=parameters, errors=errors,
                status='fail' if errors else 'pass',
                unverified=['target routes/firewall/NAT/UDP', 'endpoint TLS', 'actual ICE candidates', 'real meeting media'])


def write_report(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(report, indent=2, ensure_ascii=False)+'\n').encode('utf-8')
    (output/'network-audit.json').write_bytes(raw)
    rows = ['# Network parameter audit', '', 'Status: '+report['status'],
            'JSON SHA256: '+hashlib.sha256(raw).hexdigest(), '',
            '| Service | Parameter | Value | Source | Status |', '|---|---|---|---|---|']
    for p in report['parameters']:
        rows.append('| '+' | '.join(str(p[k]).replace('|', '&#124;').replace('\n', ' ')
                    for k in ('service', 'name', 'value', 'source', 'status'))+' |')
    rows += ['', '## Blockers', *report['errors'], '', '## Not verified', *report['unverified']]
    (output/'network-audit.md').write_text('\n'.join(rows)+'\n', encoding='utf-8')


def source_inventory(source, service):
    source = Path(source)
    parameters, inputs = [], {}
    extensions = {'.java', '.properties', '.yml', '.yaml', '.js', '.ts', '.json', '.lua', '.cfg', '.conf', '.sh', '.tpl'}
    for file in sorted(source.rglob('*')):
        if (not file.is_file() or file.is_symlink() or file.suffix not in extensions
                or any(p in {'.git', 'node_modules', 'target', 'build', 'tests', 'test'} for p in file.relative_to(source).parts)
                or file.stat().st_size > 2_000_000):
            continue
        data = file.read_bytes()
        relative = file.relative_to(source).as_posix()
        inputs[relative] = hashlib.sha256(data).hexdigest()
        for number, line in enumerate(data.decode('utf-8', errors='replace').splitlines(), 1):
            for raw in re.findall(r'''(?:https?|wss?)://[^\s"'<>`\\]+''', line):
                try:
                    url = urlsplit(raw)
                    if not url.hostname:
                        continue
                    value = url.scheme+'://'+url.hostname+(':'+str(url.port) if url.port else '')+url.path
                except ValueError:
                    continue
                parameters.append(dict(service=service, name='SOURCE_ENDPOINT', value=value,
                    source=relative+':'+str(number), status='review-required'))
            match = re.match(r'\s*([a-zA-Z_.-]*(?:port|host|address|url))\s*[=:]\s*([a-zA-Z0-9_.:-]+)\s*$', line, re.I)
            if match and not SECRET.search(match[1]):
                parameters.append(dict(service=service, name=match[1], value=match[2],
                    source=relative+':'+str(number), status='review-required'))
    return dict(status='inventory', phase='source', parameters=parameters, input_sha256=inputs,
                source_sha=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'], stderr=subprocess.DEVNULL).decode().strip()
                if (source/'.git').exists() else 'unavailable', errors=[],
                unverified=['source literal runtime applicability', 'dynamic endpoint construction'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--mode', choices=['generic', 'target'], default='generic')
    parser.add_argument('--rendered', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--service')
    args = parser.parse_args()
    try:
        report = source_inventory(args.source, args.service) if args.source else audit(args.root, args.mode, rendered=json.load(sys.stdin) if str(args.rendered) == '-'
                       else json.loads(args.rendered.read_text()) if args.rendered else None)
    except (ValueError, OSError) as error:
        # Do not echo parser input / arbitrary exception messages containing secrets.
        report = dict(status='fail', errors=['Audit input invalid: '+type(error).__name__], parameters=[], unverified=['audit incomplete'])
    write_report(report, args.output)
    print('Network audit: '+report['status']+'; '+str(args.output))
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
