#!/usr/bin/env python3
"""Derive a new image-free online archive from verified same-run build material."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile
import re
import ssl


def require_public_source(root):
    for path in root.rglob('*'):
        relative=path.relative_to(root)
        if (path.is_symlink() or any(p in ('cert','data','update-backups','.git') for p in relative.parts)
                or path.name in ('.env','cert.tar.gz') or path.suffix in ('.key','.pfx','.p12')):
            raise ValueError('Runtime/private material in public source')


def verify_archive(archive):
    """Re-read final bytes; reject duplicate, unsafe or unlisted members."""
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers();names=[m.name for m in members]
        if len(names)!=len(set(names)):raise ValueError('Duplicate archive member')
        roots=set()
        for member in members:
            parts=Path(member.name).parts
            if (not parts or member.name.startswith('/') or '..' in parts or '\\' in member.name
                    or not (member.isfile() or member.isdir())):
                raise ValueError('Unsafe archive member')
            roots.add(parts[0])
        if len(roots)!=1:raise ValueError('Expected one archive root')
        prefix=roots.pop()+'/'
        files={m.name:m for m in members if m.isfile()}
        sums=files.get(prefix+'SHA256SUMS')
        if sums is None:raise ValueError('Missing checksums')
        expected={}
        for line in tar.extractfile(sums).read().decode().splitlines():
            checksum,name=line.split('  ',1)
            if not re.fullmatch('[0-9a-f]{64}',checksum) or prefix+name in expected:
                raise ValueError('Invalid checksum record')
            expected[prefix+name]=checksum
        if set(files)!=set(expected)|{prefix+'SHA256SUMS'}:raise ValueError('Archive inventory mismatch')
        for name,checksum in expected.items():
            h=hashlib.sha256()
            with tar.extractfile(files[name]) as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
            if h.hexdigest()!=checksum:raise ValueError('Archive content mismatch')


def assemble(source,destination):
    require_public_source(source)
    spec=importlib.util.spec_from_file_location('material_verifier',source/'install.py')
    verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    verifier.verify_checksums(source)
    manifest=json.loads((source/'candidate.json').read_text());verifier.require_ready(manifest)
    verifier.verify_jitsi_mgr(source,manifest,json.loads((source/'jitsi-base.yaml').read_text()))
    spec=importlib.util.spec_from_file_location('h5_material',source/'h5.py')
    h5=importlib.util.module_from_spec(spec);spec.loader.exec_module(h5)
    h5.verify_package(source,manifest)
    if destination.exists():raise FileExistsError('Refusing existing online material')
    shutil.copytree(source,destination,ignore=shutil.ignore_patterns('images','SHA256SUMS'))
    manifest['image_transport']='registry'
    client={}
    for line in (Path(__file__).resolve().parent.parent/'config/client.env').read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            key,value=line.split('=',1);client[key.strip()]=value.strip()
    port=int(client['SITE_PORT'])
    manifest['client_origin']=client['SITE_SCHEME']+'://'+client['SITE_DOMAIN']+((':'+str(port)) if port!=443 else '')
    mode=client.get('TLS_MODE')
    if mode not in ('private-ca','caddy-public-acme'):raise ValueError('Explicit TLS_MODE required')
    manifest['tls_mode']=mode
    manifest['client_ca_sha256']=None
    if mode=='private-ca':
        ca=Path(__file__).resolve().parent.parent/'config'/client['CLIENT_CA_FILE']
        pem=ca.read_text(encoding='ascii')
        if 'PRIVATE KEY' in pem or pem.count('BEGIN CERTIFICATE')!=1:raise ValueError('One public client CA required')
        manifest['client_ca_sha256']=hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
    elif client.get('CLIENT_CA_FILE'):raise ValueError('Public ACME forbids private client CA')
    spec=importlib.util.spec_from_file_location('tls_policy',Path(__file__).parent.parent/'runtime/certificate.py')
    policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
    policy.require_mode(manifest,manifest['client_origin'])
    manifest['publication']='REQUIRES_MATCHING_PUBLISHED_REGISTRY_RECORD'
    manifest['image_archives']={}
    (destination/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (destination/'INSTALL.md').write_text('''# Online first installation / existing-instance upgrade

Requires existing matching Linux Docker Engine and supplied native Compose.
Verify the Release asset SHA256SUMS against trusted release evidence before execution.
TLS mode is fixed by candidate.json: private-ca requires adjacent private cert.tar.gz;
caddy-public-acme requires public DNS HTTPS/443, inbound TLS-ALPN-01/443 and outbound
DNS/HTTPS for issuance and renewal. No private fallback or isolated/offline ACME.
Preserve gateway /data and /config volumes (ACME account/cert state); never publish secrets.
Online first installation: use setup.py with this archive,
--verify-origin, --target-env (absolute, outside package), --registry registry.json and
--registry-sha256 <trusted hash>. Images are pulled by digest, never loaded or built.
First installation refuses existing extraction directory, secrets or data.
Do not use first installation to overwrite an existing instance.

Upgrade: use reviewed online_update.py with explicit --root, --project, --target-env,
--verify-origin, --ca (private-ca only; omit for public), --candidate <new candidate.json>, --registry and trusted
--registry-sha256. Default is read-only; --apply is separately authorized execution.
The image-only updater refuses changed external patches; configuration migration is
not implemented by pretending that image-only compatibility is sufficient.
Preserve data, secrets, CA volumes and certificates. No automatic cleanup/reinstall.

Offline delivery is an explicit extra operation via offline-export.py, not a target
fallback after a failed pull. Packaging does not establish target/media acceptance.
''')
    paths=sorted(p for p in destination.rglob('*') if p.is_file())
    (destination/'SHA256SUMS').write_text(''.join(verifier.sha256_file(p)+'  '+p.relative_to(destination).as_posix()+'\n' for p in paths))
    verifier.verify_checksums(destination);verifier.require_ready(manifest)
    archive=destination.with_name(destination.name+'.tar.gz')
    if archive.exists():raise FileExistsError('Refusing existing online archive')
    with tarfile.open(archive,'w:gz') as tar:tar.add(destination,arcname=destination.name)
    verify_archive(archive)
    Path(str(archive)+'.sha256').write_text(verifier.sha256_file(archive)+'  '+archive.name+'\n')
    return archive


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args();print(assemble(args.source,args.destination))
