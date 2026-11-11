"""Service-only smoke in disposable containers; no host ports or live secrets."""
import argparse
import json
from pathlib import Path
import secrets
import re
import subprocess
import time

EVIDENCE = Path('arm64-evidence')


def run(*args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=45)


def redact(text, credentials):
    for value in credentials:
        if value:
            text = text.replace(value, '<redacted>')
    return re.sub(r'(?i)((?:hostkey|token|password|secret|authorization)["\s]*[:=]["\s]*)([^\s,;"}]+)',
                  r'\1<redacted>', text)


def diagnose(cid, credentials):
    result = {}
    try:
        info = json.loads(run('docker', 'inspect', cid))[0]
        # Explicit state allowlist: never serialize Config.Env, mounts or secrets.
        result['state'] = {key: info['State'].get(key) for key in
                           ('Running', 'ExitCode', 'OOMKilled', 'Error', 'StartedAt', 'FinishedAt')}
        result['restarts'] = info['RestartCount']
        result['logs'] = redact(run('docker', 'logs', '--tail', '200', cid).decode(errors='replace'), credentials)
    except (subprocess.SubprocessError, ValueError, KeyError) as error:
        result['diagnostic_error'] = type(error).__name__
    return result


def http(cid, path, port, method='GET', data=None):
    args = ['docker', 'exec', cid, 'curl', '-fsS', '--max-time', '5', '-X', method]
    if data is not None:
        args += ['-H', 'Content-Type: application/json', '-d', json.dumps(data)]
    return run(*(args + ['http://127.0.0.1:' + str(port) + path]))


def wait_http(cid, path, port):
    for attempt in range(90):
        try:
            return http(cid, path, port)
        except subprocess.CalledProcessError as error:
            if attempt == 89:
                output = (error.output or b'').decode(errors='replace')[-4000:]
                raise RuntimeError('Health probe failed: ' + output) from None
            time.sleep(2)


