"""Actions-native product candidate; never grants offline-install qualification."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assemble(inputs, output, ci):
    if platform.machine() != 'aarch64':
        raise ValueError('Actions native aarch64 required')
    stack = load('stack', ci / 'tools/arm64-stack.py')
    lock = json.loads((ci / 'tools/arm64-stack-lock.json').read_text())
    output.mkdir(parents=True, exist_ok=False)
    images_dir = output / 'images'
    images_dir.mkdir()
    images = stack.import_images(images_dir, lock)
    for name in ['install.py', 'deploy.py', 'start.py', 'initialize.py']:
        shutil.copyfile(inputs / 'tools/offline-runtime' / name, output / name)
    shutil.copytree(inputs / 'patches', output / 'patches')
    verifier = load('verifier', output / 'install.py')
    credentials = {'focus': '${JICOFO_AUTH_PASSWORD:?required}',
                   'jvb': '${JVB_AUTH_PASSWORD:?required}', 'jwt': '${JWT_APP_SECRET:?required}'}
    compose = stack.topology(images, output, credentials)
    compose.pop('volumes')
    compose['networks'] = {'test': {}}
    services = compose['services']
    for service in services.values():
        service['restart'] = 'unless-stopped'
        service.pop('tmpfs', None)
        service['mem_limit'] = '640m'
    for name in ['web', 'prosody', 'jicofo', 'jvb']:
        env = services[name]['environment']
        env.update(PUBLIC_URL='${PUBLIC_URL:?required}', ENABLE_AUTH='1', AUTH_TYPE='jwt',
                   JWT_APP_ID='zhsz', JWT_APP_SECRET=credentials['jwt'], JWT_ALLOW_EMPTY='1',
                   XMPP_MUC_MODULES='muc_jwt_owner', ENABLE_AUTO_OWNER='0', ENABLE_P2P='0',
                   JICOFO_MAX_MEMORY='256m', JVB_MAX_MEMORY='384m',
                   JVB_ADVERTISE_IPS='${JVB_ADVERTISE_IPS:?required}')
    services['web']['volumes'] = ['./data/jitsi/web:/config']
    services['prosody']['volumes'] = ['./data/jitsi/prosody/config:/config',
        './data/jitsi/storage/prosody:/var/lib/prosody',
        './data/jitsi/prosody/prosody-plugins-custom:/prosody-plugins-custom:ro']
    for name in ['jicofo', 'jvb']:
        services[name]['volumes'] = ['./data/jitsi/' + name + ':/config']
    services['jvb']['ports'] = ['10000:10000/udp']
    services['api']['environment'].update(JITSI_TOKEN_APP_ID='zhsz')
    services['api']['volumes'] = ['./data/api:/app/data', './data/logos:/data/banner-logos']
    services['api']['mem_limit'] = '384m'
    services['app-web']['volumes'] = ['./data/logos:/data/banner-logos:ro']
    services['gateway']['environment'] = {'SITE_HOST': '${SITE_HOST:?required}'}
    services['gateway']['volumes'] = ['./Caddyfile:/etc/caddy/Caddyfile:ro',
                                      'caddy_data:/data', 'caddy_config:/config']
    services['gateway']['ports'] = ['8443:443', '8080:80']
    compose['volumes'] = {'caddy_data': {}, 'caddy_config': {}}
    verifier.verify_product(output, compose)
    (output / 'jitsi-base.yaml').write_text(json.dumps(compose, indent=2))
    for name in ['docker-compose.yml', 'source-images.yaml']:
        (output / name).write_text('services: {}\n')
    (output / 'jitsi.env').write_text('# All non-secret settings are explicit in Compose.\n')
    (output / 'server.env.example').write_text('SITE_HOST=47.110.84.166\nPUBLIC_URL=https://47.110.84.166:8443\nJVB_ADVERTISE_IPS=47.110.84.166\n')
    caddy = (inputs / 'Caddyfile').read_text()
    caddy = '{\n    auto_https disable_redirects\n' + caddy.split('{\n', 1)[1]
    caddy += '\nhttp://{$SITE_HOST} {\n redir https://{$SITE_HOST}:8443{uri} permanent\n}\n'
    (output / 'Caddyfile').write_text(caddy)
    source = subprocess.check_output(['git', '-C', str(inputs), 'rev-parse', 'HEAD']).decode().strip()
    archives = {s: {'tag': identity, 'image_id': identity, 'file': lock['images'][s]['archive'],
                    'bytes': lock['images'][s]['size'], 'sha256': lock['images'][s]['sha256']}
                for s, identity in images.items()}
    manifest = {'status': 'INCOMPLETE_NOT_FOR_INSTALL', 'architecture': 'arm64',
        'target_profile': 'kylin-v10-aarch64-existing-engine', 'origin': 'https://47.110.84.166:8443',
        'images': {s: [i, i] for s, i in images.items()}, 'image_archives': archives,
        'source_image_batch': lock, 'deployment_commit': source,
        'patches': {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (output / 'patches').rglob('*') if p.is_file()},
        'pending': ['independent full-system offline first-install qualification',
                    'Kylin target installation', 'Android/Electron and JVB media acceptance'],
        'requires': ['existing Docker on Kylin V10 aarch64', 'Docker Compose v2']}
    (output / 'candidate.json').write_text(json.dumps(manifest, indent=2))
    (output / 'INSTALL.md').write_text('''# Aarch64 product candidate — NOT INSTALL QUALIFIED

Target: Kylin V10 aarch64, https://47.110.84.166:8443; redirect8080, UDP10000.
Seven source images and external product patches are included. Requires existing Docker
and Compose v2; this candidate does not install Docker or claim dependency closure.
No secrets or CA are shipped. No automatic target upload or installation.

Integrity: run `sha256sum -c SHA256SUMS` in the extracted directory.
`python3 -B install.py --verify-only` deliberately refuses this incomplete candidate.
The initializer/deployer also refuse it. Do not edit candidate.json to bypass qualification.
Do not upload/install this as a qualified deployment release.
''')
    (output / 'SHA256SUMS').write_text(''.join(
        stack.digest(p) + '  ' + p.relative_to(output).as_posix() + '\n'
        for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
    verifier.verify_checksums(output)
    # Exercise the real product gate against independent damaged copies/configs.
    import copy
    for name in verifier.PRODUCT_PATCHES:
        original = output / name
        hidden = original.with_name(original.name + '.negative-fixture')
        original.rename(hidden)
        try:
            try:
                verifier.verify_product(output, compose)
            except ValueError:
                pass
            else:
                raise ValueError('Missing-patch negative gate did not reject ' + name)
        finally:
            hidden.rename(original)
    for service, key, value in [('prosody', 'ENABLE_AUTH', '0'),
                                 ('prosody', 'XMPP_MUC_MODULES', ''),
                                 ('jicofo', 'ENABLE_AUTO_OWNER', '1')]:
        bad = copy.deepcopy(compose)
        bad['services'][service]['environment'][key] = value
        try:
            verifier.verify_product(output, bad)
        except ValueError:
            pass
        else:
            raise ValueError('Invalid product configuration accepted')
    # Render only with ephemeral dummy values; never ship a usable .env.
    env = dict(__import__('os').environ)
    env.update(SITE_HOST='47.110.84.166', PUBLIC_URL=manifest['origin'],
               JVB_ADVERTISE_IPS='47.110.84.166', JWT_APP_SECRET='CI_RENDER_ONLY',
               JICOFO_AUTH_PASSWORD='CI_RENDER_ONLY', JVB_AUTH_PASSWORD='CI_RENDER_ONLY')
    rendered = json.loads(subprocess.check_output(['docker', 'compose', '-f',
        str(output / 'jitsi-base.yaml'), 'config', '--format', 'json'], env=env))
    verifier.verify_product(output, rendered)
    verifier.verify_checksums(output)
    refused = subprocess.run(['python3', '-B', str(output / 'install.py'), '--verify-only'],
                             capture_output=True)
    if refused.returncode == 0:
        raise ValueError('Incomplete candidate unexpectedly installable')
    archive = output.with_suffix('.tar.gz')
    with tarfile.open(archive, 'w:gz', compresslevel=1) as tar:
        tar.add(output, arcname=output.name)
    archive.with_name(archive.name + '.sha256').write_text(stack.digest(archive) + '  ' + archive.name + '\n')
    print(json.dumps({'archive': str(archive), 'status': manifest['status'], 'deployment_commit': source}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ci', type=Path, required=True)
    args = parser.parse_args()
    assemble(args.inputs.resolve(), args.output.resolve(), args.ci.resolve())
