#!/usr/bin/env python3
"""Single-target patch release: numbering, records, base evidence, publish orchestration.

Patch releases reuse a published joint batch identity with a -patch.N suffix.
They never allocate a joint revision, never overwrite an existing release or
registry tag, and never claim deployment or runtime acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT.parent / 'full-build-deploy' / 'tools'))
from revision_versions import digest, numeric_version  # noqa: E402

REPOSITORY = 'stevenzxs/cloudemeet-deploy'
IMAGE_SERVICES = ('gateway', 'app-web', 'api', 'web', 'prosody', 'jicofo', 'jvb')
SERVICES = IMAGE_SERVICES + ('jitsi-mgr',)
CLIENTS = ('electron', 'android')
TARGETS = SERVICES + CLIENTS
CLIENT_EXT = {'electron': '.msi', 'android': '.apk'}


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def next_patch(existing_tags, prefix):
    """Next free patch number for tags named '<prefix><n>' with n in 1..9."""
    used = []
    for tag in existing_tags:
        if not isinstance(tag, str) or not tag.startswith(prefix):
            continue
        suffix = tag[len(prefix):]
        if re.fullmatch(r'[1-9]', suffix):
            used.append(int(suffix))
    if not used:
        return 1
    candidate = max(used) + 1
    if candidate > 9:
        raise ValueError('Patch band exhausted for ' + prefix)
    return candidate


def derive_patch(policy, revision, patch):
    """Patch versions for an existing joint revision; mirrors revision_versions guards."""
    if policy.get('schema') != 1 or policy.get('approved') is not True:
        raise ValueError('Version policy is not approved/activated')
    if type(revision) is not int or revision < 1:
        raise ValueError('Positive integer base revision required')
    current = policy.get('current_revision')
    if type(current) is not int or revision > current:
        raise ValueError('Base revision exceeds allocated revisions')
    if type(patch) is not int or not 1 <= patch <= 9:
        raise ValueError('Patch number must be 1..9')
    major, minor, client_patch = numeric_version(policy['client_baseline'])
    if major > 255 or minor > 255 or (client_patch + revision) * 10 + 9 > 65535:
        raise ValueError('MSI/PE version range exhausted')
    base = policy['android_base_code']
    if type(base) is not int or base < 1 or base != major * 1000 + minor * 100 + client_patch:
        raise ValueError('Registered Android base code required')
    code = base * 1000 + revision * 10 + patch
    if not 0 < code <= 2100000000:
        raise ValueError('Android versionCode overflow')
    server = policy['server_baseline']
    if not isinstance(server, str) or not re.fullmatch(r'\d+(?:\.\d+){2,3}', server):
        raise ValueError('Approved server baseline required')
    msi = f'{major}.{minor}.{(client_patch + revision) * 10 + patch}'
    return dict(revision=revision, patch=patch, version_formula=2,
                server_version=f'{server}+r{revision}-patch.{patch}',
                server_tag=f'{server}-r{revision}-patch.{patch}',
                client_version=f"{policy['client_baseline']}+r{revision}-patch.{patch}",
                android_code=code, msi_version=msi, pe_version=msi + '.0')


def build_record(policy, identities, base_revision, target, context, patch):
    if target not in TARGETS:
        raise ValueError('Unknown patch target: ' + str(target))
    if (not isinstance(identities, dict) or not identities
            or any(not re.fullmatch(r'[0-9a-f]{40}', str(v)) for v in identities.values())):
        raise ValueError('Pinned component sources required')
    if (context.get('repository') != REPOSITORY
            or not re.fullmatch(r'[1-9]\d*', str(context.get('run_id', '')))
            or not re.fullmatch(r'[0-9a-f]{40}', str(context.get('configuration_sha', '')))):
        raise ValueError('Run context binding required')
    scope = ['server'] if target in SERVICES else [target]
    record = {
        'namespace': policy['namespace'],
        'kind': 'patch',
        'request': dict(repository=context['repository'], workflow=context.get('workflow', ''),
                        run_id=str(context['run_id']), configuration_sha=context['configuration_sha'],
                        sources=identities, target=target, base_revision=base_revision, patch=patch,
                        task='actions-' + str(context['run_id']), scope=scope),
        'versions': derive_patch(policy, base_revision, patch),
    }
    record['allocation_sha256'] = digest(record)
    return record


def load_policy_and_identities(skill_root=None):
    root = Path(skill_root) if skill_root else SKILL_ROOT.parent / 'full-build-deploy'
    policy = json.loads((root / 'config/version-policy.json').read_text(encoding='utf-8'))
    sources = json.loads((root / 'sources.json').read_text(encoding='utf-8'))
    identities = {name: item['commit'] for group in ('services', 'clients') for name, item in sources[group].items()}
    identities['lifecycle'] = sources['lifecycle']['commit']
    identities['h5'] = json.loads((root / 'config/h5-source.json').read_text(encoding='utf-8'))['commit']
    return policy, identities


def _run(runner, argv):
    result = runner(argv, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError('Command failed: ' + ' '.join(map(str, argv)) + '\n' + (result.stderr or '')[:2000])
    return result


def check_base(policy, base_revision, target, runner=subprocess.run, repository=REPOSITORY):
    """Read-only proof that the base joint batch was actually published."""
    if target not in TARGETS:
        raise ValueError('Unknown patch target: ' + str(target))
    server = policy['server_baseline']
    prefix = f'cloudmeet-{server}-r{base_revision}-'
    result = runner(['gh', 'release', 'list', '--repo', repository, '--limit', '1000',
                     '--json', 'tagName,isDraft'], capture_output=True, text=True)
    if getattr(result, 'returncode', 1) != 0:
        raise ValueError('Unable to list releases for base evidence')
    releases = json.loads(result.stdout)
    matches = sorted(r['tagName'] for r in releases
                     if not r.get('isDraft') and isinstance(r.get('tagName'), str) and r['tagName'].startswith(prefix))
    if not matches:
        raise ValueError('Base batch release not found: ' + prefix + '*')
    evidence = {'release': matches[-1]}
    if target in CLIENTS:
        view = _run(runner, ['gh', 'release', 'view', matches[-1], '--repo', repository, '--json', 'assets'])
        names = [a.get('name', '') for a in json.loads(view.stdout).get('assets', [])]
        found = sorted(n for n in names if n.endswith(CLIENT_EXT[target]))
        if not found:
            raise ValueError(f'Base release lacks a {CLIENT_EXT[target]} client asset')
        evidence['asset'] = found[-1]
    elif target in IMAGE_SERVICES:
        reference = f'ghcr.io/stevenzxs/cloudmeet-{target}:{server}-r{base_revision}'
        probe = runner(['docker', 'buildx', 'imagetools', 'inspect', reference, '--format', '{{json .Manifest}}'],
                       capture_output=True, text=True)
        if probe.returncode != 0:
            raise ValueError('Base GHCR tag not resolvable: ' + reference)
        digest_value = json.loads(probe.stdout).get('digest', '')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest_value):
            raise ValueError('Invalid base image digest')
        evidence['ghcr_digest'] = digest_value
    return evidence


def require_absent(remote, runner):
    probe = runner(['docker', 'manifest', 'inspect', remote], capture_output=True, text=True)
    if probe.returncode == 0:
        raise ValueError('Refusing existing registry tag: ' + remote)
    diagnostic = (probe.stderr or '').strip().lower()
    if (any(word in diagnostic for word in ('unauthorized', 'denied', 'authentication', 'timeout', 'timed out'))
            or not any(word in diagnostic for word in ('manifest unknown', 'no such manifest'))):
        raise RuntimeError('Unable to establish registry tag absence: ' + remote + '; ' + diagnostic[:2000])


def push_exact(remote, runner):
    for attempt in range(3):
        result = runner(['docker', 'push', remote], capture_output=True, text=True)
        if result.returncode == 0:
            return
        diagnostic = ((result.stdout or '') + '\n' + (result.stderr or '')).lower()
        if (attempt == 2 or 'unknown blob' not in diagnostic
                or any(word in diagnostic for word in ('denied', 'unauthorized', 'authentication'))):
            raise RuntimeError('Registry push failed: ' + remote)
        require_absent(remote, runner)


def _release_absent(tag, runner, repository):
    probe = runner(['gh', 'api', f'repos/{repository}/releases/tags/{tag}'], capture_output=True, text=True)
    if probe.returncode == 0:
        raise ValueError('Refusing existing release: ' + tag)


def _create_release(tag, assets, env, runner, repository):
    _release_absent(tag, runner, repository)
    notes = ('Patch release; NOT_DEPLOYED. Built and published from one reviewed run; '
             'installation, endpoint TLS and media acceptance not performed.')
    _run(runner, ['gh', 'release', 'create', tag, '--repo', repository, '--target', env['GITHUB_SHA'],
                  '--draft', '--title', tag, '--notes', notes])
    _run(runner, ['gh', 'release', 'upload', tag, *map(str, assets), '--repo', repository])
    _run(runner, ['gh', 'release', 'edit', tag, '--draft=false', '--latest=false', '--repo', repository])


def publish(target, input_dir, record, policy, runner=subprocess.run, env=None, repository=REPOSITORY):
    env = env or dict(os.environ)
    input_dir = Path(input_dir)
    if record.get('kind') != 'patch' or record.get('request', {}).get('target') != target:
        raise ValueError('Patch record/target mismatch')
    unsigned = dict(record)
    unsigned.pop('allocation_sha256', None)
    if record.get('allocation_sha256') != digest(unsigned):
        raise ValueError('Patch record integrity mismatch')
    request = record['request']
    if (request.get('configuration_sha') != env.get('GITHUB_SHA')
            or str(request.get('run_id')) != str(env.get('GITHUB_RUN_ID'))):
        raise ValueError('Patch record belongs to a different run')
    if env.get('GITHUB_REPOSITORY') != repository:
        raise ValueError('Publication restricted to reviewed repository')
    versions = record['versions']
    batch = f"{versions['server_tag']}-{env.get('GITHUB_RUN_ID')}-{env.get('GITHUB_RUN_ATTEMPT')}"
    tag = 'cloudmeet-' + versions['server_tag']
    publication = {'kind': 'patch', 'tag': tag, 'target': target, 'batch': batch,
                   'run_id': env.get('GITHUB_RUN_ID'), 'attempt': env.get('GITHUB_RUN_ATTEMPT'),
                   'configuration_commit': env.get('GITHUB_SHA'), 'version_assignment': record,
                   'status': 'PUBLISHING_NOT_COMPLETE', 'runtime_acceptance': 'NOT_RUN'}
    if target in IMAGE_SERVICES:
        build = json.loads((input_dir / f'{target}.json').read_text(encoding='utf-8'))
        for key, expected in {'service': target, 'batch': batch, 'version': versions['server_version'],
                              'workflow_commit': env['GITHUB_SHA'], 'deployment_commit': env['GITHUB_SHA'],
                              'run_id': str(env['GITHUB_RUN_ID']), 'attempt': str(env['GITHUB_RUN_ATTEMPT']),
                              'platform': 'linux/' + env.get('TARGET_ARCH', 'amd64')}.items():
            if build.get(key) != expected:
                raise ValueError('Build identity mismatch: ' + key)
        if build.get('version_assignment') != record:
            raise ValueError('Build allocation mismatch')
        if build.get('source_dirty') is not False:
            raise ValueError('Dirty source build refused')
        if build.get('source', {}).get('commit') != request['sources'][target]:
            raise ValueError('Source identity mismatch')
        archive = input_dir / build['archive']
        if not archive.is_file() or file_digest(archive) != build['sha256'] or archive.stat().st_size != build['bytes']:
            raise ValueError('Archive integrity failure')
        remote = f"ghcr.io/stevenzxs/cloudmeet-{target}:{versions['server_tag']}"
        require_absent(remote, runner)
        _run(runner, ['docker', 'load', '--input', str(archive)])
        inspected = json.loads(_run(runner, ['docker', 'image', 'inspect', build['tag']]).stdout)[0]
        labels = inspected['Config']['Labels']
        if (inspected['Id'] != build['image_id']
                or inspected['Os'] + '/' + inspected['Architecture'] != build['platform']
                or labels['org.opencontainers.image.revision'] != request['sources'][target]
                or labels['io.cloudmeet.batch'] != batch):
            raise ValueError('Loaded image mismatch')
        _run(runner, ['docker', 'tag', build['tag'], remote])
        push_exact(remote, runner)
        descriptor = json.loads(_run(runner, ['docker', 'buildx', 'imagetools', 'inspect', remote,
                                              '--format', '{{json .Manifest}}']).stdout)
        registry_digest = descriptor['digest']
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', registry_digest):
            raise ValueError('Invalid registry digest')
        publication['image'] = {'reference': remote.split(':')[0] + '@' + registry_digest, 'tag': remote,
                                'image_id': build['image_id'], 'archive_sha256': build['sha256']}
        assets = [archive, input_dir / f'{target}.json']
    elif target == 'jitsi-mgr':
        mgr = json.loads((input_dir / 'build-evidence.json').read_text(encoding='utf-8'))
        for key, expected in {'service': 'jitsi-mgr', 'batch': batch, 'version': versions['server_version'],
                              'run_id': str(env['GITHUB_RUN_ID']), 'attempt': str(env['GITHUB_RUN_ATTEMPT']),
                              'deployment_commit': env['GITHUB_SHA'],
                              'architecture': env.get('TARGET_ARCH', 'amd64'),
                              'source_commit': request['sources']['jitsi-mgr']}.items():
            if mgr.get(key) != expected:
                raise ValueError('jitsi-mgr evidence mismatch: ' + key)
        if mgr.get('version_assignment') != record:
            raise ValueError('jitsi-mgr allocation mismatch')
        artifacts = input_dir / 'artifacts'
        if not artifacts.is_dir() or any(p.is_symlink() for p in artifacts.rglob('*')):
            raise ValueError('jitsi-mgr artifacts missing or unsafe')
        bundle = input_dir / 'jitsi-mgr-artifacts.tar.gz'
        with tarfile.open(bundle, 'w:gz') as tar:
            for path in sorted(artifacts.rglob('*')):
                if path.is_file():
                    tar.add(path, arcname=path.relative_to(input_dir).as_posix())
        assets = [bundle, input_dir / 'build-evidence.json']
    else:
        # Client input is the delivery bundle written by tools/clients/delivery.cjs.
        manifest = json.loads((input_dir / 'build-evidence.json').read_text(encoding='utf-8'))
        if manifest.get('status') != 'packaged-delivered':
            raise ValueError('Client build did not complete package verification')
        if manifest.get('version') != versions['client_version']:
            raise ValueError('Client version mismatch')
        if manifest.get('versionAssignment') != record:
            raise ValueError('Client allocation mismatch')
        assets = []
        for artifact in manifest.get('artifacts', []):
            file = input_dir / artifact['file']
            if not file.name.endswith(CLIENT_EXT[target]) or not file.is_file():
                raise ValueError('Unexpected client artifact: ' + artifact['file'])
            if file_digest(file) != artifact['sha256']:
                raise ValueError('Client artifact integrity failure: ' + file.name)
            assets.append(file)
        if not assets:
            raise ValueError('No client artifacts to publish')
        assets.append(input_dir / 'build-evidence.json')
    sums = input_dir / 'SHA256SUMS'
    sums.write_text(''.join(file_digest(p) + '  ' + p.name + '\n' for p in assets), encoding='utf-8')
    _create_release(tag, assets + [sums], env, runner, repository)
    publication['status'] = 'PUBLISHED_NOT_DEPLOYED'
    publication['assets'] = [p.name for p in assets] + ['SHA256SUMS']
    (input_dir / 'patch-publication.json').write_text(json.dumps(publication, indent=2) + '\n', encoding='utf-8')
    return publication


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    allocate = commands.add_parser('allocate')
    allocate.add_argument('--base-revision', type=int, required=True)
    allocate.add_argument('--target', required=True, choices=TARGETS)
    allocate.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('check-base')
    check.add_argument('--base-revision', type=int, required=True)
    check.add_argument('--target', required=True, choices=TARGETS)
    publish_cmd = commands.add_parser('publish')
    publish_cmd.add_argument('--target', required=True, choices=TARGETS)
    publish_cmd.add_argument('--input', type=Path, required=True)
    publish_cmd.add_argument('--record', type=Path, required=True)
    args = parser.parse_args(argv)
    policy, identities = load_policy_and_identities()
    if args.command == 'allocate':
        env = os.environ
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        if sha != env.get('MATERIAL_SHA'):
            raise ValueError('Workflow/material SHA mismatch')
        prefix = f"cloudmeet-{policy['server_baseline']}-r{args.base_revision}-patch."
        listed = _run(subprocess.run, ['gh', 'release', 'list', '--repo', REPOSITORY, '--limit', '1000',
                                       '--json', 'tagName'])
        patch = next_patch([r['tagName'] for r in json.loads(listed.stdout)], prefix)
        record = build_record(policy, identities, args.base_revision, args.target,
                              dict(repository=env.get('GITHUB_REPOSITORY', REPOSITORY),
                                   workflow=env.get('GITHUB_WORKFLOW_REF', ''),
                                   run_id=env.get('GITHUB_RUN_ID', ''),
                                   configuration_sha=sha), patch)
        args.output.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(record))
    elif args.command == 'check-base':
        print(json.dumps(check_base(policy, args.base_revision, args.target)))
    else:
        record = json.loads(args.record.read_text(encoding='utf-8'))
        print(json.dumps(publish(args.target, args.input, record, policy)))


if __name__ == '__main__':
    main()
