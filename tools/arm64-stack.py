"""Exact-image ephemeral ARM64 integration, never installation or media acceptance."""
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ('prosody', 'jicofo', 'jvb', 'web', 'api', 'app-web', 'gateway')
LOCK = ROOT / 'tools/arm64-stack-lock.json'


def run(args, timeout=60):
    return subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=timeout)


def accepts(states, images, bridges):
    return (set(images) == set(SERVICES) and len(states) == 7
            and {s['service'] for s in states} == set(SERVICES) and bridges >= 1
            and all(s['running'] and not s['oom'] and not s['restarts']
                    and s['image'] == images[s['service']] for s in states))


def valid_upgrade(response):
    lines = response.split(b'\r\n')
    headers = dict(line.split(b':', 1) for line in lines[1:] if b':' in line)
    headers = {k.lower(): v.strip() for k, v in headers.items()}
    return (lines[0].split()[1:2] == [b'101']
            and headers.get(b'sec-websocket-accept') == b's3pPLMBiTxaQ9kYGzzhZRbK+xOo='
            and headers.get(b'upgrade', b'').lower() == b'websocket'
            and b'upgrade' in headers.get(b'connection', b'').lower()
            and headers.get(b'sec-websocket-protocol') == b'xmpp')


def topology(images, private, credentials):
    common = {'PUBLIC_URL': 'https://meet.jitsi', 'XMPP_DOMAIN': 'meet.jitsi',
              'XMPP_AUTH_DOMAIN': 'auth.meet.jitsi', 'XMPP_MUC_DOMAIN': 'muc.meet.jitsi',
              'XMPP_INTERNAL_MUC_DOMAIN': 'internal-muc.meet.jitsi', 'XMPP_SERVER': 'xmpp.meet.jitsi',
              'XMPP_PORT': '5222', 'JVB_BREWERY_MUC': 'jvbbrewery', 'JICOFO_AUTH_USER': 'focus',
              'JVB_AUTH_USER': 'jvb', 'JICOFO_AUTH_PASSWORD': credentials['focus'],
              'JVB_AUTH_PASSWORD': credentials['jvb'], 'ENABLE_AUTH': '0', 'ENABLE_AUTO_OWNER': '0',
              'JICOFO_ENABLE_REST': '1', 'JICOFO_MAX_MEMORY': '512m', 'JVB_MAX_MEMORY': '512m',
              'COLIBRI_REST_ENABLED': '1', 'JVB_ADVERTISE_IPS': '192.0.2.10', 'SENTRY_RELEASE': 'arm64-stack',
              'ENABLE_XMPP_WEBSOCKET': '1'}
    services = {name: {'image': images[name], 'pull_policy': 'never', 'restart': 'no',
                       'mem_limit': '1g', 'pids_limit': 512, 'networks': {'test': {}}}
                for name in SERVICES}
    for name in ('prosody', 'jicofo', 'jvb', 'web'):
        services[name]['environment'] = dict(common)
        services[name]['tmpfs'] = ['/config:uid=1000,gid=1000,mode=0755']
    services['prosody']['networks']['test']['aliases'] = ['xmpp.meet.jitsi']
    for name in ('jicofo', 'jvb', 'web'):
        services[name]['depends_on'] = ['prosody']
    services['web']['environment'].update(DISABLE_HTTPS='1', ENABLE_LETSENCRYPT='0',
        NGINX_WORKER_PROCESSES='1', XMPP_BOSH_URL_BASE='http://xmpp.meet.jitsi:5280')
    services['api'].update(volumes=['api_data:/app/data'], environment={
        'JITSI_TOKEN_APP_ID': 'arm64-ci', 'JITSI_TOKEN_APP_SECRET': credentials['jwt'],
        'JITSI_TOKEN_DOMAIN': 'meet.jitsi'})
    services['app-web']['depends_on'] = ['api']
    services['gateway'].update(environment={'SITE_HOST': 'meet.jitsi'},
        volumes=[str(private / 'Caddyfile') + ':/etc/caddy/Caddyfile:ro',
                 'ca_data:/data', 'ca_config:/config'], depends_on=['app-web', 'web'])
    return {'services': services, 'networks': {'test': {'internal': True}},
            'volumes': {'api_data': {}, 'ca_data': {}, 'ca_config': {}}}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def download(artifact_id, destination):
    url = 'https://api.github.com/repos/stevenzxs/cloudemeet-deploy/actions/artifacts/' + str(artifact_id) + '/zip'
    headers = {'User-Agent': 'CloudMeet-ARM64-integration', 'Authorization': 'Bearer ' + os.environ['GH_TOKEN']}
    try:
        response = urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url, headers=headers), timeout=60)
    except urllib.error.HTTPError as error:
        if error.code != 302:
            raise
        location = error.headers['Location']
        if not location.startswith('https://'):
            raise RuntimeError('Non-HTTPS artifact redirect')
        # Never forward the GitHub token to artifact storage.
        response = urllib.request.urlopen(location, timeout=120)
    with response, destination.open('wb') as output:
        shutil.copyfileobj(response, output, 1024 * 1024)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def import_images(work, lock):
    images = {}
    for artifact in lock['artifacts']:
        path = work / (str(artifact['id']) + '.zip')
        download(artifact['id'], path)
        if 'sha256:' + digest(path) != artifact['digest']:
            raise RuntimeError('Artifact digest mismatch')
        with zipfile.ZipFile(path) as archive:
            for service, expected in lock['images'].items():
                if service + '.json' not in archive.namelist():
                    continue
                if service in images:
                    raise RuntimeError('Duplicate service')
                record = json.loads(archive.read(service + '.json'))
                if any(record[k] != expected[k] for k in ('source', 'image_id', 'archive', 'sha256', 'size')):
                    raise RuntimeError('Candidate identity mismatch')
                target = work / (service + '.tar.gz')
                if expected['archive'] != target.name:
                    raise RuntimeError('Unexpected archive name')
                with archive.open(target.name) as src, target.open('wb') as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                if target.stat().st_size != expected['size'] or digest(target) != expected['sha256']:
                    raise RuntimeError('Image bytes mismatch')
                run(['docker', 'load', '-i', str(target)], timeout=180)
                info = json.loads(run(['docker', 'image', 'inspect', expected['image_id']]))[0]
                if (info['Os'], info['Architecture'], info['Id']) != ('linux', 'arm64', expected['image_id']):
                    raise RuntimeError('Loaded image mismatch')
                images[service] = info['Id']
        path.unlink()
    if set(images) != set(SERVICES):
        raise RuntimeError('Missing candidate images')
    return images


