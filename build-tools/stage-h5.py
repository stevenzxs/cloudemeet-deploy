#!/usr/bin/env python3
"""Stage tested fixed H5 checkout into an existing current-run server package."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


def stage(repo, source, destination, assignment):
    lock = json.loads((repo/'config/h5-source.json').read_text())
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
    if head != lock['commit'] or dirty:
        raise ValueError('H5 source must be clean at reviewed commit')
    if assignment.get('request', {}).get('sources', {}).get('h5') != head:
        raise ValueError('H5 must be bound to the parent persistent assignment')
    subprocess.run(['npm', 'ci', '--ignore-scripts'], cwd=source, check=True)
    subprocess.run(['npm', 'test'], cwd=source, check=True)
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise ValueError('H5 source changed during native tests')
    config_sha = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
        raise ValueError('Reviewed tracked deployment material changed')
    spec = importlib.util.spec_from_file_location('h5_contract', repo/'build-tools/offline-runtime/h5.py')
    h5 = importlib.util.module_from_spec(spec); spec.loader.exec_module(h5)
    public = destination/'h5/public'
    public.mkdir(parents=True)  # Refuses existing product material.
    for name in h5.PUBLIC_FILES:
        src = source/name
        if src.is_symlink() or not src.is_file() or (source/'src').is_symlink():
            raise ValueError('H5 source links prohibited')
        target = public/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    record = h5.describe(public, {'source_commit': head, 'configuration_commit': config_sha,
                                'version_assignment': assignment})
    manifest_path = destination/'candidate.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest['deployment_commit'] != config_sha or manifest['version_assignment'] != assignment:
        raise ValueError('H5/server parent identity mismatch')
    manifest['h5'] = record
    from_revision = assignment.get('versions', {}).get('revision')
    if type(from_revision) is not int or from_revision < 1 or lock.get('baseline') != '0.1.0':
        raise ValueError('Approved H5 baseline and parent revision required')
    manifest['h5_version'] = lock['baseline']+'+r'+str(from_revision)
    client = dict(line.split('=', 1) for line in (repo/'config/client.env').read_text().splitlines()
                  if line and not line.startswith('#') and '=' in line)
    port = int(client['SITE_PORT'])
    manifest['client_origin'] = client['SITE_SCHEME']+'://'+client['SITE_DOMAIN']+((':'+str(port)) if port != 443 else '')
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
    h5.verify_package(destination, manifest)
    # Source material stays immutable; first-start creates the runtime directory.
    caddy = destination/'Caddyfile'
    caddy.write_text(h5.gateway_caddy(caddy.read_text()))
    base = destination/'jitsi-base.yaml'
    compose = json.loads(base.read_text())
    compose['services']['gateway']['volumes'].append('./h5-runtime:/srv/cloudmeet-h5:ro')
    base.write_text(json.dumps(compose, indent=2)+'\n')


if __name__ == '__main__':
    repo, source, destination, assignment = map(Path, sys.argv[1:])
    stage(repo, source, destination, json.loads(assignment.read_text()))
