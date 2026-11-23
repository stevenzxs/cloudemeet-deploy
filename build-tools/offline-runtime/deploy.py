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


def deploy(root,verifier,runner=subprocess.run,verify_origin=None,target_env=None,registry=None):
    certificate=None
    if verify_origin is not None:
        spec=importlib.util.spec_from_file_location('target_certificate',root/'certificate.py')
        certificate=importlib.util.module_from_spec(spec);spec.loader.exec_module(certificate)
        certificate.preflight(root,verify_origin)
    verifier.verify_checksums(root)
    manifest=json.loads((root/'candidate.json').read_text())
    verifier.require_ready(manifest)
    if manifest.get('client_origin') and manifest['client_origin']!=verify_origin:
        raise ValueError('Deployment origin differs from built clients')
    if manifest.get('client_ca_sha256'):
        spec=importlib.util.spec_from_file_location('client_trust',root/'image_transport.py')
        trust=importlib.util.module_from_spec(spec);spec.loader.exec_module(trust)
        trust.require_ca(manifest,root/'cert/ca.crt')
    transport=None
    if manifest.get('image_transport')=='registry':
        spec=importlib.util.spec_from_file_location('image_transport',root/'image_transport.py')
        transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
        if registry is None:raise ValueError('Online first installation requires verified registry record')
        transport.require_material(registry,manifest)
    child_env=dict(os.environ)
    external=None
    if target_env is not None or manifest.get('network_audit_required'):
        spec=importlib.util.spec_from_file_location('instance_target',root/'target.py')
        target=importlib.util.module_from_spec(spec);spec.loader.exec_module(target)
        # Never inherit an unrelated task's instance selection.
        external=Path(target_env).absolute() if target_env is not None else None
        values=target.resolve_target(root,external) if external else target.load_target(root/'target.env')
        if verify_origin is not None:
            from urllib.parse import urlsplit
            if (urlsplit(verify_origin).port or 443)!=int(values['HTTPS_PORT']):
                raise ValueError('Direct-entry origin port must match HTTPS_PORT')
        if external: child_env['CLOUDMEET_TARGET_ENV']=str(external)
        else: child_env.pop('CLOUDMEET_TARGET_ENV',None)
        child_env['CLOUDMEET_TARGET_SHA256']=target.fingerprint(values)
        spec=importlib.util.spec_from_file_location('instance_network',root/'network-audit.py')
        network=importlib.util.module_from_spec(spec);spec.loader.exec_module(network)
        report=network.audit(root,mode='target',target=values)
        # Outside the immutable package, so retries retain evidence without invalidating it.
        network.write_report(report,root.parent/(root.name+'-network-preflight'))
        if report['errors']: raise ValueError('Target network preflight failed before host changes')
        spec=importlib.util.spec_from_file_location('preflight_start',root/'start.py')
        startup=importlib.util.module_from_spec(spec);spec.loader.exec_module(startup)
        render_env=startup.runtime_environment(root,external,preflight=True)
        command=verifier.compose_prefix(root,manifest)+['--project-directory',str(root),
                                                       '--env-file',str(root/'jitsi.env')]
        for name in ('jitsi-base.yaml','docker-compose.yml','source-images.yaml'):
            command+=['-f',str(root/name)]
        result=runner(command+['config','--format','json'],env=render_env,
                      capture_output=True,text=True,check=True,timeout=30)
        rendered=json.loads(result.stdout)
        verifier.verify_product(root,rendered)
        report=network.audit(root,mode='target',target=values,rendered=rendered)
        network.write_report(report,root.parent/(root.name+'-network-preflight'))
        if report['errors']: raise ValueError('Rendered target network preflight failed before host changes')
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
    acquire_images(root,manifest,verifier,runner,registry,transport)
    runner([sys.executable,'-B',str(root/'initialize.py')],check=True,timeout=30,env=child_env)
    runner([sys.executable,'-B',str(root/'start.py'),'--start'],check=True,timeout=180,env=child_env)
    if certificate is not None:
        spec=importlib.util.spec_from_file_location('instance_start',root/'start.py')
        start=importlib.util.module_from_spec(spec);spec.loader.exec_module(start)
        if ('CLOUDMEET_TARGET_SHA256' in child_env and
                target.fingerprint(start.values_for_audit(root,external))!=child_env['CLOUDMEET_TARGET_SHA256']):
            raise ValueError('Instance target changed before certificate activation')
        certificate.activate(root,verify_origin,start.compose_command(root,external),
                             env=start.runtime_environment(root,external))
    print('First-start commands completed. Target CA/TLS, signaling, clients and media must still be accepted.')


def acquire_images(root,manifest,verifier,runner,registry=None,transport=None):
    architecture=manifest.get('architecture','amd64')
    if manifest.get('image_transport')=='registry':
        transport.pull_images(registry,runner)
        transport.bind_local_tags(registry,manifest,runner)
        return
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
        if local.returncode!=0 and 'No such image' not in (local.stderr or ''):
            raise ValueError('Cannot establish local image absence: '+service)
        check_local_identity(json.loads(local.stdout)[0] if local.returncode==0 else None,identity,architecture,archive)
    for service,(tag,identity) in manifest['images'].items():
        runner(['docker','image','load','--input',str(root/'images'/archives[service]['file'])],check=True,timeout=600)
        local=runner(['docker','image','inspect',tag],capture_output=True,text=True,check=True,timeout=20)
        check_local_identity(json.loads(local.stdout)[0],identity,architecture,root/'images'/archives[service]['file'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-install',action='store_true',required=True)
    parser.add_argument('--verify-origin',required=True)
    parser.add_argument('--target-env',type=Path,help='Explicit public instance parameters outside package')
    parser.add_argument('--registry',type=Path)
    parser.add_argument('--registry-sha256')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location('package_verifier',root/'install.py')
    verifier=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    record=None
    if args.registry:
        if hashlib.sha256(args.registry.read_bytes()).hexdigest()!=args.registry_sha256:
            raise ValueError('Untrusted registry record')
        record=json.loads(args.registry.read_text())
    deploy(root,verifier,verify_origin=args.verify_origin,target_env=args.target_env,registry=record)


if __name__=='__main__':
    main()