def main(product_check=None):
    if platform.machine() != 'aarch64':
        raise RuntimeError('Native ARM64 only')
    evidence = ROOT / 'stack-evidence'
    evidence.mkdir(exist_ok=True)
    lock = json.loads(LOCK.read_text())
    project = 'cm-stack-' + secrets.token_hex(6)
    credentials = {key: secrets.token_hex(32) for key in ('focus', 'jvb', 'jwt', 'host')}
    result = {'status': 'FAIL', 'source_run': lock['run'], 'source_attempt': 2,
              'not_tested': ['JWT/host transfer', 'media', 'offline installation', 'target OS', 'security clearance']}
    with tempfile.TemporaryDirectory(prefix='cm-stack-') as directory:
        private = Path(directory)
        private.chmod(0o700)
        cmd = ['docker', 'compose', '-p', project, '-f', str(private / 'compose.json')]
        def compose(*args):
            return run(cmd + list(args))
        def execute(service, *args):
            return compose('exec', '-T', service, *args)
        def https(path, method='GET', data=None):
            args = ['curl', '-fsS', '--max-time', '10', '--cacert', '/tmp/ci-root.crt',
                    '--resolve', 'meet.jitsi:443:127.0.0.1', '-X', method]
            if data is not None:
                args += ['-H', 'Content-Type: application/json', '--data', json.dumps(data)]
            return execute('gateway', *args, 'https://meet.jitsi' + path)
        def states():
            ids = compose('ps', '-aq').decode().split()
            return [{'service': c['Config']['Labels']['com.docker.compose.service'], 'image': c['Image'],
                     'running': c['State']['Running'], 'oom': c['State']['OOMKilled'], 'restarts': c['RestartCount']}
                    for c in json.loads(run(['docker', 'inspect'] + ids))]
        try:
            images = import_images(private, lock)
            result['images'] = images
            shutil.copyfile(ROOT / 'Caddyfile', private / 'Caddyfile')
            (private / 'compose.json').write_text(json.dumps(topology(images, private, credentials)))
            compose('config', '--quiet')
            compose('up', '-d', '--no-build', '--pull', 'never')
            for attempt in range(60):
                try:
                    compose('cp', 'gateway:/data/caddy/pki/authorities/local/root.crt', str(private / 'root.crt'))
                    compose('cp', str(private / 'root.crt'), 'gateway:/tmp/ci-root.crt')
                    if json.loads(https('/mapi/actuator/health'))['status'] == 'UP':
                        break
                except (subprocess.SubprocessError, ValueError, KeyError):
                    if attempt == 59:
                        raise RuntimeError('TLS/API readiness timeout') from None
                    time.sleep(3)
            checks = result['checks'] = ['strict TLS and API health']
            for route in ('/cm/index.html', '/cm/desktop', '/', '/config.js', '/libs/app.bundle.min.js'):
                payload = https(route)
                if not payload or b'<!--#' in payload:
                    raise RuntimeError('Missing payload or SSI: ' + route)
            code = execute('gateway', 'curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}',
                '--cacert', '/tmp/ci-root.crt', '--resolve', 'meet.jitsi:443:127.0.0.1',
                'https://meet.jitsi/mapi/internal/probe')
            if code != b'404':
                raise RuntimeError('Internal API not blocked')
            checks.append('gateway routes, SSI, internal 404')
            fixture = {'roomName': '987654321', 'subject': 'Isolated CI', 'creatorId': 'stack-ci',
                       'displayName': 'CI', 'hostKey': credentials['host']}
            https('/mapi/open/desktop/meetings', 'POST', fixture)
            https('/mapi/open/desktop/meetings/987654321/end', 'POST', {'hostKey': credentials['host']})
            def history():
                items = json.loads(https('/mapi/open/desktop/meetings/history?creatorId=stack-ci'))
                if not any(i.get('roomName') == '987654321' for i in items):
                    raise RuntimeError('Missing persisted fixture')
            history()
            compose('up', '-d', '--no-deps', '--force-recreate', '--pull', 'never', 'api')
            for attempt in range(45):
                try:
                    https('/mapi/actuator/health')
                    history()
                    break
                except subprocess.SubprocessError:
                    if attempt == 44:
                        raise RuntimeError('Recreated API not ready') from None
                    time.sleep(2)
            checks.append('HTTPS create/end/history and recreated API SQLite persistence')
            bosh = execute('gateway', 'curl', '-fsS', '--max-time', '15', '--cacert', '/tmp/ci-root.crt',
                '--resolve', 'meet.jitsi:443:127.0.0.1', '-H', 'Content-Type: text/xml', '--data',
                "<body rid='12345' to='meet.jitsi' wait='5' hold='1' ver='1.6' xmlns='http://jabber.org/protocol/httpbind' xml:lang='en'/>",
                'https://meet.jitsi/http-bind')
            body = ET.fromstring(bosh)
            if body.tag != '{http://jabber.org/protocol/httpbind}body' or not body.get('sid'):
                raise RuntimeError('BOSH did not create session')
            checks.append('HTTPS BOSH session')
            # openssl is not assumed present: stdlib Python on runner probes from
            # inside gateway's network namespace using nsenter, trusting only CI CA.
            gateway = compose('ps', '-q', 'gateway').decode().strip()
            pid = json.loads(run(['docker', 'inspect', gateway]))[0]['State']['Pid']
            probe = '''import socket,ssl,sys
context=ssl.create_default_context(cafile=sys.argv[1])
with context.wrap_socket(socket.create_connection(('127.0.0.1',443),timeout=10),server_hostname='meet.jitsi') as s:
 s.sendall(b'GET /xmpp-websocket HTTP/1.1\\r\\nHost: meet.jitsi\\r\\nOrigin: https://meet.jitsi\\r\\nUpgrade: websocket\\r\\nConnection: Upgrade\\r\\nSec-WebSocket-Version: 13\\r\\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\\r\\nSec-WebSocket-Protocol: xmpp\\r\\n\\r\\n')
 data=b''
 while b'\\r\\n\\r\\n' not in data and len(data)<16384:
  part=s.recv(4096)
  if not part: break
  data+=part
 sys.stdout.buffer.write(data)
'''
            response = run(['sudo', '-n', 'nsenter', '-t', str(pid), '-n', 'python3', '-c', probe, str(private / 'root.crt')])
            if not valid_upgrade(response):
                raise RuntimeError('No valid TLS XMPP WebSocket upgrade')
            checks.append('strict TLS XMPP WebSocket 101 and accept validation')
            stable = 0
            for attempt in range(48):
                try:
                    stats = json.loads(execute('jicofo', 'curl', '-fsS', '--max-time', '3', 'http://127.0.0.1:8888/stats'))
                    current = states()
                    bridges = stats.get('bridge_selector', {}).get('operational_bridge_count', 0)
                    stable = stable + 1 if accepts(current, images, bridges) else 0
                    if stable >= 2:
                        result.update(states=current, operational_bridge_count=bridges,
                            status='PASS_SEVEN_SERVICE_INTEGRATION_NOT_OFFLINE_OR_MEDIA')
                        checks.append('seven exact images stable; operational bridge twice')
                        break
                except (subprocess.SubprocessError, ValueError):
                    stable = 0
                time.sleep(5)
            if stable < 2:
                raise RuntimeError('Seven-service stability/bridge gate failed')
            if product_check is not None:
                product_check(execute, https, private, checks)
                result['status'] = 'PASS_PRODUCT_PATCHES_ROLES_NOT_OFFLINE_OR_MEDIA'
        except Exception as error:
            # Do not print subprocess command/body, which can contain hostKey.
            result['error_type'] = type(error).__name__
            if isinstance(error, RuntimeError):
                result['error'] = str(error)
            raise RuntimeError('Integration failed; see sanitized result') from None
        finally:
            (evidence / 'result.json').write_text(json.dumps(result, indent=2))
            if (private / 'compose.json').exists():
                try:
                    logs = compose('logs', '--no-color', '--tail', '100').decode(errors='replace')
                    for value in credentials.values():
                        logs = logs.replace(value, '<redacted>')
                    (evidence / 'stack.log').write_text(logs)
                finally:
                    subprocess.run(cmd + ['down', '--volumes', '--remove-orphans'], timeout=90, check=True)


if __name__ == '__main__':
    main()
