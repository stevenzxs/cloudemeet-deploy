"""Explicit first-install executor. Incomplete packages cannot mutate the host."""
import argparse
import datetime
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import tarfile

sys.dont_write_bytecode=True


def archive_manifest_identity(archive, identity, expected):
    """Bind a containerd manifest ID to the approved archive's config ID."""
    if not isinstance(identity,str) or not identity.startswith('sha256:'):
        return False
    with tarfile.open(archive) as tar:
        members={}
        for member in tar.getmembers():
            if member.name in members:
                raise ValueError('Duplicate image archive member')
            members[member.name]=member

        def read(name):
            member=members.get(name)
            if member is None or not member.isfile() or member.size>16*1024*1024:
                raise ValueError('Invalid OCI archive metadata')
            return tar.extractfile(member).read()

        if 'index.json' not in members:
            return False
        index=json.loads(read('index.json'))
        if identity not in [item.get('digest') for item in index.get('manifests',[])]:
            return False
        raw=read('blobs/sha256/'+identity.split(':',1)[1])
        return ('sha256:'+hashlib.sha256(raw).hexdigest()==identity
                and json.loads(raw).get('config',{}).get('digest')==expected)


def check_local_identity(info,expected,architecture='amd64',archive=None):
    if info is None:
        return
    try:
        matching=(info.get('Id')==expected or
                  (archive is not None and archive_manifest_identity(archive,info.get('Id'),expected)))
    except (tarfile.TarError,KeyError,TypeError,json.JSONDecodeError) as error:
        raise ValueError('Invalid archive identity metadata; refusing image') from error
    if not matching or info.get('Os')!='linux' or info.get('Architecture')!=architecture:
        raise ValueError('Existing tag conflicts with approved image; refusing replacement')


def host_os():
    return {key:shlex.split(value)[0] for key,value in
            (line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)}


def deploy(root,verifier,runner=subprocess.run,verify_origin=None):
    certificate=None
    if verify_origin is not None:
        spec=importlib.util.spec_from_file_location('target_certificate',root/'certificate.py')
        certificate=importlib.util.module_from_spec(spec);spec.loader.exec_module(certificate)
        certificate.preflight(root,verify_origin)
    verifier.verify_checksums(root)
    manifest=json.loads((root/'candidate.json').read_text())
    verifier.require_ready(manifest)
    if any((root/name).exists() or (root/name).is_symlink() for name in ['.env','data']):
        raise ValueError('First install refuses existing secrets/data')
    profile=manifest.get('target_profile','ubuntu-22.04-amd64')
    architecture=manifest.get('architecture','amd64')
    verifier.require_target(host_os(),platform.machine(),profile)
    if os.geteuid()!=0:
        raise ValueError('Explicit installation requires root on the approved target')
    if datetime.datetime.now(datetime.timezone.utc).year<2026:
        raise ValueError('System clock appears invalid; refusing TLS installation')
    # Engine installation is deliberately separate: no implicit package/daemon changes.
    engine=runner(['docker','info','--format','{{.OSType}}/{{.Architecture}}'],capture_output=True,text=True,timeout=30)
    platforms={'amd64':['linux/x86_64','linux/amd64'], 'arm64':['linux/aarch64','linux/arm64']}
    if engine.returncode or engine.stdout.strip() not in platforms.get(architecture,[]):
        raise ValueError('A matching existing Docker engine is required; offline engine installation remains a separate gate')
    runner(verifier.compose_prefix(root,manifest)+['version'],check=True,timeout=20)
    archives=manifest.get('image_archives',{})
    if set(archives)!=set(manifest['images']):
        raise ValueError('Incomplete image archive set')
    # Check every archive and existing tag before importing the first image.
    for service,(tag,identity) in manifest['images'].items():
        record=archives[service]
        if record['tag']!=tag or record['image_id']!=identity or Path(record['file']).name!=record['file']:
            raise ValueError('Archive identity does not match service')
        archive=root/'images'/record['file']
        if archive.stat().st_size!=record['bytes'] or verifier.sha256_file(archive)!=record['sha256']:
            raise ValueError('Archive integrity failure')
        local=runner(['docker','image','inspect',tag],capture_output=True,text=True,timeout=20)
        check_local_identity(json.loads(local.stdout)[0] if local.returncode==0 else None,identity,architecture,archive)
    for service,(tag,identity) in manifest['images'].items():
        runner(['docker','image','load','--input',str(root/'images'/archives[service]['file'])],check=True,timeout=600)
        local=runner(['docker','image','inspect',tag],capture_output=True,text=True,check=True,timeout=20)
        check_local_identity(json.loads(local.stdout)[0],identity,architecture,root/'images'/archives[service]['file'])
    runner([sys.executable,'-B',str(root/'initialize.py')],check=True,timeout=30)
    runner([sys.executable,'-B',str(root/'start.py'),'--start'],check=True,timeout=180)
    if certificate is not None:
        spec=importlib.util.spec_from_file_location('instance_start',root/'start.py')
        start=importlib.util.module_from_spec(spec);spec.loader.exec_module(start)
        certificate.activate(root,verify_origin,start.compose_command(root))
    print('First-start commands completed. Target CA/TLS, signaling, clients and media must still be accepted.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-install',action='store_true',required=True)
    parser.add_argument('--verify-origin',required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location('package_verifier',root/'install.py')
    verifier=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    deploy(root,verifier,verify_origin=args.verify_origin)


if __name__=='__main__':
    main()
