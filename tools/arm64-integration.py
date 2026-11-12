"""Ephemeral ARM64 control plane only; no target access or media claim."""
import json
from pathlib import Path
import secrets
import subprocess
import time


def accepts(stats, states):
    return (stats.get('bridge_selector', {}).get('operational_bridge_count', 0) >= 1
            and len(states) == 3
            and all(s['running'] and not s['oom'] and s['restarts'] == 0 for s in states))


def main():
    evidence = Path('arm64-evidence')
    evidence.mkdir(exist_ok=True)
    project = 'arm64-ci-' + secrets.token_hex(4)
    common = {
        'PUBLIC_URL': 'https://meet.jitsi', 'XMPP_DOMAIN': 'meet.jitsi',
        'XMPP_AUTH_DOMAIN': 'auth.meet.jitsi', 'XMPP_MUC_DOMAIN': 'muc.meet.jitsi',
        'XMPP_INTERNAL_MUC_DOMAIN': 'internal-muc.meet.jitsi',
        'XMPP_SERVER': 'xmpp.meet.jitsi', 'XMPP_PORT': '5222',
        'JVB_BREWERY_MUC': 'jvbbrewery', 'JICOFO_AUTH_USER': 'focus',
        'JVB_AUTH_USER': 'jvb', 'JICOFO_AUTH_PASSWORD': secrets.token_hex(32),
        'JVB_AUTH_PASSWORD': secrets.token_hex(32),
        'ENABLE_AUTH': '0', 'ENABLE_AUTO_OWNER': '0',
        'JICOFO_ENABLE_REST': '1', 'JICOFO_MAX_MEMORY': '512m',
        'JVB_MAX_MEMORY': '512m', 'COLIBRI_REST_ENABLED': '1',
        'JVB_ADVERTISE_IPS': '192.0.2.10', 'SENTRY_RELEASE': 'arm64-ci',
    }
    services = {}
    for name in ('prosody', 'jicofo', 'jvb'):
        image = 'cloudmeet-ci/' + name
        identity = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]
        if (identity['Os'], identity['Architecture']) != ('linux', 'arm64'):
            raise RuntimeError('Wrong image platform: ' + name)
        services[name] = {
            'image': image, 'pull_policy': 'never', 'restart': 'no',
            'environment': common, 'mem_limit': '1g', 'pids_limit': 512,
            'tmpfs': ['/config:uid=1000,gid=1000,mode=0755'],
            'networks': {'test': {'aliases': ['xmpp.meet.jitsi']} if name == 'prosody' else {}},
        }
        if name != 'prosody':
            services[name]['depends_on'] = ['prosody']
    # No published host ports; keep the test bridge on an internal-only network.
    compose = {'services': services, 'networks': {'test': {'internal': True}}}
    config = evidence / '.compose.private.json'
    config.write_text(json.dumps(compose))
    config.chmod(0o600)
    cmd = ['docker', 'compose', '-p', project, '-f', str(config)]
    result = {'status': 'FAIL', 'scope': 'ARM64 XMPP and operational bridge; not host-transfer or media acceptance'}

    def run(args):
        return subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=45)

    try:
        run(cmd + ['config', '--quiet'])
        run(cmd + ['up', '-d', '--no-build', '--pull', 'never'])
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            try:
                stats = json.loads(run(cmd + ['exec', '-T', 'jicofo', 'curl', '-fsS',
                                             '--max-time', '3', 'http://127.0.0.1:8888/stats']))
                ids = run(cmd + ['ps', '-aq']).decode().split()
                containers = json.loads(run(['docker', 'inspect'] + ids))
                states = [{'service': c['Config']['Labels']['com.docker.compose.service'],
                           'running': c['State']['Running'], 'oom': c['State']['OOMKilled'],
                           'restarts': c['RestartCount'], 'image': c['Image']} for c in containers]
                if accepts(stats, states):
                    # A second observation guards against immediate startup crashes.
                    if result.get('observed_once'):
                        result.update(status='PASS_CONTROL_PLANE_NOT_MEDIA', states=states,
                                      bridge_selector=stats['bridge_selector'])
                        return
                    result['observed_once'] = True
                else:
                    result.pop('observed_once', None)
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                result.pop('observed_once', None)
            time.sleep(5)
        raise RuntimeError('No stable operational bridge within 240 seconds')
    finally:
        try:
            logs = run(cmd + ['logs', '--no-color']).decode(errors='replace')
            for key in ('JICOFO_AUTH_PASSWORD', 'JVB_AUTH_PASSWORD'):
                logs = logs.replace(common[key], '<redacted>')
            (evidence / 'integration.log').write_text(logs)
        finally:
            (evidence / 'result.json').write_text(json.dumps(result, indent=2))
            try:
                subprocess.run(cmd + ['down', '--volumes', '--remove-orphans'], timeout=60, check=True)
            finally:
                config.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
