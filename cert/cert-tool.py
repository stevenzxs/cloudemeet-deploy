#!/usr/bin/env python3
"""Offline IP certificate generation. Requires Python 3 and OpenSSL CLI."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import tarfile


def ip_list(value):
    result = []
    for item in value.split(','):
        ip = ipaddress.ip_address(item.strip())
        if ip.version != 4:
            raise ValueError('Only IPv4 is supported')
        if str(ip) not in result:
            result.append(str(ip))
    return result


def external_tls(text, directory):
    import re
    updated, count = re.subn(r'(?m)^([ \t]*)tls (?:internal|/config/cloudmeet-cert/[A-Za-z0-9-]+/server\.crt /config/cloudmeet-cert/[A-Za-z0-9-]+/server\.key)[ \t]*$',
                             lambda m: m[1] + 'tls ' + directory + '/server.crt ' + directory + '/server.key', text)
    if count != 2:
        raise ValueError('Expected exactly two baseline or tool-managed TLS directives; inspect instance first')
    return updated


def run(*args):
    subprocess.run(['openssl', *map(str, args)], check=True)


def fixed_tls_json(source, directory):
    """Convert reviewed two-certificate JSON; never change routes or internal keys."""
    import copy
    import re
    if not re.fullmatch(r'/config/cloudmeet-cert/[A-Za-z0-9-]+', directory):
        raise ValueError('Expected versioned certificate directory under /config/cloudmeet-cert')
    result = copy.deepcopy(source)
    try:
        files = result['apps']['tls']['certificates']['load_files']
        servers = result['apps']['http']['servers']
        internal = [f for f in files if f['certificate'] == '/host-control/gateway.crt'
                    and f['key'] == '/host-control/gateway.key']
        external = [f for f in files if f not in internal]
        if len(files) != 2 or len(internal) != 1 or len(external) != 1:
            raise ValueError('Expected exactly one external and one internal certificate')
        external[0].update(certificate=directory+'/server.crt', key=directory+'/server.key', tags=['cert'])
        internal[0]['tags'] = ['cert-inner']
        found = set()
        for server in servers.values():
            listeners = server['listen']
            if listeners not in ([':443'], [':9443']):
                if listeners != [':80']:
                    raise ValueError('Unknown listener layout')
                continue
            tag = 'cert' if listeners == [':443'] else 'cert-inner'
            if tag in found or not server.get('tls_connection_policies'):
                raise ValueError('Missing or duplicate TLS listener')
            found.add(tag)
            for policy in server['tls_connection_policies']:
                policy['certificate_selection'] = {'any_tag': [tag]}
        if found != {'cert', 'cert-inner'}:
            raise ValueError('Both external and internal TLS listeners required')
    except (KeyError, TypeError) as error:
        raise ValueError('Unsupported Caddy JSON layout') from error
    return result


def write_checksums(directory):
    lines = ''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n'
                    for p in sorted(directory.iterdir()) if p.is_file() and p.name != 'SHA256SUMS')
    # Bytes avoid Windows text-mode LF -> CRLF conversion (GNU sha256sum reads CR as filename).
    (directory/'SHA256SUMS').write_bytes(lines.encode('utf-8'))


def write_archive(directory):
    """Archive only checksum-listed regular files, never CA private material."""
    archive=Path(str(directory)+'.tar.gz')
    checksum=Path(str(archive)+'.sha256')
    if archive.exists() or archive.is_symlink() or checksum.exists() or checksum.is_symlink():
        raise FileExistsError('Archive or checksum already exists: '+str(archive))
    entries={}
    for line in (directory/'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        digest,name=line.split('  ',1)
        if name in entries or Path(name).name!=name or name=='ca.key':
            raise ValueError('Unsafe or duplicate bundle member')
        entries[name]=digest
    paths=list(directory.iterdir())
    if {p.name for p in paths}!=set(entries)|{'SHA256SUMS'}:
        raise ValueError('Unlisted bundle files')
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError('Bundle requires regular files only')
        if path.name in entries and hashlib.sha256(path.read_bytes()).hexdigest()!=entries[path.name]:
            raise ValueError('Bundle checksum mismatch: '+path.name)
    with archive.open('xb') as output:
        with tarfile.open(fileobj=output,mode='w:gz') as tar:
            top=tarfile.TarInfo(directory.name);top.type=tarfile.DIRTYPE;top.mode=0o700
            tar.addfile(top)
            for path in sorted(paths):
                info=tar.gettarinfo(str(path),arcname=directory.name+'/'+path.name)
                info.uid=info.gid=0;info.uname=info.gname=''
                info.mode=0o600 if path.suffix=='.key' else (0o755 if path.suffix=='.sh' else 0o644)
                with path.open('rb') as source: tar.addfile(info,source)
    with tarfile.open(archive) as tar:
        members=tar.getmembers()
        expected={directory.name+'/'+p.name:p.read_bytes() for p in paths}
        if len(members)!=len(expected)+1 or {m.name for m in members}!=set(expected)|{directory.name}:
            raise ValueError('Archive inventory mismatch')
        for name,data in expected.items():
            if tar.extractfile(name).read()!=data:
                raise ValueError('Archive contents mismatch: '+name)
    with checksum.open('xb') as output:
        output.write((hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n').encode())
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    fixed = sub.add_parser('fixed-json', help='Generate reviewed fixed-tag JSON without contacting a server')
    fixed.add_argument('--input', type=Path, required=True)
    fixed.add_argument('--output', type=Path, required=True)
    fixed.add_argument('--certificate-directory', required=True)
    ca = sub.add_parser('init-ca')
    ca.add_argument('--directory', type=Path, required=True)
    issue = sub.add_parser('issue')
    issue.add_argument('--ca-directory', type=Path, required=True)
    issue.add_argument('--ips', required=True, help='Comma-separated actual client-access IPv4 addresses; ports excluded')
    issue.add_argument('--output', type=Path, required=True)
    issue.add_argument('--days', type=int, default=365)
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == 'fixed-json':
        result = fixed_tls_json(json.loads(args.input.read_text(encoding='utf-8')), args.certificate_directory)
        with args.output.open('x', encoding='utf-8', newline='\n') as output:
            output.write(json.dumps(result, indent=2)+'\n')
        return
    if args.command == 'init-ca':
        args.directory.mkdir(parents=True, exist_ok=False)
        run('req', '-x509', '-newkey', 'rsa:3072', '-sha256', '-days', '3650',
            '-keyout', args.directory/'ca.key', '-out', args.directory/'ca.crt',
            '-subj', '/CN=CloudMeet Offline Private CA', '-addext', 'basicConstraints=critical,CA:TRUE',
            '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
        print('CA private key is encrypted: keep this directory OFFLINE; never upload it to the server or Git.')
        return
    ips = ip_list(args.ips)
    if not 1 <= args.days <= 825:
        raise ValueError('Leaf validity must be 1..825 days')
    for path in (Path(str(args.output)+'.tar.gz'),Path(str(args.output)+'.tar.gz.sha256')):
        if path.exists() or path.is_symlink():
            raise FileExistsError('Refusing existing archive output: '+str(path))
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output
    ext = out/'extensions.cnf'
    ext.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n'
                   'extendedKeyUsage=serverAuth\nsubjectAltName=' + ','.join(
                       ['IP:'+ip for ip in ips] + ['DNS:cloudmeet.internal']) + '\n')
    run('req', '-new', '-newkey', 'rsa:3072', '-nodes', '-keyout', out/'server.key',
        '-out', out/'server.csr', '-subj', '/CN='+ips[0])
    run('x509', '-req', '-in', out/'server.csr', '-CA', args.ca_directory/'ca.crt',
        '-CAkey', args.ca_directory/'ca.key', '-set_serial', '0x'+os.urandom(16).hex(),
        '-days', args.days, '-sha256', '-extfile', ext, '-out', out/'server.crt')
    (out/'ca.crt').write_bytes((args.ca_directory/'ca.crt').read_bytes())
    for ip in ips:
        run('verify', '-CAfile', out/'ca.crt', '-purpose', 'sslserver', '-verify_ip', ip, out/'server.crt')
    run('verify', '-CAfile', out/'ca.crt', '-purpose', 'sslserver',
        '-verify_hostname', 'cloudmeet.internal', out/'server.crt')
    (out/'certificate.json').write_text(json.dumps({'ips': ips, 'dns': ['cloudmeet.internal'], 'days': args.days}, indent=2)+'\n')
    for name in ['replace-cert.sh', 'replace-fixed-cert.sh', 'rollback-cert.sh', 'restart-verify-gateway.sh', 'cert-tool.py', 'README.md']:
        (out/name).write_bytes(Path(__file__).with_name(name).read_bytes())
    write_checksums(out)
    archive=write_archive(out)
    print('Sensitive server bundle:', out, '\nContains server.key, NOT ca.key. Restrict file permissions and transfer securely.')
    print('Verified archive:', archive, '\nArchive checksum:', str(archive)+'.sha256')


if __name__ == '__main__':
    main()
