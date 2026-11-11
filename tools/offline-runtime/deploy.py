"""Explicit first-install executor. Incomplete packages cannot mutate the host."""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys

sys.dont_write_bytecode=True


def check_local_identity(info,expected,architecture='amd64'):
    if info is not None and (info.get('Id')!=expected or info.get('Os')!='linux' or info.get('Architecture')!=architecture):
        raise ValueError('Existing tag conflicts with approved image; refusing replacement')


def host_os():
    return {key:shlex.split(value)[0] for key,value in
            (line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)}


def deploy(root,verifier,runner=subprocess.run):
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
    runner(['docker','compose','version'],check=True,timeout=20)
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
        check_local_identity(json.loads(local.stdout)[0] if local.returncode==0 else None,identity,architecture)
    for service,(tag,identity) in manifest['images'].items():
        runner(['docker','image','load','--input',str(root/'images'/archives[service]['file'])],check=True,timeout=600)
        local=runner(['docker','image','inspect',tag],capture_output=True,text=True,check=True,timeout=20)
        check_local_identity(json.loads(local.stdout)[0],identity,architecture)
    runner([sys.executable,'-B',str(root/'initialize.py')],check=True,timeout=30)
    runner([sys.executable,'-B',str(root/'start.py'),'--start'],check=True,timeout=180)
    print('First-start commands completed. Target CA/TLS, signaling, clients and media must still be accepted.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-install',action='store_true',required=True)
    parser.parse_args()
    root=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location('package_verifier',root/'install.py')
    verifier=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    deploy(root,verifier)


if __name__=='__main__':
    main()
