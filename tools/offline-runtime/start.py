"""Source-image first-start entry; incomplete packages always refuse startup."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True


def compose_command(root):
    command=['docker','compose','--project-directory',str(root),
             '--env-file',str(root/'jitsi.env'),'--env-file',str(root/'.env')]
    for name in ['jitsi-base.yaml','docker-compose.yml','source-images.yaml']:
        command+=['-f',str(root/name)]
    return command


def require_instance(root):
    manifest=json.loads((root/'candidate.json').read_text())
    if manifest.get('status')!='READY_FOR_INSTALL':
        raise ValueError('Incomplete candidate; startup refused')
    if not (root/'.env').is_file() or (root/'.env').is_symlink():
        raise ValueError('Initialize fresh instance first')
    if (root/'.env').stat().st_mode & 0o077:
        raise ValueError('Instance secrets must not be group/world accessible')
    if (root/'data').exists() or (root/'data').is_symlink():
        raise ValueError('First-start refuses existing data; use a separately reviewed resume procedure')
    return manifest


def safe_directory(root,relative):
    path=Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe data path')
    current=root
    for part in path.parts:
        current=current/part
        if current.is_symlink():
            raise ValueError('Symlink in data path')
        current.mkdir(exist_ok=True)
    return current


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',action='store_true',required=True)
    parser.parse_args()
    root=Path(__file__).resolve().parent
    manifest=require_instance(root)
    spec=importlib.util.spec_from_file_location('package_verifier',root/'install.py')
    verifier=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    verifier.require_ready(manifest)
    # Validate exact locally imported identities before creating any data.
    for service,(tag,identity) in manifest['images'].items():
        info=json.loads(subprocess.check_output(['docker','image','inspect',tag]))[0]
        if info['Id']!=identity or info['Os']!='linux' or info['Architecture']!=manifest.get('architecture','amd64'):
            raise ValueError('Local image mismatch: '+service)
    command=compose_command(root)
    rendered=json.loads(subprocess.check_output(command+['config','--format','json'],stderr=subprocess.PIPE))
    # Independent product requirements before creating data or launching services.
    verifier.verify_product(root, rendered)
    if set(rendered['services'])!=set(manifest['images']):
        raise ValueError('Unexpected service set')
    for service,config in rendered['services'].items():
        if config.get('build') or config.get('pull_policy')!='never' or config['image']!=manifest['images'][service][0]:
            raise ValueError('Unsafe source-image configuration')
        if any('/artifacts/' in volume.get('source','') for volume in config.get('volumes',[])):
            raise ValueError('Old artifact shadow mount')
    directories=['data/api','data/logos','data/jitsi/web/nginx-custom','data/jitsi/storage/web',
                 'data/jitsi/storage/transcripts','data/jitsi/storage/prosody','data/jitsi/prosody/config',
                 'data/jitsi/prosody/prosody-plugins-custom','data/jitsi/jicofo','data/jitsi/jvb',
                 'data/jitsi/tmp/web-load-test']
    for directory in directories:
        safe_directory(root,directory)
    patches={'patches/web/custom-interface_config.js':'data/jitsi/web/custom-interface_config.js',
             'patches/web/custom-head.html':'data/jitsi/web/custom-head.html',
             'patches/web/custom.css':'data/jitsi/web/custom.css',
             'patches/web/nginx-custom/custom-css.conf':'data/jitsi/web/nginx-custom/custom-css.conf',
             'patches/prosody/mod_muc_jwt_owner.lua':'data/jitsi/prosody/prosody-plugins-custom/mod_muc_jwt_owner.lua'}
    for source,target in patches.items():
        destination=root/target
        if destination.exists() or destination.is_symlink():
            raise ValueError('First-start refuses existing patch: '+target)
        shutil.copyfile(root/source,destination)
        destination.chmod(0o644)
    for path in (root/'data/jitsi').rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlink in prepared Jitsi data')
        os.chown(path,1000,1000)
        if path.is_dir():
            path.chmod(0o755)
    os.chown(root/'data/jitsi',1000,1000)
    subprocess.run(command+['up','-d','--no-build','--pull','never'],check=True)
    subprocess.run(command+['ps'],check=True)
    print('Services started; TLS, signaling and media acceptance still required. Preserve target CA volumes.')


if __name__=='__main__':
    main()