def smoke(service):
    EVIDENCE.mkdir(exist_ok=True)
    image = 'cloudmeet-ci/' + service
    containers = []
    volume = None
    result = {'service': service, 'status': 'FAIL', 'scope': 'service smoke only; no full-stack/media acceptance'}
    checks = []
    credentials = []

    def start(*options):
        cid = run('docker', 'run', '-d', '--network', 'none', '--memory', '1g',
                  '--pids-limit', '512', *options, image).decode().strip()
        containers.append(cid)
        return cid

    try:
        if service == 'web':
            cid = start('--tmpfs', '/config:uid=1000,gid=1000,mode=0755',
                        '-e', 'DISABLE_HTTPS=1', '-e', 'ENABLE_LETSENCRYPT=0',
                        '-e', 'NGINX_WORKER_PROCESSES=1', '-e', 'PUBLIC_URL=https://meet.jitsi',
                        '-e', 'XMPP_BOSH_URL_BASE=http://127.0.0.1:5280')
            config = wait_http(cid, '/config.js', 8000)
            if not config or b'<!--#' in config:
                raise RuntimeError('Config SSI failed')
            run('docker', 'exec', cid, 'nginx', '-e', 'stderr', '-t', '-c', '/run/web/config/nginx/nginx.conf')
            for route in ('/', '/interface_config.js', '/libs/app.bundle.min.js', '/external_api.js', '/css/all.css'):
                if not http(cid, route, 8000):
                    raise RuntimeError('Empty web payload')
            checks += ['default lifecycle', 'nginx config', 'config SSI', 'source static routes']
        elif service == 'app-web':
            cid = start('--add-host', 'api:127.0.0.1')
            # nginx alpine ships wget, not curl.
            for attempt in range(30):
                try:
                    run('docker', 'exec', cid, 'wget', '-qO-', 'http://127.0.0.1/healthz')
                    break
                except subprocess.CalledProcessError:
                    if attempt == 29:
                        raise
                    time.sleep(1)
            index = run('docker', 'exec', cid, 'wget', '-qO-', 'http://127.0.0.1/cm/index.html')
            deep = run('docker', 'exec', cid, 'wget', '-qO-', 'http://127.0.0.1/cm/desktop')
            if not index or index != deep:
                raise RuntimeError('SPA fallback mismatch')
            run('docker', 'exec', cid, 'nginx', '-t')
            response = subprocess.run(['docker', 'exec', cid, 'wget', '-S', '-O-',
                                       'http://127.0.0.1/mapi/internal/probe'], capture_output=True)
            if response.returncode == 0 or b'404' not in response.stderr:
                raise RuntimeError('Internal API was not blocked')
            checks += ['health', 'nginx config', 'SPA fallback', 'internal 404']
        elif service == 'api':
            volume = 'arm64-api-ci-' + secrets.token_hex(8)
            run('docker', 'volume', 'create', volume)
            # Throwaway fixture only; never serialize hostKey or tokens into evidence.
            fixture = {'roomName': '987654321', 'subject': 'ARM64 persistence smoke',
                       'displayName': 'CI', 'creatorId': 'arm64-ci', 'hostKey': secrets.token_hex(32)}
            credentials.append(fixture['hostKey'])
            for index in range(2):
                # With network=none there is no non-loopback address. MyBatis-Plus
                # falls back to InetAddress.getLocalHost(), so explicitly resolve
                # this container's hostname without granting network access.
                cid = start('--hostname', 'arm64-api-ci', '--add-host', 'arm64-api-ci:127.0.0.1',
                            '-v', volume + ':/app/data')
                wait_http(cid, '/mapi/actuator/health', 9000)
                if index == 0:
                    http(cid, '/mapi/open/desktop/meetings', 9000, 'POST', fixture)
                history = json.loads(http(cid, '/mapi/open/desktop/meetings/history?creatorId=arm64-ci', 9000))
                if not any(item.get('roomName') == fixture['roomName'] for item in history):
                    raise RuntimeError('SQLite persisted fixture missing')
                run('docker', 'stop', '-t', '20', cid)
            checks += ['API health', 'native sqlite write/read', 'persistence across fresh containers']
        elif service == 'gateway':
            cid = run('docker', 'run', '-d', '--network', 'none', '--memory', '256m',
                      image, 'respond', '--listen', '127.0.0.1:9080', '--body', 'ARM64-CI').decode().strip()
            containers.append(cid)
            if wait_http(cid, '/', 9080) != b'ARM64-CI':
                raise RuntimeError('Caddy response mismatch')
            run('docker', 'exec', cid, 'caddy', 'version')
            modules = run('docker', 'exec', cid, 'caddy', 'list-modules')
            if b'tls' not in modules:
                raise RuntimeError('TLS modules missing')
            checks += ['source binary version/modules', 'HTTP startup']
        else:
            raise ValueError('Unknown service')
        for cid in containers:
            state = json.loads(run('docker', 'inspect', cid))[0]
            if state['State']['OOMKilled'] or state['RestartCount']:
                raise RuntimeError('Unstable candidate container')
            if service != 'api' and not state['State']['Running']:
                raise RuntimeError('Candidate stopped')
        result.update(status='PASS_SERVICE_SMOKE_NOT_INTEGRATION', checks=checks)
    except Exception as error:
        # Do not serialize command args: POST args could contain the fixture hostKey.
        result['error_type'] = type(error).__name__
        if isinstance(error, RuntimeError):
            result['error'] = redact(str(error), credentials)
        result['diagnostics'] = [diagnose(cid, credentials) for cid in containers]
        raise
    finally:
        # Failure-only, bounded/redacted diagnostics; no raw runtime log artifact.
        (EVIDENCE / (service + '-smoke.json')).write_text(json.dumps(result, indent=2))
        for cid in containers:
            subprocess.run(['docker', 'rm', '-f', '-v', cid], check=True, timeout=60)
        if volume:
            subprocess.run(['docker', 'volume', 'rm', volume], check=True, timeout=30)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('service', choices=['web', 'app-web', 'api', 'gateway'])
    smoke(parser.parse_args().service)
