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


def values_for_audit(root, external=None):
    spec=importlib.util.spec_from_file_location('target_config',root/'target.py')
    target=importlib.util.module_from_spec(spec);spec.loader.exec_module(target)
    return target.resolve_target(root,external)


def runtime_environment(root, external=None, preflight=False):
    # Transport/tool selection only; never inherit arbitrary Compose interpolation
    # variables, COMPOSE_* overrides or stale instance credentials.
    allowed={'PATH','HOME','USER','LANG','LC_ALL','TMPDIR','SSL_CERT_FILE',
             'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_CONFIG','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'}
    env={k:v for k,v in os.environ.items() if k in allowed}
    spec=importlib.util.spec_from_file_location('runtime_target',root/'target.py')
    target=importlib.util.module_from_spec(spec);spec.loader.exec_module(target)
    env.update(target.read_env(root/'jitsi.env'))
    env.update(target.resolve_target(root,external))
    keys={'JWT_APP_SECRET','JICOFO_AUTH_PASSWORD','JVB_AUTH_PASSWORD','JITSI_ROLE_CHECK_SECRET'}
    secrets={k:'PREFLIGHT_ONLY' for k in keys} if preflight else target.read_env(root/'.env')
    if set(secrets)!=keys:
        raise ValueError('Instance .env must contain secrets only')
    env.update(secrets)
    return env


def compose_command(root, external=None):
    if (root/'target.env').is_file():
        spec=importlib.util.spec_from_file_location('target_config',root/'target.py')
        target=importlib.util.module_from_spec(spec); spec.loader.exec_module(target)
        values=target.resolve_target(root,external)
        secrets=target.read_env(root/'.env')
        if set(secrets)!={'JWT_APP_SECRET','JICOFO_AUTH_PASSWORD','JVB_AUTH_PASSWORD','JITSI_ROLE_CHECK_SECRET'}:
            raise ValueError('Instance .env must contain secrets only')
    prefix=['docker','compose']
    if (root/'candidate.json').is_file():
        spec=importlib.util.spec_from_file_location('compose_verifier',root/'install.py')
        verifier=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        prefix=verifier.compose_prefix(root,json.loads((root/'candidate.json').read_text()))
    command=prefix+['--project-directory',str(root),
             '--env-file',str(root/'jitsi.env'),'--env-file',str(root/'.env')]
    for name in ['jitsi-base.yaml','docker-compose.yml','source-images.yaml']:
        command+=['-f',str(root/name)]
    return command


