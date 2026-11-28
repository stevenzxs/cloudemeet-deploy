#!/usr/bin/env python3
"""full-clean: inventory and wipe a CloudMeet instance on a target server.

Two phases: read-only SSH inventory first, then an explicitly confirmed wipe.
Only the identified compose project, its labeled volumes, cloudmeet/* images
and the validated instance root are touched. Never global prune, never backup.
"""
import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys

DANGEROUS_ROOTS = {'/', '/root', '/home', '/etc', '/var', '/usr', '/opt', '/srv', '/tmp', '/boot'}
PRODUCT_IMAGE_RE = re.compile(r'^cloudmeet/[a-z-]+:')
PROJECT_RE = re.compile(r'^cloudmeet(?:-[a-z0-9][a-z0-9-]{0,60})?$')
COMPOSE_LABEL = 'com.docker.compose.project'
ROOT_MARKERS = ('candidate.json', 'jitsi-base.yaml', 'compose.yaml', 'images.json')


def parse_jdbc(url):
    """Return (host, port, database) for a postgres JDBC URL, None for non-postgres."""
    match = re.fullmatch(r'jdbc:postgresql://([^/:?]+)(?::(\d+))?/([A-Za-z0-9_]+)(?:\?\S*)?', url.strip())
    if not match:
        if url.strip().startswith('jdbc:h2:'):
            return None
        raise ValueError('Unsupported jitsi-mgr database URL; refusing to identify the external schema')
    host, port, database = match.group(1), int(match.group(2) or 5432), match.group(3)
    if 'jitsi' not in database.lower():
        raise ValueError('External database name lacks jitsi marker; refusing to wipe a possibly shared database: ' + database)
    return host, port, database


def validate_instance_root(root):
    if not isinstance(root, str) or not root.startswith('/') or root.endswith('/') and root != '/' and len(root) < 4:
        raise ValueError('Absolute instance root required')
    normalized = re.sub(r'/+', '/', root).rstrip('/') or '/'
    if '..' in normalized.split('/'):
        raise ValueError('Instance root must not contain ..')
    if normalized in DANGEROUS_ROOTS or len(normalized) < 5:
        raise ValueError('Refusing dangerous instance root: ' + normalized)
    return normalized


def require_instance_markers(root, probe):
    command = ('for f in candidate.json jitsi-base.yaml compose.yaml images.json .env data; do '
               f'test -e "{root}/$f" && echo "present:$f"; done')
    result = probe(command)
    present = set()
    for line in (result.stdout or '').splitlines():
        if line.startswith('present:'):
            present.add(line.split(':', 1)[1])
    if not any(marker in present for marker in ROOT_MARKERS) or 'data' not in present:
        raise ValueError('Instance markers missing; refusing to identify the instance root')


def group_containers(ps_json_lines):
    projects = {}
    for line in ps_json_lines.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        labels = {}
        for pair in item.get('Labels', '').split(','):
            if '=' in pair:
                key, value = pair.split('=', 1)
                labels[key] = value
        project = labels.get(COMPOSE_LABEL)
        if not project:
            continue
        projects.setdefault(project, []).append({
            'id': item.get('ID'), 'service': labels.get('com.docker.compose.service'),
            'working_dir': labels.get('com.docker.compose.project.working_dir')})
    return projects


def select_project(ps_json_lines, root):
    projects = group_containers(ps_json_lines)
    cloudmeet = {name: items for name, items in projects.items() if PROJECT_RE.fullmatch(name)}
    if len(cloudmeet) > 1:
        raise ValueError('Multiple CloudMeet compose projects found; refusing to pick one: ' + ', '.join(sorted(cloudmeet)))
    matches = [name for name, items in cloudmeet.items()
               if any(item.get('working_dir') == root for item in items)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ValueError('Ambiguous project mapping for instance root')
    if not cloudmeet:
        raise ValueError('No running CloudMeet compose project found')
    return next(iter(cloudmeet))


def host_fingerprints(scan_output):
    """SHA256 fingerprints of every host key line, in scan order.

    ssh-keyscan ordering across rsa/ed25519 lines is unstable between runs;
    matching only the first line caused spurious mismatch rejections against
    the very same host (observed on 118.193.36.35).
    """
    fingerprints = []
    for line in scan_output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1].startswith('ssh-'):
            digest = hashlib.sha256(base64.b64decode(parts[2])).digest()
            fingerprints.append('SHA256:' + base64.b64encode(digest).decode().rstrip('='))
    if not fingerprints:
        raise ValueError('No host key found in scan output')
    return fingerprints


def host_fingerprint(scan_output):
    """SHA256 fingerprint of the first host key line, in the ssh-keygen display format."""
    return host_fingerprints(scan_output)[0]


def check_fingerprint(host, port, accepted, scan_output):
    fingerprints = host_fingerprints(scan_output)
    if accepted is None:
        raise ValueError(f'First contact with {host}:{port}: rerun with --accept-fingerprint {fingerprints[0]}')
    if accepted not in fingerprints:
        raise ValueError(f'Host fingerprint mismatch for {host}:{port}: expected {accepted}, actual one of {fingerprints}')
    return accepted


