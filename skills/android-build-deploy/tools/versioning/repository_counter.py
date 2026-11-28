#!/usr/bin/env python3
"""Allocate Android revisions in the Android-owned policy on main."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from revision_versions import derive, digest


REPOSITORY = 'stevenzxs/cloudemeet-deploy'
POLICY_REL = Path('skills/android-build-deploy/config/version-policy.json')


def _git(root, *args, check=True):
    env = os.environ.copy()
    token = env.get('GH_TOKEN')
    if token:
        header = base64.b64encode(f'x-access-token:{token}'.encode()).decode()
        env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
                   GIT_CONFIG_VALUE_0=f'AUTHORIZATION: basic {header}')
    return subprocess.run(['git', '-C', str(root), *args], text=True, capture_output=True,
                          check=check, timeout=60, env=env)


def _validate_request(request):
    if request.get('repository') != REPOSITORY or request.get('scope') != ['android']:
        raise ValueError('Android repository/scope mismatch')
    if not re.fullmatch(r'[1-9]\d*', request.get('run_id', '')):
        raise ValueError('Real numeric Run ID required')
    if not re.fullmatch(r'[0-9a-f]{40}', request.get('configuration_sha', '')):
        raise ValueError('Full configuration SHA required')
    if not request.get('workflow') or not request.get('task'):
        raise ValueError('Workflow and task identity required')
    sources = request.get('sources')
    if not isinstance(sources, dict) or not sources or any(not re.fullmatch(r'[0-9a-f]{40}', s) for s in sources.values()):
        raise ValueError('Pinned source commits required')
    if 'android' not in sources:
        raise ValueError('Android source pin required')


def _canonical_policy_path(policy_path):
    resolved = Path(policy_path).resolve(strict=True)
    repo_root = Path(_git(resolved.parent, 'rev-parse', '--show-toplevel').stdout.strip())
    rel = resolved.relative_to(repo_root)
    if rel != POLICY_REL:
        raise ValueError('Android allocator may only update its own version policy')
    return resolved, repo_root, rel


def _find_existing(root, policy_rel, run_id, attempt):
    commits = _git(root, 'log', '--format=%H', 'HEAD', '--', policy_rel.as_posix()).stdout.splitlines()
    for commit in commits:
        data = json.loads(_git(root, 'show', f'{commit}:{policy_rel.as_posix()}').stdout)
        allocation = data.get('last_allocation')
        if allocation and allocation.get('run_id') == run_id and allocation.get('attempt') == attempt:
            return allocation['record']
    return None


def _policy_digest(policy):
    normalized = dict(policy)
    normalized.pop('last_allocation', None)
    return digest(normalized)


def allocate(policy_path, request, *, attempt=1, remote=None, retries=8):
    _validate_request(request)
    if type(attempt) is not int or attempt < 1:
        raise ValueError('Positive attempt required')
    policy_path, repo_root, policy_rel = _canonical_policy_path(policy_path)
    remote = remote or _git(repo_root, 'remote', 'get-url', 'origin').stdout.strip()
    with tempfile.TemporaryDirectory(prefix='cloudmeet-android-counter-') as directory:
        root = Path(directory)
        _git(root, 'init')
        _git(root, 'remote', 'add', 'origin', remote)
        _git(root, 'config', 'user.name', 'CloudMeet Android revision allocator')
        _git(root, 'config', 'user.email', 'cloudmeet-android-allocator@users.noreply.github.com')
        for _ in range(retries):
            _git(root, 'fetch', '--no-tags', 'origin', 'refs/heads/main')
            tip = _git(root, 'rev-parse', 'FETCH_HEAD').stdout.strip()
            _git(root, 'checkout', '-B', 'main', tip)
            existing = _find_existing(root, policy_rel, request['run_id'], attempt)
            if existing:
                if existing.get('request') != request:
                    raise ValueError('Run/attempt already allocated with a different request')
                expected = dict(existing)
                expected.pop('allocation_sha256', None)
                policy = json.loads((root / policy_rel).read_text(encoding='utf-8'))
                revision = existing.get('versions', {}).get('revision')
                original_policy = dict(policy, current_revision=revision - 1)
                if existing.get('policy_sha256') != _policy_digest(original_policy) or existing.get('allocation_sha256') != digest(expected) or existing.get('versions') != derive(policy, revision):
                    raise ValueError('Existing Android assignment integrity/policy mismatch')
                return existing
            checked = root / policy_rel
            policy = json.loads(checked.read_text(encoding='utf-8'))
            if policy.get('namespace') != 'cloudmeet-android-v1' or policy.get('approved') is not True:
                raise ValueError('Android version policy identity/approval mismatch')
            revision = policy.get('current_revision')
            if type(revision) is not int or revision < 63:
                raise ValueError('Valid Android current_revision required')
            allocation_policy = dict(policy, current_revision=revision + 1)
            record = {'namespace': policy['namespace'], 'policy_sha256': _policy_digest(policy), 'request': request,
                      'versions': derive(allocation_policy, revision + 1)}
            record['allocation_sha256'] = digest(record)
            policy['current_revision'] = revision + 1
            policy['last_allocation'] = {'run_id': request['run_id'], 'attempt': attempt, 'record': record}
            checked.write_text(json.dumps(policy, indent=2) + '\n', encoding='utf-8')
            _git(root, 'add', policy_rel.as_posix())
            _git(root, 'commit', '-m', f"Allocate Android revision {policy['current_revision']} for run {request['run_id']} attempt {attempt}")
            candidate = _git(root, 'rev-parse', 'HEAD').stdout.strip()
            result = _git(root, 'push', 'origin', f'{candidate}:refs/heads/main', check=False)
            if not result.returncode:
                return record
        raise ValueError('Android revision allocation retry limit reached')