def validate_initialized_data(root):
    """Only the exact TLS bootstrap output may precede first service startup."""
    data=root/'data'
    if data.is_symlink():
        raise ValueError('Symlink in initialized data')
    if not data.exists():
        return
    expected={'ca.key','ca.crt','gateway.key','gateway.csr','cert.ext','gateway.crt'}
    control=data/'host-control'
    if (not data.is_dir() or {p.name for p in data.iterdir()}!={'host-control'}
            or control.is_symlink() or not control.is_dir()
            or {p.name for p in control.iterdir()} not in (expected,expected|{'ca.srl'})):
        raise ValueError('First-start refuses existing business data or incomplete TLS bootstrap')
    for p in control.iterdir():
        if p.is_symlink() or not p.is_file() or p.stat().st_size==0:
            raise ValueError('Unsafe internal TLS file: '+p.name)
        if p.suffix!='.crt' and p.stat().st_mode & 0o077:
            raise ValueError('Internal private material permissions too open: '+p.name)
    def openssl(*args):
        result=subprocess.run(['openssl',*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        return result.stdout
    openssl('verify','-CAfile',str(control/'ca.crt'),'-purpose','sslserver',
            '-verify_hostname','gateway',str(control/'gateway.crt'))
    for cert,key in [('ca.crt','ca.key'),('gateway.crt','gateway.key')]:
        if openssl('x509','-in',str(control/cert),'-pubkey','-noout')!=openssl(
                'pkey','-in',str(control/key),'-pubout'):
            raise ValueError('Internal certificate/private key mismatch: '+cert)


def require_instance(root):
    manifest=json.loads((root/'candidate.json').read_text())
    if manifest.get('status') not in ('READY_FOR_INSTALL', 'PACKAGED'):
        raise ValueError('Incomplete candidate; startup refused')
    if not (root/'.env').is_file() or (root/'.env').is_symlink():
        raise ValueError('Initialize fresh instance first')
    if (root/'.env').stat().st_mode & 0o077:
        raise ValueError('Instance secrets must not be group/world accessible')
    validate_initialized_data(root)
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


def validate_local_images(root,manifest):
    """Share config/manifest identity semantics with the import entry."""
    spec=importlib.util.spec_from_file_location('image_identity',root/'deploy.py')
    identity_check=importlib.util.module_from_spec(spec); spec.loader.exec_module(identity_check)
    for service,(tag,identity) in manifest['images'].items():
        info=json.loads(subprocess.check_output(['docker','image','inspect',tag]))[0]
        record=manifest.get('image_archives',{}).get(service)
        if manifest.get('image_transport')=='registry':
            identity_check.check_local_identity(info,identity,manifest.get('architecture','amd64'))
            continue
        if Path(record['file']).name!=record['file']:
            raise ValueError('Unsafe image archive path')
        identity_check.check_local_identity(info,identity,manifest.get('architecture','amd64'),
                                            root/'images'/record['file'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',action='store_true',required=True)
    parser.add_argument('--target-env',type=Path,help='Explicit public instance configuration outside package')
    args=parser.parse_args()
    if args.target_env is not None:
        os.environ['CLOUDMEET_TARGET_ENV']=str(args.target_env.absolute())
    root=Path(__file__).resolve().parent
    manifest=require_instance(root)
    spec=importlib.util.spec_from_file_location('package_verifier',root/'install.py')
    verifier=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    verifier.require_ready(manifest)
    # H5 is part of new joint deliveries; old immutable packages retain their entry.
    h5_module = None
    if 'h5' in manifest:
        spec=importlib.util.spec_from_file_location('h5_start',root/'h5.py')
        h5_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(h5_module)
        h5_module.verify_package(root,manifest)
        if (root/'h5-runtime').exists() or (root/'h5-runtime').is_symlink():
            raise ValueError('First-start refuses existing H5 runtime')
    # Validate exact locally imported identities before creating any data.
    validate_local_images(root,manifest)
    command=compose_command(root)
    runtime_env=runtime_environment(root)
    rendered=json.loads(subprocess.check_output(command+['config','--format','json'],stderr=subprocess.PIPE,env=runtime_env))
    # Independent product requirements before creating data or launching services.
    verifier.verify_product(root, rendered)
    if manifest.get('network_audit_required'):
        spec=importlib.util.spec_from_file_location('network_audit',root/'network-audit.py')
        audit_module=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit_module)
        report=audit_module.audit(root,mode='target',target=values_for_audit(root),rendered=rendered)
        audit_module.write_report(report,root/'instance-audit/network-startup')
        if report['errors']:
            raise ValueError('Target network audit failed; see instance-audit/network-startup')
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
    if manifest.get('entry_mode') == 'request-origin-local-certificate':
        spec=importlib.util.spec_from_file_location('target_config',root/'target.py')
        target=importlib.util.module_from_spec(spec); spec.loader.exec_module(target)
        target.install_origin_config(root/'data/jitsi/web/custom-config.js')
    patches={'patches/web/custom-interface_config.js':'data/jitsi/web/custom-interface_config.js',
             'patches/web/custom-head.html':'data/jitsi/web/custom-head.html',
             'patches/web/custom.css':'data/jitsi/web/custom.css',
             'patches/web/nginx-custom/custom-css.conf':'data/jitsi/web/nginx-custom/custom-css.conf',
             'patches/prosody/mod_muc_jwt_owner.lua':'data/jitsi/prosody/prosody-plugins-custom/mod_muc_jwt_owner.lua',
             'patches/prosody/mod_muc_host_transfer.lua':'data/jitsi/prosody/prosody-plugins-custom/mod_muc_host_transfer.lua'}
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
    # Only the selected image's explicit numeric identity may own Prosody storage.
    uid,gid=manifest.get('prosody_storage_owner',[1000,1000])
    settings=dict(line.split('=',1) for line in (root/'.env').read_text().splitlines()
                  if line and not line.startswith('#') and '=' in line)
    secret=settings['JITSI_ROLE_CHECK_SECRET']
    if len(secret)<32:
        raise ValueError('Internal service secret is too short')
    config='Component "muc.meet.jitsi" "muc"\n'
    config+='host_role_check_secret = '+json.dumps(secret)+';\n'
    config+='host_transfer_participant_domain = "meet.jitsi";\n'
    config+='host_transfer_enabled = true;\nhost_reclaim_enabled = true;\nhost_transfer_admin_recovery_enabled = false;\n'
    for name,endpoint in {'host_role_check_url':'check','host_transfer_url':'rotate',
            'host_transfer_complete_url':'complete','host_transfer_status_url':'status',
            'host_transfer_rebind_url':'rebind','host_transfer_claim_url':'claim',
            'host_reclaim_url':'reclaim'}.items():
        config+=name+' = "https://gateway:9443/internal/host-role/v1/'+endpoint+'";\n'
    confdir=root/'data/jitsi/prosody/config/conf.d'
    confdir.mkdir(exist_ok=True)
    cfg=confdir/'zz-cloudmeet-host-control.cfg.lua'
    cfg.write_text(config)
    cfg.chmod(0o600)
    for path in [root/'data/jitsi/storage/prosody',root/'data/jitsi/prosody',
                 *(root/'data/jitsi/storage/prosody').rglob('*'),
                 *(root/'data/jitsi/prosody').rglob('*')]:
        os.chown(path,uid,gid)
    if h5_module:
        release=h5_module.prepare_release(root/'h5-runtime',root/'h5/public',manifest['h5'],manifest['client_origin'])
        h5_module.activate(root/'h5-runtime',release)
    subprocess.run(command+['up','-d','--no-build','--pull','never'],check=True,env=runtime_env)
    subprocess.run(command+['ps'],check=True,env=runtime_env)
    print('Services started; TLS, signaling and media acceptance still required. Preserve target CA volumes.')


if __name__=='__main__':
    main()