def apply_commands(project, root, postgres, db_user, db_password):
    """Ordered destructive commands for one validated wipe; runner executes them remotely."""
    commands = [
        f'docker rm -f $(docker ps -aq --filter label={COMPOSE_LABEL}={project})',
        f'docker volume rm $(docker volume ls -q --filter label={COMPOSE_LABEL}={project})',
        f'docker network rm $(docker network ls -q --filter label={COMPOSE_LABEL}={project})',
        'docker rmi $(docker images -q --filter "reference=cloudmeet/*")',
        f'rm -rf -- "{root}"',
    ]
    if postgres:
        host, port, database = postgres
        sql = 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
        commands.append(
            f'PGPASSWORD={db_password} psql -h {host} -p {port} -U {db_user} {database} -c "{sql}"')
    return commands


def verify_commands(project, root):
    return [
        f'test -z "$(docker ps -aq --filter label={COMPOSE_LABEL}={project})"',
        f'test -z "$(docker volume ls -q --filter label={COMPOSE_LABEL}={project})"',
        'test -z "$(docker images -q --filter reference=cloudmeet/*)"',
        f'test ! -e "{root}"',
    ]


def _local(command, runner):
    """Execute the probe locally (--local mode: the script runs on the target itself)."""
    result = runner(['bash', '-c', command], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError('Local command failed: ' + command[:120] + '\n' + (result.stderr or '')[:2000])
    return result


def _ssh(args, command, runner):
    argv = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
            '-o', 'StrictHostKeyChecking=no', '-p', str(args.port)]
    if args.identity_file:
        argv += ['-i', args.identity_file]
    argv += [f'{args.user}@{args.host}', command]
    result = runner(argv, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError('Remote command failed: ' + command[:120] + '\n' + (result.stderr or '')[:2000])
    return result


def _env_values(probe, file, keys):
    pattern = '|'.join(keys)
    result = probe(f'grep -E "^({pattern})=" "{file}" || true')
    values = {}
    for line in (result.stdout or '').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            values[key] = value
    return values


def collect_inventory(args, runner):
    local = getattr(args, 'local', False)
    probe = lambda command: _local(command, runner) if local else _ssh(args, command, runner)
    if local:
        fingerprint = 'local-exec'
    else:
        scan = runner(['ssh-keyscan', '-T', '10', '-p', str(args.port), '-t', 'rsa,ed25519', args.host],
                      capture_output=True, text=True)
        if scan.returncode != 0 or not scan.stdout.strip():
            raise ValueError('Host key scan failed: ' + (scan.stderr or '')[:1000])
        fingerprint = check_fingerprint(args.host, args.port, args.accept_fingerprint, scan.stdout)
    root = validate_instance_root(args.instance_root)
    require_instance_markers(root, probe)
    hostname = probe('hostname').stdout.strip()
    containers = probe('docker ps -a --format "{{json .}}"').stdout
    project = select_project(containers, root)
    volumes = sorted(probe(f'docker volume ls -q --filter label={COMPOSE_LABEL}={project}').stdout.split())
    images = [json.loads(line) for line in probe('docker images --format "{{json .}}"').stdout.splitlines() if line.strip()]
    product_images = [item for item in images if PRODUCT_IMAGE_RE.match(item.get('Repository', '') + ':')]
    mgr = _env_values(probe, f'{root}/jitsi-mgr.env', ['JITSI_MGR_DB_URL', 'JITSI_MGR_DB_USER'])
    secrets = _env_values(probe, f'{root}/.env', ['JITSI_MGR_DB_PASSWORD'])
    postgres = parse_jdbc(mgr['JITSI_MGR_DB_URL']) if mgr.get('JITSI_MGR_DB_URL') else None
    return {'host': args.host, 'hostname': hostname, 'fingerprint': fingerprint, 'root': root,
            'project': project, 'containers': group_containers(containers)[project],
            'volumes': volumes, 'images': product_images,
            'postgres': list(postgres) if postgres else None,
            'db_user': mgr.get('JITSI_MGR_DB_USER', ''), 'db_password': secrets.get('JITSI_MGR_DB_PASSWORD', '')}


def execute_wipe(args, inventory, runner):
    probe = lambda command: _local(command, runner) if getattr(args, 'local', False) else _ssh(args, command, runner)
    postgres = tuple(inventory['postgres']) if inventory['postgres'] else None
    for command in apply_commands(inventory['project'], inventory['root'], postgres,
                                  inventory['db_user'], inventory['db_password']):
        probe(command)
    for command in verify_commands(inventory['project'], inventory['root']):
        if probe(command).returncode != 0:
            raise ValueError('Residue detected after wipe: ' + command)
    print('READY_FOR_REINSTALL: zero containers/volumes/images/instance-data remain. '
          'External target.env preserved; reinstall is a separate action and is NOT performed.')


def main(argv=None, runner=subprocess.run):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--user', default='root')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--identity-file')
    parser.add_argument('--instance-root', required=True)
    parser.add_argument('--accept-fingerprint')
    parser.add_argument('--local', dest='local', action='store_true', default=True,
                        help='Run on the target machine itself (default); no SSH, no host key check')
    parser.add_argument('--remote', dest='local', action='store_false',
                        help='Probe the target over SSH instead of running locally')
    parser.add_argument('--apply', action='store_true', help='Execute the wipe; without it only inventory is printed')
    args = parser.parse_args(argv)
    inventory = collect_inventory(args, runner)
    print(json.dumps(inventory, indent=2))
    if args.apply:
        execute_wipe(args, inventory, runner)


if __name__ == '__main__':
    main()
