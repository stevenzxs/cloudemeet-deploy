#!/usr/bin/env python3
"""Allocate CloudMeet build revisions from version-policy.json on main."""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile

from revision_versions import derive, digest


def _git(root, *args, check=True):
    env = os.environ.copy()
    token = env.get('GH_TOKEN')
    if token:
        header = base64.b64encode(f'x-access-token:{token}'.encode()).decode()
        env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
                   GIT_CONFIG_VALUE_0=f'AUTHORIZATION: basic {header}')
    return subprocess.run(['git', '-C', str(root), *args], text=True, capture_output=True,
                          check=check, timeout=60, env=env)




def _find_existing(root, policy_rel, run_id, attempt):
    commits = _git(root, 'log', '--format=%H', 'HEAD', '--', str(policy_rel)).stdout.splitlines()
    for commit in commits:
        data = json.loads(_git(root, 'show', f'{commit}:{policy_rel.as_posix()}').stdout)
        allocation = data.get('last_allocation')
        if allocation and allocation.get('run_id') == run_id and allocation.get('attempt') == attempt:
            return allocation['record']
    return None


def allocate(policy_path, request, *, attempt=1, remote=None, retries=8):
    if type(attempt) is not int or attempt < 1:
        raise ValueError('Positive attempt required')
    policy_path = Path(policy_path).resolve(strict=True)
    repo_root = Path(_git(policy_path.parent, 'rev-parse', '--show-toplevel').stdout.strip())
    policy_rel = policy_path.relative_to(repo_root)
    remote = remote or _git(repo_root, 'remote', 'get-url', 'origin').stdout.strip()
    with tempfile.TemporaryDirectory(prefix='cloudmeet-counter-') as directory:
        root = Path(directory)
        _git(root, 'init')
        _git(root, 'remote', 'add', 'origin', remote)
        _git(root, 'config', 'user.name', 'CloudMeet revision allocator')
        _git(root, 'config', 'user.email', 'cloudmeet-allocator@users.noreply.github.com')
        for _ in range(retries):
            _git(root, 'fetch', '--no-tags', 'origin', 'refs/heads/main')
            tip = _git(root, 'rev-parse', 'FETCH_HEAD').stdout.strip()
            _git(root, 'checkout', '-B', 'main', tip)
            existing = _find_existing(root, policy_rel, request['run_id'], attempt)
            if existing:
                return existing
            checked = root / policy_rel
            policy = json.loads(checked.read_text(encoding='utf-8'))
            revision = policy.get('current_revision')
            if type(revision) is not int or revision < 0:
                raise ValueError('Nonnegative integer current_revision required')
            policy['current_revision'] = revision + 1
            record = {
                'namespace': policy['namespace'],
                'request': request,
                'versions': derive(policy, policy['current_revision']),
            }
            record['allocation_sha256'] = digest(record)
            policy['last_allocation'] = {
                'run_id': request['run_id'],
                'attempt': attempt,
                'record': record,
            }
            checked.write_text(json.dumps(policy, indent=2) + '\n', encoding='utf-8')
            _git(root, 'add', str(policy_rel))
            _git(root, 'commit', '-m', f"Allocate revision {policy['current_revision']} for run {request['run_id']} attempt {attempt}")
            candidate = _git(root, 'rev-parse', 'HEAD').stdout.strip()
            result = _git(root, 'push', 'origin', f'{candidate}:refs/heads/main', check=False)
            if not result.returncode:
                return record
        raise ValueError('Revision allocation retry limit reached')
