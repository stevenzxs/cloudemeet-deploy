"""Native Actions-only product integration; not full-system offline qualification."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import os
import sys


def product_topology(config, inputs, private, secret):
    for name in ['web', 'prosody', 'jicofo', 'jvb']:
        service = config['services'][name]
        service['environment'].update(ENABLE_AUTH='1', AUTH_TYPE='jwt', JWT_APP_ID='arm64-ci',
            JWT_APP_SECRET=secret, JWT_ALLOW_EMPTY='1', XMPP_MUC_MODULES='muc_jwt_owner',
            ENABLE_AUTO_OWNER='0', ENABLE_P2P='0')
    config['services']['web'].pop('tmpfs', None)
    config['services']['web']['volumes'] = [str(private / 'web') + ':/config']
    config['services']['prosody']['volumes'] = [str(private / 'prosody-plugins-custom') + ':/prosody-plugins-custom:ro']
    return config


def restore_web_owner(private, uid, gid, runner=subprocess.run):
    runner(['sudo', '-n', 'chown', '-R', '--no-dereference',
            str(uid) + ':' + str(gid), str(private / 'web')], check=True)


def main(inputs):
    inputs = inputs.resolve()
    spec = importlib.util.spec_from_file_location('stack', inputs / 'tools/arm64-stack.py')
    stack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stack)
    original = stack.topology

    def topology(images, private, credentials):
        # Temporary test path only; the immutable delivery patches are unchanged.
        private.chmod(0o755)
        (private / 'web/nginx-custom').mkdir(parents=True)
        (private / 'prosody-plugins-custom').mkdir()
        for name in ['custom-interface_config.js', 'custom.css', 'custom-head.html']:
            shutil.copyfile(inputs / 'patches/web' / name, private / 'web' / name)
        shutil.copyfile(inputs / 'patches/web/nginx-custom/custom-css.conf',
                        private / 'web/nginx-custom/custom-css.conf')
        shutil.copyfile(inputs / 'patches/prosody/mod_muc_jwt_owner.lua',
                        private / 'prosody-plugins-custom/mod_muc_jwt_owner.lua')
        for p in private.rglob('*'):
            p.chmod(0o755 if p.is_dir() else 0o644)
        subprocess.run(['sudo', '-n', 'chown', '-R', '1000:1000', str(private / 'web')], check=True)
        return product_topology(original(images, private, credentials), inputs, private, credentials['jwt'])

    stack.topology = topology

    def check(execute, https, private, checks):
        def probe(label, function, *args):
            try:
                return function(*args)
            except subprocess.CalledProcessError as error:
                raise RuntimeError(label + ' failed with exit ' + str(error.returncode)) from None
        css = probe('CSS HTTPS fetch', https, '/css/custom.css')
        expected = (inputs / 'patches/web/custom.css').read_bytes()
        if hashlib.sha256(css).digest() != hashlib.sha256(expected).digest():
            raise RuntimeError('Runtime CSS digest mismatch')
        page = probe('HTML HTTPS fetch', https, '/')
        if b'/css/custom.css' not in page:
            raise RuntimeError('Runtime CSS head reference missing')
        plugin = probe('Prosody plugin read', execute, 'prosody', 'cat', '/prosody-plugins-custom/mod_muc_jwt_owner.lua')
        if plugin != (inputs / 'patches/prosody/mod_muc_jwt_owner.lua').read_bytes():
            raise RuntimeError('Runtime plugin digest mismatch')
        config = probe('Prosody config read', execute, 'prosody', 'cat', '/config/conf.d/jitsi-meet.cfg.lua')
        if b'muc_jwt_owner' not in config:
            raise RuntimeError('JWT role plugin not configured')
        checks.append('CSS digest and rendered head; JWT plugin bytes and configured module')
        roles = inputs / 'tools/product-role-probe.py'
        namespace = {'request': lambda path, data, content='text/xml', headers=():
                     https(path, 'POST', __import__('json').loads(data)) if content == 'application/json'
                     else xml_request(execute, path, data), '__name__': 'product_role_probe'}
        exec(compile(roles.read_text(), str(roles), 'exec'), namespace)
        namespace['verify_roles'](checks)

    stack.main(product_check=check,
               product_cleanup=lambda private: restore_web_owner(private, os.getuid(), os.getgid()))


def xml_request(execute, path, data):
    return execute('gateway', 'curl', '-fsS', '--max-time', '15', '--cacert', '/tmp/ci-root.crt',
        '--resolve', 'meet.jitsi:443:127.0.0.1', '-H', 'Content-Type: text/xml',
        '--data-binary', data, 'https://meet.jitsi' + path)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
