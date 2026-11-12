"""Offline package verification entry. Installation remains disabled until qualified."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import re
import subprocess
import sys

SERVICES={'web','app-web','api','gateway','prosody','jicofo','jvb'}

# Required external baseline. Built-in alternatives require separate qualification;
# a package cannot exempt itself merely by declaring a patch in its own manifest.
PRODUCT_PATCHES = (
    'patches/web/custom-interface_config.js',
    'patches/web/custom-head.html',
    'patches/web/custom.css',
    'patches/web/nginx-custom/custom-css.conf',
    'patches/prosody/mod_muc_jwt_owner.lua',
)


def verify_product(root, rendered):
    """Static content/config gate only; mounts and runtime behavior need validation."""
    root = Path(root).resolve()
    for name in PRODUCT_PATCHES:
        path = root / name
        if (not path.is_file() or path.is_symlink()
                or any(p.is_symlink() for p in path.parents if p != root)
                or path.stat().st_size == 0):
            raise ValueError('Missing product patch: ' + name)
    services = rendered.get('services', {})
    prosody = services.get('prosody', {}).get('environment', {})
    jicofo = services.get('jicofo', {}).get('environment', {})
    api = services.get('api', {}).get('environment', {})
    enabled = lambda value: str(value).lower() in ('1', 'true')
    if not enabled(prosody.get('ENABLE_AUTH')) or prosody.get('AUTH_TYPE') != 'jwt':
        raise ValueError('Product requires JWT authentication')
    if str(jicofo.get('ENABLE_AUTO_OWNER')).lower() not in ('0', 'false'):
        raise ValueError('Product requires automatic ownership disabled')
    modules = str(prosody.get('XMPP_MUC_MODULES', '')).split(',')
    if 'muc_jwt_owner' not in [m.strip() for m in modules]:
        raise ValueError('Product role module is not enabled')
    for key, api_key in [('JWT_APP_ID', 'JITSI_TOKEN_APP_ID'),
                         ('JWT_APP_SECRET', 'JITSI_TOKEN_APP_SECRET'),
                         ('XMPP_DOMAIN', 'JITSI_TOKEN_DOMAIN')]:
        if not prosody.get(key) or prosody[key] != api.get(api_key):
            raise ValueError('Product JWT configuration mismatch: ' + key)

def sha256_file(path):
    # Support target Python 3.7 as well as the original Ubuntu 3.10 runtime.
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def verify_checksums(root):
    root=Path(root).resolve()
    seen=set()
    lines=(root/'SHA256SUMS').read_text().splitlines()
    if not lines:
        raise ValueError('Empty checksum manifest')
    for line in lines:
        if '  ' not in line:
            raise ValueError('Invalid checksum record')
        digest,name=line.split('  ',1)
        relative=Path(name)
        if not re.fullmatch('[0-9a-f]{64}',digest) or relative.is_absolute() or '..' in relative.parts or '\\' in name:
            raise ValueError('Unsafe checksum record')
        path=root/relative
        if name in seen or any(p.is_symlink() for p in [path,*path.parents] if p!=root) or not path.is_file() or root not in path.resolve().parents:
            raise ValueError('Duplicate, missing or unsafe file: '+name)
        seen.add(name)
        actual=sha256_file(path)
        if actual!=digest:
            raise ValueError('Checksum mismatch: '+name)
    expected={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p!=root/'SHA256SUMS'}
    if expected!=seen:
        raise ValueError('Unlisted package files')
    return len(seen)

def require_ready(manifest):
    if manifest.get('status')!='READY_FOR_INSTALL':
        raise ValueError('Incomplete candidate; installation refused')
    images=manifest.get('images',{})
    if set(images)!=SERVICES:
        raise ValueError('Exactly seven service images required')
    for tag,identity in images.values():
        if not tag or not identity or not re.fullmatch('sha256:[0-9a-f]{64}',identity):
            raise ValueError('Unverified image identity')
    if len({v[1] for v in images.values()})!=7:
        raise ValueError('Duplicate service image identities')

def require_target(os_release,architecture,profile='ubuntu-22.04-amd64'):
    if profile == 'kylin-v10-aarch64-existing-engine':
        if os_release.get('ID') != 'kylin' or os_release.get('VERSION_ID') not in ('V10', '10') or architecture != 'aarch64':
            raise ValueError('This profile requires Kylin V10 aarch64 with existing Docker')
        return
    if profile != 'ubuntu-22.04-amd64':
        raise ValueError('Unknown target profile')
    if os_release.get('ID')!='ubuntu' or os_release.get('VERSION_ID')!='22.04' or architecture!='x86_64':
        raise ValueError('This dependency set requires Ubuntu 22.04 amd64')

def require_packages(packages):
    names=set()
    for item in packages:
        name=item['file']
        if Path(name).name!=name or not name.endswith('.deb') or item['architecture'] not in ('amd64','all'):
            raise ValueError('Unsafe dependency package')
        names.add(name.split('_',1)[0])
    if not {'docker-ce','docker-ce-cli','containerd.io','docker-compose-plugin'}<=names:
        raise ValueError('Incomplete Docker package set')

def dependency_command(packages,simulate=True):
    if not packages:
        raise ValueError('No dependency packages supplied')
    command=['apt-get','--no-download','--no-remove']
    if simulate:
        command+=['--simulate']
    command+=['install']+[str(p.resolve()) for p in packages]
    return command

def select_packages(packages,runner=subprocess.run):
    selected=[]
    for path in packages:
        metadata=runner(['dpkg-deb','-f',str(path),'Package','Version'],capture_output=True,text=True,check=True)
        fields=metadata.stdout.splitlines()
        name,version=[value.split(': ',1)[-1] for value in fields]
        installed=runner(['dpkg-query','-W','-f=${Version}',name],capture_output=True,text=True)
        if installed.returncode==0 and installed.stdout.strip():
            compare=runner(['dpkg','--compare-versions',installed.stdout.strip(),'ge',version])
            if compare.returncode==0:
                continue
        selected.append(path)
    return selected

def dependency_plan(root):
    # Only an explicitly requested plan invokes apt; no install, update or daemon change.
    import shlex
    os_release={}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            key,value=line.split('=',1)
            parsed=shlex.split(value)
            os_release[key]=parsed[0] if parsed else ''
    require_target(os_release,platform.machine())
    dependency_root=root/'dependencies/docker-debs'
    manifest=json.loads((dependency_root/'manifest.json').read_text())
    require_packages(manifest['files'])
    paths=[]
    for item in manifest['files']:
        path=dependency_root/item['file']
        if path.stat().st_size!=item['bytes']:
            raise ValueError('Dependency size mismatch')
        if sha256_file(path)!=item['sha256']:
            raise ValueError('Dependency hash mismatch')
        paths.append(path)
    selected=select_packages(paths)
    if not selected:
        return 0
    return subprocess.run(dependency_command(selected),check=True).returncode

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only',action='store_true',required=True,
                        help='Check file integrity and readiness without installing or starting services')
    parser.add_argument('--dependency-plan',action='store_true',help='Also simulate offline apt resolution on Ubuntu 22.04 amd64')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    count=verify_checksums(root)
    manifest=json.loads((root/'candidate.json').read_text())
    require_ready(manifest)
    if args.dependency_plan:
        dependency_plan(root)
    print(json.dumps({'status':'PASS_PACKAGE_INTEGRITY_ONLY','files':count,
                      'limitations':'No Docker installation, import, startup or media acceptance'}))

if __name__=='__main__':
    try:
        main()
    except (ValueError,OSError) as error:
        print('REFUSED: '+str(error),file=sys.stderr)
        raise SystemExit(1)
